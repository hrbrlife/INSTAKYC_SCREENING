"""Lightweight smoke tests for a running Yente instance."""

from __future__ import annotations

import logging
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests


LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class SmokeTestConfig:
    """Configuration for the Yente smoke test utility."""

    base_url: str
    api_key: str | None = None
    timeout: float = 30.0
    entity_id: str = "NKC-6CU9E6R4-8"  # sample entry available in public dumps
    search_query: str = "Test"
    match_payload: dict[str, object] | None = None


class YenteSmokeTester:
    """Perform minimal health checks against a Yente deployment."""

    def __init__(self, config: SmokeTestConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    # Requests emitted by the smoke tests are tiny, so connection pooling is not
    # critical. The dedicated ``Session`` mainly helps tests patch HTTP requests
    # via ``requests_mock`` or ``responses``.

    @property
    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.config.api_key:
            headers["X-API-KEY"] = self.config.api_key
        return headers

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = urljoin(self.config.base_url, path)
        response = self.session.request(
            method,
            url,
            headers={**self.headers, **kwargs.pop("headers", {})},
            timeout=self.config.timeout,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def check_entity(self) -> dict[str, object]:
        response = self._request("GET", f"/entities/{self.config.entity_id}")
        return response.json()

    def check_search(self) -> dict[str, object]:
        response = self._request("POST", "/search", json={"q": self.config.search_query})
        return response.json()

    def check_match(self) -> dict[str, object]:
        payload = self.config.match_payload or {
            "schema": "Person",
            "properties": {"name": [self.config.search_query]},
        }
        response = self._request("POST", "/match", json=payload)
        return response.json()

    def run(self) -> dict[str, dict[str, object]]:
        """Run all smoke tests and return the JSON payloads."""

        results = {
            "entity": self.check_entity(),
            "search": self.check_search(),
            "match": self.check_match(),
        }
        LOG.info("Yente smoke tests passed")
        return results


def parse_args(argv: Iterable[str] | None = None) -> SmokeTestConfig:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Base URL of the Yente API, e.g. http://localhost:8001")
    parser.add_argument("--api-key", dest="api_key", default=None, help="Optional API key")
    parser.add_argument(
        "--entity-id",
        dest="entity_id",
        default=SmokeTestConfig.__dataclass_fields__["entity_id"].default,  # type: ignore[index]
        help="Entity ID to request during the smoke test.",
    )
    parser.add_argument(
        "--search-query",
        dest="search_query",
        default=SmokeTestConfig.__dataclass_fields__["search_query"].default,  # type: ignore[index]
        help="Query string for the /search smoke test.",
    )
    parser.add_argument(
        "--timeout",
        dest="timeout",
        type=float,
        default=SmokeTestConfig.__dataclass_fields__["timeout"].default,  # type: ignore[index]
        help="Request timeout in seconds.",
    )
    args = parser.parse_args(argv)
    return SmokeTestConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        entity_id=args.entity_id,
        search_query=args.search_query,
        timeout=args.timeout,
    )


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    config = parse_args(argv)
    tester = YenteSmokeTester(config)
    try:
        tester.run()
    except requests.HTTPError as exc:  # pragma: no cover - defensive
        LOG.error("Smoke test failed", exc_info=exc)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI dispatcher
    raise SystemExit(main())

