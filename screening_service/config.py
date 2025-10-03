from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SANCTIONS_URL = (
    "https://data.opensanctions.org/datasets/latest/default/targets.simple.csv"
)


class Settings(BaseSettings):
    """Runtime configuration for the consolidated screening service."""

    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    api_key: str = Field(
        default="change_me",
        description="Single API key required for all client requests",
    )
    sanctions_data_url: HttpUrl = Field(
        default=DEFAULT_SANCTIONS_URL,
        description="CSV export containing OpenSanctions targets",
    )
    data_dir: Path = Field(
        default=Path(__file__).resolve().parents[1] / "data" / "cache",
        description="Directory used to persist downloaded datasets",
    )
    sanctions_cache_filename: str = Field(
        default="targets.simple.csv",
        description="Filename of the cached sanctions dataset",
    )
    sanctions_refresh_hours: int = Field(
        default=12,
        description="Age threshold before the sanctions dataset is refreshed",
    )
    web_search_region: str = Field(default="wt-wt", description="DuckDuckGo region code")
    web_search_safe: str = Field(
        default="moderate",
        description="Safe search level for DuckDuckGo",
    )
    web_search_limit: int = Field(default=6, description="Maximum news results to fetch")
    tron_account_url: HttpUrl = Field(
        default="https://apilist.tronscanapi.com/api/account",
        description="Public TronScan API endpoint used for address profiling",
    )
    tron_timeout: float = Field(
        default=12.0, description="HTTP timeout for Tron reputation requests"
    )
    http_user_agent: Optional[str] = Field(
        default=None,
        description="Optional override for outbound HTTP user-agent",
    )

    @property
    def sanctions_cache_path(self) -> Path:
        return self.data_dir / self.sanctions_cache_filename


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
