import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_case_persists_and_lists(client):
    created = client.post("/api/v1/cases", json={"title": "Caso sintético"})
    assert created.status_code == 201
    case = created.json()
    assert case["created_at"].endswith("Z")
    assert client.get(f"/api/v1/cases/{case['id']}").json() == case
    assert client.get("/api/v1/cases").json()["total"] == 1
    assert client.get("/api/v1/cases?limit=101").status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "   "},
        {"title": "OK?", "timezone": "Invented/Zone"},
    ],
)
def test_invalid_case(client, payload):
    assert client.post("/api/v1/cases", json=payload).status_code == 422
    assert client.get("/api/v1/cases").json()["total"] == 0


def test_missing_case(client):
    assert client.get("/api/v1/cases/00000000-0000-0000-0000-000000000001").status_code == 404


def test_ollama_offline_is_not_analysis_failure(client, monkeypatch):
    async def offline(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx.AsyncClient, "get", offline)
    data = client.get("/api/v1/system").json()
    assert data["ai_status"] == "unavailable"
    assert data["analysis_available"] is True
    assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize("url", ["https://ollama.com", "http://example.com:11434"])
def test_remote_ai_rejected(url):
    with pytest.raises(ValueError):
        Settings(ollama_url=url)


def test_readiness_requires_migrated_schema(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'empty.db'}"))
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_UNAVAILABLE"
