"""API behaviour, driven with a stub LLM so the suite needs no API key and no network."""

import math
import re
import zlib

import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.main import create_app
from app.models import Enrichment, Link
from app.services.embeddings import EmbeddingProvider, ProviderStatus
from app.services.llm import LLMService

DIM = 32


class _StubProvider(EmbeddingProvider):
    name = "stub"

    def __init__(self, ok: bool, dim: int):
        super().__init__(dim)
        self.model = "stub-embed"
        self._ok = ok

    def probe(self):
        return ProviderStatus(self.name if self._ok else "none", self.model, self.dim,
                              ok=self._ok, detail="" if self._ok else "no provider")


class StubLLM(LLMService):
    """Deterministic stand-in: same text -> same vector, so similarity is testable."""

    def __init__(self, enabled=True, relation="contradicts"):
        self.enabled = enabled
        self.dim = DIM
        self._client = None
        self._relation = relation
        self.enrich_calls = []
        self.embeddings = _StubProvider(enabled, DIM)

    def embed(self, text):
        """Hashed bag-of-words: overlapping text yields genuinely similar vectors,
        so similarity thresholds are exercised rather than faked. Stable across
        processes (unlike Python's randomized str hash)."""
        if not self.enabled or not text or not text.strip():
            return None
        vec = [0.0] * DIM
        words = re.findall(r"[a-z0-9']+", text.lower())
        for w in words:
            vec[zlib.crc32(w.encode()) % DIM] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def enrich(self, title, passage, note):
        self.enrich_calls.append((title, passage, note))
        if not self.enabled:
            return Enrichment(), 0
        return Enrichment(claim=f"The piece argues about {title}.",
                          open_question="What would falsify this?",
                          tags=["reading", "ideas"]), 42

    def characterize_links(self, note, candidates):
        if not candidates:
            return [], 0
        return [
            Link(note_id=c.id, title=c.title, url=c.url, note=c.note[:200],
                 relation=self._relation, score=round(s, 3), why="cuts against your earlier take")
            for c, s, _ in candidates
        ], 17


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "api.db"), dim=DIM)
    with TestClient(app) as c:
        c.app.state.llm = StubLLM()
        c.app.state.db = Database(str(tmp_path / "api.db"), dim=DIM)
        yield c


def save(client, note, title="An Article", passage="a passage", url="https://example.com/a"):
    return client.post("/v1/notes", json={"url": url, "title": title,
                                          "passage": passage, "note": note})


# --- the core rule ----------------------------------------------------------

def test_a_note_without_your_words_is_rejected(client):
    r = client.post("/v1/notes", json={"url": "https://e.com", "title": "T",
                                       "passage": "some passage", "note": "   "})
    assert r.status_code == 422
    assert "your own words" in r.text


def test_the_machine_never_writes_your_opinion(client):
    r = save(client, "I think this is overstated")
    body = r.json()
    assert body["note"] == "I think this is overstated"      # preserved verbatim
    assert body["claim"] and body["claim"] != body["note"]   # machine wrote about the source
    assert "overstated" not in body["claim"]


# --- capture ---------------------------------------------------------------

def test_capture_returns_an_enriched_note(client):
    body = save(client, "scale alone will not get us there").json()
    assert body["id"] and body["open_question"]
    assert set(body["tags"]) >= {"reading", "ideas"}
    assert body["links"] == []          # nothing to connect to yet


def test_second_note_links_back_to_the_first(client):
    first = save(client, "scale alone will not get us there", title="Scaling Laws").json()
    second = save(client, "scale alone will not get us there, roughly",
                  title="A Rebuttal", url="https://example.com/b").json()
    assert len(second["links"]) == 1
    link = second["links"][0]
    assert link["note_id"] == first["id"]
    assert link["relation"] == "contradicts"
    assert link["why"]


def test_a_note_never_links_to_itself(client):
    body = save(client, "a thought about nothing in particular").json()
    assert all(l["note_id"] != body["id"] for l in body["links"])


# --- retrieval -------------------------------------------------------------

def test_search_finds_a_note_by_its_idea(client):
    save(client, "hydration above 75% makes the crumb open")
    hits = client.get("/v1/search", params={"q": "hydration above 75% makes the crumb open"}).json()["hits"]
    assert hits and hits[0]["score"] > 0.99
    assert hits[0]["matched_on"] in ("note", "passage")


def test_search_scope_separates_your_words_from_the_authors(client):
    save(client, "I disagree with this framing", passage="The author claims productivity is rising")
    mine = client.get("/v1/search", params={"q": "I disagree with this framing",
                                            "scope": "note"}).json()["hits"]
    theirs = client.get("/v1/search", params={"q": "The author claims productivity is rising",
                                              "scope": "passage"}).json()["hits"]
    assert mine[0]["matched_on"] == "note"
    assert theirs[0]["matched_on"] == "passage"


def test_related_surfaces_prior_reading_for_the_current_page(client):
    save(client, "attention is quadratic and that matters", url="https://example.com/old")
    hits = client.post("/v1/related", json={"url": "https://example.com/new", "title": "New piece",
                                            "text": "attention is quadratic and that matters"}).json()["hits"]
    assert hits and hits[0]["url"] == "https://example.com/old"


def test_related_excludes_notes_from_the_same_page(client):
    save(client, "a thought", url="https://example.com/same")
    hits = client.post("/v1/related", json={"url": "https://example.com/same",
                                            "title": "t", "text": "a thought"}).json()["hits"]
    assert hits == []


# --- lifecycle & empty states ----------------------------------------------

def test_empty_store_serves_every_read_endpoint(client):
    assert client.get("/v1/notes").json() == []
    assert client.get("/v1/search", params={"q": "anything"}).json()["hits"] == []
    assert client.post("/v1/related", json={"url": "u", "text": "x"}).json()["hits"] == []
    assert client.get("/v1/health").json()["notes"] == 0


def test_get_and_delete_roundtrip(client):
    nid = save(client, "a keeper").json()["id"]
    assert client.get(f"/v1/notes/{nid}").json()["note"] == "a keeper"
    assert client.delete(f"/v1/notes/{nid}").status_code == 204
    assert client.get(f"/v1/notes/{nid}").status_code == 404
    assert client.delete(f"/v1/notes/{nid}").status_code == 404


def test_missing_note_is_404_not_500(client):
    """v1 wrapped its own HTTPException in a bare `except Exception` and returned 500."""
    assert client.get("/v1/notes/nope").status_code == 404


def test_notes_list_is_newest_first_and_filterable(client):
    save(client, "older", url="https://example.com/1")
    save(client, "newer", url="https://example.com/2")
    assert [n["note"] for n in client.get("/v1/notes").json()] == ["newer", "older"]
    only = client.get("/v1/notes", params={"url": "https://example.com/1"}).json()
    assert [n["note"] for n in only] == ["older"]


def test_metrics_are_prometheus_text(client):
    save(client, "something")
    body = client.get("/v1/metrics").text
    assert "memo_notes_total 1" in body and "memo_tokens_total" in body


# --- degraded mode ----------------------------------------------------------

def test_without_an_api_key_notes_still_save(client):
    client.app.state.llm = StubLLM(enabled=False)
    body = save(client, "I still want to keep this").json()
    assert body["note"] == "I still want to keep this"
    assert body["claim"] == ""                      # no enrichment
    assert client.get("/v1/health").json()["enrichment"].startswith("off")
    assert client.get("/v1/search", params={"q": "anything"}).json()["hits"] == []


# --- keyword tier (no key, no model, no network) -----------------------------

def test_keyword_search_works_with_no_embeddings(client):
    """The floor: someone clones the repo, sets no key, and search still works."""
    client.app.state.llm = StubLLM(enabled=False)
    save(client, "productivity rose while wages stagnated badly")
    save(client, "sourdough hydration changes the crumb")

    body = client.get("/v1/search", params={"q": "wages stagnated"}).json()
    assert body["mode"] == "keyword"
    assert len(body["hits"]) == 1
    assert "wages" in body["hits"][0]["note"]["note"]


def test_keyword_search_ignores_fts_punctuation(client):
    """FTS5 treats ':' and quotes as syntax; a raw query would raise."""
    client.app.state.llm = StubLLM(enabled=False)
    save(client, "a note about scaling laws")
    body = client.get("/v1/search", params={"q": 'scaling: "laws" AND (x'}).json()
    assert body["mode"] == "keyword"
    assert len(body["hits"]) == 1


def test_related_falls_back_to_keywords(client):
    client.app.state.llm = StubLLM(enabled=False)
    save(client, "attention is quadratic and that matters", url="https://example.com/old")
    hits = client.post("/v1/related", json={"url": "https://example.com/new", "title": "t",
                                            "text": "attention quadratic"}).json()["hits"]
    assert hits and hits[0]["url"] == "https://example.com/old"


def test_semantic_miss_falls_through_to_keywords(client):
    """Embeddings on, but the vector finds nothing — exact jargon should still hit."""
    save(client, "the Chomsky hierarchy still matters here")
    body = client.get("/v1/search", params={"q": "zzzz Chomsky"}).json()
    assert body["hits"], "keyword fallback should have rescued the query"


# --- honest health reporting -------------------------------------------------

def test_health_reports_keyword_mode_when_embeddings_are_off(client):
    client.app.state.llm = StubLLM(enabled=False)
    body = client.get("/v1/health").json()
    assert body["search"] == "keyword"
    assert body["embeddings"]["state"] == "off"


def test_health_reports_semantic_mode_when_embeddings_work(client):
    body = client.get("/v1/health").json()
    assert body["search"] == "semantic"
    assert body["embeddings"]["state"] == "on"
    assert body["embeddings"]["dimensions"] == DIM
