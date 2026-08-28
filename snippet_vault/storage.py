"""SQLite-backed persistent storage for snippets, tags, and embeddings.

Schema
------
snippets(id, title, code, description, created_at, updated_at, use_count)
tags(id, name UNIQUE)
snippet_tags(snippet_id, tag_id)
embeddings(snippet_id PRIMARY KEY, vector BLOB, dim INT, model TEXT)
"""

from __future__ import annotations

import sqlite3
import struct
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

import numpy as np

from snippet_vault.config import DB_PATH


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class Snippet:
    id: int
    title: str
    code: str
    description: str
    created_at: float
    updated_at: float
    use_count: int = 0
    tags: list[str] = field(default_factory=list)


@dataclass
class SearchHit:
    snippet: Snippet
    score: float


# ---------------------------------------------------------------------------
# Storage class
# ---------------------------------------------------------------------------
class Storage:
    """Thin wrapper around the SQLite database.

    A single connection is reused via a thread-local slot.  For a CLI tool
    this is fine; if the project ever grows into a server we can swap this
    out for a real pool.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS snippets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT    NOT NULL,
        code        TEXT    NOT NULL,
        description TEXT    NOT NULL DEFAULT '',
        created_at  REAL    NOT NULL,
        updated_at  REAL    NOT NULL,
        use_count   INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS tags (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT    NOT NULL UNIQUE COLLATE NOCASE
    );

    CREATE TABLE IF NOT EXISTS snippet_tags (
        snippet_id INTEGER NOT NULL REFERENCES snippets(id) ON DELETE CASCADE,
        tag_id     INTEGER NOT NULL REFERENCES tags(id)     ON DELETE CASCADE,
        PRIMARY KEY (snippet_id, tag_id)
    );

    CREATE TABLE IF NOT EXISTS embeddings (
        snippet_id INTEGER PRIMARY KEY REFERENCES snippets(id) ON DELETE CASCADE,
        vector     BLOB    NOT NULL,
        dim        INTEGER NOT NULL,
        model      TEXT    NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_snippets_updated ON snippets(updated_at);
    CREATE INDEX IF NOT EXISTS idx_snippets_created ON snippets(created_at);
    CREATE INDEX IF NOT EXISTS idx_snippets_title   ON snippets(title);
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(self.SCHEMA)

    # -- low-level helpers ------------------------------------------------
    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Connection]:
        try:
            self._conn.execute("BEGIN")
            yield self._conn
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self._conn.close()

    # -- snippets ---------------------------------------------------------
    def add_snippet(
        self, title: str, code: str, description: str = "", tags: Optional[list[str]] = None
    ) -> int:
        now = time.time()
        with self._txn():
            cur = self._conn.execute(
                "INSERT INTO snippets(title, code, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (title, code, description, now, now),
            )
            sid = int(cur.lastrowid or 0)
            self._set_tags(sid, tags or [])
        return sid

    def update_snippet(
        self,
        sid: int,
        title: Optional[str] = None,
        code: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        fields, values = [], []
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if code is not None:
            fields.append("code = ?")
            values.append(code)
        if description is not None:
            fields.append("description = ?")
            values.append(description)
        if not fields:
            return False
        fields.append("updated_at = ?")
        values.append(time.time())
        values.append(sid)
        cur = self._conn.execute(
            f"UPDATE snippets SET {', '.join(fields)} WHERE id = ?", values
        )
        return cur.rowcount > 0

    def delete_snippet(self, sid: int) -> bool:
        cur = self._conn.execute("DELETE FROM snippets WHERE id = ?", (sid,))
        return cur.rowcount > 0

    def get_snippet(self, sid: int) -> Optional[Snippet]:
        row = self._conn.execute(
            "SELECT * FROM snippets WHERE id = ?", (sid,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_snippet(row)

    def list_snippets(
        self,
        limit: int = 50,
        offset: int = 0,
        sort: str = "updated",
        tag: Optional[str] = None,
    ) -> list[Snippet]:
        order_col = {
            "updated": "updated_at",
            "created": "created_at",
            "title":   "title",
            "uses":    "use_count",
        }.get(sort, "updated_at")
        if tag:
            rows = self._conn.execute(
                f"""SELECT s.* FROM snippets s
                    JOIN snippet_tags st ON st.snippet_id = s.id
                    JOIN tags t          ON t.id = st.tag_id
                    WHERE t.name = ?
                    ORDER BY s.{order_col} DESC
                    LIMIT ? OFFSET ?""",
                (tag, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT * FROM snippets ORDER BY {order_col} DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._row_to_snippet(r) for r in rows]

    def count_snippets(self, tag: Optional[str] = None) -> int:
        if tag:
            row = self._conn.execute(
                """SELECT COUNT(*) AS c FROM snippets s
                   JOIN snippet_tags st ON st.snippet_id = s.id
                   JOIN tags t          ON t.id = st.tag_id
                   WHERE t.name = ?""",
                (tag,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM snippets").fetchone()
        return int(row["c"])

    def increment_uses(self, sid: int) -> None:
        self._conn.execute(
            "UPDATE snippets SET use_count = use_count + 1 WHERE id = ?", (sid,)
        )

    # -- tags -------------------------------------------------------------
    def _set_tags(self, sid: int, tags: Iterable[str]) -> None:
        cleaned = sorted({t.strip().lower() for t in tags if t and t.strip()})
        self._conn.execute("DELETE FROM snippet_tags WHERE snippet_id = ?", (sid,))
        for name in cleaned:
            self._conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
            row = self._conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
            self._conn.execute(
                "INSERT OR IGNORE INTO snippet_tags(snippet_id, tag_id) VALUES (?, ?)",
                (sid, row["id"]),
            )

    def set_snippet_tags(self, sid: int, tags: Iterable[str]) -> None:
        with self._txn():
            self._set_tags(sid, tags)

    def add_tag_to_snippet(self, sid: int, tag: str) -> None:
        self.set_snippet_tags(sid, list(self.get_snippet(sid).tags) + [tag])

    def remove_tag_from_snippet(self, sid: int, tag: str) -> None:
        snip = self.get_snippet(sid)
        if snip is None:
            return
        self.set_snippet_tags(sid, [t for t in snip.tags if t != tag.strip().lower()])

    def all_tags(self) -> list[tuple[str, int]]:
        """Return ``[(name, usage_count), ...]`` sorted by frequency desc."""
        rows = self._conn.execute(
            """SELECT t.name AS name, COUNT(*) AS c
               FROM tags t JOIN snippet_tags st ON st.tag_id = t.id
               GROUP BY t.id ORDER BY c DESC, t.name ASC"""
        ).fetchall()
        return [(r["name"], r["c"]) for r in rows]

    def rename_tag(self, old: str, new: str) -> int:
        old, new = old.strip().lower(), new.strip().lower()
        if not new or old == new:
            return 0
        with self._txn():
            row = self._conn.execute("SELECT id FROM tags WHERE name = ?", (old,)).fetchone()
            if row is None:
                return 0
            tid = row["id"]
            existing = self._conn.execute(
                "SELECT id FROM tags WHERE name = ?", (new,)
            ).fetchone()
            if existing is None:
                self._conn.execute("UPDATE tags SET name = ? WHERE id = ?", (new, tid))
                return 1
            # merge old into existing
            new_id = existing["id"]
            self._conn.execute(
                """UPDATE OR IGNORE snippet_tags SET tag_id = ?
                   WHERE tag_id = ?""",
                (new_id, tid),
            )
            self._conn.execute("DELETE FROM tags WHERE id = ?", (tid,))
            # remove duplicates
            self._conn.execute(
                """DELETE FROM snippet_tags
                   WHERE rowid NOT IN (
                       SELECT MIN(rowid) FROM snippet_tags
                       GROUP BY snippet_id, tag_id
                   )"""
            )
            return 1

    def delete_tag(self, name: str) -> int:
        name = name.strip().lower()
        cur = self._conn.execute("DELETE FROM tags WHERE name = ?", (name,))
        return cur.rowcount

    # -- embeddings -------------------------------------------------------
    def save_embedding(self, sid: int, vector: np.ndarray, model: str) -> None:
        if vector.ndim != 1:
            vector = vector.reshape(-1)
        blob = struct.pack(f"<{len(vector)}f", *vector.tolist())
        self._conn.execute(
            """INSERT INTO embeddings(snippet_id, vector, dim, model)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(snippet_id) DO UPDATE SET
                 vector = excluded.vector,
                 dim    = excluded.dim,
                 model  = excluded.model""",
            (sid, blob, len(vector), model),
        )

    def all_embeddings(self) -> tuple[np.ndarray, list[int], str]:
        rows = self._conn.execute(
            "SELECT snippet_id, vector, dim, model FROM embeddings"
        ).fetchall()
        if not rows:
            return np.empty((0, 0), dtype=np.float32), [], ""
        ids, vecs = [], []
        dim, model = None, None
        for r in rows:
            ids.append(r["snippet_id"])
            arr = np.frombuffer(r["vector"], dtype="<f4")
            if dim is None:
                dim = arr.shape[0]
            vecs.append(arr)
            if model is None:
                model = r["model"]
        matrix = np.vstack(vecs).astype(np.float32)
        return matrix, ids, model or ""

    def delete_embedding(self, sid: int) -> None:
        self._conn.execute("DELETE FROM embeddings WHERE snippet_id = ?", (sid,))

    # -- helpers ----------------------------------------------------------
    def _row_to_snippet(self, row: sqlite3.Row) -> Snippet:
        tag_rows = self._conn.execute(
            """SELECT t.name FROM tags t
               JOIN snippet_tags st ON st.tag_id = t.id
               WHERE st.snippet_id = ?
               ORDER BY t.name""",
            (row["id"],),
        ).fetchall()
        return Snippet(
            id=row["id"],
            title=row["title"],
            code=row["code"],
            description=row["description"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            use_count=row["use_count"],
            tags=[r["name"] for r in tag_rows],
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_storage: Optional[Storage] = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


def close_storage() -> None:
    global _storage
    if _storage is not None:
        _storage.close()
        _storage = None
