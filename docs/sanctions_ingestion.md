# Sanctions ingestion playbook

This document captures the agreed scope for **Milestone 2** and the steps
required to keep the sanctions dataset powering `sanctions_core` up to date.

## Dataset selection and sizing

- **Source**: `opensanctions/zavod` using the consolidated `sanctions` dataset.
- **Coverage**: Aggregates the major UN, EU, OFAC, UK, AU and CH sanction
  programmes which is sufficient for an initial launch while keeping build time
  manageable.
- **Storage footprint**: the compressed `export.tar.gz` produced by `zavod crawl
  sanctions` varies between 550–700 MB. Once unpacked by Yente it expands to
  roughly 1.6 GB of JSON and index files. Provision at least 2 GB of free space
  on the shared `sanctions_data` Docker volume.

The pipeline can ingest additional datasets (e.g. `debarment` or `pep`) by
passing multiple `--dataset` values to the helper CLI introduced below. Disk
usage grows linearly with each dataset and should be documented in the runbook
before enabling them in production.

## Automated build workflow

The repository now includes a small Python helper that wraps `zavod crawl`. It
creates the export directory, manages cache reuse, and can be triggered from a
CI job or a cron task.

```bash
python -m sanctions_pipeline.build \
  --dataset sanctions \
  --export-path data/opensanctions/export.tar.gz
```

Key features:

- Multiple `--dataset` flags are supported for compound builds.
- `--release 20240101` forces a specific snapshot, which is handy when building
  reproducible archives for audits.
- Cache and export directories default to `data/opensanctions/` and
  `.cache/opensanctions/` but can be relocated via CLI flags.
- Secrets required by upstream sources can be provided through environment
  variables and forwarded using the `env_overrides` hook.

### Scheduling guidance

For the initial rollout we recommend running the build once every 6 hours to
align with the default `YENTE_SCHEDULE` shipping in `compose-sanctions.yml`.
Trigger options include:

1. A cron entry on the host:
   ```cron
   0 */6 * * * cd /opt/instakyc && /usr/bin/python -m sanctions_pipeline.build \
       --dataset sanctions --export-path /srv/opensanctions/export.tar.gz
   ```
2. A CI pipeline step that uploads the resulting archive to object storage. The
   deployment host can then sync the latest archive before starting the stack.

## Yente smoke testing

After each build deploy the archive and confirm the API functions end-to-end:

```bash
python -m sanctions_pipeline.validate http://localhost:8001 \
  --api-key "$YENTE_API_KEY" \
  --entity-id NKC-6CU9E6R4-8 \
  --search-query "John Smith"
```

The command calls `/entities/{id}`, `/search`, and `/match` with representative
payloads and raises an error if any endpoint fails. Test fixtures mock the HTTP
traffic so the helper remains covered by the repository’s unit tests.

## Operational notes

- Keep a rolling history of at least the last three exports to simplify rollbacks.
- Monitor disk usage on the `sanctions_data` volume; build scripts exit early if
  the export directory cannot be created.
- When adding datasets remember to update this document with expected storage
  growth and refresh cadences.

