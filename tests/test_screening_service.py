import importlib
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, Optional

import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from screening_service import config


DEFAULT_DATASET = (
    """id,name,datasets,topics,countries,birth_date\n"""
    "1,John Doe,ofac|eu,politically exposed person,US,1980-01-01\n"
    "2,Jane Smith,ofac,terrorism,GB,1975-05-05\n"""
)


@dataclass
class _QueuedResponse:
    status_code: int
    content: bytes
    json_data: Optional[object]
    url: str

    def raise_for_status(self) -> None:
        if 400 <= self.status_code:
            request = httpx.Request("GET", self.url)
            response = httpx.Response(
                self.status_code, request=request, content=self.content
            )
            raise httpx.HTTPStatusError(
                "HTTP error", request=request, response=response
            )

    def json(self) -> object:
        if self.json_data is not None:
            return self.json_data
        return json.loads(self.content.decode("utf-8"))


class _HttpxMock:
    def __init__(self) -> None:
        self._queue: list[_QueuedResponse] = []
        self.assert_all_responses_were_requested = True

    def add_response(
        self,
        *,
        url: str,
        text: Optional[str] = None,
        json: Optional[object] = None,
        status_code: int = 200,
    ) -> None:
        if text is not None and json is not None:
            raise ValueError("Specify either text or json, not both")
        if text is None and json is None:
            raise ValueError("A text or json payload is required")
        if text is not None:
            content = text.encode("utf-8")
            json_data = None
        else:
            response = httpx.Response(200, json=json)  # type: ignore[arg-type]
            content = response.content
            json_data = json
        self._queue.append(
            _QueuedResponse(
                status_code=status_code,
                content=content,
                json_data=json_data,
                url=url,
            )
        )

    def next_response(self, url: str) -> _QueuedResponse:
        if not self._queue:
            raise AssertionError(f"No queued httpx responses for request to {url}")
        response = self._queue.pop(0)
        response.url = url
        return response

    def verify(self) -> None:
        if self.assert_all_responses_were_requested and self._queue:
            raise AssertionError("Unconsumed httpx responses remain in queue")


class _FakeSyncClient:
    def __init__(self, mock: _HttpxMock) -> None:
        self._mock = mock

    def __enter__(self) -> "_FakeSyncClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str, *args, **kwargs):
        return _FakeResponse(self._mock.next_response(url))


class _FakeAsyncClient:
    def __init__(self, mock: _HttpxMock) -> None:
        self._mock = mock

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, *args, **kwargs):
        return _FakeResponse(self._mock.next_response(url))


class _FakeResponse:
    def __init__(self, queued: _QueuedResponse) -> None:
        self._queued = queued
        self.status_code = queued.status_code
        self.content = queued.content

    def raise_for_status(self) -> None:
        self._queued.raise_for_status()

    def json(self) -> object:
        return self._queued.json()


def _set_common_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("SANCTIONS_DATA_URL", "https://example.test/sanctions.csv")
    monkeypatch.setenv("TRON_ACCOUNT_URL", "https://tron.test/account")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


@pytest.fixture()
def httpx_mock(monkeypatch) -> Iterable[_HttpxMock]:
    mock = _HttpxMock()

    def fake_client(*args, **kwargs):
        return _FakeSyncClient(mock)

    def fake_async_client(*args, **kwargs):
        return _FakeAsyncClient(mock)

    monkeypatch.setattr(httpx, "Client", fake_client)
    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)

    yield mock

    mock.verify()


@contextmanager
def build_client(
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: _HttpxMock,
    tmp_path: Path,
    dataset_text: Optional[str] = None,
    dataset_responses: Optional[list[dict]] = None,
):
    _set_common_env(monkeypatch, tmp_path)
    if dataset_responses:
        for response_kwargs in dataset_responses:
            httpx_mock.add_response(
                url="https://example.test/sanctions.csv", **response_kwargs
            )
    else:
        httpx_mock.add_response(
            url="https://example.test/sanctions.csv",
            text=dataset_text or DEFAULT_DATASET,
        )

    config.get_settings.cache_clear()
    module = importlib.import_module("screening_service.main")
    importlib.reload(module)

    httpx_mock.assert_all_responses_were_requested = False

    with TestClient(module.app) as test_client:
        setattr(test_client, "httpx_mock", httpx_mock)
        setattr(test_client, "module", module)
        yield test_client


@pytest.fixture()
def client(monkeypatch, httpx_mock, tmp_path) -> Iterable[TestClient]:
    with build_client(monkeypatch, httpx_mock, tmp_path) as test_client:
        yield test_client


def test_health_endpoint(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["sanctions"]["records"] == 2
    assert data["sanctions"]["status"] == "ready"


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
    assert data["matches"][0]["birth_dates"] == ["1980-01-01"]


def test_web_reputation(client, monkeypatch):
    def fake_search(query: str):
        return [
            SimpleNamespace(
                title="Test", url="https://news", published="2024", source="News", snippet="Body"
            )
        ]

    monkeypatch.setattr(client.module.web_reputation, "search", fake_search)

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
            "privateKey": "super-secret",
            "ownerPermission": {"keys": [{"address": "abc", "privateKey": "hidden"}]},
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
    assert data["raw"]["totalTransactionCount"] == 1200
    assert "privateKey" not in data["raw"]
    assert data["raw"]["ownerPermission"]["keys"][0]["address"] == "abc"
    assert "privateKey" not in data["raw"]["ownerPermission"]["keys"][0]


def test_sanctions_search_filters_by_dob(monkeypatch, httpx_mock, tmp_path):
    dataset = (
        """id,name,datasets,topics,countries,birth_date\n"""
        "1,John Doe,ofac|eu,politically exposed person,US,1980-01-01\n"
        "2,John Doe,ofac,terrorism,US,1975-05-05\n"""
    )
    with build_client(monkeypatch, httpx_mock, tmp_path, dataset_text=dataset) as test_client:
        response = test_client.post(
            "/sanctions/search",
            json={"query": "John Doe", "date_of_birth": "1980-01-01"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["matches"][0]["name"] == "John Doe"
        assert data["matches"][0]["birth_dates"] == ["1980-01-01"]


def test_sanctions_search_returns_503_when_dataset_unavailable(
    monkeypatch, httpx_mock, tmp_path
):
    with build_client(
        monkeypatch,
        httpx_mock,
        tmp_path,
        dataset_responses=[{"status_code": 500, "text": ""}, {"status_code": 500, "text": ""}],
    ) as test_client:
        response = test_client.post(
            "/sanctions/search",
            json={"query": "John"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 503
        assert "Failed to download sanctions dataset" in response.json()["detail"]


def test_web_reputation_failure(monkeypatch, httpx_mock, tmp_path):
    with build_client(monkeypatch, httpx_mock, tmp_path) as test_client:
        def failing_search(_: str):
            raise test_client.module.WebReputationError("boom")

        monkeypatch.setattr(test_client.module.web_reputation, "search", failing_search)

        response = test_client.post(
            "/web/reputation",
            json={"query": "Example"},
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 503
        assert "boom" in response.json()["detail"]
