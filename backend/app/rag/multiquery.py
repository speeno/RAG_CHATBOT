"""Multi Query 생성 (PRD §20) — 질문을 서로 다른 표현으로 확장해 검색 recall 을 높인다.

LLM 프로바이더가 extractive(오프라인)면 빈 목록을 반환한다(단일 쿼리 검색으로 폴백).
"""
from __future__ import annotations

import logging
import re

from app.providers.llm import ChatMessage, LLMProvider

logger = logging.getLogger(__name__)

_SYSTEM = (
    "당신은 검색 쿼리 확장기입니다. 사용자 질문과 같은 의도를 가진 한국어 검색 쿼리를 서로 다른 표현으로 "
    "{n}개 생성하세요. 한 줄에 하나씩, 번호/설명 없이 쿼리만 출력합니다. 원 질문을 반복하지 마세요."
)


def generate_multi_queries(llm: LLMProvider, query: str, n: int = 3) -> list[str]:
    if llm.name == "extractive" or n <= 0:
        return []
    try:
        text = "".join(llm.stream(system=_SYSTEM.format(n=n), messages=[ChatMessage("user", query)]))
    except Exception:  # noqa: BLE001 — 확장 실패는 단일 쿼리로 폴백
        logger.exception("Multi Query 생성 실패 — 단일 쿼리로 진행")
        return []
    out: list[str] = []
    for line in text.splitlines():
        q = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"')
        if q and q != query and q not in out:
            out.append(q)
    return out[:n]
