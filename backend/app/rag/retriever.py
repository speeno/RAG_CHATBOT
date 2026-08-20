"""Vector Store 인터페이스 + DB(SQLite/Postgres)→numpy 인메모리 구현, Hybrid Retriever.

PRD §16~§18: Dense(임베딩 코사인) top-N + Sparse(BM25) top-N → RRF 융합 → top-k (Phase 2 Hybrid).
Fail-Closed 임계값은 프로바이더별로 보정된 **코사인 점수** 기준을 유지한다(top_score = 후보 중 최대 벡터 점수).
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
from app.rag.bm25 import BM25Index, rrf_fuse


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_pk: str
    document_id: str
    title: str
    section: str | None
    content: str
    score: float                     # 벡터(코사인) 점수 — Fail-Closed 임계값 비교 기준
    version: str | None = None
    updated_at: str | None = None
    category: str | None = None
    bm25_score: float | None = None  # Hybrid 시 BM25 점수 (sparse 상위에 없으면 None)
    rerank_score: float | None = None
    fused_score: float | None = None # RRF 융합 점수 (정렬 기준)
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
    def search(self, query_vec: np.ndarray, top_k: int, allowed_levels: set[str] | None = None) -> list[RetrievedChunk]: ...

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
        self._bm25 = BM25Index()
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
            self._bm25 = BM25Index()
            self._bm25.build([r["content"] for r in keep])
            self._dirty = False

    def _chunk(self, i: int, dense: float, bm25: float | None = None, fused: float | None = None) -> RetrievedChunk:
        r = self._rows[i]
        return RetrievedChunk(
            chunk_id=r["id"],
            document_pk=r["document_id"],
            document_id=r["business_document_id"],
            title=r["title"],
            section=r["section"],
            content=r["content"],
            score=round(float(dense), 4),
            version=r.get("version"),
            updated_at=r.get("updated_at") or r.get("effective_date"),
            category=r.get("category"),
            bm25_score=bm25,
            fused_score=fused,
        )

    def _dense_scores(self, query_vec: np.ndarray) -> np.ndarray | None:
        self._ensure_loaded()
        if self._matrix is None or not self._rows:
            return None
        q = np.asarray(query_vec, dtype=np.float32)
        if q.size != self._matrix.shape[1]:
            # 임베딩 모델이 바뀌어 차원이 다르면 재색인 필요 → 빈 결과(Fail-Closed로 이어짐)
            return None
        return self._matrix @ q

    def _allowed_mask(self, allowed_levels: set[str] | None) -> np.ndarray | None:
        """접근 레벨 필터(PRD §29) — LLM 이전, 검색 단계에서 적용한다. None 이면 전체 허용(관리자)."""
        if allowed_levels is None:
            return None
        return np.array([(r.get("access_level") or "public") in allowed_levels for r in self._rows], dtype=bool)

    def search(self, query_vec: np.ndarray, top_k: int, allowed_levels: set[str] | None = None) -> list[RetrievedChunk]:
        scores = self._dense_scores(query_vec)
        if scores is None:
            return []
        mask = self._allowed_mask(allowed_levels)
        if mask is not None:
            scores = np.where(mask, scores, -np.inf)
        idx = [int(i) for i in np.argsort(-scores)[:top_k] if scores[int(i)] != -np.inf]
        return [self._chunk(i, scores[i]) for i in idx]

    def search_hybrid(self, query_vec: np.ndarray, query_text: str, top_k: int,
                      dense_n: int = 30, sparse_n: int = 30, rrf_k: int = 60,
                      dense_weight: float = 0.7, allowed_levels: set[str] | None = None) -> list[RetrievedChunk]:
        """Dense top-N + BM25 top-N → 가중 RRF 융합 → top_k (PRD §17). dense 를 우선하되 BM25 로 recall 보강."""
        scores = self._dense_scores(query_vec)
        if scores is None:
            return []
        mask = self._allowed_mask(allowed_levels)
        if mask is not None:
            scores = np.where(mask, scores, -np.inf)
        dense_rank = [int(i) for i in np.argsort(-scores)[:dense_n] if scores[int(i)] != -np.inf]
        sparse = [(i, sc) for i, sc in self._bm25.search(query_text, top_k=sparse_n) if mask is None or mask[i]]
        bm25_by_idx = dict(sparse)
        fused = rrf_fuse([dense_rank, [i for i, _ in sparse]], k=rrf_k,
                         weights=[dense_weight, 1.0 - dense_weight])[:top_k]
        # 융합은 **후보 선택**에 사용하고, 최종 정렬은 보정된 코사인 점수 기준으로 한다
        # (Fail-Closed 임계값·컨텍스트 순서의 일관성 유지; 재정렬은 Reranker 의 몫 — PRD §18).
        picked = sorted(fused, key=lambda x: -scores[x[0]])
        return [self._chunk(i, scores[i], bm25_by_idx.get(i), round(f, 5)) for i, f in picked]

    @property
    def size(self) -> int:
        self._ensure_loaded()
        return len(self._rows)


@dataclass
class RetrievalResult:
    query: str
    chunks: list[RetrievedChunk]
    elapsed_ms: int
    top_score: float                 # 후보 중 최대 벡터 점수 (Fail-Closed 기준)
    mode: str = "dense"
    queries: list[str] = field(default_factory=list)   # Multi Query 사용 시 실제 검색된 쿼리들


class Retriever:
    def __init__(self, store: VectorStore, embedder: EmbeddingProvider, top_k: int = 5,
                 mode: str = "hybrid", rrf_k: int = 60, candidate_n: int = 30, dense_weight: float = 0.7):
        self.store = store
        self.embedder = embedder
        self.top_k = top_k
        self.mode = mode if mode in ("hybrid", "dense") else "hybrid"
        self.rrf_k = rrf_k
        self.candidate_n = candidate_n
        self.dense_weight = max(0.0, min(1.0, dense_weight))

    def _search(self, query: str, top_k: int, allowed_levels: set[str] | None = None) -> list[RetrievedChunk]:
        qv = self.embedder.embed_query(query)
        if self.mode == "hybrid" and isinstance(self.store, NumpyVectorStore):
            return self.store.search_hybrid(qv, query, top_k, dense_n=self.candidate_n,
                                            sparse_n=self.candidate_n, rrf_k=self.rrf_k,
                                            dense_weight=self.dense_weight, allowed_levels=allowed_levels)
        return self.store.search(qv, top_k, allowed_levels=allowed_levels)

    def retrieve(self, query: str, top_k: int | None = None, allowed_levels: set[str] | None = None) -> RetrievalResult:
        t0 = time.perf_counter()
        chunks = self._search(query, top_k or self.top_k, allowed_levels)
        elapsed = int((time.perf_counter() - t0) * 1000)
        top = max((c.score for c in chunks), default=0.0)
        return RetrievalResult(query=query, chunks=chunks, elapsed_ms=elapsed, top_score=top,
                               mode=self.mode, queries=[query])

    def retrieve_multi(self, queries: list[str], top_k: int | None = None,
                       allowed_levels: set[str] | None = None) -> RetrievalResult:
        """Multi Query(PRD §20): 쿼리별 검색 결과를 RRF 로 union. 첫 쿼리가 원 질문."""
        t0 = time.perf_counter()
        k = top_k or self.top_k
        per_query: list[list[RetrievedChunk]] = [self._search(q, k * 2, allowed_levels) for q in queries]
        best: dict[str, RetrievedChunk] = {}
        rankings: list[list[str]] = []
        for chunks in per_query:
            rankings.append([c.chunk_id for c in chunks])
            for c in chunks:
                prev = best.get(c.chunk_id)
                if prev is None or c.score > prev.score:
                    best[c.chunk_id] = c
        from app.rag.bm25 import rrf_fuse as _fuse
        id_rankings = rankings
        # rrf_fuse 는 int 인덱스를 기대하므로 chunk_id → 인덱스 매핑
        ids = list(best.keys())
        pos = {cid: i for i, cid in enumerate(ids)}
        fused = _fuse([[pos[cid] for cid in r] for r in id_rankings], k=self.rrf_k)[:k]
        chunks = []
        for i, f in fused:
            c = best[ids[i]]
            c.fused_score = round(f, 5)
            chunks.append(c)
        chunks.sort(key=lambda c: -c.score)
        elapsed = int((time.perf_counter() - t0) * 1000)
        top = max((c.score for c in chunks), default=0.0)
        return RetrievalResult(query=queries[0], chunks=chunks, elapsed_ms=elapsed, top_score=top,
                               mode=f"{self.mode}+multi", queries=queries)


# 하위 호환 별칭
SqliteNumpyVectorStore = NumpyVectorStore
