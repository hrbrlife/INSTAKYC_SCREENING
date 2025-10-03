import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from screening_service import config


@pytest.fixture()
def client(monkeypatch, httpx_mock, tmp_path) -> Iterable[TestClient]:
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("SANCTIONS_DATA_URL", "https://example.test/sanctions.csv")
    monkeypatch.setenv("TRON_ACCOUNT_URL", "https://tron.test/account")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    dataset = """id,name,datasets,topics,countries\n1,John Doe,ofac|eu,politically exposed person,US\n2,Jane Smith,ofac,terrorism,GB\n"""
    httpx_mock.add_response(url="https://example.test/sanctions.csv", text=dataset)

    config.get_settings.cache_clear()
    module = importlib.import_module("screening_service.main")
    importlib.reload(module)

    httpx_mock.assert_all_responses_were_requested = False

    with TestClient(module.app) as test_client:
        setattr(test_client, "httpx_mock", httpx_mock)
        yield test_client


def test_health_endpoint(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["sanctions"]["records"] == 2


def test_sanctions_search(client):
    response = client.post(
        "/sanctions/search",
        json={"query": "John"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["matches"][0]["name"] == "John Doe"


def test_web_reputation(client, monkeypatch):
    from screening_service import main as module

    def fake_search(query: str):
        return [
            SimpleNamespace(
                title="Test", url="https://news", published="2024", source="News", snippet="Body"
            )
        ]

    monkeypatch.setattr(module.web_reputation, "search", fake_search)

    response = client.post(
        "/web/reputation",
        json={"query": "Example"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["title"] == "Test"


def test_tron_reputation(client):
    address = "TMwFHYXLJaRUPeW6421aqXL4ZEzPRFGkGT"
    client.httpx_mock.add_response(
        url=f"https://tron.test/account?address={address}",
        json={
            "totalTransactionCount": 1200,
            "balance": "250000000000",
            "transactions_in": [{}] * 5,
            "transactions_out": [{}] * 10,
            "trc20token_balances": [{"amount": 150000}],
        },
    )
    response = client.post(
        "/tron/reputation",
        json={"address": address},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["risk"] == "medium"
    assert data["stats"]["transaction_count"] == 1200
