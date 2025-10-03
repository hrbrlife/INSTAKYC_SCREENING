"""Lightweight cron helpers for the blockchain ETL pipeline."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Dict

DEFAULT_SCHEDULE: Dict[str, str] = {
    "bitcoin": "0 2 * * *",
    "ethereum": "30 2 * * *",
    "litecoin": "0 3 * * 1,4",
}


@dataclass
class CronEntry:
    """Represents a rendered cron expression."""

    expression: str
    command: str

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.expression} {self.command}"


def create_cron_entry(chain: str, command: str | None = None) -> CronEntry:
    """Return the cron line for ``chain`` using :data:`DEFAULT_SCHEDULE`.

    Parameters
    ----------
    chain:
        Supported blockchain identifier (``bitcoin``, ``ethereum`` or
        ``litecoin``).
    command:
        Optional command to execute. When omitted a sensible default that calls
        the Prefect fallback runner is returned.
    """

    try:
        expression = DEFAULT_SCHEDULE[chain]
    except KeyError as exc:  # pragma: no cover - invalid chain
        raise ValueError(f"Unsupported chain '{chain}'.") from exc

    if command is None:
        command = (
            f"/usr/local/bin/python -m blockchain_pipeline.prefect_runner "
            f"--chain {chain}"
        )

    return CronEntry(expression=expression, command=command)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chain", choices=sorted(DEFAULT_SCHEDULE))
    parser.add_argument(
        "--command",
        help="Override the command executed by cron",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    entry = create_cron_entry(args.chain, args.command)
    print(entry)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main())
