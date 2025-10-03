from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import time
from typing import Dict, Iterable, Optional, Set

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import PlainTextResponse
import httpx
import redis.asyncio as redis
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import uuid


class Settings(BaseSettings):
    """Runtime configuration for the API gateway.

    Default values are aligned with the docker-compose stack so that
    the application can boot without manually exporting environment
    variables during development. They can be overridden via environment
    variables or a local ``.env`` file.
    """

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    sanctions_url: str = "http://sanctions_core:8000"
    crypto_url: str = "http://graphsense_api:8000"
    web_url: str = "http://puppeteer_srv:7000"
    redis_url: str = "redis://localhost:6379/0"
    redis_url_file: Optional[str] = None

    api_keys: Dict[str, Set[str]] = Field(
        default_factory=lambda: {
            "change_me": {
                "sanctions:read",
                "sanctions:search",
                "sanctions:match",
                "tasks:enqueue",
                "tasks:read",
                "crypto:read",
                "web:read",
                "metrics:read",
            }
        }
    )
    api_keys_file: Optional[str] = None

    sanctions_token: Optional[str] = None
    sanctions_token_file: Optional[str] = None
    sanctions_token_header: str = "Authorization"

    crypto_token: Optional[str] = None
    crypto_token_file: Optional[str] = None
    crypto_token_header: str = "Authorization"

    web_token: Optional[str] = "change_me_worker"
    web_token_file: Optional[str] = None
    web_token_header: str = "X-Service-Token"

    @field_validator("api_keys", mode="before")
    @classmethod
    def parse_api_keys_field(cls, value: object) -> object:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, (list, tuple, set)):
            raise ValueError("API_KEYS must be provided as a mapping or delimited string")
        return cls._parse_api_key_string(str(value))

    def model_post_init(self, __context: Dict[str, object]) -> None:
        api_keys = self.api_keys
        if self.api_keys_file:
            api_keys = self._parse_api_keys_file(self.api_keys_file)
        object.__setattr__(self, "api_keys", self._normalise_scope_mapping(api_keys))

        redis_url = self._resolve_secret(self.redis_url, self.redis_url_file)
        object.__setattr__(self, "redis_url", redis_url or self.redis_url)

        object.__setattr__(
            self,
            "sanctions_token",
            self._resolve_secret(self.sanctions_token, self.sanctions_token_file),
        )
        object.__setattr__(
            self,
            "crypto_token",
            self._resolve_secret(self.crypto_token, self.crypto_token_file),
        )
        object.__setattr__(
            self,
            "web_token",
            self._resolve_secret(self.web_token, self.web_token_file),
        )

    @staticmethod
    def _normalise_scope_mapping(raw: Dict[str, Iterable[str]]) -> Dict[str, Set[str]]:
        normalised: Dict[str, Set[str]] = {}
        for key, scopes in raw.items():
            if not scopes:
                normalised[key] = set()
                continue
            normalised[key] = {scope.strip() for scope in scopes if scope and scope.strip()}
        return normalised

    @staticmethod
    def _parse_api_key_string(raw: str) -> Dict[str, Set[str]]:
        raw = raw.strip()
        if not raw:
            return {}
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                return Settings._normalise_scope_mapping({k: Settings._coerce_iter(v) for k, v in loaded.items()})
        except json.JSONDecodeError:
            pass

        mapping: Dict[str, Set[str]] = {}
        for chunk in raw.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            key, _, scope_str = chunk.partition(":")
            scopes = scope_str.split("|") if scope_str else ["*"]
            mapping[key] = {scope.strip() for scope in scopes if scope.strip()}
        return mapping

    @staticmethod
    def _parse_api_keys_file(path: str) -> Dict[str, Set[str]]:
        data = Path(path).read_text(encoding="utf-8")
        return Settings._parse_api_key_string(data)

    @staticmethod
    def _coerce_iter(value: object) -> Iterable[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _resolve_secret(value: Optional[str], file_path: Optional[str]) -> Optional[str]:
        if file_path:
            try:
                return Path(file_path).read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                raise RuntimeError(f"Secret file {file_path} is not accessible") from None
        if value:
            return value.strip()
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
app = FastAPI(title="API Gateway")
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def _auth_headers(token: Optional[str], header_name: str) -> Dict[str, str]:
    if not token:
        return {}
    header_value = token.strip()
    if header_name.lower() == "authorization" and not header_value.lower().startswith("bearer "):
        header_value = f"Bearer {header_value}"
    return {header_name: header_value}


METRICS_REGISTRY = CollectorRegistry()

REQUEST_COUNTER = Counter(
    "api_gateway_requests_total",
    "Total number of HTTP requests processed by the gateway",
    ["method", "path", "status"],
    registry=METRICS_REGISTRY,
)
REQUEST_LATENCY = Histogram(
    "api_gateway_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    registry=METRICS_REGISTRY,
)


@app.middleware("http")
async def record_metrics(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    raw_path = request.url.path
    if raw_path != "/metrics":
        duration = time.perf_counter() - start
        route = request.scope.get("route")
        path_template = getattr(route, "path", raw_path)
        REQUEST_COUNTER.labels(request.method, path_template, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, path_template).observe(duration)
    return response


@dataclass(frozen=True)
class Credential:
    key: str
    scopes: Set[str]


async def verify_api_key(x_api_key: str = Header(...)) -> Credential:
    scopes = settings.api_keys.get(x_api_key)
    if not scopes:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return Credential(key=x_api_key, scopes=scopes)


def require_scope(scope: str):
    async def dependency(credential: Credential = Depends(verify_api_key)) -> Credential:
        if "*" in credential.scopes or scope in credential.scopes:
            return credential
        raise HTTPException(status_code=403, detail="Insufficient scope")

    return dependency


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    try:
        await redis_client.ping()
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics(_: Credential = Depends(require_scope("metrics:read"))) -> Response:
    payload = generate_latest(METRICS_REGISTRY)
    return PlainTextResponse(payload, media_type=CONTENT_TYPE_LATEST)


@app.get("/sanctions/entities/{entity_id}", dependencies=[Depends(require_scope("sanctions:read"))])
async def get_sanction_entity(entity_id: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.sanctions_url}/entities/{entity_id}",
            headers=_auth_headers(settings.sanctions_token, settings.sanctions_token_header),
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/tasks", dependencies=[Depends(require_scope("tasks:enqueue"))])
async def enqueue_task(payload: dict):
    task_id = str(uuid.uuid4())
    await redis_client.hset(f"task:{task_id}", mapping={"status": "queued"})
    await redis_client.rpush("task_queue", task_id)
    await redis_client.expire(f"task:{task_id}", 300)
    return {"task_id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}", dependencies=[Depends(require_scope("tasks:read"))])
async def get_task(task_id: str):
    data = await redis_client.hgetall(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, **data}


@app.get("/sanctions/search", dependencies=[Depends(require_scope("sanctions:search"))])
async def search_sanctions(q: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.sanctions_url}/search",
            params={"q": q},
            headers=_auth_headers(settings.sanctions_token, settings.sanctions_token_header),
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/sanctions/match", dependencies=[Depends(require_scope("sanctions:match"))])
async def match_sanctions(payload: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.sanctions_url}/match",
            json=payload,
            headers=_auth_headers(settings.sanctions_token, settings.sanctions_token_header),
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/crypto/health", dependencies=[Depends(require_scope("crypto:read"))])
async def crypto_health():
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.crypto_url}/health",
            headers=_auth_headers(settings.crypto_token, settings.crypto_token_header),
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/web/search", dependencies=[Depends(require_scope("web:read"))])
async def web_search(q: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.web_url}/search",
            params={"q": q},
            headers=_auth_headers(settings.web_token, settings.web_token_header),
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
