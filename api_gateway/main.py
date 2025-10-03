from functools import lru_cache

from fastapi import Depends, FastAPI, Header, HTTPException
import httpx
import redis.asyncio as redis
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
    api_key: str = "change_me"
    redis_url: str = "redis://localhost:6379/0"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
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
