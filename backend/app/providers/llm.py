"""LLM 추상화.

- AnthropicLLM  : Claude(기본 claude-opus-5) — 스트리밍, 서버측 refusal fallback("default") 사용
- ExtractiveLLM : API 키 없이 동작하는 오프라인 폴백. 검색된 컨텍스트에서 질문과 가장 관련 있는 문장을 발췌해
                  답변을 구성한다(생성 X → 환각 0). 데모/테스트/CI용.
"""
from __future__ import annotations

import logging
import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Sequence

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str  # user | assistant
    content: str


@dataclass
class LLMResult:
    text: str
    refused: bool = False
    stop_reason: str | None = None
    model: str | None = None
    usage: dict = field(default_factory=dict)


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> Iterator[str]:
        """텍스트 델타를 순서대로 yield. 완료 후 self.last_result 로 최종 결과 조회."""

    last_result: LLMResult | None = None

    def generate(self, *, system: str, messages: Sequence[ChatMessage]) -> LLMResult:
        text = "".join(self.stream(system=system, messages=messages))
        return self.last_result or LLMResult(text=text)


# ── Anthropic Claude ─────────────────────────────────────────────
class AnthropicLLM(LLMProvider):
    def __init__(self, *, model: str = "claude-opus-5", api_key: str | None = None, effort: str = "low",
                 max_tokens: int = 2048):
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.name = f"anthropic:{model}"

    def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> Iterator[str]:
        self.last_result = None
        kwargs: dict = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": m.role, "content": m.content} for m in messages],
            output_config={"effort": self.effort},
            # 안전 분류기 거부 시 서버측에서 권장 대체 모델로 자동 재시도 (Claude API 전용)
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        collected: list[str] = []
        try:
            with self._client.beta.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    collected.append(text)
                    yield text
                final = stream.get_final_message()
        except self._anthropic.BadRequestError as e:
            # fallbacks/베타 미지원 환경(예: 프록시)일 때 한 번 더 표준 호출로 재시도
            if "fallbacks" in str(e) or "beta" in str(e).lower():
                logger.warning("fallbacks 미지원 → 표준 messages.stream 으로 재시도: %s", e)
                kwargs.pop("betas", None)
                kwargs.pop("fallbacks", None)
                with self._client.messages.stream(**kwargs) as stream:
                    for text in stream.text_stream:
                        collected.append(text)
                        yield text
                    final = stream.get_final_message()
            else:
                raise
        refused = getattr(final, "stop_reason", None) == "refusal"
        usage = getattr(final, "usage", None)
        self.last_result = LLMResult(
            text="".join(collected),
            refused=refused,
            stop_reason=getattr(final, "stop_reason", None),
            model=getattr(final, "model", self.model),
            usage={
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
            } if usage else {},
        )


# ── OpenAI (Chat Completions, streaming) ─────────────────────────
class OpenAILLM(LLMProvider):
    def __init__(self, *, api_key: str, model: str = "gpt-4.1-mini", max_tokens: int = 2048):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.name = f"openai:{model}"

    def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> Iterator[str]:
        self.last_result = None
        collected: list[str] = []
        finish = None
        usage = {}
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *({"role": m.role, "content": m.content} for m in messages)],
            max_completion_tokens=self.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = {"input_tokens": chunk.usage.prompt_tokens, "output_tokens": chunk.usage.completion_tokens}
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = getattr(choice.delta, "content", None)
            if delta:
                collected.append(delta)
                yield delta
            if choice.finish_reason:
                finish = choice.finish_reason
        self.last_result = LLMResult(
            text="".join(collected), refused=(finish == "content_filter"), stop_reason=finish, model=self.model, usage=usage,
        )


# ── Extractive (오프라인) ────────────────────────────────────────
_SENT_SPLIT = re.compile(r"(?<=[.!?。？！])\s+|(?<=다\.)\s*|\n+")


class ExtractiveLLM(LLMProvider):
    """컨텍스트 블록([Document N] ...)에서 질문과 어휘가 가장 많이 겹치는 문장을 골라 답한다."""

    name = "extractive"

    def __init__(self, no_answer_message: str, max_sentences: int = 3, min_overlap: float = 0.12):
        self.no_answer_message = no_answer_message
        self.max_sentences = max_sentences
        self.min_overlap = min_overlap

    def stream(self, *, system: str, messages: Sequence[ChatMessage]) -> Iterator[str]:
        self.last_result = None
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        question, context = _split_question_and_context(last_user)
        answer = self._answer(question, context)
        self.last_result = LLMResult(text=answer, model="extractive")
        # 스트리밍 흉내: 어절 단위로 yield
        for i, tok in enumerate(re.split(r"(\s+)", answer)):
            if tok:
                yield tok

    def _answer(self, question: str, context: str) -> str:
        docs = re.split(r"\n(?=\[Document \d+\])", context.strip())
        q_feats = _features(question)
        q_norm = math.sqrt(sum(w * w for w in q_feats.values())) or 1.0
        scored: list[tuple[float, int, str]] = []
        for block in docs:
            m = re.match(r"\[Document (\d+)\]", block)
            if not m:
                continue
            idx = int(m.group(1))
            rank_weight = 1.0 - 0.08 * (idx - 1)  # 상위 검색 문서 우대
            body = block.split("Content:", 1)[-1] if "Content:" in block else block
            for sent in _SENT_SPLIT.split(body):
                s = sent.strip(" -•\t")
                if len(s) < 6 or s.startswith("[") or s.startswith("Title:") or s.startswith("Section:"):
                    continue
                feats = _features(s)
                if not feats:
                    continue
                dot = sum(w * feats[k] for k, w in q_feats.items() if k in feats)
                s_norm = math.sqrt(sum(w * w for w in feats.values())) or 1.0
                overlap = dot / (q_norm * s_norm)
                if overlap >= self.min_overlap:
                    scored.append((overlap * rank_weight, idx, s))
        if not scored:
            return self.no_answer_message
        scored.sort(key=lambda t: -t[0])
        chosen: list[tuple[int, str]] = []
        seen = set()
        for _, idx, s in scored:
            if s in seen:
                continue
            seen.add(s)
            chosen.append((idx, s))
            if len(chosen) >= self.max_sentences:
                break
        # 문서 순서대로 정렬해 자연스럽게, 각 문장 뒤에 출처 번호 표기
        chosen.sort(key=lambda t: t[0])
        return " ".join(f"{s} [{idx}]" for idx, s in chosen)


def _features(text: str) -> dict[str, float]:
    # 임베딩(HashEmbedding)과 동일한 어간/n-gram 특징을 사용해 조사 차이에 강건하게 비교
    from app.providers.embeddings import HashEmbedding

    return HashEmbedding._features(text)


def _split_question_and_context(user_content: str) -> tuple[str, str]:
    """orchestrator가 만든 user 메시지 형식([참고 문서]... [질문] ...)에서 질문/컨텍스트를 분리."""
    if "[질문]" in user_content:
        ctx, q = user_content.rsplit("[질문]", 1)
        return q.strip(), ctx
    return user_content, ""


def build_llm_provider(kind: str, *, model: str, api_key: str | None, effort: str, max_tokens: int,
                       no_answer_message: str, openai_api_key: str | None = None,
                       openai_model: str = "gpt-4.1-mini") -> LLMProvider:
    if kind == "anthropic":
        return AnthropicLLM(model=model, api_key=api_key, effort=effort, max_tokens=max_tokens)
    if kind == "openai":
        if not openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai 이지만 OPENAI_API_KEY(또는 키 파일)가 없습니다.")
        return OpenAILLM(api_key=openai_api_key, model=openai_model, max_tokens=max_tokens)
    if kind == "extractive":
        return ExtractiveLLM(no_answer_message)
    raise ValueError(f"unknown llm provider: {kind}")
