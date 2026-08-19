"""API 요청/응답 스키마 (PRD §44~§45)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    chunk_id: str
    document_id: str
    document_pk: str
    title: str
    section: str | None = None
    version: str | None = None
    updated_at: str | None = None
    category: str | None = None
    score: float


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    answerable: bool
    handoff: bool
    sources: list[Source]
    rewritten_query: str | None = None
    timings: dict[str, int] = {}
    model: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list[dict[str, Any]] = []
    answerable: bool | None = None
    created_at: str


class ConversationOut(BaseModel):
    conversation_id: str
    messages: list[MessageOut]


class FeedbackRequest(BaseModel):
    message_id: str
    rating: Literal["positive", "negative"]
    reason: str | None = Field(default=None, max_length=500)


class DocumentOut(BaseModel):
    id: str
    document_id: str
    title: str
    category: str | None = None
    source: str | None = None
    version: str | None = None
    effective_date: str | None = None
    updated_at: str | None = None
    status: str
    language: str | None = None
    filename: str | None = None
    content_type: str | None = None
    processing_status: str
    error_message: str | None = None
    chunk_count: int = 0
    created_at: str
    indexed_at: str | None = None


class DocumentDetail(DocumentOut):
    raw_text: str


class ChunkOut(BaseModel):
    id: str
    chunk_index: int
    section: str | None
    content: str
    char_count: int
    embedding_model: str | None


class DocumentPatch(BaseModel):
    status: Literal["active", "inactive"] | None = None
    title: str | None = None
    category: str | None = None
    version: str | None = None


class SearchTestRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    previous_query: str | None = Field(default=None, max_length=2000)   # 후속 질문 Rewrite 시뮬레이션용(직전 사용자 질문)
    expected_document_id: str | None = None                            # 정답 문서(document_id 또는 pk) → Top-k Hit 계산


class SearchTestHit(BaseModel):
    top1: bool
    top3: bool
    top5: bool
    rank: int | None   # 정답 문서가 처음 등장한 순위(1-base), 없으면 None


class SearchTestResponse(BaseModel):
    query: str
    normalized_query: str
    rewritten_query: str | None
    search_query: str
    multi_queries: list[str]          # Phase 2(Multi Query) 도입 전까지는 []
    threshold: float
    passes_threshold: bool            # top1 score >= threshold (아니면 Fail-Closed)
    top_score: float
    elapsed_ms: int
    embedding_provider: str
    indexed_chunks: int
    hit: SearchTestHit | None
    results: list[dict[str, Any]]


class TurnLogOut(BaseModel):
    id: str
    conversation_id: str
    message_id: str
    user_query: str
    rewritten_query: str | None = None
    retrieved: list[dict[str, Any]] = []
    answer: str | None = None
    answerable: bool | None = None
    llm_provider: str | None = None
    embedding_provider: str | None = None
    retrieval_ms: int | None = None
    llm_ms: int | None = None
    total_ms: int | None = None
    feedback: str | None = None
    feedback_reason: str | None = None
    created_at: str


class LogsPage(BaseModel):
    items: list[TurnLogOut]
    total: int
    limit: int
    offset: int


class UnansweredReviewPatch(BaseModel):
    status: Literal["open", "resolved"]
    note: str | None = Field(default=None, max_length=500)


class InquiryCreate(BaseModel):
    conversation_id: str | None = None
    message_id: str | None = None
    kind: Literal["inquiry", "agent"] = "inquiry"
    contact: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1, max_length=2000)


class InquiryOut(BaseModel):
    id: str
    conversation_id: str | None = None
    message_id: str | None = None
    kind: str
    contact: str | None = None
    content: str
    status: str
    created_at: str


class InquiryPatch(BaseModel):
    status: Literal["open", "done"]


class HealthOut(BaseModel):
    status: str
    db_backend: str = "sqlite"
    db_ok: bool = True
    admin_auth: bool = False
    llm_provider: str
    embedding_provider: str
    score_threshold: float
    indexed_chunks: int
    offline_mode: bool
