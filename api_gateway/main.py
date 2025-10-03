from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
import httpx
import redis.asyncio as redis
from pydantic import BaseModel, Field
import uuid

from .config import settings
from .http_out import (
    PowerboxConfigurationError,
    PowerboxRequestError,
    format_proxy_response,
    send_http_out,
)


class OTPRequest(BaseModel):
    destination: str = Field(..., description="OTP delivery target (phone/email)")
    code: str = Field(..., description="One-time password value")
    delivery_url: str | None = Field(
        default=None,
        description="Powerbox-style URL for the outbound OTP request",
    )
    message: str | None = Field(
        default=None,
        description="Optional message template to send to the delivery provider",
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Provider-specific metadata"
    )


class AdminHttpOutRequest(BaseModel):
    url: str = Field(..., description="Powerbox URL for the downstream request")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = (
        "POST"
    )
    body: dict[str, Any] | None = Field(
        default=None, description="JSON payload to forward with the request"
    )
    headers: dict[str, str] | None = Field(
        default=None, description="Headers to forward to the downstream service"
    )
    timeout: float | None = Field(
        default=None, description="Optional timeout to apply to the proxy request"
    )


app = FastAPI(title="API Gateway")
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def verify_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/sanctions/entities/{entity_id}", dependencies=[Depends(verify_api_key)])
async def get_sanction_entity(entity_id: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.sanctions_url}/entities/{entity_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/tasks", dependencies=[Depends(verify_api_key)])
async def enqueue_task(payload: dict):
    task_id = str(uuid.uuid4())
    await redis_client.hset(f"task:{task_id}", mapping={"status": "queued"})
    await redis_client.rpush("task_queue", task_id)
    await redis_client.expire(f"task:{task_id}", 300)
    return {"task_id": task_id, "status": "queued"}


@app.get("/tasks/{task_id}", dependencies=[Depends(verify_api_key)])
async def get_task(task_id: str):
    data = await redis_client.hgetall(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, **data}


@app.get("/sanctions/search", dependencies=[Depends(verify_api_key)])
async def search_sanctions(q: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.sanctions_url}/search", params={"q": q})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/sanctions/match", dependencies=[Depends(verify_api_key)])
async def match_sanctions(payload: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{settings.sanctions_url}/match", json=payload)
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/crypto/health", dependencies=[Depends(verify_api_key)])
async def crypto_health():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.crypto_url}/health")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.get("/web/search", dependencies=[Depends(verify_api_key)])
async def web_search(q: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.web_url}/search", params={"q": q})
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/identity/otp", dependencies=[Depends(verify_api_key)])
async def send_identity_otp(request: OTPRequest):
    delivery_url = request.delivery_url or settings.otp_delivery_default_url
    if not delivery_url:
        raise HTTPException(
            status_code=500, detail="OTP delivery URL is not configured"
        )

    payload: dict[str, Any] = {
        "destination": request.destination,
        "code": request.code,
    }
    if request.message is not None:
        payload["message"] = request.message
    if request.metadata is not None:
        payload["metadata"] = request.metadata

    try:
        response = await send_http_out(delivery_url, json_payload=payload)
    except PowerboxConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PowerboxRequestError as exc:
        raise HTTPException(status_code=502, detail=exc.detail) from exc

    formatted = format_proxy_response(response)
    formatted["status"] = "sent"
    return formatted


@app.post("/admin/http-out", dependencies=[Depends(verify_api_key)])
async def admin_http_out(request: AdminHttpOutRequest):
    try:
        response = await send_http_out(
            request.url,
            method=request.method,
            json_payload=request.body,
            headers=request.headers,
            timeout=request.timeout,
        )
    except PowerboxConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PowerboxRequestError as exc:
        raise HTTPException(status_code=502, detail=exc.detail) from exc

    return format_proxy_response(response)
