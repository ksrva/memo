import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Database  # noqa: E402
from app.models import Note  # noqa: E402

DIM = 32  # small vectors keep the suite fast; the real one is 1536


@pytest.fixture
def db(tmp_path) -> Database:
    """A real database in a fresh temp dir — never the developer's memo.db."""
    return Database(str(tmp_path / "test.db"), dim=DIM)


@pytest.fixture
def vec():
    """Deterministic unit-ish vectors: same seed -> same vector, across processes."""
    import random

    def make(seed: int, dim: int = DIM):
        r = random.Random(seed)
        return [r.uniform(-1, 1) for _ in range(dim)]

    return make


@pytest.fixture
def make_note():
    def build(nid="n1", note="my thought", title="An Article", passage="a passage",
              url="https://example.com/a"):
        return Note(id=nid, url=url, title=title, passage=passage, note=note)

    return build
