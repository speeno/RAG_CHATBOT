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


def _log_filters(date_from: str | None, date_to: str | None, answerable: bool | None, feedback: str | None, q: str | None) -> dict[str, Any]:
    """date_from/date_to 는 'YYYY-MM-DD' 또는 ISO8601. date_to 는 포함(inclusive)이라 다음 날 0시로 바꿔 비교한다."""
    def _norm(d: str | None, end: bool) -> str | None:
        if not d:
            return None
        d = d.strip()
        if len(d) == 10:  # YYYY-MM-DD
            if end:
                from datetime import date, timedelta
                return (date.fromisoformat(d) + timedelta(days=1)).isoformat()
            return d
        return d
    if feedback not in (None, "", "positive", "negative", "none"):
        raise HTTPException(422, "feedback must be positive|negative|none")
    return {"date_from": _norm(date_from, False), "date_to": _norm(date_to, True),
            "answerable": answerable, "feedback": feedback or None, "q": (q or "").strip() or None}


@router.get("/logs", response_model=S.LogsPage)
def logs(limit: int = 20, offset: int = 0, date_from: str | None = None, date_to: str | None = None,
         answerable: bool | None = None, feedback: str | None = None, q: str | None = None,
         svc: Services = Depends(get_services)) -> dict[str, Any]:
    """상담 로그 목록(PRD §33) — 기간/응답 상태/피드백/검색어 필터 + 페이징."""
    f = _log_filters(date_from, date_to, answerable, feedback, q)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return {"items": svc.db.list_turn_logs(limit=limit, offset=offset, **f), "total": svc.db.count_turn_logs(**f),
            "limit": limit, "offset": offset}


@router.get("/logs/export.csv")
def logs_export(date_from: str | None = None, date_to: str | None = None, answerable: bool | None = None,
                feedback: str | None = None, q: str | None = None, svc: Services = Depends(get_services)) -> StreamingResponse:
    """현재 필터의 로그를 CSV로 내보낸다(최대 5,000건, UTF-8 BOM → Excel 호환)."""
    import csv
    import io

    f = _log_filters(date_from, date_to, answerable, feedback, q)
    rows = svc.db.list_turn_logs(limit=5000, offset=0, **f)
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["created_at", "conversation_id", "message_id", "user_query", "rewritten_query", "answerable", "answer",
                "feedback", "feedback_reason", "retrieval_ms", "llm_ms", "total_ms", "llm_provider", "embedding_provider",
                "retrieved_titles", "top_score"])
    for r in rows:
        ret = r.get("retrieved") or []
        w.writerow([r["created_at"], r["conversation_id"], r["message_id"], r["user_query"], r.get("rewritten_query") or "",
                    "" if r.get("answerable") is None else int(bool(r["answerable"])), (r.get("answer") or "").replace("\n", " "),
                    r.get("feedback") or "", r.get("feedback_reason") or "", r.get("retrieval_ms"), r.get("llm_ms"), r.get("total_ms"),
                    r.get("llm_provider") or "", r.get("embedding_provider") or "",
                    " | ".join(f"{x.get('title')}({x.get('score')})" for x in ret), ret[0].get("score") if ret else ""])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=conversation-logs.csv"})


@router.get("/logs/{message_id}", response_model=S.TurnLogOut)
def log_detail(message_id: str, svc: Services = Depends(get_services)) -> dict[str, Any]:
    row = svc.db.get_turn_log(message_id)
    if not row:
        raise HTTPException(404, "log not found")
    return row


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
