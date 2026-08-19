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


class SearchTestResponse(BaseModel):
    query: str
    threshold: float
    elapsed_ms: int
    results: list[dict[str, Any]]


class HealthOut(BaseModel):
    status: str
    llm_provider: str
    embedding_provider: str
    score_threshold: float
    indexed_chunks: int
    offline_mode: bool
