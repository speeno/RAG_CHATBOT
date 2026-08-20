"""Reranker 추상화 (PRD §18) — Phase 2.

무료 티어 제약(512MB, cross-encoder 모델 탑재 불가) 때문에 기본은 없음(noop)이며,
`RERANKER=llm` 설정 시 LLM(listwise) 재순위화를 사용한다. 전용 rerank API(Voyage/Cohere)는
키가 생기면 이 인터페이스 뒤에 추가한다.
"""
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod

from app.providers.llm import ChatMessage, LLMProvider
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


class Reranker(ABC):
    name: str = "none"

    @abstractmethod
    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """chunks 에 rerank_score 를 채우고 재정렬해 반환한다. 실패 시 원본 순서 그대로."""


class NoopReranker(Reranker):
    name = "none"

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        return chunks


_SYSTEM = (
    "당신은 검색 결과 재순위화기(reranker)입니다. 질문과 각 문서 발췌의 관련도를 0.0~1.0 로 평가하세요. "
    '반드시 JSON 배열만 출력합니다: [{"i": <번호>, "s": <점수>}, ...] (모든 번호 포함, 설명 금지)'
)


class LLMReranker(Reranker):
    """LLM listwise 재순위화 — 한 번의 호출로 후보 전체(≤20)를 채점한다."""

    name = "llm"

    def __init__(self, llm: LLMProvider, max_chunks: int = 20, snippet_chars: int = 400):
        self.llm = llm
        self.max_chunks = max_chunks
        self.snippet_chars = snippet_chars

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        cand = chunks[: self.max_chunks]
        if len(cand) <= 1:
            return chunks
        lines = [f"[{i}] ({c.title} > {c.section or '-'}) {c.content[: self.snippet_chars]}" for i, c in enumerate(cand)]
        prompt = f"질문: {query}\n\n문서 발췌:\n" + "\n\n".join(lines)
        try:
            text = "".join(self.llm.stream(system=_SYSTEM, messages=[ChatMessage("user", prompt)]))
            m = re.search(r"\[.*\]", text, re.S)
            scores = {int(x["i"]): float(x["s"]) for x in json.loads(m.group(0))} if m else {}
        except Exception:  # noqa: BLE001 — rerank 실패는 치명적이지 않다(원 순서 유지)
            logger.exception("LLM rerank 실패 — 원본 순서 유지")
            return chunks
        if not scores:
            return chunks
        for i, c in enumerate(cand):
            c.rerank_score = round(max(0.0, min(1.0, scores.get(i, 0.0))), 3)
        ordered = sorted(cand, key=lambda c: -(c.rerank_score or 0.0))
        return ordered + chunks[self.max_chunks :]


def build_reranker(kind: str, llm: LLMProvider) -> Reranker:
    if kind == "llm" and llm.name != "extractive":
        return LLMReranker(llm)
    return NoopReranker()
