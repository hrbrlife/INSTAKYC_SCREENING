from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API gateway."""

    sanctions_url: str
    crypto_url: str
    web_url: str
    api_key: str
    redis_url: str

    http_out_proxy_url: str | None = None
    http_out_bearer_token: str | None = None
    otp_delivery_default_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

