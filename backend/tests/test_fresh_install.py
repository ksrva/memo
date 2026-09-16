"""The fresh-install path.

Both bugs these cover shipped in v1 and were invisible on a developer machine,
because a dev box always has a populated database and a long-running process.
"""

import subprocess
import sys
import textwrap

import pytest

from app.database import Database, EmbeddingModelMismatch


def test_search_on_empty_store_returns_nothing(db, vec):
    """v1 aborted the process here (faiss 'k > 0 failed'), uncatchable from Python."""
    assert db.count() == 0
    assert db.search(vec(1), k=5) == []


def test_related_on_empty_store_is_survivable(db, vec):
    for scope in ("note", "passage", "both"):
        assert db.search(vec(2), k=3, scope=scope) == []


def test_first_note_saves_against_an_empty_store(db, vec, make_note):
    saved = db.add_note(make_note(), note_embedding=vec(10), passage_embedding=vec(11))
    assert db.count() == 1
    assert db.get_note(saved.id).note == "my thought"


def test_search_survives_a_restart(tmp_path, vec, make_note):
    """v1 keyed vectors by abs(hash(id)); Python reseeds string hashing per process,
    so every restart silently orphaned the whole store. Must run in a real subprocess."""
    path = str(tmp_path / "restart.db")
    db = Database(path, dim=32)
    db.add_note(make_note(nid="keep", note="scale alone will not get us there"),
                note_embedding=vec(42))
    assert len(db.search(vec(42), k=3)) == 1

    script = textwrap.dedent(f"""
        import sys, random
        sys.path.insert(0, {str(__import__("pathlib").Path(__file__).resolve().parents[1])!r})
        from app.database import Database
        r = random.Random(42)
        v = [r.uniform(-1, 1) for _ in range(32)]
        hits = Database({path!r}, dim=32).search(v, k=3)
        print(len(hits), hits[0][0].id if hits else "")
    """)
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert out.returncode == 0, f"child process died: {out.stderr}"
    count, note_id = out.stdout.split()
    assert count == "1" and note_id == "keep", "store was orphaned by the restart"


# --- switching embedding models ---------------------------------------------

def test_switching_embedding_model_is_refused_not_silently_wrong(tmp_path, vec, make_note):
    """Two models can share a dimension while living in different vector spaces.
    Mixing them returns plausible-looking nonsense, so it must fail loudly."""
    path = str(tmp_path / "switch.db")
    db = Database(path, dim=32, fingerprint="openai:text-embedding-3-small:32")
    db.add_note(make_note(), note_embedding=vec(1))

    with pytest.raises(EmbeddingModelMismatch) as err:
        Database(path, dim=32, fingerprint="ollama:nomic-embed-text:32")
    assert "not comparable" in str(err.value)


def test_same_model_reopens_cleanly(tmp_path, vec, make_note):
    path = str(tmp_path / "same.db")
    fp = "openai:text-embedding-3-small:32"
    Database(path, dim=32, fingerprint=fp).add_note(make_note(), note_embedding=vec(1))
    assert Database(path, dim=32, fingerprint=fp).count() == 1


def test_empty_store_adopts_whatever_model_arrives_first(tmp_path):
    """No vectors yet means nothing to invalidate — switching is harmless."""
    path = str(tmp_path / "adopt.db")
    Database(path, dim=32, fingerprint="openai:a:32")
    Database(path, dim=32, fingerprint="ollama:b:32")  # must not raise


def test_keyword_search_needs_no_embeddings_at_all(tmp_path, make_note):
    db = Database(str(tmp_path / "lex.db"), dim=32)
    db.add_note(make_note(note="wages stagnated while productivity rose"))
    hits = db.search_lexical("productivity", k=3)
    assert len(hits) == 1 and "productivity" in hits[0][0].note
