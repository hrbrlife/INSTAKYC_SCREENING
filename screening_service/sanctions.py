from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import httpx
from rapidfuzz import fuzz, process

from .config import Settings


@dataclass
class SanctionRecord:
    """Single entry in the OpenSanctions targets export."""

    entity_id: str
    name: str
    datasets: List[str]
    topics: List[str]
    countries: List[str]
    birth_dates: List[dt.date]


class SanctionsDatasetUnavailable(RuntimeError):
    """Raised when the sanctions dataset cannot be downloaded or parsed."""


class SanctionsRepository:
    """Repository that lazily downloads and searches the sanctions dataset."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._records: List[SanctionRecord] = []
        self._last_loaded: Optional[dt.datetime] = None
        self._last_error: Optional[str] = None

    @property
    def cache_path(self) -> Path:
        return self.settings.sanctions_cache_path

    def _http_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "text/csv"}
        if self.settings.http_user_agent:
            headers["User-Agent"] = self.settings.http_user_agent
        return headers

    def _download_dataset(self) -> None:
        try:
            with httpx.Client(timeout=self.settings.tron_timeout) as client:
                response = client.get(
                    str(self.settings.sanctions_data_url), headers=self._http_headers()
                )
                response.raise_for_status()
                self.cache_path.write_bytes(response.content)
        except (httpx.HTTPError, OSError) as exc:
            message = f"Failed to download sanctions dataset: {exc}"
            self._last_error = message
            raise SanctionsDatasetUnavailable(message) from exc

    def _dataset_is_stale(self) -> bool:
        if not self.cache_path.exists():
            return True
        modified = dt.datetime.fromtimestamp(self.cache_path.stat().st_mtime, tz=dt.UTC)
        age = dt.datetime.now(tz=dt.UTC) - modified
        return age > dt.timedelta(hours=self.settings.sanctions_refresh_hours)

    def _load_records(self) -> None:
        try:
            if not self.cache_path.exists() or self._dataset_is_stale():
                self._download_dataset()
            raw_text = self.cache_path.read_text(encoding="utf-8", errors="ignore")
        except SanctionsDatasetUnavailable:
            raise
        except OSError as exc:
            message = f"Failed to read sanctions dataset: {exc}"
            self._last_error = message
            raise SanctionsDatasetUnavailable(message) from exc

        try:
            reader = csv.DictReader(raw_text.splitlines())
            records: List[SanctionRecord] = []
            for row in reader:
                records.append(
                    SanctionRecord(
                        entity_id=row.get("id", ""),
                        name=row.get("name", "").strip(),
                        datasets=_split_csv_field(row.get("datasets")),
                        topics=_split_csv_field(row.get("topics")),
                        countries=_split_csv_field(row.get("countries")),
                        birth_dates=_parse_birth_dates(row.get("birth_date")),
                    )
                )
        except csv.Error as exc:
            message = f"Failed to parse sanctions dataset: {exc}"
            self._last_error = message
            raise SanctionsDatasetUnavailable(message) from exc

        self._records = [record for record in records if record.name]
        self._last_loaded = dt.datetime.now(tz=dt.UTC)
        self._last_error = None

    def ensure_loaded(self) -> None:
        if not self._records or self._dataset_is_stale():
            self._load_records()

    def search(
        self,
        query: str,
        limit: int = 5,
        min_score: int = 70,
        date_of_birth: Optional[dt.date] = None,
    ) -> List[dict]:
        query = query.strip()
        if not query:
            return []
        self.ensure_loaded()
        names = [record.name for record in self._records]
        matches = process.extract(
            query,
            names,
            scorer=fuzz.WRatio,
            processor=None,
            limit=max(limit * 3, limit),
        )
        results: List[dict] = []
        for _, score, index in matches:
            if score < min_score:
                continue
            record = self._records[index]
            if date_of_birth and not _record_matches_birthdate(record, date_of_birth):
                continue
            results.append(
                {
                    "entity_id": record.entity_id,
                    "name": record.name,
                    "score": score,
                    "datasets": record.datasets,
                    "topics": record.topics,
                    "countries": record.countries,
                    "birth_dates": [value.isoformat() for value in record.birth_dates],
                }
            )
            if len(results) >= limit:
                break
        return results

    def stats(self) -> dict:
        status = "ready"
        detail = None
        try:
            self.ensure_loaded()
        except SanctionsDatasetUnavailable:
            status = "unavailable"
            detail = self._last_error
        return {
            "records": len(self._records),
            "last_loaded": self._last_loaded.isoformat() if self._last_loaded else None,
            "status": status,
            "detail": detail,
        }


def _split_csv_field(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    parts: Iterable[str] = raw.replace("|", ",").split(",")
    return [part.strip() for part in parts if part and part.strip()]


def _parse_birth_dates(raw: Optional[str]) -> List[dt.date]:
    dates: List[dt.date] = []
    for value in _split_csv_field(raw):
        parsed = _parse_date(value)
        if parsed:
            dates.append(parsed)
    return dates


def _parse_date(value: str) -> Optional[dt.date]:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m", "%Y"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
        if fmt == "%Y":
            return dt.date(parsed.year, 1, 1)
        if fmt == "%Y-%m":
            return dt.date(parsed.year, parsed.month, 1)
        if fmt == "%d-%m-%Y":
            return dt.date(parsed.year, parsed.month, parsed.day)
        return parsed.date()
    return None


def _record_matches_birthdate(record: SanctionRecord, date_of_birth: dt.date) -> bool:
    if not record.birth_dates:
        return False
    return any(candidate == date_of_birth for candidate in record.birth_dates)


__all__ = ["SanctionsDatasetUnavailable", "SanctionsRepository"]
