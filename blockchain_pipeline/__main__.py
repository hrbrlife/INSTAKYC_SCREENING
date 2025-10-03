"""CLI helper that proxies to :func:`blockchain_pipeline.schedule.main`."""

from __future__ import annotations

import sys

from . import schedule


def main(argv: list[str] | None = None) -> int:
    return schedule.main(argv)


if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main(sys.argv[1:]))
