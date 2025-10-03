"""Entry point that executes :func:`ingest_chain_flow` from the command line."""

from __future__ import annotations

import argparse
import sys

from .prefect_flow import ingest_chain_flow


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chain", required=True, help="Blockchain identifier")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the spark and ingestion commands instead of executing them",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ingest_chain_flow(args.chain, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual execution
    raise SystemExit(main(sys.argv[1:]))
