"""PostgreSQL 어댑터 검증 — `TEST_DATABASE_URL`이 설정된 경우에만 실행된다.

예)  TEST_DATABASE_URL=postgresql://localhost/rag_chatbot_test .venv/bin/python -m pytest -q tests/test_postgres.py
     (Supabase Session Pooler URI도 동일하게 사용 가능)
테스트 시작 시 대상 DB의 테이블을 DROP 후 재생성하므로 전용 DB를 사용할 것.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import NO_ANSWER_MESSAGE

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_docs"

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL 미설정")


@pytest.fixture()
def pg_client(monkeypatch):
    from app.core.db_postgres import PostgresDatabase

    PostgresDatabase(TEST_DATABASE_URL).reset_schema()

    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("LLM_PROVIDER", "extractive")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("KMA_SERVICE_KEY", "")
    from app.core.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c
        c.app.state.services.db.close()
    get_settings.cache_clear()


@pytest.fixture()
def pg_seeded(pg_client):
    for p in sorted(SAMPLE_DIR.iterdir()):
        r = pg_client.post("/api/knowledge", data={"sync": "true"}, files={"file": (p.name, p.read_bytes())})
        assert r.status_code == 201, r.text
        assert r.json()["processing_status"] == "indexed", r.json()
    return pg_client


def test_health_reports_postgres(pg_client):
    h = pg_client.get("/api/health").json()
    assert h["db_backend"] == "postgres"
    assert h["db_ok"] is True
    assert h["status"] == "ok"


def test_upload_chunks_and_delete(pg_seeded):
    docs = pg_seeded.get("/api/knowledge").json()
    assert len(docs) == 3
    doc = docs[0]
    chunks = pg_seeded.get(f"/api/knowledge/{doc['id']}/chunks").json()
    assert chunks and all(c["content"] for c in chunks)
    assert pg_seeded.get("/api/health").json()["indexed_chunks"] > 0
    r = pg_seeded.delete(f"/api/knowledge/{doc['id']}")
    assert r.status_code == 204
    assert len(pg_seeded.get("/api/knowledge").json()) == 2


def test_grounded_answer_with_sources(pg_seeded):
    r = pg_seeded.post("/api/chat", json={"message": "환불은 며칠 이내에 신청해야 하나요?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answerable"] is True
    assert body["sources"], body
    assert body["answer"] != NO_ANSWER_MESSAGE

    # 같은 대화의 후속 메시지가 user/assistant 순서대로 저장되는지 (seq 정렬)
    cid = body["conversation_id"]
    r2 = pg_seeded.post("/api/chat", json={"message": "배송비는요?", "conversation_id": cid})
    assert r2.status_code == 200
    msgs = pg_seeded.get(f"/api/conversations/{cid}").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert "seq" not in msgs[0]


def test_fail_closed(pg_seeded):
    r = pg_seeded.post("/api/chat", json={"message": "양자역학의 슈뢰딩거 방정식을 유도해줘"})
    body = r.json()
    assert body["answerable"] is False
    assert body["answer"] == NO_ANSWER_MESSAGE
    assert body["sources"] == []


def test_feedback_and_logs(pg_seeded):
    body = pg_seeded.post("/api/chat", json={"message": "환불 절차 알려줘"}).json()
    r = pg_seeded.post("/api/feedback", json={"message_id": body["message_id"], "rating": "negative", "reason": "incorrect"})
    assert r.status_code == 200
    logs = pg_seeded.get("/api/logs").json()["items"]
    mine = [l for l in logs if l["message_id"] == body["message_id"]]
    assert mine and mine[0]["feedback"] == "negative"
    assert isinstance(mine[0]["retrieved"], list)


def test_inactive_document_not_searchable(pg_seeded):
    docs = pg_seeded.get("/api/knowledge").json()
    for d in docs:
        pg_seeded.patch(f"/api/knowledge/{d['id']}", json={"status": "inactive"})
    assert pg_seeded.get("/api/health").json()["indexed_chunks"] == 0
    body = pg_seeded.post("/api/chat", json={"message": "환불은 며칠 이내에 신청해야 하나요?"}).json()
    assert body["answerable"] is False
