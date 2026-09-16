"""HTTP API.

Services hang off `app.state` (see main.py) rather than module-level globals,
so the app can be constructed with a temp database in tests and so importing
this module never touches the network or the filesystem.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from ..database import Database
from ..models import (
    Link, Note, NoteCreate, RelatedRequest, RelatedResponse,
    SearchHit, SearchResponse,
)
from ..services.llm import LLMService

router = APIRouter(prefix="/v1")

# How similar an earlier note must be before it is worth surfacing.
LINK_THRESHOLD = 0.35
MAX_LINKS = 4


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_llm(request: Request) -> LLMService:
    return request.app.state.llm


class _Timer:
    """Records latency/tokens/success for an endpoint without swallowing errors."""

    def __init__(self, db: Database, endpoint: str):
        self.db, self.endpoint, self.tokens = db, endpoint, 0
        self.start = time.perf_counter()

    def done(self, success: bool) -> None:
        elapsed = (time.perf_counter() - self.start) * 1000
        try:
            self.db.record_metric(self.endpoint, elapsed, self.tokens, success)
        except Exception:  # metrics must never break a request
            pass


@router.post("/notes", response_model=Note, status_code=201)
def create_note(
    payload: NoteCreate,
    db: Database = Depends(get_db),
    llm: LLMService = Depends(get_llm),
) -> Note:
    """Save a highlight plus the reader's take, enrich it, and link it to prior reading."""
    timer = _Timer(db, "notes.create")
    try:
        note_vec = llm.embed(payload.note)
        passage_vec = llm.embed(payload.passage) if payload.passage else None

        enrichment, tokens = llm.enrich(payload.title, payload.passage, payload.note)
        timer.tokens += tokens

        # Find prior notes worth connecting to. Done before insert so the new
        # note can't match itself.
        candidates: List = []
        if note_vec:
            candidates = [
                (n, s, on)
                for n, s, on in db.search(note_vec, k=MAX_LINKS + 2, scope="both")
                if s >= LINK_THRESHOLD
            ][:MAX_LINKS]

        note = Note(
            id=uuid.uuid4().hex[:12],
            url=payload.url,
            title=payload.title or payload.url,
            passage=payload.passage,
            note=payload.note,
            claim=enrichment.claim,
            open_question=enrichment.open_question,
            tags=sorted({*payload.tags, *enrichment.tags}),
            created_at=datetime.now(timezone.utc),
        )

        links, tokens = llm.characterize_links(note, candidates)
        timer.tokens += tokens
        note.links = links

        db.add_note(note, note_embedding=note_vec, passage_embedding=passage_vec)
        timer.done(True)
        return note
    except Exception:
        timer.done(False)
        raise


@router.get("/notes", response_model=List[Note])
def list_notes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    url: Optional[str] = None,
    db: Database = Depends(get_db),
) -> List[Note]:
    return db.list_notes(limit=limit, offset=offset, url=url)


@router.get("/notes/{note_id}", response_model=Note)
def get_note(note_id: str, db: Database = Depends(get_db)) -> Note:
    note = db.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="No note with that id")
    return note


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: str, db: Database = Depends(get_db)) -> None:
    if not db.delete_note(note_id):
        raise HTTPException(status_code=404, detail="No note with that id")


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(min_length=1),
    k: int = Query(8, ge=1, le=50),
    scope: str = Query("both", pattern="^(note|passage|both)$"),
    db: Database = Depends(get_db),
    llm: LLMService = Depends(get_llm),
) -> SearchResponse:
    """Search your own thinking (`scope=note`), what you read (`scope=passage`), or both."""
    timer = _Timer(db, "search")
    try:
        vec = llm.embed(q)
        if vec is not None:
            results = db.search(vec, k=k, scope=scope)
            mode = "semantic"
            # A semantic miss can still be a lexical hit (exact names, jargon).
            if not results:
                results = db.search_lexical(q, k=k, scope=scope)
                mode = "keyword" if results else "semantic"
        else:
            results = db.search_lexical(q, k=k, scope=scope)
            mode = "keyword"

        timer.done(True)
        return SearchResponse(
            query=q,
            mode=mode,
            hits=[SearchHit(note=n, score=sc, matched_on=on) for n, sc, on in results],
        )
    except Exception:
        timer.done(False)
        raise


@router.post("/related", response_model=RelatedResponse)
def related(
    payload: RelatedRequest,
    db: Database = Depends(get_db),
    llm: LLMService = Depends(get_llm),
) -> RelatedResponse:
    """What prior reading bears on the page open right now.

    This is the move a web search cannot make: it fires without being asked,
    because you don't know you should search for something you've forgotten.
    """
    timer = _Timer(db, "related")
    try:
        probe = (payload.text or payload.title).strip()
        if not probe:
            timer.done(True)
            return RelatedResponse(hits=[])

        vec = llm.embed(probe)
        if vec is not None:
            results = [
                (n, sc, on)
                for n, sc, on in db.search(vec, k=6, scope="both")
                if sc >= LINK_THRESHOLD and n.url != payload.url
            ]
        else:
            results = db.search_lexical(probe, k=6, exclude_url=payload.url)

        hits = [
            Link(
                note_id=n.id, title=n.title, url=n.url, note=n.note[:200],
                relation="related", score=sc,
                why=f"you noted this {'thought' if on == 'note' else 'passage'} before",
            )
            for n, sc, on in results[:5]
        ]
        timer.done(True)
        return RelatedResponse(hits=hits)
    except Exception:
        timer.done(False)
        raise


@router.get("/health")
def health(request: Request, db: Database = Depends(get_db)) -> dict:
    """Reports what is actually working, not merely what is configured.

    A key that is present but rejected is reported as an error rather than "on" —
    otherwise the only visible symptom is search quietly returning nothing.
    """
    llm: LLMService = request.app.state.llm
    embed = llm.embed_status
    return {
        "status": "healthy",
        "notes": db.count(),
        "search": "semantic" if embed.ok else "keyword",
        "embeddings": {
            "provider": embed.name,
            "model": embed.model,
            "dimensions": embed.dim,
            "state": "on" if embed.ok else ("off" if embed.name == "none" else "error"),
            "detail": embed.detail,
        },
        "enrichment": "on" if llm.enabled else "off (no OPENAI_API_KEY)",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(db: Database = Depends(get_db)) -> str:
    m = db.metrics_summary()
    return (
        "# HELP memo_notes_total Notes saved\n"
        "# TYPE memo_notes_total gauge\n"
        f"memo_notes_total {m['notes']}\n\n"
        "# HELP memo_latency_p95_ms 95th percentile request latency\n"
        "# TYPE memo_latency_p95_ms gauge\n"
        f"memo_latency_p95_ms {m['latency_p95']:.2f}\n\n"
        "# HELP memo_tokens_total LLM tokens consumed\n"
        "# TYPE memo_tokens_total counter\n"
        f"memo_tokens_total {m['tokens_total']}\n\n"
        "# HELP memo_success_rate Fraction of requests that succeeded\n"
        "# TYPE memo_success_rate gauge\n"
        f"memo_success_rate {m['success_rate']:.4f}\n"
    )
