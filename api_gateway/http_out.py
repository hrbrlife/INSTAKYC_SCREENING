from __future__ import annotations

import json
import re
from typing import Any, Mapping

import httpx

from .config import settings

_POWERBOX_URL_PATTERN = re.compile(r"<\?(https?://[^>]+)\?>")


class PowerboxConfigurationError(RuntimeError):
    """Raised when the HTTP-out proxy is not configured."""


class PowerboxRequestError(RuntimeError):
    """Raised when the proxy returns a non-success response."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def resolve_powerbox_url(raw: str) -> str:
    """Resolve Sandstorm-style powerbox URLs of the form `<?https://...?>`."""

    match = _POWERBOX_URL_PATTERN.fullmatch(raw.strip())
    if match:
        return match.group(1)
    return raw


def _build_proxy_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.http_out_bearer_token:
        headers["Authorization"] = f"Bearer {settings.http_out_bearer_token}"
    return headers


async def send_http_out(
    url: str,
    *,
    method: str = "POST",
    json_payload: Any | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """Forward an HTTP request to the configured powerbox proxy."""

    proxy_url = settings.http_out_proxy_url
    if not proxy_url:
        raise PowerboxConfigurationError(
            "HTTP-out proxy URL is not configured. Set HTTP_OUT_PROXY_URL."
        )

    resolved_url = resolve_powerbox_url(url)
    payload: dict[str, Any] = {"url": resolved_url, "method": method.upper()}
    if json_payload is not None:
        payload["json"] = json_payload
    if headers:
        payload["headers"] = dict(headers)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            proxy_url,
            json=payload,
            headers=_build_proxy_headers(),
        )

    if response.status_code >= 400:
        detail = response.text
        try:
            parsed = response.json()
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, Mapping) and "detail" in parsed:
            detail = str(parsed["detail"])
        raise PowerboxRequestError(response.status_code, detail)

    return response


def format_proxy_response(response: httpx.Response) -> dict[str, Any]:
    """Return a serialisable representation of the proxy response."""

    try:
        body: Any = response.json()
    except json.JSONDecodeError:
        body = response.text

    return {
        "status_code": response.status_code,
        "body": body,
    }

