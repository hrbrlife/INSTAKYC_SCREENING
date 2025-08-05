import importlib
import pathlib
import sys

from fastapi.testclient import TestClient


def create_client(monkeypatch, httpx_mock):
    monkeypatch.setenv("SANCTIONS_URL", "http://sanctions")
    monkeypatch.setenv("CRYPTO_URL", "http://crypto")
    monkeypatch.setenv("WEB_URL", "http://web")
    monkeypatch.setenv("API_KEY", "testkey")

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


def test_crypto_health_proxy(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)
    httpx_mock.add_response(url="http://crypto/health", json="READY")

    resp = client.get("/crypto/health", headers={"X-API-KEY": "testkey"})
    assert resp.status_code == 200
    assert resp.json() == "READY"


def test_auth_failure(monkeypatch, httpx_mock):
    client = create_client(monkeypatch, httpx_mock)

    resp = client.get("/crypto/health")
    assert resp.status_code == 422  # missing header triggers validation error

    resp = client.get("/crypto/health", headers={"X-API-KEY": "wrong"})
    assert resp.status_code == 401
