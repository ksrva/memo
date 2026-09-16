"""LLM enrichment.

The contract: the machine may describe what the *author* argued and label how
two notes relate. It never writes the reader's opinion — `note` is the reader's
alone. If that line blurs, the store stops being worth more than a web search.

Degrades cleanly: with no API key the service reports `enabled == False`, the
app still boots, and notes still save (without embeddings or enrichment).
"""

import json
import logging
import os
from typing import List, Optional, Sequence, Tuple

from ..models import Enrichment, Link, Note
from .embeddings import DEFAULT_DIM, EmbeddingProvider, resolve_provider

log = logging.getLogger(__name__)

CHAT_MODEL = os.getenv("MEMO_CHAT_MODEL", "gpt-4o-mini")

ENRICH_SYSTEM = """You annotate a reader's saved highlight.

You are given a passage the reader highlighted and the reader's own note about it.
Your job is to describe the SOURCE, never to restate, improve, or invent the
reader's opinion. The reader's take already exists and is not yours to write.

Return JSON with exactly these keys:
  "claim":         one sentence stating what the passage argues or reports.
                   If the passage is empty, describe what the article is about.
  "open_question": one genuine question the passage leaves unresolved.
                   Not a quiz question — something a thoughtful reader would still wonder.
  "tags":          3-6 lowercase topic tags, each 1-2 words.

Never include the reader's judgment in "claim". Never address the reader."""

RELATE_SYSTEM = """You label how a reader's new note relates to their earlier notes.

For each candidate, choose exactly one relation:
  "agrees"     - the new note supports or echoes the earlier one
  "contradicts"- the new note cuts against the earlier one
  "extends"    - the new note builds on or complicates the earlier one
  "example_of" - the new note is a concrete instance of the earlier one's idea
  "related"    - connected in subject, but none of the above

Return JSON: {"links": [{"id": "<candidate id>", "relation": "<one of the above>",
"why": "<max 12 words, addressed to the reader>"}]}

Only include candidates with a real connection. Prefer "contradicts" and "extends"
when they genuinely apply — those are the connections worth surfacing. Omit weak matches."""


class LLMService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        provider: Optional[EmbeddingProvider] = None,
    ):
        self.embeddings = provider if provider is not None else resolve_provider()
        self.dim = self.embeddings.dim

        # Chat enrichment is OpenAI-only and strictly optional; embeddings may
        # come from somewhere else entirely (or nowhere).
        key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self._client = None
        self.enabled = bool(key and key.strip())
        if self.enabled:
            try:
                import openai

                self._client = openai.OpenAI(api_key=key)
            except Exception as exc:  # pragma: no cover - construction rarely fails
                log.warning("enrichment disabled (client init failed): %s", exc)
                self.enabled = False

    # --- embeddings ------------------------------------------------------

    @property
    def embed_status(self):
        return self.embeddings.status

    def embed(self, text: str) -> Optional[List[float]]:
        """Embedding for `text`, or None when no provider is available.

        Never raises: a missing vector degrades search to lexical, it does not
        fail the request.
        """
        return self.embeddings.embed(text)

    # --- enrichment ------------------------------------------------------

    def enrich(self, title: str, passage: str, note: str) -> Tuple[Enrichment, int]:
        """Describe the source. Returns (enrichment, tokens_used)."""
        if not self.enabled:
            return Enrichment(), 0

        user = (
            f"Article title: {title}\n\n"
            f"Highlighted passage:\n{passage[:4000] or '(none — reader noted the article as a whole)'}\n\n"
            f"The reader's own note (for context only — do not rewrite it):\n{note[:2000]}"
        )
        try:
            resp = self._client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": ENRICH_SYSTEM},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=400,
            )
            data = json.loads(resp.choices[0].message.content)
            enrichment = Enrichment(
                claim=str(data.get("claim", ""))[:500],
                open_question=str(data.get("open_question", ""))[:300],
                tags=[str(t).lower()[:30] for t in (data.get("tags") or [])][:6],
            )
            return enrichment, (resp.usage.total_tokens if resp.usage else 0)
        except Exception as exc:
            log.warning("enrichment failed, saving note unenriched: %s", exc)
            return Enrichment(), 0

    # --- relationships ---------------------------------------------------

    def characterize_links(
        self, note: Note, candidates: Sequence[Tuple[Note, float, str]]
    ) -> Tuple[List[Link], int]:
        """Label how `note` relates to nearby earlier notes.

        Falls back to plain similarity links ("related") if the LLM is off or errors,
        so the connection is still surfaced — just without the verb.
        """
        if not candidates:
            return [], 0

        fallback = [
            Link(
                note_id=c.id, title=c.title, url=c.url, note=c.note[:200],
                relation="related", score=round(score, 3),
                why=f"similar {'thought' if on == 'note' else 'passage'}",
            )
            for c, score, on in candidates
        ]
        if not self.enabled:
            return fallback, 0

        listing = "\n\n".join(
            f'id: {c.id}\ntitle: {c.title}\ntheir note: "{c.note[:300]}"' for c, _, _ in candidates
        )
        user = (
            f'NEW NOTE\ntitle: {note.title}\npassage: "{note.passage[:600]}"\n'
            f'the reader wrote: "{note.note[:600]}"\n\nEARLIER NOTES\n{listing}'
        )
        try:
            resp = self._client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": RELATE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=500,
            )
            data = json.loads(resp.choices[0].message.content)
            by_id = {c.id: (c, score) for c, score, _ in candidates}
            valid = {"agrees", "contradicts", "extends", "example_of", "related"}

            links: List[Link] = []
            for item in data.get("links", []):
                cid = str(item.get("id", ""))
                if cid not in by_id:
                    continue
                cand, score = by_id[cid]
                relation = str(item.get("relation", "related"))
                links.append(
                    Link(
                        note_id=cid, title=cand.title, url=cand.url, note=cand.note[:200],
                        relation=relation if relation in valid else "related",
                        score=round(score, 3),
                        why=str(item.get("why", ""))[:120],
                    )
                )
            return (links or fallback), (resp.usage.total_tokens if resp.usage else 0)
        except Exception as exc:
            log.warning("link labelling failed, falling back to similarity: %s", exc)
            return fallback, 0
