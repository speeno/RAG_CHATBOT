"""Vector Store 인터페이스 + DB(SQLite/Postgres)→numpy 인메모리 구현, Retriever.

PRD §16~§18: MVP는 Dense(Vector) 검색만 수행하며 Hybrid(BM25)·Reranker는 Phase 2에서 이 인터페이스 뒤에 추가한다.
PRD §29/§31: 권한·상태(active) 필터는 검색 단계(DB 조회)에서 적용한다.
"""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.db import BaseDatabase
from app.providers.embeddings import EmbeddingProvider


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_pk: str
    document_id: str
    title: str
    section: str | None
    content: str
    score: float
    version: str | None = None
    updated_at: str | None = None
    category: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_source(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_pk": self.document_pk,
            "title": self.title,
            "section": self.section,
            "version": self.version,
            "updated_at": self.updated_at,
            "category": self.category,
            "score": round(float(self.score), 4),
        }


class VectorStore(ABC):
    @abstractmethod
    def search(self, query_vec: np.ndarray, top_k: int) -> list[RetrievedChunk]: ...

    @abstractmethod
    def invalidate(self) -> None:
        """색인 변경(문서 추가/삭제/상태 변경) 시 캐시 무효화."""


class NumpyVectorStore(VectorStore):
    """활성·색인 완료 청크의 임베딩을 메모리에 캐시하고 코사인 유사도로 검색한다(수천~수만 청크 규모 적합)."""

    def __init__(self, db: BaseDatabase):
        self.db = db
        self._lock = threading.Lock()
        self._matrix: np.ndarray | None = None
        self._rows: list[dict[str, Any]] = []
        self._dirty = True

    def invalidate(self) -> None:
        with self._lock:
            self._dirty = True

    def _ensure_loaded(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            rows = self.db.all_indexed_chunks()
            vecs = []
            keep = []
            for r in rows:
                emb = np.frombuffer(r["embedding"], dtype=np.float32)
                if emb.size == 0:
                    continue
                vecs.append(emb)
                keep.append(r)
            if vecs:
                dim = max(v.size for v in vecs)
                mat = np.zeros((len(vecs), dim), dtype=np.float32)
                for i, v in enumerate(vecs):
                    mat[i, : v.size] = v
                self._matrix = mat
            else:
                self._matrix = None
            self._rows = keep
            self._dirty = False

    def search(self, query_vec: np.ndarray, top_k: int) -> list[RetrievedChunk]:
        self._ensure_loaded()
        if self._matrix is None or not self._rows:
            return []
        q = np.asarray(query_vec, dtype=np.float32)
        if q.size != self._matrix.shape[1]:
            # 임베딩 모델이 바뀌어 차원이 다르면 재색인 필요 → 빈 결과(Fail-Closed로 이어짐)
            return []
        scores = self._matrix @ q
        idx = np.argsort(-scores)[:top_k]
        out: list[RetrievedChunk] = []
        for i in idx:
            r = self._rows[int(i)]
            out.append(
                RetrievedChunk(
                    chunk_id=r["id"],
                    document_pk=r["document_id"],
                    document_id=r["business_document_id"],
                    title=r["title"],
                    section=r["section"],
                    content=r["content"],
                    score=float(scores[int(i)]),
                    version=r.get("version"),
                    updated_at=r.get("updated_at") or r.get("effective_date"),
                    category=r.get("category"),
                )
            )
        return out

    @property
    def size(self) -> int:
        self._ensure_loaded()
        return len(self._rows)


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    elapsed_ms: int
    top_score: float


class Retriever:
    def __init__(self, store: VectorStore, embedder: EmbeddingProvider, top_k: int = 5):
        self.store = store
        self.embedder = embedder
        self.top_k = top_k

    def retrieve(self, query: str, top_k: int | None = None) -> RetrievalResult:
        t0 = time.perf_counter()
        qv = self.embedder.embed_query(query)
        chunks = self.store.search(qv, top_k or self.top_k)
        elapsed = int((time.perf_counter() - t0) * 1000)
        return RetrievalResult(query=query, chunks=chunks, elapsed_ms=elapsed, top_score=chunks[0].score if chunks else 0.0)


# 하위 호환 별칭
SqliteNumpyVectorStore = NumpyVectorStore
