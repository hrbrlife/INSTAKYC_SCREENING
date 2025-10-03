"""Prefect orchestration helpers for the GraphSense ETL pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import os
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List

try:  # Prefect is optional during development
    from prefect import flow, get_run_logger, task
except Exception:  # pragma: no cover - Prefect not installed in CI
    flow = None  # type: ignore
    task = None  # type: ignore
    get_run_logger = None  # type: ignore


CONFIG_DIR = Path(__file__).resolve().parent / "config"


@dataclass
class ChainConfig:
    """Configuration describing how to ingest a blockchain into GraphSense."""

    name: str
    config_path: Path
    bucket: str
    dataset: str
    spark_submit_bin: str = "spark-submit"
    spark_master: str = "yarn"
    ingest_image: str = "graphsense/ingest:latest"

    def spark_command(self) -> List[str]:
        """Build the spark-submit command used to run ``graphsense-etl``."""

        return [
            self.spark_submit_bin,
            "--master",
            self.spark_master,
            "--conf",
            f"spark.hadoop.fs.s3a.bucket={self.bucket}",
            "graphsense_etl.py",
            "--config",
            str(self.config_path),
            "--dataset",
            self.dataset,
        ]

    def ingest_command(self) -> List[str]:
        """Render the ECS/Fargate ingestion command for documentation purposes."""

        return [
            "docker",
            "run",
            "--rm",
            "-e",
            "CHAIN_CONFIG=/graphsense/config.yaml",
            "-v",
            f"{self.config_path}:/graphsense/config.yaml:ro",
            self.ingest_image,
            "import",
        ]


def _load_chain_config(chain: str) -> ChainConfig:
    config_path = CONFIG_DIR / f"{chain}.yaml"
    if not config_path.exists():  # pragma: no cover - defensive guard
        raise FileNotFoundError(
            f"Missing GraphSense ETL config for chain '{chain}'. "
            "Create the file under blockchain_pipeline/config/."
        )

    bucket = os.environ.get("GRAPHSENSE_RAW_BUCKET", "instakyc-graphsense-raw")
    dataset = os.environ.get("GRAPHSENSE_DATASET", chain)

    return ChainConfig(
        name=chain,
        config_path=config_path,
        bucket=bucket,
        dataset=dataset,
    )


def _execute(cmd: Iterable[str], *, env: Dict[str, str] | None = None, dry_run: bool = False) -> None:
    """Execute a shell command or print it when ``dry_run`` is enabled."""

    command_list = list(cmd)
    if dry_run:
        print("[dry-run]", " ".join(command_list))
        return

    subprocess.run(command_list, check=True, env=env)


if flow and task:  # pragma: no branch

    @task
    def export_chain(config: ChainConfig, dry_run: bool = False) -> None:
        logger = get_run_logger()
        logger.info("Starting Spark export for %s", config.name)
        _execute(config.spark_command(), dry_run=dry_run)

    @task
    def ingest_chain(config: ChainConfig, dry_run: bool = False) -> None:
        logger = get_run_logger()
        logger.info("Importing parquet output into Cassandra for %s", config.name)
        _execute(config.ingest_command(), dry_run=dry_run)

    @task
    def validate_dataset(config: ChainConfig) -> None:
        logger = get_run_logger()
        logger.info("Validation placeholder for chain %s", config.name)

    @flow(name="graphsense-etl")
    def ingest_chain_flow(chain: str, dry_run: bool = False) -> None:
        """Prefect flow orchestrating the export and ingestion for ``chain``."""

        config = _load_chain_config(chain)
        export_chain(config, dry_run)
        ingest_chain(config, dry_run)
        validate_dataset(config)

else:  # pragma: no cover - executed when Prefect is absent

    def ingest_chain_flow(chain: str, dry_run: bool = False) -> None:
        raise RuntimeError(
            "Prefect is not installed. Install Prefect to use the managed flow "
            "or rely on blockchain_pipeline.schedule.create_cron_entry() for "
            "cron-based orchestration."
        )

__all__ = ["ChainConfig", "ingest_chain_flow"]
