"""BM25(Okapi) 희소 검색 — Phase 2 Hybrid Search의 sparse 축 (PRD §17).

외부 의존성 없이 순수 Python으로 구현한다(무료 티어 512MB 제약, konlpy 등 형태소 분석기 배제).
한국어는 교착어라 공백 토큰만으로는 recall이 낮으므로, 공백 토큰 + **한글 문자 bigram**을 함께 색인한다.
(예: "배송비는" → ["배송비는", "배송", "송비", "비는"]) — 조사 변형에 강건하다.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

_TOKEN = re.compile(r"[0-9a-zA-Z]+|[가-힣]+")
_HANGUL = re.compile(r"[가-힣]")


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _TOKEN.findall((text or "").lower()):
        out.append(tok)
        if _HANGUL.match(tok) and len(tok) >= 2:
            out.extend(tok[i : i + 2] for i in range(len(tok) - 1))
    return out


class BM25Index:
    """청크 리스트에 대한 인메모리 BM25. VectorStore 캐시와 함께 rebuild/invalidate 된다."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._df: dict[str, int] = {}
        self._tf: list[dict[str, int]] = []
        self._len: list[int] = []
        self._avg_len = 0.0
        self._n = 0
        self._postings: dict[str, list[int]] = {}

    def build(self, texts: list[str]) -> None:
        self._tf = []
        self._len = []
        df: dict[str, int] = defaultdict(int)
        postings: dict[str, list[int]] = defaultdict(list)
        for i, text in enumerate(texts):
            toks = tokenize(text)
            tf = dict(Counter(toks))
            self._tf.append(tf)
            self._len.append(len(toks))
            for t in tf:
                df[t] += 1
                postings[t].append(i)
        self._n = len(texts)
        self._df = dict(df)
        self._postings = dict(postings)
        self._avg_len = (sum(self._len) / self._n) if self._n else 0.0

    def search(self, query: str, top_k: int = 30) -> list[tuple[int, float]]:
        """(문서 인덱스, BM25 점수) 상위 top_k. 점수 0은 제외."""
        if not self._n:
            return []
        scores: dict[int, float] = defaultdict(float)
        seen_terms = set()
        for t in tokenize(query):
            if t in seen_terms:
                continue
            seen_terms.add(t)
            df = self._df.get(t)
            if not df:
                continue
            idf = math.log(1 + (self._n - df + 0.5) / (df + 0.5))
            for i in self._postings[t]:
                tf = self._tf[i][t]
                denom = tf + self.k1 * (1 - self.b + self.b * self._len[i] / (self._avg_len or 1))
                scores[i] += idf * tf * (self.k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:top_k]
        return [(i, round(s, 4)) for i, s in ranked if s > 0]


def rrf_fuse(rankings: list[list[int]], k: int = 60, weights: list[float] | None = None) -> list[tuple[int, float]]:
    """(가중) Reciprocal Rank Fusion: 점수 스케일이 다른 랭킹들을 순위 기반으로 융합한다.

    weights 로 축별 기여도를 조절한다(예: dense 0.7 / sparse 0.3 — 의미 검색을 우선하되
    키워드 일치가 강한 청크를 끌어올린다).
    """
    scores: dict[int, float] = defaultdict(float)
    for j, ranking in enumerate(rankings):
        w = weights[j] if weights and j < len(weights) else 1.0
        for rank, idx in enumerate(ranking):
            scores[idx] += w / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))
