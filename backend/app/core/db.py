"""SQLite 저장소 — 문서/청크(+임베딩)/대화/상담 로그.

MVP는 SQLite 단일 파일을 Document DB · Vector DB · Conversation DB로 함께 사용한다.
벡터 검색은 numpy 코사인 유사도로 수행하며, VectorStore 인터페이스(retrieval/vector_store.py)
뒤에 있으므로 pgvector/Qdrant 등으로 교체 가능하다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  title TEXT NOT NULL,
  category TEXT,
  source TEXT,
  version TEXT,
  effective_date TEXT,
  updated_at TEXT,
  status TEXT NOT NULL DEFAULT 'active',          -- active | inactive
  language TEXT DEFAULT 'ko',
  filename TEXT,
  content_type TEXT,                              -- markdown | html
  raw_text TEXT NOT NULL,
  processing_status TEXT NOT NULL DEFAULT 'uploaded', -- uploaded|parsing|chunking|embedding|indexed|error
  error_message TEXT,
  chunk_count INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  indexed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_document_id ON documents(document_id);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  section TEXT,
  content TEXT NOT NULL,
  char_count INTEGER NOT NULL,
  embedding BLOB,
  embedding_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,                 -- user | assistant
  content TEXT NOT NULL,
  sources TEXT,                       -- JSON
  answerable INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

CREATE TABLE IF NOT EXISTS turn_logs (
  id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL,
  message_id TEXT NOT NULL,           -- assistant message id
  user_query TEXT NOT NULL,
  rewritten_query TEXT,
  retrieved TEXT,                     -- JSON [{chunk_id, document_id, title, section, score}]
  answer TEXT,
  answerable INTEGER,
  llm_provider TEXT,
  embedding_provider TEXT,
  retrieval_ms INTEGER,
  llm_ms INTEGER,
  total_ms INTEGER,
  feedback TEXT,                      -- positive | negative
  feedback_reason TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turn_logs_message ON turn_logs(message_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            with self._lock:
                yield conn
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── documents ────────────────────────────────────────────────
    def insert_document(self, doc: dict[str, Any]) -> dict[str, Any]:
        doc = {**doc}
        doc.setdefault("id", new_id())
        doc.setdefault("created_at", now_iso())
        doc.setdefault("status", "active")
        doc.setdefault("processing_status", "uploaded")
        cols = ",".join(doc.keys())
        qs = ",".join("?" for _ in doc)
        with self.connect() as conn:
            conn.execute(f"INSERT INTO documents ({cols}) VALUES ({qs})", list(doc.values()))
        return self.get_document(doc["id"])  # type: ignore[return-value]

    def update_document(self, doc_id: str, **fields: Any) -> None:
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        with self.connect() as conn:
            conn.execute(f"UPDATE documents SET {sets} WHERE id=?", [*fields.values(), doc_id])

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_document(self, doc_id: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        return cur.rowcount > 0

    # ── chunks ───────────────────────────────────────────────────
    def replace_chunks(self, doc_id: str, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chunks WHERE document_id=?", (doc_id,))
            conn.executemany(
                "INSERT INTO chunks (id, document_id, chunk_index, section, content, char_count, embedding, embedding_model)"
                " VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        c.get("id") or f"{doc_id}-{c['chunk_index']:03d}",
                        doc_id,
                        c["chunk_index"],
                        c.get("section"),
                        c["content"],
                        len(c["content"]),
                        c.get("embedding"),
                        c.get("embedding_model"),
                    )
                    for c in chunks
                ],
            )
            conn.execute("UPDATE documents SET chunk_count=? WHERE id=?", (len(chunks), doc_id))

    def list_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, document_id, chunk_index, section, content, char_count, embedding_model"
                " FROM chunks WHERE document_id=? ORDER BY chunk_index",
                (doc_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_indexed_chunks(self) -> list[dict[str, Any]]:
        """활성(active) + 색인 완료(indexed) 문서의 청크만 반환 — PRD §31 (status=active 만 검색)."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.document_id, c.chunk_index, c.section, c.content, c.embedding, c.embedding_model,
                       d.document_id AS business_document_id, d.title, d.category, d.version, d.updated_at, d.effective_date
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE d.status='active' AND d.processing_status='indexed' AND c.embedding IS NOT NULL
                """
            ).fetchall()
        return [dict(r) for r in rows]

    # ── conversations / messages ─────────────────────────────────
    def ensure_conversation(self, conversation_id: str | None) -> str:
        ts = now_iso()
        with self.connect() as conn:
            if conversation_id:
                row = conn.execute("SELECT id FROM conversations WHERE id=?", (conversation_id,)).fetchone()
                if row:
                    conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (ts, conversation_id))
                    return conversation_id
            cid = conversation_id or new_id()
            conn.execute("INSERT INTO conversations (id, created_at, updated_at) VALUES (?,?,?)", (cid, ts, ts))
            return cid

    def add_message(self, conversation_id: str, role: str, content: str,
                    sources: list[dict[str, Any]] | None = None, answerable: bool | None = None,
                    message_id: str | None = None) -> dict[str, Any]:
        msg = {
            "id": message_id or new_id(),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": json.dumps(sources or [], ensure_ascii=False),
            "answerable": None if answerable is None else int(answerable),
            "created_at": now_iso(),
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, sources, answerable, created_at) VALUES (?,?,?,?,?,?,?)",
                list(msg.values()),
            )
        msg["sources"] = sources or []
        msg["answerable"] = answerable
        return msg

    def list_messages(self, conversation_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC, rowid ASC"
        with self.connect() as conn:
            rows = conn.execute(sql, (conversation_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sources"] = json.loads(d["sources"] or "[]")
            d["answerable"] = None if d["answerable"] is None else bool(d["answerable"])
            out.append(d)
        return out[-limit:] if limit else out

    # ── turn logs / feedback ─────────────────────────────────────
    def add_turn_log(self, log: dict[str, Any]) -> None:
        log = {**log}
        log.setdefault("id", new_id())
        log.setdefault("created_at", now_iso())
        if isinstance(log.get("retrieved"), (list, dict)):
            log["retrieved"] = json.dumps(log["retrieved"], ensure_ascii=False)
        if "answerable" in log and log["answerable"] is not None:
            log["answerable"] = int(log["answerable"])
        cols = ",".join(log.keys())
        qs = ",".join("?" for _ in log)
        with self.connect() as conn:
            conn.execute(f"INSERT INTO turn_logs ({cols}) VALUES ({qs})", list(log.values()))

    def set_feedback(self, message_id: str, rating: str, reason: str | None) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE turn_logs SET feedback=?, feedback_reason=? WHERE message_id=?", (rating, reason, message_id)
            )
        return cur.rowcount > 0

    def list_turn_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM turn_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["retrieved"] = json.loads(d["retrieved"] or "[]")
            out.append(d)
        return out
