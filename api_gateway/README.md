# API Gateway

This FastAPI application exposes unified endpoints and forwards requests to the
underlying services. Requests must include an `X-API-KEY` header matching the
`API_KEY` environment variable.

## Endpoints

- `GET /sanctions/entities/{entity_id}` – proxy entity lookup to the sanctions service.
- `GET /sanctions/search?q=...` – search the sanctions index.
- `POST /sanctions/match` – bulk match against the sanctions index.
- `GET /crypto/health` – health check for the GraphSense service.

## Development

Install test dependencies and run the unit tests:

```sh
pip install -r ../requirements-test.txt
pytest
```
