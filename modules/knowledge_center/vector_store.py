"""TITAN AI — local vector store (SQLite).

Stores libraries, documents, and embedded chunks on the local filesystem. No
external service is contacted. Similarity search is exact cosine in pure Python
— fine for the local, project-sized knowledge bases TITAN targets.

Chunks are tagged with the embedder name so a library embedded with the lexical
fallback is never mixed with one embedded by the Ollama model.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from modules.knowledge_center.embeddings import cosine


@dataclass
class Hit:
    chunk_id: int
    document: str
    source: str
    ordinal: int
    text: str
    score: float


class VectorStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode=WAL")
        con.row_factory = sqlite3.Row
        return con

    def _init(self) -> None:
        with self._conn() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS libraries(
                name TEXT PRIMARY KEY,
                created_at REAL
            );
            CREATE TABLE IF NOT EXISTS documents(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library TEXT NOT NULL,
                name TEXT NOT NULL,
                source TEXT,
                kind TEXT,
                added_at REAL,
                UNIQUE(library, name)
            );
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                library TEXT NOT NULL,
                ordinal INTEGER,
                text TEXT,
                embedding TEXT,     -- JSON array
                embedder TEXT,
                FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_lib ON chunks(library, embedder);
            """)

    # -- libraries -------------------------------------------------------- #
    def create_library(self, name: str) -> None:
        with self._conn() as con:
            con.execute("INSERT OR IGNORE INTO libraries(name, created_at) VALUES(?,?)",
                        (name, time.time()))

    def list_libraries(self) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT l.name, l.created_at, "
                "(SELECT COUNT(*) FROM documents d WHERE d.library=l.name) AS docs, "
                "(SELECT COUNT(*) FROM chunks c WHERE c.library=l.name) AS chunks "
                "FROM libraries l ORDER BY l.created_at").fetchall()
        return [dict(r) for r in rows]

    def list_documents(self, library: str) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT d.id, d.name, d.source, d.kind, d.added_at, "
                "(SELECT COUNT(*) FROM chunks c WHERE c.document_id=d.id) AS chunks "
                "FROM documents d WHERE d.library=? ORDER BY d.added_at", (library,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -- ingest ----------------------------------------------------------- #
    def add_document(self, library: str, name: str, source: str, kind: str,
                     chunks: list[tuple[int, str, list[float]]],
                     embedder: str) -> int:
        """Insert (or replace) a document and its embedded chunks.

        chunks: list of (ordinal, text, embedding).
        Returns the document id.
        """
        self.create_library(library)
        with self._conn() as con:
            # Replace any existing document of the same name in this library.
            old = con.execute("SELECT id FROM documents WHERE library=? AND name=?",
                              (library, name)).fetchone()
            if old:
                con.execute("DELETE FROM chunks WHERE document_id=?", (old["id"],))
                con.execute("DELETE FROM documents WHERE id=?", (old["id"],))
            cur = con.execute(
                "INSERT INTO documents(library, name, source, kind, added_at) "
                "VALUES(?,?,?,?,?)", (library, name, source, kind, time.time()))
            doc_id = cur.lastrowid
            con.executemany(
                "INSERT INTO chunks(document_id, library, ordinal, text, embedding, embedder) "
                "VALUES(?,?,?,?,?,?)",
                [(doc_id, library, o, t, json.dumps(e), embedder) for o, t, e in chunks])
            return doc_id

    def delete_document(self, library: str, name: str) -> bool:
        with self._conn() as con:
            row = con.execute("SELECT id FROM documents WHERE library=? AND name=?",
                              (library, name)).fetchone()
            if not row:
                return False
            con.execute("DELETE FROM chunks WHERE document_id=?", (row["id"],))
            con.execute("DELETE FROM documents WHERE id=?", (row["id"],))
            return True

    # -- search ----------------------------------------------------------- #
    def search(self, library: str, query_vec: list[float], embedder: str,
               top_k: int = 4) -> list[Hit]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT c.id, c.ordinal, c.text, c.embedding, d.name, d.source "
                "FROM chunks c JOIN documents d ON d.id=c.document_id "
                "WHERE c.library=? AND c.embedder=?", (library, embedder)).fetchall()
        scored: list[Hit] = []
        for r in rows:
            vec = json.loads(r["embedding"])
            if len(vec) != len(query_vec):
                continue  # different embedder dim; skip defensively
            scored.append(Hit(
                chunk_id=r["id"], document=r["name"], source=r["source"],
                ordinal=r["ordinal"], text=r["text"],
                score=cosine(query_vec, vec)))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]
