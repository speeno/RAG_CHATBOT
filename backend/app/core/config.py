"""애플리케이션 설정 (환경변수 / .env)."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# PRD §24 Fail-Closed 정책의 표준 안내 문구
NO_ANSWER_MESSAGE = "현재 등록된 자료에서는 해당 내용을 확인할 수 없습니다. 담당자에게 문의해주세요."


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_provider: str = "auto"  # auto | anthropic | openai | extractive
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    llm_effort: str = "low"
    llm_max_tokens: int = 2048
    openai_api_key: str | None = None
    openai_api_key_file: str = "../openaikey"   # 키를 .env에 복사하지 않고 파일에서 읽음
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Embedding
    embedding_provider: str = "auto"  # auto | voyage | openai | local | hash
    voyage_api_key: str | None = None
    voyage_model: str = "voyage-3"
    local_embedding_model: str = "intfloat/multilingual-e5-small"

    # Retrieval (Phase 2: Hybrid + Multi Query + Reranker)
    top_k: int = 5
    retrieval_score_threshold: float | None = None
    max_context_chunks: int = 5
    retrieval_mode: str = "hybrid"       # hybrid(dense+BM25 RRF) | dense
    rrf_k: int = 60                      # RRF 상수 (클수록 순위 차이 완만)
    dense_weight: float = 0.7            # 가중 RRF 에서 dense 축 비중 (sparse = 1 - dense_weight)
    retrieval_candidates: int = 30       # dense/sparse 각 후보 수 (PRD §17 top-30)
    multi_query: bool = False            # 채팅에서 Multi Query 사용(LLM 호출 추가 → 지연/비용 증가)
    multi_query_n: int = 3
    reranker: str = "none"               # none | llm

    # Chunking
    chunk_max_chars: int = 1200
    chunk_overlap_chars: int = 150

    # Storage / infra
    database_path: str = "./data/rag.db"          # SQLite (로컬 개발/테스트 기본값)
    database_url: str | None = None               # postgresql://… 설정 시 Postgres(Supabase) 사용
    cors_origins: str = "http://localhost:3100,http://localhost:3000"
    cors_origin_regex: str | None = None          # 예: https://.*\.vercel\.app (Vercel Preview 도메인)
    admin_token: str | None = None                # 설정 시 관리자 API(/knowledge, /logs, /stats, /search/test …)에 Bearer 토큰 필요

    @field_validator("retrieval_score_threshold", "anthropic_api_key", "voyage_api_key", "openai_api_key",
                     "database_url", "cors_origin_regex", "admin_token", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        if isinstance(v, str):
            v = v.split(" #", 1)[0].strip() if not v.strip().startswith("#") else ""
            return v or None
        return v

    # ── 파생 값 ──────────────────────────────────────
    @property
    def resolved_openai_key(self) -> str | None:
        if self.openai_api_key:
            return self.openai_api_key
        env = os.environ.get("OPENAI_API_KEY")
        if env:
            return env
        p = Path(self.openai_api_key_file)
        p = p if p.is_absolute() else (BASE_DIR / p)
        if p.is_file():
            try:
                raw = p.read_text(encoding="utf-8-sig")
            except OSError:
                return None
            # 파일에 라벨/따옴표 등이 섞여 있어도 키 토큰만 추출
            m = re.search(r"sk-[A-Za-z0-9_\-]{20,}", raw)
            if m:
                return m.group(0)
            key = "".join(ch for ch in raw.strip() if ch.isascii() and not ch.isspace())
            return key or None
        return None

    @property
    def db_path(self) -> Path:
        p = Path(self.database_path)
        return p if p.is_absolute() else (BASE_DIR / p).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def resolved_db_backend(self) -> str:
        return "postgres" if self.database_url else "sqlite"

    @property
    def resolved_llm_provider(self) -> str:
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if self.resolved_openai_key:
            return "openai"
        return "extractive"

    @property
    def resolved_embedding_provider(self) -> str:
        if self.embedding_provider != "auto":
            return self.embedding_provider
        if self.voyage_api_key or os.environ.get("VOYAGE_API_KEY"):
            return "voyage"
        if self.resolved_openai_key:
            return "openai"
        return "hash"

    @property
    def score_threshold(self) -> float:
        if self.retrieval_score_threshold is not None:
            return self.retrieval_score_threshold
        return {"voyage": 0.35, "openai": 0.30, "local": 0.40, "hash": 0.22}.get(self.resolved_embedding_provider, 0.3)


@lru_cache
def get_settings() -> Settings:
    return Settings()
