"""SQLite + sqlite-vec storage for notes.

Two design decisions worth stating, because the previous version got both wrong:

1. Notes are keyed by their own TEXT id inside the vector table. The old build
   derived a rowid with `abs(hash(id))`; Python randomizes string hashing per
   process, so every restart orphaned the entire store.
2. Querying an empty index returns []. sqlite-vss called abort() here, which
   killed the server on a fresh install's first request — uncatchable from Python.
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sqlite_vec

from .models import Link, Note

DEFAULT_DIM = 768

_WORD = re.compile(r"[^\w\s]+")


class EmbeddingModelMismatch(RuntimeError):
    """Raised when a store's vectors came from a different embedding model."""


def _fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 OR-query. FTS5 treats characters like
    ':' and '"' as syntax, so everything is stripped and re-quoted."""
    words = [w for w in _WORD.sub(" ", text).split() if len(w) > 1]
    return " OR ".join(f'"{w}"' for w in words[:24])


def _overlaps(query: str, text: str) -> bool:
    q = {w.lower() for w in _WORD.sub(" ", query).split() if len(w) > 2}
    t = {w.lower() for w in _WORD.sub(" ", text).split() if len(w) > 2}
    return bool(q & t)


class Database:
    def __init__(
        self,
        db_path: str = "memo.db",
        dim: int = DEFAULT_DIM,
        fingerprint: str = "",
    ):
        """`fingerprint` identifies the embedding model that produced the stored
        vectors (e.g. "openai:text-embedding-3-small:768"). Vectors from two
        different models are not comparable even at equal dimensions, so a
        mismatch must fail loudly rather than return quietly-wrong rankings."""
        self.db_path = db_path
        self.dim = dim
        self.fingerprint = fingerprint
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._shared = sqlite3.connect(db_path) if db_path == ":memory:" else None
        if self._shared is not None:
            self._load_vec(self._shared)
        self.init_db()

    # --- connections -----------------------------------------------------

    @staticmethod
    def _load_vec(conn: sqlite3.Connection) -> None:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

    def connect(self) -> sqlite3.Connection:
        """A connection with the vector extension loaded and rows as dicts."""
        if self._shared is not None:
            self._shared.row_factory = sqlite3.Row
            return self._shared
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._load_vec(conn)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _close(self, conn: sqlite3.Connection) -> None:
        if self._shared is None:
            conn.close()

    # --- schema ----------------------------------------------------------

    def init_db(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id            TEXT PRIMARY KEY,
                    url           TEXT NOT NULL,
                    title         TEXT NOT NULL,
                    passage       TEXT NOT NULL DEFAULT '',
                    note          TEXT NOT NULL,
                    claim         TEXT NOT NULL DEFAULT '',
                    open_question TEXT NOT NULL DEFAULT '',
                    tags          TEXT NOT NULL DEFAULT '[]',
                    created_at    TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_notes_url ON notes(url);

                CREATE TABLE IF NOT EXISTS links (
                    from_id  TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                    to_id    TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL DEFAULT 'related',
                    score    REAL NOT NULL DEFAULT 0.0,
                    why      TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (from_id, to_id)
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS metrics (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    endpoint   TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    tokens     INTEGER NOT NULL DEFAULT 0,
                    success    INTEGER NOT NULL,
                    at         TEXT NOT NULL
                );
                """
            )
            # Lexical index. Built on SQLite's own FTS5, so keyword search works
            # with no embedding provider, no model download and no API key.
            conn.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    note, passage, title, tags,
                    content='notes', content_rowid='rowid', tokenize='porter unicode61'
                );

                CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                    INSERT INTO notes_fts(rowid, note, passage, title, tags)
                    VALUES (new.rowid, new.note, new.passage, new.title, new.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, note, passage, title, tags)
                    VALUES ('delete', old.rowid, old.note, old.passage, old.title, old.tags);
                END;

                CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                    INSERT INTO notes_fts(notes_fts, rowid, note, passage, title, tags)
                    VALUES ('delete', old.rowid, old.note, old.passage, old.title, old.tags);
                    INSERT INTO notes_fts(rowid, note, passage, title, tags)
                    VALUES (new.rowid, new.note, new.passage, new.title, new.tags);
                END;
                """
            )

            # The reader's words and the author's words are embedded separately,
            # so "where was I skeptical about X" and "what did I read about X"
            # are different queries.
            for table in ("vec_notes", "vec_passages"):
                conn.execute(
                    f"""CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0(
                            note_id TEXT PRIMARY KEY,
                            embedding float[{self.dim}] distance_metric=cosine
                        )"""
                )
            self._check_fingerprint(conn)
            conn.commit()
        finally:
            self._close(conn)

    def _check_fingerprint(self, conn: sqlite3.Connection) -> None:
        """Refuse to mix vectors from different embedding models."""
        if not self.fingerprint:
            return
        row = conn.execute("SELECT value FROM meta WHERE key = 'embed_fingerprint'").fetchone()
        stored = row[0] if row else None

        if stored is None:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('embed_fingerprint', ?)",
                (self.fingerprint,),
            )
            return

        if stored != self.fingerprint:
            has_vectors = conn.execute("SELECT COUNT(*) FROM vec_notes").fetchone()[0]
            if has_vectors:
                raise EmbeddingModelMismatch(
                    f"This store was built with {stored!r} but the app is configured for "
                    f"{self.fingerprint!r}. Vectors from different models are not comparable. "
                    f"Either restore the previous setting, or re-embed into a new database "
                    f"(set MEMO_DB_PATH to a new file)."
                )
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('embed_fingerprint', ?)",
                (self.fingerprint,),
            )

    # --- writes ----------------------------------------------------------

    def add_note(
        self,
        note: Note,
        note_embedding: Optional[List[float]] = None,
        passage_embedding: Optional[List[float]] = None,
    ) -> Note:
        conn = self.connect()
        try:
            conn.execute(
                """INSERT INTO notes (id, url, title, passage, note, claim,
                                      open_question, tags, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    note.id, note.url, note.title, note.passage, note.note,
                    note.claim, note.open_question, json.dumps(note.tags),
                    note.created_at.isoformat(),
                ),
            )
            self._put_vector(conn, "vec_notes", note.id, note_embedding)
            self._put_vector(conn, "vec_passages", note.id, passage_embedding)
            for link in note.links:
                conn.execute(
                    """INSERT OR REPLACE INTO links (from_id, to_id, relation, score, why)
                       VALUES (?, ?, ?, ?, ?)""",
                    (note.id, link.note_id, link.relation, link.score, link.why),
                )
            conn.commit()
            return note
        finally:
            self._close(conn)

    def _put_vector(
        self, conn: sqlite3.Connection, table: str, note_id: str, embedding: Optional[List[float]]
    ) -> None:
        if not embedding:
            return
        if len(embedding) != self.dim:
            raise ValueError(f"expected {self.dim}-dim embedding, got {len(embedding)}")
        conn.execute(f"DELETE FROM {table} WHERE note_id = ?", (note_id,))
        conn.execute(
            f"INSERT INTO {table} (note_id, embedding) VALUES (?, ?)",
            (note_id, sqlite_vec.serialize_float32(embedding)),
        )

    def delete_note(self, note_id: str) -> bool:
        conn = self.connect()
        try:
            cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
            for table in ("vec_notes", "vec_passages"):
                conn.execute(f"DELETE FROM {table} WHERE note_id = ?", (note_id,))
            conn.execute("DELETE FROM links WHERE from_id = ? OR to_id = ?", (note_id, note_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            self._close(conn)

    # --- reads -----------------------------------------------------------

    def count(self) -> int:
        conn = self.connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        finally:
            self._close(conn)

    def get_note(self, note_id: str, with_links: bool = True) -> Optional[Note]:
        conn = self.connect()
        try:
            row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if row is None:
                return None
            return self._hydrate(conn, row, with_links)
        finally:
            self._close(conn)

    def list_notes(self, limit: int = 50, offset: int = 0, url: Optional[str] = None) -> List[Note]:
        conn = self.connect()
        try:
            if url:
                rows = conn.execute(
                    "SELECT * FROM notes WHERE url = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (url, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM notes ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [self._hydrate(conn, r, with_links=False) for r in rows]
        finally:
            self._close(conn)

    def search(
        self,
        embedding: List[float],
        k: int = 5,
        scope: str = "both",
        exclude_id: Optional[str] = None,
    ) -> List[Tuple[Note, float, str]]:
        """Nearest notes as (note, similarity, matched_on), best first.

        Returns [] on an empty store rather than taking the process down with it.
        """
        if k <= 0:
            return []
        conn = self.connect()
        try:
            if conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0:
                return []

            tables = {"note": ["vec_notes"], "passage": ["vec_passages"]}.get(
                scope, ["vec_notes", "vec_passages"]
            )
            blob = sqlite_vec.serialize_float32(embedding)

            best: Dict[str, Tuple[float, str]] = {}
            for table in tables:
                matched_on = "note" if table == "vec_notes" else "passage"
                if conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0:
                    continue
                rows = conn.execute(
                    f"""SELECT note_id, distance FROM {table}
                        WHERE embedding MATCH ? AND k = ?
                        ORDER BY distance""",
                    (blob, k + (1 if exclude_id else 0)),
                ).fetchall()
                for note_id, distance in rows:
                    if note_id == exclude_id:
                        continue
                    score = max(0.0, 1.0 - float(distance))  # cosine distance -> similarity
                    if note_id not in best or score > best[note_id][0]:
                        best[note_id] = (score, matched_on)

            if not best:
                return []

            ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:k]
            out: List[Tuple[Note, float, str]] = []
            for note_id, (score, matched_on) in ranked:
                row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
                if row is not None:
                    out.append((self._hydrate(conn, row, with_links=False), score, matched_on))
            return out
        finally:
            self._close(conn)

    def _hydrate(self, conn: sqlite3.Connection, row: sqlite3.Row, with_links: bool) -> Note:
        note = Note(
            id=row["id"],
            url=row["url"],
            title=row["title"],
            passage=row["passage"],
            note=row["note"],
            claim=row["claim"],
            open_question=row["open_question"],
            tags=json.loads(row["tags"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
        if with_links:
            note.links = self._links_for(conn, note.id)
        return note

    def _links_for(self, conn: sqlite3.Connection, note_id: str) -> List[Link]:
        rows = conn.execute(
            """SELECT l.to_id, l.relation, l.score, l.why, n.title, n.url, n.note
               FROM links l JOIN notes n ON n.id = l.to_id
               WHERE l.from_id = ? ORDER BY l.score DESC""",
            (note_id,),
        ).fetchall()
        return [
            Link(
                note_id=r["to_id"], title=r["title"], url=r["url"],
                note=r["note"][:200], relation=r["relation"],
                score=r["score"], why=r["why"],
            )
            for r in rows
        ]

    def search_lexical(
        self, query: str, k: int = 5, scope: str = "both", exclude_url: Optional[str] = None
    ) -> List[Tuple[Note, float, str]]:
        """Keyword search via FTS5/BM25 — the floor beneath semantic search.

        Works with no API key, no model and no network. Scores are normalised to
        0..1 so callers can treat them like similarity scores.
        """
        terms = _fts_query(query)
        if not terms:
            return []

        columns = {"note": "note", "passage": "passage"}.get(scope)
        match = f"{columns}:({terms})" if columns else terms

        conn = self.connect()
        try:
            try:
                rows = conn.execute(
                    """SELECT n.*, bm25(notes_fts) AS rank
                       FROM notes_fts JOIN notes n ON n.rowid = notes_fts.rowid
                       WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?""",
                    (match, k * 2),
                ).fetchall()
            except sqlite3.OperationalError:
                return []  # malformed FTS expression from odd punctuation

            # bm25() returns negative numbers on an open-ended scale (more
            # negative is better), which is not comparable to cosine similarity.
            # Normalise against the best hit so the score means "how good
            # relative to the best match here" — honest, and interpretable in
            # the UI, which labels the mode as "keyword" anyway.
            kept = [
                (self._hydrate(conn, row, with_links=False), abs(float(row["rank"])))
                for row in rows
            ]
            kept = [(n, r) for n, r in kept if not (exclude_url and n.url == exclude_url)]
            if not kept:
                return []

            best = max(r for _, r in kept) or 1.0
            return [
                (n, round(r / best, 3), "note" if _overlaps(query, n.note) else "passage")
                for n, r in kept
            ][:k]
        finally:
            self._close(conn)

    # --- metrics ---------------------------------------------------------

    def record_metric(self, endpoint: str, latency_ms: float, tokens: int, success: bool) -> None:
        conn = self.connect()
        try:
            conn.execute(
                "INSERT INTO metrics (endpoint, latency_ms, tokens, success, at) VALUES (?,?,?,?,?)",
                (endpoint, latency_ms, tokens, int(success), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            self._close(conn)

    def metrics_summary(self) -> Dict[str, float]:
        conn = self.connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
            if not total:
                return {"latency_p95": 0.0, "tokens_total": 0, "success_rate": 1.0, "notes": 0}
            p95 = conn.execute(
                "SELECT latency_ms FROM metrics ORDER BY latency_ms LIMIT 1 OFFSET ?",
                (min(total - 1, (total * 95) // 100),),
            ).fetchone()[0]
            tokens = conn.execute("SELECT COALESCE(SUM(tokens),0) FROM metrics").fetchone()[0]
            ok = conn.execute("SELECT AVG(success) FROM metrics").fetchone()[0]
            notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            return {
                "latency_p95": float(p95),
                "tokens_total": int(tokens),
                "success_rate": float(ok),
                "notes": int(notes),
            }
        finally:
            self._close(conn)
