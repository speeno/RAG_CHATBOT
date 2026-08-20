"""저장소 — 문서/청크(+임베딩)/대화/상담 로그.

MVP는 단일 관계형 DB를 Document DB · Vector DB · Conversation DB로 함께 사용한다.
- `SqliteDatabase`  : 로컬 개발/테스트용 단일 파일(기본값, `DATABASE_PATH`)
- `PostgresDatabase`: 운영용(Supabase 등, `DATABASE_URL`) — `app.core.db_postgres`
벡터 검색은 numpy 코사인 유사도로 수행하며(`rag/retriever.py`), 임베딩은 float32 바이트열(BLOB/BYTEA)로 저장한다.

모든 SQL은 `?` 플레이스홀더로 작성하고, 구현체의 `_exec()`가 드라이버에 맞게 변환한다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SQLITE_SCHEMA = """
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
  tags TEXT,                                      -- JSON array (예: ["환불","VIP"])
  access_level TEXT DEFAULT 'public',             -- public | internal — 검색 단계 필터(PRD §29)
  created_at TEXT NOT NULL,
  indexed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_document_id ON documents(document_id);

CREATE TABLE IF NOT EXISTS categories (
  name TEXT PRIMARY KEY,
  description TEXT,
  created_at TEXT NOT NULL
);

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
CREATE INDEX IF NOT EXISTS idx_turn_logs_created ON turn_logs(created_at);

CREATE TABLE IF NOT EXISTS unanswered_reviews (
  question_key TEXT PRIMARY KEY,      -- normalize_question(user_query)
  status TEXT NOT NULL DEFAULT 'open', -- open | resolved
  note TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inquiries (
  id TEXT PRIMARY KEY,
  conversation_id TEXT,
  message_id TEXT,
  kind TEXT NOT NULL DEFAULT 'inquiry', -- inquiry | agent
  contact TEXT,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',  -- open | done
  created_at TEXT NOT NULL
);
"""

# 하위 호환 별칭
SCHEMA = SQLITE_SCHEMA


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex


class BaseDatabase(ABC):
    """DB 구현체 공통 로직. 서브클래스는 `connect()`·`_exec()`·`_executemany()`·`_MESSAGE_ORDER`·`ping()`만 제공한다."""

    #: messages/turn_logs 정렬 보조 컬럼 (같은 초에 저장된 행의 순서 보장) — SQLite: rowid, Postgres: seq
    _MESSAGE_ORDER = "rowid"
    name = "base"

    @contextmanager
    @abstractmethod
    def connect(self) -> Iterator[Any]: ...

    @abstractmethod
    def _exec(self, conn: Any, sql: str, params: Any = ()) -> Any:
        """단일 문장을 실행하고 커서(또는 커서 유사 객체)를 반환한다."""

    @abstractmethod
    def _executemany(self, conn: Any, sql: str, rows: list[Any]) -> None: ...

    @abstractmethod
    def ping(self) -> bool:
        """연결 확인(SELECT 1). keep-alive/health 용."""

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
            self._exec(conn, f"INSERT INTO documents ({cols}) VALUES ({qs})", list(doc.values()))
        return self.get_document(doc["id"])  # type: ignore[return-value]

    def update_document(self, doc_id: str, **fields: Any) -> None:
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        with self.connect() as conn:
            self._exec(conn, f"UPDATE documents SET {sets} WHERE id=?", [*fields.values(), doc_id])

    @staticmethod
    def _parse_doc(d: dict[str, Any]) -> dict[str, Any]:
        d.pop("seq", None)
        d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
        d["access_level"] = d.get("access_level") or "public"
        return d

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = self._exec(conn, "SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return self._parse_doc(dict(row)) if row else None

    #: 목록 조회용 컬럼 — raw_text(원문 전체)는 제외한다. 문서가 커지면(예: PDF 수 MB)
    #: `SELECT *` 는 매 폴링마다 원문 전체를 DB에서 끌어와 응답 지연/타임아웃을 유발한다.
    _DOC_LIST_COLS = ("id, document_id, title, category, source, version, effective_date, updated_at, status, "
                      "language, filename, content_type, processing_status, error_message, chunk_count, tags, access_level, created_at, indexed_at")

    def list_documents(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = self._exec(conn, f"SELECT {self._DOC_LIST_COLS} FROM documents ORDER BY created_at DESC").fetchall()
        return [self._parse_doc(dict(r)) for r in rows]

    # ── categories (N4) ──────────────────────────────────────────
    def list_categories(self) -> list[dict[str, Any]]:
        """등록된 카테고리(categories 테이블) + 문서에서 실제 사용 중인 카테고리를 합쳐 문서 수와 함께 반환."""
        with self.connect() as conn:
            regs = self._exec(conn, "SELECT name, description FROM categories").fetchall()
            counts = self._exec(conn, "SELECT category AS name, COUNT(*) AS n FROM documents WHERE category IS NOT NULL GROUP BY category").fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in regs:
            out[r["name"]] = {"name": r["name"], "description": r["description"], "doc_count": 0, "registered": True}
        for r in counts:
            c = out.setdefault(r["name"], {"name": r["name"], "description": None, "doc_count": 0, "registered": False})
            c["doc_count"] = int(r["n"])
        return sorted(out.values(), key=lambda c: (-c["doc_count"], c["name"]))

    def upsert_category(self, name: str, description: str | None) -> dict[str, Any]:
        with self.connect() as conn:
            cur = self._exec(conn, "UPDATE categories SET description=? WHERE name=?", (description, name))
            if cur.rowcount == 0:
                self._exec(conn, "INSERT INTO categories (name, description, created_at) VALUES (?,?,?)", (name, description, now_iso()))
        return {"name": name, "description": description}

    def rename_category(self, old: str, new: str) -> int:
        """카테고리명 변경 — 문서에도 일괄 반영. 반환: 변경된 문서 수."""
        with self.connect() as conn:
            desc_row = self._exec(conn, "SELECT description FROM categories WHERE name=?", (old,)).fetchone()
            self._exec(conn, "DELETE FROM categories WHERE name IN (?,?)", (old, new))
            self._exec(conn, "INSERT INTO categories (name, description, created_at) VALUES (?,?,?)",
                       (new, desc_row["description"] if desc_row else None, now_iso()))
            cur = self._exec(conn, "UPDATE documents SET category=? WHERE category=?", (new, old))
        return cur.rowcount

    def delete_category(self, name: str, reassign_to: str | None = None) -> int:
        with self.connect() as conn:
            cur = self._exec(conn, "UPDATE documents SET category=? WHERE category=?", (reassign_to, name))
            self._exec(conn, "DELETE FROM categories WHERE name=?", (name,))
        return cur.rowcount

    # ── tags (N4) ────────────────────────────────────────────────
    def list_tags(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = self._exec(conn, "SELECT tags FROM documents WHERE tags IS NOT NULL").fetchall()
        from collections import Counter
        c: Counter[str] = Counter()
        for r in rows:
            try:
                c.update(t for t in json.loads(r["tags"]) if isinstance(t, str))
            except (TypeError, ValueError):
                continue
        return [{"name": t, "doc_count": n} for t, n in sorted(c.items(), key=lambda x: (-x[1], x[0]))]

    def _rewrite_tags(self, fn) -> int:
        """모든 문서의 tags 배열을 fn(list)->list 로 재작성. 반환: 변경 문서 수."""
        with self.connect() as conn:
            rows = self._exec(conn, "SELECT id, tags FROM documents WHERE tags IS NOT NULL").fetchall()
            changed = 0
            for r in rows:
                try:
                    tags = [t for t in json.loads(r["tags"]) if isinstance(t, str)]
                except (TypeError, ValueError):
                    continue
                new = fn(list(tags))
                if new != tags:
                    self._exec(conn, "UPDATE documents SET tags=? WHERE id=?",
                               (json.dumps(new, ensure_ascii=False) if new else None, r["id"]))
                    changed += 1
        return changed

    def rename_tag(self, old: str, new: str) -> int:
        def fn(tags: list[str]) -> list[str]:
            out = [new if t == old else t for t in tags]
            dedup: list[str] = []
            for t in out:
                if t not in dedup:
                    dedup.append(t)
            return dedup
        return self._rewrite_tags(fn)

    def delete_tag(self, name: str) -> int:
        return self._rewrite_tags(lambda tags: [t for t in tags if t != name])

    def delete_document(self, doc_id: str) -> bool:
        with self.connect() as conn:
            cur = self._exec(conn, "DELETE FROM documents WHERE id=?", (doc_id,))
        return cur.rowcount > 0

    # ── chunks ───────────────────────────────────────────────────
    def replace_chunks(self, doc_id: str, chunks: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            self._exec(conn, "DELETE FROM chunks WHERE document_id=?", (doc_id,))
            self._executemany(
                conn,
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
            self._exec(conn, "UPDATE documents SET chunk_count=? WHERE id=?", (len(chunks), doc_id))

    def list_chunks(self, doc_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = self._exec(
                conn,
                "SELECT id, document_id, chunk_index, section, content, char_count, embedding_model"
                " FROM chunks WHERE document_id=? ORDER BY chunk_index",
                (doc_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def all_indexed_chunks(self) -> list[dict[str, Any]]:
        """활성(active) + 색인 완료(indexed) 문서의 청크만 반환 — PRD §31 (status=active 만 검색)."""
        with self.connect() as conn:
            rows = self._exec(
                conn,
                """
                SELECT c.id, c.document_id, c.chunk_index, c.section, c.content, c.embedding, c.embedding_model,
                       d.document_id AS business_document_id, d.title, d.category, d.version, d.updated_at, d.effective_date,
                       d.access_level
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE d.status='active' AND d.processing_status='indexed' AND c.embedding IS NOT NULL
                """,
            ).fetchall()
        return [dict(r) for r in rows]

    # ── conversations / messages ─────────────────────────────────
    def ensure_conversation(self, conversation_id: str | None) -> str:
        ts = now_iso()
        with self.connect() as conn:
            if conversation_id:
                row = self._exec(conn, "SELECT id FROM conversations WHERE id=?", (conversation_id,)).fetchone()
                if row:
                    self._exec(conn, "UPDATE conversations SET updated_at=? WHERE id=?", (ts, conversation_id))
                    return conversation_id
            cid = conversation_id or new_id()
            self._exec(conn, "INSERT INTO conversations (id, created_at, updated_at) VALUES (?,?,?)", (cid, ts, ts))
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
            self._exec(
                conn,
                "INSERT INTO messages (id, conversation_id, role, content, sources, answerable, created_at) VALUES (?,?,?,?,?,?,?)",
                list(msg.values()),
            )
        msg["sources"] = sources or []
        msg["answerable"] = answerable
        return msg

    def list_messages(self, conversation_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC, {self._MESSAGE_ORDER} ASC"
        with self.connect() as conn:
            rows = self._exec(conn, sql, (conversation_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d.pop("seq", None)
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
            self._exec(conn, f"INSERT INTO turn_logs ({cols}) VALUES ({qs})", list(log.values()))

    def set_feedback(self, message_id: str, rating: str, reason: str | None) -> bool:
        with self.connect() as conn:
            cur = self._exec(
                conn, "UPDATE turn_logs SET feedback=?, feedback_reason=? WHERE message_id=?", (rating, reason, message_id)
            )
        return cur.rowcount > 0

    @staticmethod
    def _turn_log_filters(*, date_from: str | None = None, date_to: str | None = None,
                          answerable: bool | None = None, feedback: str | None = None,
                          q: str | None = None) -> tuple[str, list[Any]]:
        """상담 로그 필터 → (WHERE 절, 파라미터). created_at 은 ISO8601 문자열이라 문자열 비교로 충분하다."""
        where: list[str] = []
        params: list[Any] = []
        if date_from:
            where.append("created_at >= ?"); params.append(date_from)
        if date_to:
            where.append("created_at < ?"); params.append(date_to)
        if answerable is not None:
            where.append("answerable = ?"); params.append(int(answerable))
        if feedback == "none":
            where.append("feedback IS NULL")
        elif feedback in ("positive", "negative"):
            where.append("feedback = ?"); params.append(feedback)
        if q:
            where.append("(LOWER(user_query) LIKE LOWER(?) OR LOWER(COALESCE(answer,'')) LIKE LOWER(?))")
            params += [f"%{q}%", f"%{q}%"]
        return (" WHERE " + " AND ".join(where)) if where else "", params

    def list_turn_logs(self, limit: int = 100, offset: int = 0, **filters: Any) -> list[dict[str, Any]]:
        where, params = self._turn_log_filters(**filters)
        with self.connect() as conn:
            rows = self._exec(
                conn, f"SELECT * FROM turn_logs{where} ORDER BY created_at DESC, {self._MESSAGE_ORDER} DESC LIMIT ? OFFSET ?", [*params, limit, offset]
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d.pop("seq", None)
            d["retrieved"] = json.loads(d["retrieved"] or "[]")
            d["answerable"] = None if d["answerable"] is None else bool(d["answerable"])
            out.append(d)
        return out

    def count_turn_logs(self, **filters: Any) -> int:
        where, params = self._turn_log_filters(**filters)
        with self.connect() as conn:
            row = self._exec(conn, f"SELECT COUNT(*) AS n FROM turn_logs{where}", params).fetchone()
        return int(row["n"] if row else 0)

    def turn_log_rows(self, created_from: str, created_to: str) -> list[dict[str, Any]]:
        """통계 집계용 경량 조회: [created_from, created_to) 범위의 턴 로그(답변 본문 제외)."""
        with self.connect() as conn:
            rows = self._exec(
                conn,
                "SELECT conversation_id, message_id, user_query, retrieved, answerable, feedback, retrieval_ms, llm_ms, total_ms, created_at"
                " FROM turn_logs WHERE created_at >= ? AND created_at < ? ORDER BY created_at",
                (created_from, created_to),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["retrieved"] = json.loads(d["retrieved"] or "[]")
            d["answerable"] = None if d["answerable"] is None else bool(d["answerable"])
            out.append(d)
        return out

    # ── unanswered reviews (PRD §35 처리 상태) ───────────────────
    def list_unanswered_reviews(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = self._exec(conn, "SELECT * FROM unanswered_reviews").fetchall()
        return [dict(r) for r in rows]

    def upsert_unanswered_review(self, question_key: str, status: str, note: str | None) -> dict[str, Any]:
        ts = now_iso()
        with self.connect() as conn:
            cur = self._exec(conn, "UPDATE unanswered_reviews SET status=?, note=?, updated_at=? WHERE question_key=?",
                             (status, note, ts, question_key))
            if cur.rowcount == 0:
                self._exec(conn, "INSERT INTO unanswered_reviews (question_key, status, note, updated_at) VALUES (?,?,?,?)",
                           (question_key, status, note, ts))
        return {"question_key": question_key, "status": status, "note": note, "updated_at": ts}

    # ── inquiries (PRD §43 상담원 연결/문의 남기기) ───────────────
    def add_inquiry(self, *, conversation_id: str | None, message_id: str | None, kind: str, contact: str | None,
                    content: str) -> dict[str, Any]:
        row = {"id": new_id(), "conversation_id": conversation_id, "message_id": message_id, "kind": kind,
               "contact": contact, "content": content, "status": "open", "created_at": now_iso()}
        with self.connect() as conn:
            self._exec(conn, "INSERT INTO inquiries (id, conversation_id, message_id, kind, contact, content, status, created_at)"
                             " VALUES (?,?,?,?,?,?,?,?)", list(row.values()))
        return row

    def list_inquiries(self, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        where = " WHERE status=?" if status else ""
        params: list[Any] = [status] if status else []
        with self.connect() as conn:
            rows = self._exec(conn, f"SELECT * FROM inquiries{where} ORDER BY created_at DESC, {self._MESSAGE_ORDER} DESC LIMIT ?",
                              [*params, limit]).fetchall()
        return [{k: v for k, v in dict(r).items() if k != "seq"} for r in rows]

    def set_inquiry_status(self, inquiry_id: str, status: str) -> bool:
        with self.connect() as conn:
            cur = self._exec(conn, "UPDATE inquiries SET status=? WHERE id=?", (status, inquiry_id))
        return cur.rowcount > 0

    def get_turn_log(self, message_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = self._exec(conn, "SELECT * FROM turn_logs WHERE message_id=?", (message_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d.pop("seq", None)
        d["retrieved"] = json.loads(d["retrieved"] or "[]")
        d["answerable"] = None if d["answerable"] is None else bool(d["answerable"])
        return d


class SqliteDatabase(BaseDatabase):
    """SQLite 단일 파일 구현 — 로컬 개발/테스트 기본값."""

    _MESSAGE_ORDER = "rowid"
    name = "sqlite"

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as conn:
            conn.executescript(SQLITE_SCHEMA)
        # 기존 로컬 DB 마이그레이션(멱등): 새 컬럼이 없으면 추가
        for ddl in ("ALTER TABLE documents ADD COLUMN tags TEXT",
                    "ALTER TABLE documents ADD COLUMN access_level TEXT DEFAULT 'public'"):
            try:
                with self.connect() as conn:
                    conn.execute(ddl)
            except sqlite3.OperationalError:
                pass  # duplicate column

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

    def _exec(self, conn: sqlite3.Connection, sql: str, params: Any = ()) -> sqlite3.Cursor:
        return conn.execute(sql, params)

    def _executemany(self, conn: sqlite3.Connection, sql: str, rows: list[Any]) -> None:
        conn.executemany(sql, rows)

    def ping(self) -> bool:
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True


# 하위 호환: 기존 코드/테스트가 `Database(path)`를 쓰던 것을 유지
Database = SqliteDatabase


def build_database(database_url: str | None, sqlite_path: Path | str) -> BaseDatabase:
    """`DATABASE_URL`(postgres://…)이 있으면 Postgres, 없으면 SQLite."""
    if database_url:
        from app.core.db_postgres import PostgresDatabase

        return PostgresDatabase(database_url)
    return SqliteDatabase(sqlite_path)
