# MVP operations guide

This guide summarises the day-two operations for the single-container screening
service.

## Prerequisites

- Docker Engine 20.10+ or Docker Desktop.
- The `docker compose` plugin.
- Internet connectivity so the container can download OpenSanctions datasets,
  DuckDuckGo news results, and TronScan account metadata.

## Bootstrapping

Run the helper script once per environment to create the `.env` file and ensure
the persistent cache directory exists:

```bash
./scripts/bootstrap.sh <api-key>
```

The script validates the argument, backs up any existing `.env`, checks for
Docker/Compose availability, and prints the exact command required to start the
stack.

## Starting the stack

```bash
docker compose -f compose-mvp.yml up --build -d
```

- The container exposes the API on `http://localhost:8000`.
- A Docker health check queries `/healthz`. Check `docker compose ps` for the
  `healthy` status before sending requests.
- The `screening_data` volume caches the OpenSanctions export so subsequent
  restarts avoid repeated downloads.

## Monitoring and troubleshooting

- `docker compose logs -f screening_api` – tail the FastAPI and background
  dataset refresh logs.
- `docker compose exec screening_api curl -s http://localhost:8000/healthz | jq`
  – inspect health information from inside the container.
- `docker compose ps` – confirm the container is healthy and port `8000` is
  published.

If downloads fail, the service returns a `503` for sanctions searches until the
cache is restored. Deleting the `screening_data` volume forces a clean refresh.

## Updating the service

1. Pull the latest repository changes.
2. Re-run `docker compose -f compose-mvp.yml build` to rebuild the image.
3. Restart the stack with `docker compose -f compose-mvp.yml up -d`.

The persistent volume means you do not need to re-bootstrap the API key unless
it has changed.
