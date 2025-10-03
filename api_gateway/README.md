# API Gateway

This FastAPI application exposes unified endpoints and forwards requests to the
underlying services. Requests must include an `X-API-KEY` header matching one of
the configured keys and scopes. Service-to-service calls to Puppeteer, Yente,
and GraphSense automatically attach the configured bearer or token headers.

## Configuration

The gateway reads the following environment variables (all of which have
development-friendly defaults baked into the application so it can boot without
additional configuration):

- `SANCTIONS_URL` – base URL of the sanctions service.
- `CRYPTO_URL` – base URL of the GraphSense service.
- `WEB_URL` – base URL of the web-scraping service.
- `API_KEYS` – comma-separated mapping of `key:scope1|scope2`. Accepts JSON when
  loading from files.
- `API_KEYS_FILE` – optional path to a JSON secret defining key-to-scope
  mappings. Overrides `API_KEYS` when present.
- `REDIS_URL` – connection string for the Redis task queue.
- `REDIS_URL_FILE` – optional path to a secret containing the Redis connection
  string.
- `SANCTIONS_TOKEN` / `_FILE` – optional bearer token forwarded to Yente.
- `CRYPTO_TOKEN` / `_FILE` – optional bearer token forwarded to GraphSense.
- `WEB_TOKEN` / `_FILE` – token forwarded to the Puppeteer worker. Defaults to
  `change_me_worker` to match the development Docker secret.
- `WEB_TOKEN_HEADER` – header name used when forwarding the Puppeteer token.

## Endpoints

- `GET /sanctions/entities/{entity_id}` – proxy entity lookup to the sanctions service.
- `GET /sanctions/search?q=...` – search the sanctions index.
- `POST /sanctions/match` – bulk match against the sanctions index.
- `GET /crypto/health` – health check for the GraphSense service.
- `GET /web/search?q=...` – proxy open‑web search requests.
- `POST /tasks` – enqueue a short‑lived task.
- `GET /tasks/{task_id}` – retrieve task status.
- `GET /healthz` – verifies Redis connectivity without authentication.
- `GET /metrics` – Prometheus metrics endpoint (requires the `metrics:read`
  scope).

### Scopes

Each API key maps to a set of scopes. Routes require the following scopes:

| Scope | Description |
| --- | --- |
| `sanctions:read` | Access `/sanctions/entities/{id}`. |
| `sanctions:search` | Access `/sanctions/search`. |
| `sanctions:match` | Access `/sanctions/match`. |
| `tasks:enqueue` | Create queue jobs via `/tasks`. |
| `tasks:read` | Read queue state via `/tasks/{id}`. |
| `crypto:read` | Call `/crypto/health`. |
| `web:read` | Call `/web/search`. |
| `metrics:read` | Read Prometheus metrics. |

## Development

Install test dependencies and run the unit tests:

```sh
pip install -r ../requirements-test.txt
pytest
```
