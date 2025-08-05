from fastapi import Depends, FastAPI, Header, HTTPException
import httpx
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    sanctions_url: str
    crypto_url: str
    web_url: str
    api_key: str


settings = Settings()
app = FastAPI(title="API Gateway")


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


@app.get("/crypto/health", dependencies=[Depends(verify_api_key)])
async def crypto_health():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.crypto_url}/health")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()
