"""Tools for automating the OpenSanctions export build."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from argparse import ArgumentParser
from pathlib import Path
from typing import Iterable

from .config import DEFAULT_DATASETS, SanctionsBuildConfig


LOG = logging.getLogger(__name__)


def _resolve_binary(binary: str) -> str:
    """Return an absolute path to ``binary`` if it exists on ``PATH``."""

    resolved = shutil.which(binary)
    return resolved or binary


def build_command(config: SanctionsBuildConfig) -> list[str]:
    """Construct the ``zavod`` CLI invocation for ``config``."""

    command: list[str] = [_resolve_binary(config.zavod_bin), "crawl"]
    command.extend(config.normalised_datasets())
    command.extend(["--export", str(config.export_path)])
    command.extend(["--cache", str(config.cache_path)])
    if config.release:
        command.extend(["--release", config.release])
    command.extend(config.extra_args)
    return command


def run_build(config: SanctionsBuildConfig) -> subprocess.CompletedProcess[bytes]:
    """Execute ``zavod`` with the provided configuration."""

    export_dir = config.export_path.parent
    export_dir.mkdir(parents=True, exist_ok=True)
    config.cache_path.mkdir(parents=True, exist_ok=True)
    command = build_command(config)
    LOG.info("Running zavod build", extra={"command": command})
    env = os.environ.copy()
    if config.env_overrides:
        env.update(config.env_overrides)
    return subprocess.run(command, check=True, env=env)


def parse_args(argv: Iterable[str] | None = None) -> SanctionsBuildConfig:
    """Parse CLI arguments into a :class:`SanctionsBuildConfig`."""

    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        "-d",
        dest="datasets",
        action="append",
        default=list(DEFAULT_DATASETS),
        help=(
            "Dataset slug to crawl. Specify multiple times to include several "
            "datasets. Defaults to the consolidated `sanctions` bundle."
        ),
    )
    parser.add_argument(
        "--export-path",
        type=Path,
        default=SanctionsBuildConfig().export_path,
        help="Path where export.tar.gz should be written.",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=SanctionsBuildConfig().cache_path,
        help="Directory used to store zavod caches between runs.",
    )
    parser.add_argument(
        "--release",
        type=str,
        default=None,
        help="Optional release identifier to pass to zavod.",
    )
    parser.add_argument(
        "--zavod-bin",
        type=str,
        default="zavod",
        help="Executable name or path for zavod.",
    )
    parser.add_argument(
        "extra_args",
        nargs="*",
        help="Additional flags to append to the zavod invocation.",
    )
    args = parser.parse_args(argv)
    return SanctionsBuildConfig(
        datasets=args.datasets,
        export_path=args.export_path,
        cache_path=args.cache_path,
        release=args.release,
        zavod_bin=args.zavod_bin,
        extra_args=tuple(args.extra_args or ()),
    )


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entry point."""

    logging.basicConfig(level=logging.INFO)
    config = parse_args(argv)
    try:
        run_build(config)
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive
        LOG.error("zavod failed", extra={"returncode": exc.returncode})
        return exc.returncode
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI dispatcher
    raise SystemExit(main())

