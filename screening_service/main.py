from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import asdict

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import get_settings
from .sanctions import SanctionsDatasetUnavailable, SanctionsRepository
from .tron import TronReputationClient
from .web_reputation import WebReputationError, WebReputationService

settings = get_settings()
sanctions_repo = SanctionsRepository(settings)
web_reputation = WebReputationService(settings)
tron_client = TronReputationClient(settings)
app = FastAPI(title="InstaKYC Screening MVP")
logger = logging.getLogger(__name__)


class SanctionsQuery(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)
    min_score: int = Field(default=70, ge=1, le=100)
    date_of_birth: dt.date | None = None


class WebQuery(BaseModel):
    query: str


class TronQuery(BaseModel):
    address: str


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@app.on_event("startup")
async def startup() -> None:
    try:
        await asyncio.to_thread(sanctions_repo.ensure_loaded)
    except SanctionsDatasetUnavailable as exc:
        logger.warning("Sanctions dataset unavailable during startup: %s", exc)


@app.get("/healthz")
async def health() -> dict:
    return {
        "status": "ok",
        "sanctions": sanctions_repo.stats(),
    }


@app.post("/sanctions/search")
async def sanctions_search(payload: SanctionsQuery, _: None = Depends(verify_api_key)) -> dict:
    try:
        matches = sanctions_repo.search(
            payload.query,
            limit=payload.limit,
            min_score=payload.min_score,
            date_of_birth=payload.date_of_birth,
        )
    except SanctionsDatasetUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"query": payload.query, "count": len(matches), "matches": matches}


@app.post("/web/reputation")
async def web_reputation_search(payload: WebQuery, _: None = Depends(verify_api_key)) -> dict:
    try:
        results = web_reputation.search(payload.query)
    except WebReputationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "query": payload.query,
        "count": len(results),
        "results": [asdict(result) for result in results],
    }


@app.post("/tron/reputation")
async def tron_reputation_lookup(payload: TronQuery, _: None = Depends(verify_api_key)) -> JSONResponse:
    try:
        reputation = await tron_client.reputation(payload.address)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def _is_sensitive(key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in {"private", "secret", "seed", "mnemonic", "password"})

    def _sanitize_raw(raw: dict[str, object]) -> dict[str, object]:
        sanitized: dict[str, object] = {}
        for key, value in raw.items():
            if _is_sensitive(key):
                continue
            if isinstance(value, dict):
                sanitized[key] = _sanitize_raw(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    _sanitize_raw(item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    body = {
        "address": reputation.address,
        "risk": reputation.risk,
        "score": reputation.score,
        "reasons": reputation.reasons,
        "stats": reputation.stats,
        "raw": _sanitize_raw(reputation.raw),
    }
    return JSONResponse(content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):  # type: ignore[override]
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


__all__ = ["app"]
