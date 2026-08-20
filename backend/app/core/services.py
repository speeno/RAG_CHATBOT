"""서비스 컨테이너 — 설정에 따라 DB/임베딩/벡터스토어/LLM/오케스트레이터를 조립한다."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import NO_ANSWER_MESSAGE, Settings
from app.core.db import BaseDatabase, build_database
from app.ingestion.indexer import Indexer
from app.providers.embeddings import EmbeddingProvider, build_embedding_provider
from app.providers.llm import LLMProvider, build_llm_provider
from app.rag.orchestrator import RAGOrchestrator
from app.rag.reranker import Reranker, build_reranker
from app.rag.retriever import NumpyVectorStore, Retriever

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    db: BaseDatabase
    embedder: EmbeddingProvider
    store: NumpyVectorStore
    retriever: Retriever
    reranker: Reranker
    llm: LLMProvider
    indexer: Indexer
    orchestrator: RAGOrchestrator

    def health(self) -> dict:
        # DB를 실제로 한 번 조회한다 — 외부 keep-alive ping이 Supabase 무활동 정지까지 막도록(배포 문서 참고)
        try:
            db_ok = bool(self.db.ping())
        except Exception:  # noqa: BLE001
            logger.exception("DB ping 실패")
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "db_backend": self.db.name,
            "db_ok": db_ok,
            "admin_auth": bool(self.settings.admin_token),
            "llm_provider": self.llm.name,
            "embedding_provider": self.embedder.name,
            "retrieval_mode": self.retriever.mode,
            "reranker": self.reranker.name,
            "score_threshold": self.settings.score_threshold,
            "indexed_chunks": self.store.size,
            "offline_mode": self.settings.resolved_llm_provider == "extractive",
        }


def build_services(settings: Settings, *, db_path: str | None = None) -> Services:
    # 명시적 db_path(테스트)가 있으면 SQLite, 아니면 DATABASE_URL → Postgres / DATABASE_PATH → SQLite
    db = build_database(None if db_path else settings.database_url, db_path or settings.db_path)
    embedder = build_embedding_provider(
        settings.resolved_embedding_provider,
        voyage_api_key=settings.voyage_api_key,
        voyage_model=settings.voyage_model,
        openai_api_key=settings.resolved_openai_key,
        openai_model=settings.openai_embedding_model,
        local_model=settings.local_embedding_model,
    )
    store = NumpyVectorStore(db)
    retriever = Retriever(store, embedder, top_k=settings.top_k, mode=settings.retrieval_mode,
                          rrf_k=settings.rrf_k, candidate_n=settings.retrieval_candidates, dense_weight=settings.dense_weight)
    llm = build_llm_provider(
        settings.resolved_llm_provider,
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        effort=settings.llm_effort,
        max_tokens=settings.llm_max_tokens,
        no_answer_message=NO_ANSWER_MESSAGE,
        openai_api_key=settings.resolved_openai_key,
        openai_model=settings.openai_model,
    )
    reranker = build_reranker(settings.reranker, llm)
    indexer = Indexer(db, embedder, store, chunk_max_chars=settings.chunk_max_chars,
                      chunk_overlap_chars=settings.chunk_overlap_chars)
    orchestrator = RAGOrchestrator(
        db=db, retriever=retriever, llm=llm, score_threshold=settings.score_threshold,
        max_context_chunks=settings.max_context_chunks, embedding_name=embedder.name, llm_name=llm.name,
        reranker=reranker, multi_query=settings.multi_query, multi_query_n=settings.multi_query_n,
    )
    if settings.resolved_llm_provider == "extractive":
        logger.warning("LLM API 키 미설정 → 오프라인 모드(extractive LLM). 실제 답변 생성은 ANTHROPIC/OPENAI 키 설정 후 가능합니다.")
    if settings.resolved_embedding_provider == "hash":
        logger.warning("임베딩 API 키 미설정 → hash n-gram 임베딩(어휘 기반) 사용. 의미 검색 품질은 제한적입니다.")
    return Services(settings, db, embedder, store, retriever, reranker, llm, indexer, orchestrator)
