"""서비스 컨테이너 — 설정에 따라 DB/임베딩/벡터스토어/LLM/오케스트레이터를 조립한다."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import NO_ANSWER_MESSAGE, Settings
from app.core.db import Database
from app.ingestion.indexer import Indexer
from app.providers.embeddings import EmbeddingProvider, build_embedding_provider
from app.providers.llm import LLMProvider, build_llm_provider
from app.rag.orchestrator import RAGOrchestrator
from app.rag.retriever import Retriever, SqliteNumpyVectorStore

logger = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    db: Database
    embedder: EmbeddingProvider
    store: SqliteNumpyVectorStore
    retriever: Retriever
    llm: LLMProvider
    indexer: Indexer
    orchestrator: RAGOrchestrator

    def health(self) -> dict:
        return {
            "status": "ok",
            "llm_provider": self.llm.name,
            "embedding_provider": self.embedder.name,
            "score_threshold": self.settings.score_threshold,
            "indexed_chunks": self.store.size,
            "offline_mode": self.settings.resolved_llm_provider == "extractive",
        }


def build_services(settings: Settings, *, db_path: str | None = None) -> Services:
    db = Database(db_path or settings.db_path)
    embedder = build_embedding_provider(
        settings.resolved_embedding_provider,
        voyage_api_key=settings.voyage_api_key,
        voyage_model=settings.voyage_model,
        openai_api_key=settings.resolved_openai_key,
        openai_model=settings.openai_embedding_model,
        local_model=settings.local_embedding_model,
    )
    store = SqliteNumpyVectorStore(db)
    retriever = Retriever(store, embedder, top_k=settings.top_k)
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
    indexer = Indexer(db, embedder, store, chunk_max_chars=settings.chunk_max_chars,
                      chunk_overlap_chars=settings.chunk_overlap_chars)
    orchestrator = RAGOrchestrator(
        db=db, retriever=retriever, llm=llm, score_threshold=settings.score_threshold,
        max_context_chunks=settings.max_context_chunks, embedding_name=embedder.name, llm_name=llm.name,
    )
    if settings.resolved_llm_provider == "extractive":
        logger.warning("LLM API 키 미설정 → 오프라인 모드(extractive LLM). 실제 답변 생성은 ANTHROPIC/OPENAI 키 설정 후 가능합니다.")
    if settings.resolved_embedding_provider == "hash":
        logger.warning("임베딩 API 키 미설정 → hash n-gram 임베딩(어휘 기반) 사용. 의미 검색 품질은 제한적입니다.")
    return Services(settings, db, embedder, store, retriever, llm, indexer, orchestrator)
