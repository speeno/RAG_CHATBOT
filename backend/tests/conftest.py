import os
from pathlib import Path

import pytest

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_docs"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """오프라인 프로바이더(extractive + hash)로 구성된 API 테스트 클라이언트 (임시 DB)."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_PROVIDER", "extractive")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("KMA_SERVICE_KEY", "")   # .env 의 실제 키가 테스트로 새지 않도록
    from app.core.config import get_settings
    get_settings.cache_clear()
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture()
def seeded(client):
    for p in sorted(SAMPLE_DIR.iterdir()):
        r = client.post("/api/knowledge", data={"sync": "true"}, files={"file": (p.name, p.read_bytes())})
        assert r.status_code == 201, r.text
        assert r.json()["processing_status"] == "indexed", r.json()
    return client
