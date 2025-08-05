# API Gateway

This FastAPI application exposes unified endpoints and forwards requests to the
underlying services. Requests must include an `X-API-KEY` header matching the
`API_KEY` environment variable.
