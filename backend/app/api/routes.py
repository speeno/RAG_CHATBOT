"""REST API 라우트."""
from __future__ import annotations

import json
from typing import Any, Iterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api import schemas as S
from app.core.services import Services

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = (".md", ".markdown", ".txt", ".html", ".htm")


def get_services(request: Request) -> Services:
    return request.app.state.services


# ── health ──────────────────────────────────────────────────────
@router.get("/health", response_model=S.HealthOut)
def health(svc: Services = Depends(get_services)) -> dict[str, Any]:
    return svc.health()


# ── chat ────────────────────────────────────────────────────────
@router.post("/chat", response_model=S.ChatResponse)
def chat(req: S.ChatRequest, svc: Services = Depends(get_services)) -> dict[str, Any]:
    turn = svc.orchestrator.chat(req.message, req.conversation_id)
    return _turn_to_response(turn)


@router.post("/chat/stream")
def chat_stream(req: S.ChatRequest, svc: Services = Depends(get_services)) -> StreamingResponse:
    """SSE 스트림. 이벤트: meta → sources → delta* → done."""

    def gen() -> Iterator[str]:
        for ev in svc.orchestrator.chat_stream(req.message, req.conversation_id):
            if ev["type"] == "done":
                payload = _turn_to_response(ev["turn"])
                yield _sse("done", payload)
            else:
                data = {k: v for k, v in ev.items() if k != "type"}
                yield _sse(ev["type"], data)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations/{conversation_id}", response_model=S.ConversationOut)
def get_conversation(conversation_id: str, svc: Services = Depends(get_services)) -> dict[str, Any]:
    msgs = svc.db.list_messages(conversation_id)
    if not msgs:
        raise HTTPException(404, "conversation not found")
    return {"conversation_id": conversation_id, "messages": msgs}


@router.post("/feedback")
def feedback(req: S.FeedbackRequest, svc: Services = Depends(get_services)) -> dict[str, Any]:
    ok = svc.db.set_feedback(req.message_id, req.rating, req.reason)
    if not ok:
        raise HTTPException(404, "message not found")
    return {"ok": True}


@router.get("/logs")
def logs(limit: int = 100, svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    return svc.db.list_turn_logs(limit=min(limit, 500))


# ── knowledge ───────────────────────────────────────────────────
@router.get("/knowledge", response_model=list[S.DocumentOut])
def list_knowledge(svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    return svc.db.list_documents()


@router.post("/knowledge", response_model=S.DocumentOut, status_code=201)
async def upload_knowledge(
    svc: Services = Depends(get_services),
    file: UploadFile | None = File(default=None),
    content: str | None = Form(default=None),
    filename: str | None = Form(default=None),
    title: str | None = Form(default=None),
    document_id: str | None = Form(default=None),
    category: str | None = Form(default=None),
    version: str | None = Form(default=None),
    effective_date: str | None = Form(default=None),
    updated_at: str | None = Form(default=None),
    source: str | None = Form(default=None),
    language: str | None = Form(default=None),
    status: str | None = Form(default=None),
    sync: bool = Form(default=False),
) -> dict[str, Any]:
    """문서 등록. multipart로 `file`을 올리거나 `content`(+`filename`) 텍스트를 직접 보낸다.
    front matter의 메타데이터보다 폼 필드가 우선한다. `sync=true`면 색인 완료까지 기다렸다가 응답."""
    if file is not None:
        name = file.filename or filename or "upload.md"
        if not name.lower().endswith(ALLOWED_EXT):
            raise HTTPException(400, f"지원하지 않는 형식입니다. 허용: {', '.join(ALLOWED_EXT)}")
        raw = await file.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "파일이 너무 큽니다 (최대 5MB)")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp949", errors="replace")
    elif content:
        name = filename or "upload.md"
        text = content
    else:
        raise HTTPException(400, "file 또는 content 중 하나는 필요합니다.")
    if not text.strip():
        raise HTTPException(400, "빈 문서입니다.")

    overrides = {
        "title": title, "document_id": document_id, "category": category, "version": version,
        "effective_date": effective_date, "updated_at": updated_at, "source": source, "language": language,
        "status": status,
    }
    doc = svc.indexer.register(text, filename=name, overrides=overrides)
    if sync:
        doc = svc.indexer.index(doc["id"])
    else:
        svc.indexer.index_async(doc["id"])
    return doc


@router.get("/knowledge/{doc_id}", response_model=S.DocumentDetail)
def get_knowledge(doc_id: str, svc: Services = Depends(get_services)) -> dict[str, Any]:
    doc = svc.db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    return doc


@router.get("/knowledge/{doc_id}/chunks", response_model=list[S.ChunkOut])
def get_chunks(doc_id: str, svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    if not svc.db.get_document(doc_id):
        raise HTTPException(404, "document not found")
    return svc.db.list_chunks(doc_id)


@router.patch("/knowledge/{doc_id}", response_model=S.DocumentOut)
def patch_knowledge(doc_id: str, patch: S.DocumentPatch, svc: Services = Depends(get_services)) -> dict[str, Any]:
    if not svc.db.get_document(doc_id):
        raise HTTPException(404, "document not found")
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    svc.db.update_document(doc_id, **fields)
    svc.store.invalidate()
    return svc.db.get_document(doc_id)  # type: ignore[return-value]


@router.delete("/knowledge/{doc_id}", status_code=204)
def delete_knowledge(doc_id: str, svc: Services = Depends(get_services)) -> None:
    if not svc.db.delete_document(doc_id):
        raise HTTPException(404, "document not found")
    svc.store.invalidate()


@router.post("/knowledge/{doc_id}/reindex", response_model=S.DocumentOut)
def reindex_knowledge(doc_id: str, sync: bool = False, svc: Services = Depends(get_services)) -> dict[str, Any]:
    doc = svc.db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if sync:
        return svc.indexer.index(doc_id)
    svc.db.update_document(doc_id, processing_status="uploaded", error_message=None)
    svc.indexer.index_async(doc_id)
    return svc.db.get_document(doc_id)  # type: ignore[return-value]


# ── search test (관리자용 검색 디버그, PRD §32) ───────────────────
@router.post("/search/test", response_model=S.SearchTestResponse)
def search_test(req: S.SearchTestRequest, svc: Services = Depends(get_services)) -> dict[str, Any]:
    """관리자 검색 테스트: 정규화 → (선택) Rewrite → 검색 → 임계값/정답 문서 기준 평가."""
    normalized = " ".join(req.query.split())
    history = [{"role": "user", "content": req.previous_query}] if req.previous_query else []
    search_query = svc.orchestrator.build_search_query(normalized, history)
    rewritten = search_query if search_query != normalized else None
    threshold = svc.settings.score_threshold

    r = svc.retriever.retrieve(search_query, top_k=req.top_k)
    results = []
    for i, c in enumerate(r.chunks):
        results.append({
            **c.as_source(),
            "rank": i + 1,
            "content": c.content,
            "passes_threshold": c.score >= threshold,
            "bm25_score": None,      # Phase 2: Hybrid(BM25) 도입 시 채움
            "rerank_score": None,    # Phase 2: Reranker 도입 시 채움
        })

    hit = None
    if req.expected_document_id:
        key = req.expected_document_id
        rank = next((x["rank"] for x in results if key in (x["document_id"], x["document_pk"])), None)
        hit = {"top1": rank is not None and rank <= 1, "top3": rank is not None and rank <= 3,
               "top5": rank is not None and rank <= 5, "rank": rank}

    return {
        "query": req.query,
        "normalized_query": normalized,
        "rewritten_query": rewritten,
        "search_query": search_query,
        "multi_queries": [],
        "threshold": threshold,
        "passes_threshold": bool(r.chunks) and r.top_score >= threshold,
        "top_score": round(float(r.top_score), 4),
        "elapsed_ms": r.elapsed_ms,
        "embedding_provider": svc.embedder.name,
        "indexed_chunks": svc.store.size,
        "hit": hit,
        "results": results,
    }


# ── helpers ─────────────────────────────────────────────────────
def _turn_to_response(turn: Any) -> dict[str, Any]:
    return {
        "conversation_id": turn.conversation_id,
        "message_id": turn.message_id,
        "answer": turn.answer,
        "answerable": turn.answerable,
        "handoff": turn.handoff,
        "sources": turn.sources,
        "rewritten_query": turn.rewritten_query,
        "timings": turn.timings,
        "model": turn.llm_model,
    }


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
