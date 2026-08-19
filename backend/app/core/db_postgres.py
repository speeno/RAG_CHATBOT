"""PostgreSQL(Supabase 등) 구현 — `DATABASE_URL`이 설정되면 사용한다.

- psycopg 3 + 커넥션 풀(min 1 / max 4). 무료 티어 Supabase Session Pooler(IPv4)와 함께 쓰기 위해
  prepared statement를 끈다(`prepare_threshold=None`) — transaction 모드 풀러에서도 안전.
- 스키마는 SQLite와 동일하되 `embedding BYTEA`, `messages.seq BIGSERIAL`(정렬 보조)만 다르다.
- 임베딩은 float32 바이트열 그대로 BYTEA에 저장하고 검색은 `rag/retriever.py`의 numpy 코사인 유사도로 수행한다.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from app.core.db import BaseDatabase

logger = logging.getLogger(__name__)

POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS documents (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL,
      title TEXT NOT NULL,
      category TEXT,
      source TEXT,
      version TEXT,
      effective_date TEXT,
      updated_at TEXT,
      status TEXT NOT NULL DEFAULT 'active',
      language TEXT DEFAULT 'ko',
      filename TEXT,
      content_type TEXT,
      raw_text TEXT NOT NULL,
      processing_status TEXT NOT NULL DEFAULT 'uploaded',
      error_message TEXT,
      chunk_count INTEGER DEFAULT 0,
      created_at TEXT NOT NULL,
      indexed_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documents_document_id ON documents(document_id)",
    """
    CREATE TABLE IF NOT EXISTS chunks (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
      chunk_index INTEGER NOT NULL,
      section TEXT,
      content TEXT NOT NULL,
      char_count INTEGER NOT NULL,
      embedding BYTEA,
      embedding_model TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id)",
    """
    CREATE TABLE IF NOT EXISTS conversations (
      id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
      seq BIGSERIAL,
      id TEXT PRIMARY KEY,
      conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      sources TEXT,
      answerable SMALLINT,
      created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)",
    """
    CREATE TABLE IF NOT EXISTS turn_logs (
      seq BIGSERIAL,
      id TEXT PRIMARY KEY,
      conversation_id TEXT NOT NULL,
      message_id TEXT NOT NULL,
      user_query TEXT NOT NULL,
      rewritten_query TEXT,
      retrieved TEXT,
      answer TEXT,
      answerable SMALLINT,
      llm_provider TEXT,
      embedding_provider TEXT,
      retrieval_ms INTEGER,
      llm_ms INTEGER,
      total_ms INTEGER,
      feedback TEXT,
      feedback_reason TEXT,
      created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_turn_logs_message ON turn_logs(message_id)",
    # 기존 테이블(초기 배포분)에 정렬 보조 컬럼이 없으면 추가 — 멱등
    "ALTER TABLE turn_logs ADD COLUMN IF NOT EXISTS seq BIGSERIAL",
    "ALTER TABLE messages ADD COLUMN IF NOT EXISTS seq BIGSERIAL",
    "CREATE INDEX IF NOT EXISTS idx_turn_logs_created ON turn_logs(created_at)",
    """
    CREATE TABLE IF NOT EXISTS unanswered_reviews (
      question_key TEXT PRIMARY KEY,
      status TEXT NOT NULL DEFAULT 'open',
      note TEXT,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inquiries (
      seq BIGSERIAL,
      id TEXT PRIMARY KEY,
      conversation_id TEXT,
      message_id TEXT,
      kind TEXT NOT NULL DEFAULT 'inquiry',
      contact TEXT,
      content TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open',
      created_at TEXT NOT NULL
    )
    """,
]

TABLES = ("inquiries", "unanswered_reviews", "turn_logs", "messages", "conversations", "chunks", "documents")


class PostgresDatabase(BaseDatabase):
    _MESSAGE_ORDER = "seq"
    name = "postgres"

    def __init__(self, url: str, *, min_size: int = 1, max_size: int = 4, connect_timeout: float = 30.0):
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("DATABASE_URL 사용에는 'psycopg[binary]'와 'psycopg-pool' 패키지가 필요합니다.") from e

        self.url = url
        self.pool = ConnectionPool(
            conninfo=url,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            name="rag-db",
        )
        self.pool.open(wait=True, timeout=connect_timeout)
        self._init_schema()
        logger.info("PostgreSQL 연결 완료 (pool %d..%d)", min_size, max_size)

    # ── infra ────────────────────────────────────────────────────
    def _init_schema(self) -> None:
        with self.connect() as conn:
            for stmt in POSTGRES_SCHEMA:
                conn.execute(stmt)

    def reset_schema(self) -> None:
        """모든 테이블 DROP 후 재생성 — 테스트 전용."""
        with self.connect() as conn:
            for t in TABLES:
                conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        self._init_schema()

    def close(self) -> None:
        self.pool.close()

    @contextmanager
    def connect(self) -> Iterator[Any]:
        # psycopg_pool: 블록 정상 종료 시 commit, 예외 시 rollback 후 반납
        with self.pool.connection() as conn:
            yield conn

    @staticmethod
    def _q(sql: str) -> str:
        return sql.replace("?", "%s")

    def _exec(self, conn: Any, sql: str, params: Any = ()) -> Any:
        return conn.execute(self._q(sql), params)

    def _executemany(self, conn: Any, sql: str, rows: list[Any]) -> None:
        if not rows:
            return
        with conn.cursor() as cur:
            cur.executemany(self._q(sql), rows)

    def ping(self) -> bool:
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
