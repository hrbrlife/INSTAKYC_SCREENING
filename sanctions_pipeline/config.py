"""Configuration helpers for the sanctions dataset build pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_DATASETS: Sequence[str] = ("sanctions",)
"""Dataset slugs to include when running ``zavod crawl``."""


@dataclass(slots=True)
class SanctionsBuildConfig:
    """Settings used to execute a ``zavod`` build.

    Parameters
    ----------
    datasets:
        Iterable of dataset slugs to process. By default the consolidated
        ``sanctions`` bundle is used so the pipeline stays small enough for
        local experimentation while still covering global lists.
    export_path:
        Location of the ``export.tar.gz`` artefact that the Yente container
        expects. The parent directory is created automatically.
    cache_path:
        Optional cache directory that ``zavod`` can reuse across executions to
        reduce download time.
    release:
        Optional release label (``latest`` or a date such as ``20240101``). If
        ``None`` the ``zavod`` default is used, allowing the crawler to fetch
        the newest available snapshot.
    zavod_bin:
        Name or path of the ``zavod`` executable. Overridable via environment
        variables or CLI arguments so that the same configuration works inside
        Docker or a virtual environment.
    extra_args:
        Additional CLI flags appended to the ``zavod`` invocation.
    env_overrides:
        Environment variables that should be passed to the subprocess. This is
        mainly used to forward API tokens to the crawler without storing them on
        disk.
    """

    datasets: Iterable[str] = field(default_factory=lambda: DEFAULT_DATASETS)
    export_path: Path = Path("data/opensanctions/export.tar.gz")
    cache_path: Path = Path(".cache/opensanctions")
    release: str | None = None
    zavod_bin: str = "zavod"
    extra_args: Sequence[str] = field(default_factory=tuple)
    env_overrides: dict[str, str] | None = None

    def normalised_datasets(self) -> tuple[str, ...]:
        """Return dataset slugs as an immutable tuple."""

        return tuple(self.datasets)

