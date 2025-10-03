import importlib
import json
import pathlib
import sys

import redis.asyncio as redis
from fakeredis import aioredis as fakeredis
from fastapi.testclient import TestClient


def create_client(monkeypatch, httpx_mock, api_keys=None):
    if api_keys is None:
        api_keys = {
            "testkey": [
                "sanctions:read",
                "sanctions:search",
                "sanctions:match",
                "tasks:enqueue",
                "tasks:read",
                "crypto:read",
                "web:read",
                "metrics:read",
            ]
        }
    monkeypatch.setenv("SANCTIONS_URL", "http://sanctions")
    monkeypatch.setenv("CRYPTO_URL", "http://crypto")
    monkeypatch.setenv("WEB_URL", "http://web")
    if isinstance(api_keys, str):
        monkeypatch.setenv("API_KEYS", api_keys)
    else:
        monkeypatch.setenv("API_KEYS", json.dumps(api_keys))
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    fake_redis = fakeredis.FakeRedis()
    monkeypatch.setattr(redis, "from_url", lambda *a, **k: fake_redis)

    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
    import api_gateway.main as main
    importlib.reload(main)
    client = TestClient(main.app)
    return client


def test_sanction_entity_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    httpx_mock.add_response(url="http://sanctions/entities/123", json={"id": "123"})

    resp = client.get("/sanctions/entities/123", headers={"X-API-KEY": "testkey"})
    assert resp.status_code == 200
    assert resp.json() == {"id": "123"}


def test_sanctions_search_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    httpx_mock.add_response(url="http://sanctions/search?q=john", json={"results": []})

    resp = client.get(
        "/sanctions/search",
        headers={"X-API-KEY": "testkey"},
        params={"q": "john"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"results": []}


def test_sanctions_match_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    httpx_mock.add_response(url="http://sanctions/match", json={"matches": []})

    payload = {"queries": [{"query": "john"}]}
    resp = client.post(
        "/sanctions/match",
        headers={"X-API-KEY": "testkey"},
        json=payload,
    )
    assert resp.status_code == 200
    assert resp.json() == {"matches": []}


def test_crypto_health_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    httpx_mock.add_response(url="http://crypto/health", json="READY")

    resp = client.get("/crypto/health", headers={"X-API-KEY": "testkey"})
    assert resp.status_code == 200
    assert resp.json() == "READY"


def test_web_search_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    httpx_mock.add_response(url="http://web/search?q=acme", json={"articles": []})

    resp = client.get(
        "/web/search",
        headers={"X-API-KEY": "testkey"},
        params={"q": "acme"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"articles": []}


def test_task_queue(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)

    resp = client.post("/tasks", headers={"X-API-KEY": "testkey"}, json={"foo": "bar"})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    assert resp.json()["status"] == "queued"

    resp = client.get(f"/tasks/{task_id}", headers={"X-API-KEY": "testkey"})
    assert resp.status_code == 200
    assert resp.json() == {"task_id": task_id, "status": "queued"}


def test_auth_failure(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)

    resp = client.get("/crypto/health")
    assert resp.status_code == 422  # missing header triggers validation error

    resp = client.get("/crypto/health", headers={"X-API-KEY": "wrong"})
    assert resp.status_code == 401


def test_scope_enforced(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock, api_keys={"limited": ["sanctions:read"]})
    resp = client.get(
        "/sanctions/search",
        headers={"X-API-KEY": "limited"},
        params={"q": "acme"},
    )
    assert resp.status_code == 403


def test_metrics_requires_scope(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    resp = client.get("/metrics", headers={"X-API-KEY": "testkey"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")

    client = create_client(monkeypatch, httpx_mock, api_keys={"limited": ["web:read"]})
    resp = client.get("/metrics", headers={"X-API-KEY": "limited"})
    assert resp.status_code == 403


def test_healthz_returns_ok(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
