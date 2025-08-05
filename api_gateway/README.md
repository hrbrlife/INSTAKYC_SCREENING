# API Gateway

This FastAPI application exposes unified endpoints and forwards requests to the
underlying services. Requests must include an `X-API-KEY` header matching the
`API_KEY` environment variable.

## Configuration

The gateway reads the following environment variables:

- `SANCTIONS_URL` – base URL of the sanctions service.
- `CRYPTO_URL` – base URL of the GraphSense service.
- `WEB_URL` – base URL of the web-scraping service.
- `API_KEY` – shared secret required in the `X-API-KEY` header.

## Endpoints

- `GET /sanctions/entities/{entity_id}` – proxy entity lookup to the sanctions service.
- `GET /sanctions/search?q=...` – search the sanctions index.
- `POST /sanctions/match` – bulk match against the sanctions index.
- `GET /crypto/health` – health check for the GraphSense service.
- `GET /web/search?q=...` – proxy open‑web search requests.

## Development

Install test dependencies and run the unit tests:

```sh
pip install -r ../requirements-test.txt
pytest
```
