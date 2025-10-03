from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from duckduckgo_search import DDGS

from .config import Settings


@dataclass
class WebReputationResult:
    title: str
    url: str
    published: str
    source: str
    snippet: str


class WebReputationService:
    """Simple DuckDuckGo-powered reputation lookups."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def search(self, query: str) -> List[WebReputationResult]:
        query = query.strip()
        if not query:
            return []
        results: List[WebReputationResult] = []
        with DDGS() as ddgs:
            stream: Iterable[dict] = ddgs.news(
                query,
                max_results=self.settings.web_search_limit,
                region=self.settings.web_search_region,
                safesearch=self.settings.web_search_safe,
            )
            for item in stream:
                results.append(
                    WebReputationResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        published=item.get("date", ""),
                        source=item.get("source", ""),
                        snippet=item.get("body", ""),
                    )
                )
        return results
