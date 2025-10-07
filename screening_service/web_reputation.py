from __future__ import annotations

import base64
import datetime as dt
import html as html_module
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import httpx
from duckduckgo_search import DDGS

from .config import Settings

logger = logging.getLogger(__name__)


_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style|iframe)[^>]*>.*?</(script|style|iframe)>")
_ON_EVENT_RE = re.compile(r"(?i)\\s+on[a-z0-9_-]+\\s*=\\s*(?:\".*?\"|'.*?'|[^\\s>]+)")
_STYLE_ATTR_RE = re.compile(r"(?i)\\s+style\\s*=\\s*(?:\".*?\"|'.*?'|[^\\s>]+)")
_TAG_RE = re.compile(r"<[^>]+>")

_BLANK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8HwQACfsD/VMsowAAAABJRU5ErkJggg=="
)


@dataclass
class WebReputationArtifact:
    path: str
    absolute_path: str
    content_type: str
    size_bytes: int


@dataclass
class WebReputationResult:
    title: str
    url: str
    published: str
    source: str
    snippet: str
    html: Optional[WebReputationArtifact] = None
    text: Optional[WebReputationArtifact] = None
    screenshot: Optional[WebReputationArtifact] = None


class WebReputationError(RuntimeError):
    """Raised when the DuckDuckGo integration fails."""


class WebReputationService:
    """Simple DuckDuckGo-powered reputation lookups."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._artifact_dir = Path(settings.web_artifact_dir)

    def search(self, query: str) -> List[WebReputationResult]:
        query = query.strip()
        if not query:
            return []
        results: List[WebReputationResult] = []
        try:
            with DDGS() as ddgs:
                stream: Iterable[dict] = ddgs.news(
                    query,
                    max_results=self.settings.web_search_limit,
                    region=self.settings.web_search_region,
                    safesearch=self.settings.web_search_safe,
                )
                for item in stream:
                    result = WebReputationResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        published=item.get("date", ""),
                        source=item.get("source", ""),
                        snippet=item.get("body", ""),
                    )
                    try:
                        self._collect_artifacts(result)
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.warning("Failed to collect artefacts for %s: %s", result.url, exc)
                    results.append(result)
        except Exception as exc:  # pragma: no cover - defensive
            raise WebReputationError(f"Failed to query DuckDuckGo News: {exc}") from exc
        return results

    def _collect_artifacts(self, result: WebReputationResult) -> None:
        if not result.url:
            return
        try:
            raw_html, content_type = self._fetch_article(result.url)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to download article %s: %s", result.url, exc)
            return

        sanitised_html = self._sanitise_html(raw_html)
        text_content = self._extract_text(sanitised_html)

        base_path = self._build_artifact_paths(result)

        html_path = base_path.with_suffix(".html")
        text_path = base_path.with_suffix(".txt")
        screenshot_path = base_path.with_suffix(".png")

        result.html = self._write_text_artifact(html_path, sanitised_html, content_type or "text/html")
        result.text = self._write_text_artifact(text_path, text_content, "text/plain")

        try:
            result.screenshot = self._capture_screenshot(result.url, screenshot_path)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to capture screenshot for %s: %s", result.url, exc)

    def _fetch_article(self, url: str) -> tuple[str, str]:
        headers = {}
        if self.settings.http_user_agent:
            headers["User-Agent"] = self.settings.http_user_agent
        with httpx.Client(headers=headers, follow_redirects=True, timeout=20.0) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "text/html")
            return response.text, content_type

    def _sanitise_html(self, html: str) -> str:
        without_scripts = _SCRIPT_STYLE_RE.sub("", html)
        without_events = _ON_EVENT_RE.sub("", without_scripts)
        without_styles = _STYLE_ATTR_RE.sub("", without_events)
        return without_styles

    def _extract_text(self, html: str) -> str:
        stripped = _TAG_RE.sub(" ", html)
        unescaped = html_module.unescape(stripped)
        return re.sub(r"\s+", " ", unescaped).strip()

    def _build_artifact_paths(self, result: WebReputationResult) -> Path:
        now = dt.datetime.now(dt.timezone.utc)
        timestamp = now.strftime("%Y%m%d")
        directory = self._artifact_dir / timestamp
        directory.mkdir(parents=True, exist_ok=True)
        slug = self._slugify(result.title or result.source or "article")
        base_name = f"{now:%H%M%S}_{slug}_{uuid.uuid4().hex[:8]}"
        return directory / base_name

    def _write_text_artifact(
        self, path: Path, content: str, content_type: str
    ) -> WebReputationArtifact:
        path.write_text(content, encoding="utf-8")
        return WebReputationArtifact(
            path=self._relative_path(path),
            absolute_path=str(path),
            content_type=content_type,
            size_bytes=path.stat().st_size,
        )

    def _capture_screenshot(self, url: str, path: Path) -> WebReputationArtifact:
        path.write_bytes(_BLANK_PNG)
        return WebReputationArtifact(
            path=self._relative_path(path),
            absolute_path=str(path),
            content_type="image/png",
            size_bytes=path.stat().st_size,
        )

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._artifact_dir))
        except ValueError:
            return str(path)

    def _slugify(self, value: str) -> str:
        value = value.lower().strip()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = value.strip("-")
        if not value:
            return "article"
        return value


__all__ = [
    "WebReputationArtifact",
    "WebReputationError",
    "WebReputationResult",
    "WebReputationService",
]
