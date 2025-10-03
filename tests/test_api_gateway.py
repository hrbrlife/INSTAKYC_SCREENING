import importlib
import json
import pathlib
import sys

import redis.asyncio as redis
from fakeredis import aioredis as fakeredis
from fastapi.testclient import TestClient
import httpx


def create_client(monkeypatch, httpx_mock, *, proxy_url: str | None = "http://proxy/dispatch"):
    monkeypatch.setenv("SANCTIONS_URL", "http://sanctions")
    monkeypatch.setenv("CRYPTO_URL", "http://crypto")
    monkeypatch.setenv("WEB_URL", "http://web")
    monkeypatch.setenv("API_KEY", "testkey")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    if proxy_url:
        monkeypatch.setenv("HTTP_OUT_PROXY_URL", proxy_url)
    else:
        monkeypatch.delenv("HTTP_OUT_PROXY_URL", raising=False)
    monkeypatch.setenv(
        "OTP_DELIVERY_DEFAULT_URL", "<?https://sms.default.local/send?>"
    )

    fake_redis = fakeredis.FakeRedis()
    monkeypatch.setattr(redis, "from_url", lambda *a, **k: fake_redis)

    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
    import api_gateway.config as config
    importlib.reload(config)
    import api_gateway.http_out as http_out
    importlib.reload(http_out)
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


def test_identity_otp_uses_powerbox(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)

    def callback(request):
        payload = json.loads(request.content.decode())
        assert payload["url"] == "https://sms.provider.local/send"
        assert payload["method"] == "POST"
        assert payload["json"] == {
            "destination": "+15555550123",
            "code": "123456",
            "metadata": {"channel": "sms"},
        }
        return httpx.Response(200, json={"accepted": True})

    httpx_mock.add_callback(
        callback,
        method="POST",
        url="http://proxy/dispatch",
    )

    resp = client.post(
        "/identity/otp",
        headers={"X-API-KEY": "testkey"},
        json={
            "destination": "+15555550123",
            "code": "123456",
            "delivery_url": "<?https://sms.provider.local/send?>",
            "metadata": {"channel": "sms"},
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "status_code": 200,
        "body": {"accepted": True},
        "status": "sent",
    }


def test_identity_otp_missing_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock, proxy_url=None)

    resp = client.post(
        "/identity/otp",
        headers={"X-API-KEY": "testkey"},
        json={"destination": "user@example.com", "code": "123", "delivery_url": "<?https://otp.example/send?>"},
    )

    assert resp.status_code == 500


def test_admin_http_out_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)

    def callback(request):
        payload = json.loads(request.content.decode())
        assert payload["url"] == "https://api.example.com/audit"
        assert payload["method"] == "GET"
        return httpx.Response(200, json={"ok": True})

    httpx_mock.add_callback(
        callback,
        method="POST",
        url="http://proxy/dispatch",
    )

    resp = client.post(
        "/admin/http-out",
        headers={"X-API-KEY": "testkey"},
        json={
            "url": "<?https://api.example.com/audit?>",
            "method": "GET",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status_code": 200, "body": {"ok": True}}
