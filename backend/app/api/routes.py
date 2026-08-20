"""REST API 라우트."""
from __future__ import annotations

import json
import time as _time
from typing import Any, Iterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.api import schemas as S
from app.core.config import NO_ANSWER_MESSAGE
from app.core import stats as ST
from app.core.services import Services

router = APIRouter(prefix="/api")


# ── 관리자 인증 (PRD §29 권한 관리의 1단계: 단일 관리자 토큰) ────────
def require_admin(request: Request) -> None:
    """`ADMIN_TOKEN`이 설정돼 있으면 `Authorization: Bearer <token>` 또는 `X-Admin-Token` 헤더를 요구한다.
    미설정(로컬 개발)이면 통과하되 /api/health 의 admin_auth=false 로 드러낸다."""
    import secrets

    token = request.app.state.services.settings.admin_token
    if not token:
        return
    auth = request.headers.get("authorization", "")
    given = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("x-admin-token", "").strip()
    if not given or not secrets.compare_digest(given, token):
        raise HTTPException(401, "admin token required", headers={"WWW-Authenticate": "Bearer"})


admin = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = (".md", ".markdown", ".txt", ".html", ".htm", ".pdf")


def get_services(request: Request) -> Services:
    return request.app.state.services


# ── health ──────────────────────────────────────────────────────
@router.get("/health", response_model=S.HealthOut)
def health(svc: Services = Depends(get_services)) -> dict[str, Any]:
    return svc.health()


# ── chat ────────────────────────────────────────────────────────
@router.post("/chat", response_model=S.ChatResponse)
def chat(req: S.ChatRequest, svc: Services = Depends(get_services)) -> dict[str, Any]:
    loc = (req.location.lat, req.location.lon) if req.location else None
    turn = svc.orchestrator.chat(req.message, req.conversation_id, location=loc)
    return _turn_to_response(turn)


@router.post("/chat/stream")
def chat_stream(req: S.ChatRequest, svc: Services = Depends(get_services)) -> StreamingResponse:
    """SSE 스트림. 이벤트: meta → sources → delta* → done."""

    loc = (req.location.lat, req.location.lon) if req.location else None

    def gen() -> Iterator[str]:
        for ev in svc.orchestrator.chat_stream(req.message, req.conversation_id, location=loc):
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
    """피드백 저장(PRD §36). 복수 사유·추가 의견은 feedback_reason 한 컬럼에 사람이 읽을 수 있게 합친다.
    `escalate=True` 면 상담원 확인용 문의(inquiries)로도 접수한다(목업 user/04 '상담원에게 전달')."""
    parts = [r.strip() for r in (req.reasons or []) if r.strip()]
    if req.reason and req.reason.strip() and req.reason.strip() not in parts:
        parts.append(req.reason.strip())
    reason_text = ", ".join(parts) if parts else None
    if req.comment and req.comment.strip():
        reason_text = (reason_text + " | 의견: " if reason_text else "의견: ") + req.comment.strip()
    ok = svc.db.set_feedback(req.message_id, req.rating, reason_text)
    if not ok:
        raise HTTPException(404, "message not found")
    escalated = False
    if req.escalate:
        log = svc.db.get_turn_log(req.message_id)
        content = f"[피드백 전달] 질문: {log['user_query'] if log else '-'}"
        if reason_text:
            content += f"\n사유: {reason_text}"
        svc.db.add_inquiry(conversation_id=log["conversation_id"] if log else None, message_id=req.message_id,
                           kind="inquiry", contact=None, content=content[:2000])
        escalated = True
    return {"ok": True, "escalated": escalated}


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


@admin.get("/logs", response_model=S.LogsPage)
def logs(limit: int = 20, offset: int = 0, date_from: str | None = None, date_to: str | None = None,
         answerable: bool | None = None, feedback: str | None = None, q: str | None = None,
         svc: Services = Depends(get_services)) -> dict[str, Any]:
    """상담 로그 목록(PRD §33) — 기간/응답 상태/피드백/검색어 필터 + 페이징."""
    f = _log_filters(date_from, date_to, answerable, feedback, q)
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return {"items": svc.db.list_turn_logs(limit=limit, offset=offset, **f), "total": svc.db.count_turn_logs(**f),
            "limit": limit, "offset": offset}


@admin.get("/logs/export.csv")
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


@admin.get("/logs/{message_id}", response_model=S.TurnLogOut)
def log_detail(message_id: str, svc: Services = Depends(get_services)) -> dict[str, Any]:
    row = svc.db.get_turn_log(message_id)
    if not row:
        raise HTTPException(404, "log not found")
    return row


# ── knowledge ───────────────────────────────────────────────────
@admin.get("/knowledge", response_model=list[S.DocumentOut])
def list_knowledge(svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    return svc.db.list_documents()


@admin.post("/knowledge", response_model=S.DocumentOut, status_code=201)
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
    tags: str | None = Form(default=None),          # 쉼표 구분 (예: "환불,VIP")
    access_level: str | None = Form(default=None),  # public | internal
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
            raise HTTPException(413, "파일이 너무 큽니다 (최대 10MB)")
        if name.lower().endswith(".pdf"):
            text = _pdf_to_text(raw)                     # PDF → 텍스트 추출(PRD §12: 가급적 Markdown 변환 권장)
            if not text.strip():
                raise HTTPException(400, "PDF에서 텍스트를 추출하지 못했습니다. 스캔본이면 텍스트 레이어가 필요합니다.")
        else:
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
    extra: dict[str, Any] = {}
    if tags and tags.strip():
        extra["tags"] = json.dumps([t.strip() for t in tags.split(",") if t.strip()], ensure_ascii=False)
    if access_level in ("public", "internal"):
        extra["access_level"] = access_level
    if extra:
        svc.db.update_document(doc["id"], **extra)
        doc = svc.db.get_document(doc["id"])
    if sync:
        doc = svc.indexer.index(doc["id"])
    else:
        svc.indexer.index_async(doc["id"])
    return doc


@admin.get("/knowledge/{doc_id}", response_model=S.DocumentDetail)
def get_knowledge(doc_id: str, svc: Services = Depends(get_services)) -> dict[str, Any]:
    doc = svc.db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    return doc


@admin.get("/knowledge/{doc_id}/chunks", response_model=list[S.ChunkOut])
def get_chunks(doc_id: str, svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    if not svc.db.get_document(doc_id):
        raise HTTPException(404, "document not found")
    return svc.db.list_chunks(doc_id)


@admin.patch("/knowledge/{doc_id}", response_model=S.DocumentOut)
def patch_knowledge(doc_id: str, patch: S.DocumentPatch, svc: Services = Depends(get_services)) -> dict[str, Any]:
    if not svc.db.get_document(doc_id):
        raise HTTPException(404, "document not found")
    fields = {k: v for k, v in patch.model_dump().items() if v is not None}
    if "tags" in fields:
        tags = [t.strip() for t in fields["tags"] if t and t.strip()]
        fields["tags"] = json.dumps(tags, ensure_ascii=False) if tags else None
    svc.db.update_document(doc_id, **fields)
    svc.store.invalidate()
    return svc.db.get_document(doc_id)  # type: ignore[return-value]


@admin.delete("/knowledge/{doc_id}", status_code=204)
def delete_knowledge(doc_id: str, svc: Services = Depends(get_services)) -> None:
    if not svc.db.delete_document(doc_id):
        raise HTTPException(404, "document not found")
    svc.store.invalidate()


@admin.post("/knowledge/{doc_id}/reindex", response_model=S.DocumentOut)
def reindex_knowledge(doc_id: str, sync: bool = False, svc: Services = Depends(get_services)) -> dict[str, Any]:
    doc = svc.db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if sync:
        return svc.indexer.index(doc_id)
    svc.db.update_document(doc_id, processing_status="uploaded", error_message=None)
    svc.indexer.index_async(doc_id)
    return svc.db.get_document(doc_id)  # type: ignore[return-value]


@admin.get("/admin/me")
def admin_me() -> dict[str, Any]:
    """토큰 검증용(프론트 로그인 게이트). 401이면 토큰 불일치."""
    return {"ok": True, "role": "admin"}


@admin.get("/admin/settings")
def admin_settings(svc: Services = Depends(get_services)) -> dict[str, Any]:
    """런타임 설정 스냅샷(읽기 전용, 비밀 제외) — /admin/settings 화면."""
    st = svc.settings
    return {
        "llm": {"provider": svc.llm.name, "anthropic_model": st.anthropic_model, "openai_model": st.openai_model,
                 "effort": st.llm_effort, "max_tokens": st.llm_max_tokens},
        "embedding": {"provider": svc.embedder.name, "voyage_model": st.voyage_model,
                       "openai_model": st.openai_embedding_model},
        "retrieval": {"mode": svc.retriever.mode, "top_k": st.top_k, "threshold": st.score_threshold,
                       "candidates": st.retrieval_candidates, "rrf_k": st.rrf_k, "dense_weight": st.dense_weight,
                       "multi_query": st.multi_query, "multi_query_n": st.multi_query_n, "reranker": svc.reranker.name,
                       "max_context_chunks": st.max_context_chunks},
        "chunking": {"max_chars": st.chunk_max_chars, "overlap_chars": st.chunk_overlap_chars},
        "storage": {"db_backend": svc.db.name, "indexed_chunks": svc.store.size},
        "security": {"admin_auth": bool(st.admin_token), "cors_origins": st.cors_origin_list,
                      "cors_origin_regex": st.cors_origin_regex},
        "no_answer_message": NO_ANSWER_MESSAGE,
    }


# ── stats (PRD §34 대시보드 · §35 미답변 분석) ─────────────────────
def _range(date_from: str | None, date_to: str | None, tz_offset: int, default_days: int) -> ST.Range:
    try:
        return ST.make_range(date_from, date_to, tz_offset, default_days)
    except ValueError as e:
        raise HTTPException(422, f"invalid date: {e}") from e


@admin.get("/stats/overview")
def stats_overview(date_from: str | None = None, date_to: str | None = None, tz_offset: int = 540,
                   svc: Services = Depends(get_services)) -> dict[str, Any]:
    """대시보드 KPI·일별 추이·카테고리·피드백·주요 질문 (기본 최근 7일, KST)."""
    return ST.dashboard(svc.db, _range(date_from, date_to, tz_offset, 7))


@admin.get("/stats/unanswered")
def stats_unanswered(date_from: str | None = None, date_to: str | None = None, tz_offset: int = 540, top_n: int = 10,
                     svc: Services = Depends(get_services)) -> dict[str, Any]:
    """미답변 분석: TOP N·추이·카테고리·개선 추천·처리 상태 (기본 최근 7일)."""
    return ST.unanswered(svc.db, _range(date_from, date_to, tz_offset, 7), top_n=max(1, min(top_n, 50)))


@admin.patch("/stats/unanswered/{question_key}")
def patch_unanswered(question_key: str, body: S.UnansweredReviewPatch, svc: Services = Depends(get_services)) -> dict[str, Any]:
    return svc.db.upsert_unanswered_review(question_key, body.status, body.note)


# ── inquiries (PRD §43 상담원 연결 / 문의 남기기) ──────────────────
@router.post("/inquiries", response_model=S.InquiryOut, status_code=201)
def create_inquiry(body: S.InquiryCreate, svc: Services = Depends(get_services)) -> dict[str, Any]:
    return svc.db.add_inquiry(conversation_id=body.conversation_id, message_id=body.message_id, kind=body.kind,
                              contact=(body.contact or "").strip() or None, content=body.content.strip())


@admin.get("/inquiries", response_model=list[S.InquiryOut])
def list_inquiries(status: str | None = None, limit: int = 100, svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    if status not in (None, "open", "done"):
        raise HTTPException(422, "status must be open|done")
    return svc.db.list_inquiries(limit=max(1, min(limit, 500)), status=status)


@admin.patch("/inquiries/{inquiry_id}", response_model=dict)
def patch_inquiry(inquiry_id: str, body: S.InquiryPatch, svc: Services = Depends(get_services)) -> dict[str, Any]:
    if not svc.db.set_inquiry_status(inquiry_id, body.status):
        raise HTTPException(404, "inquiry not found")
    return {"ok": True}


# ── categories / tags (N4 분류 관리) ────────────────────────────
@admin.get("/categories")
def list_categories(svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    return svc.db.list_categories()


@admin.post("/categories", status_code=201)
def create_category(body: S.CategoryIn, svc: Services = Depends(get_services)) -> dict[str, Any]:
    return svc.db.upsert_category(body.name.strip(), (body.description or "").strip() or None)


@admin.patch("/categories/{name}")
def patch_category(name: str, body: S.CategoryPatch, svc: Services = Depends(get_services)) -> dict[str, Any]:
    changed = 0
    if body.new_name and body.new_name.strip() and body.new_name.strip() != name:
        changed = svc.db.rename_category(name, body.new_name.strip())
        name = body.new_name.strip()
    if body.description is not None:
        svc.db.upsert_category(name, body.description.strip() or None)
    svc.store.invalidate()
    return {"ok": True, "name": name, "documents_updated": changed}


@admin.delete("/categories/{name}")
def delete_category(name: str, reassign_to: str | None = None, svc: Services = Depends(get_services)) -> dict[str, Any]:
    changed = svc.db.delete_category(name, (reassign_to or "").strip() or None)
    svc.store.invalidate()
    return {"ok": True, "documents_updated": changed}


@admin.get("/tags")
def list_tags(svc: Services = Depends(get_services)) -> list[dict[str, Any]]:
    return svc.db.list_tags()


@admin.patch("/tags/{name}")
def rename_tag(name: str, body: S.TagPatch, svc: Services = Depends(get_services)) -> dict[str, Any]:
    return {"ok": True, "documents_updated": svc.db.rename_tag(name, body.new_name.strip())}


@admin.delete("/tags/{name}")
def delete_tag(name: str, svc: Services = Depends(get_services)) -> dict[str, Any]:
    return {"ok": True, "documents_updated": svc.db.delete_tag(name)}


# ── monitoring (N6) ──────────────────────────────────────────────
@admin.get("/admin/monitoring")
def monitoring(svc: Services = Depends(get_services)) -> dict[str, Any]:
    """색인 작업 현황 + 시스템 상태 — /admin/monitoring 화면."""
    from datetime import datetime

    def _elapsed(d: dict[str, Any]) -> float | None:
        if not d.get("indexed_at") or not d.get("created_at"):
            return None
        try:
            return round((datetime.fromisoformat(d["indexed_at"]) - datetime.fromisoformat(d["created_at"])).total_seconds(), 1)
        except ValueError:
            return None

    docs = svc.db.list_documents()
    jobs = [{
        "id": d["id"], "title": d["title"], "document_id": d["document_id"], "category": d.get("category"),
        "processing_status": d["processing_status"], "error_message": d.get("error_message"),
        "chunk_count": d.get("chunk_count", 0), "created_at": d["created_at"], "indexed_at": d.get("indexed_at"),
        "elapsed_s": _elapsed(d), "status": d["status"], "access_level": d.get("access_level", "public"),
    } for d in docs]
    summary = {"total": len(docs),
               "indexed": sum(1 for d in docs if d["processing_status"] == "indexed"),
               "processing": sum(1 for d in docs if d["processing_status"] not in ("indexed", "error")),
               "error": sum(1 for d in docs if d["processing_status"] == "error")}
    return {"summary": summary, "jobs": jobs, "system": svc.health(),
            "uptime_s": int(_time.time() - svc.started_at),
            "open_inquiries": len(svc.db.list_inquiries(limit=500, status="open"))}


@admin.get("/admin/weather")
def weather_test(region: str = "서울", svc: Services = Depends(get_services)) -> dict[str, Any]:
    """날씨 연동 확인용(관리자). KMA_SERVICE_KEY 미설정이면 503."""
    if svc.weather is None:
        raise HTTPException(503, "KMA_SERVICE_KEY 미설정 — 날씨 기능 비활성")
    report = svc.weather.get_report(region)
    if report is None:
        raise HTTPException(502, "기상청 API 응답 실패(키 승인 여부/네트워크 확인)")
    return {"region": report.region, "observed_at": report.observed_at, "now": report.now,
            "today": report.today, "tomorrow": report.tomorrow, "context_text": report.as_context_text()}


# ── search test (관리자용 검색 디버그, PRD §32) ───────────────────
@admin.post("/search/test", response_model=S.SearchTestResponse)
def search_test(req: S.SearchTestRequest, svc: Services = Depends(get_services)) -> dict[str, Any]:
    """관리자 검색 테스트: 정규화 → (선택) Rewrite → 검색 → 임계값/정답 문서 기준 평가."""
    normalized = " ".join(req.query.split())
    history = [{"role": "user", "content": req.previous_query}] if req.previous_query else []
    search_query = svc.orchestrator.build_search_query(normalized, history)
    rewritten = search_query if search_query != normalized else None
    threshold = svc.settings.score_threshold

    access = None if req.include_internal else {"public"}
    r = svc.orchestrator.search(search_query, use_multi_query=req.use_multi_query, top_k=req.top_k, access_levels=access)
    results = []
    for i, c in enumerate(r.chunks):
        results.append({
            **c.as_source(),
            "rank": i + 1,
            "content": c.content,
            "passes_threshold": c.score >= threshold,
            "bm25_score": c.bm25_score,
            "rerank_score": c.rerank_score,
            "fused_score": c.fused_score,
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
        "multi_queries": r.queries[1:],
        "retrieval_mode": r.mode,
        "reranker": svc.reranker.name,
        "threshold": threshold,
        "passes_threshold": bool(r.chunks) and r.top_score >= threshold,
        "top_score": round(float(r.top_score), 4),
        "elapsed_ms": r.elapsed_ms,
        "embedding_provider": svc.embedder.name,
        "indexed_chunks": svc.store.size,
        "hit": hit,
        "results": results,
    }


def _pdf_to_text(raw: bytes) -> str:
    import io

    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"PDF 파싱 실패: {e}") from e
    pages = []
    for pg in reader.pages[:200]:
        try:
            pages.append(pg.extract_text() or "")
        except Exception:  # noqa: BLE001 — 일부 페이지 실패는 건너뜀
            pages.append("")
    return "\n\n".join(pages)


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
