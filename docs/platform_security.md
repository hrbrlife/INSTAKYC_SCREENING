# Platform security and observability baseline

Milestone 5 introduces a repeatable security and operations baseline across the
stack. This document summarises the current controls, how to configure them, and
where additional hardening is still required.

## Authentication and authorisation

- **Scoped API keys** – The FastAPI gateway requires an `X-API-KEY` header for
  every request. Keys map to named scopes (e.g. `sanctions:search`,
  `metrics:read`) so that teams can provision least-privilege credentials.
  Configure keys via the `API_KEYS` environment variable or the
  `API_KEYS_FILE` Docker secret.
- **Service tokens** – Internal services expect bearer tokens for downstream
  calls. The Puppeteer worker rejects requests without the `X-Service-Token`
  header, and the gateway automatically forwards the configured token to
  Yente/GraphSense when values are supplied.
- **Secrets via Docker secrets** – `compose-sanctions.yml` mounts secrets for API
  keys, Redis URLs/passwords, and the Puppeteer service token. Replace the files
  in `secrets/` with environment-specific values before deploying to shared
  environments.

## Observability

- **Prometheus metrics** – Both the gateway and the Puppeteer worker expose
  `GET /metrics`. The gateway tracks request totals and latency histograms per
  route, while the worker records HTTP throughput and latency alongside default
  Node.js metrics. Access to the gateway metrics requires the `metrics:read`
  scope; the worker uses the same service token as other routes.
- **Health checks** – `GET /healthz` on the gateway verifies Redis connectivity.
  The Puppeteer worker returns `503` while initialising and `200` once queue
  connections succeed. These endpoints are designed for container orchestrators
  and uptime checks.

## Container hardening

- Application containers now run as dedicated non-root users and set `PYTHON*`
  and `NODE_ENV` runtime safeguards. File permissions are restricted to the
  application directories to minimise blast radius.
- Redis loads its password from Docker secrets and refuses unauthenticated
  clients, even when the port is published locally.

## Remaining gaps

Milestone 5 establishes the base layer but further improvements are required
before production:

1. Centralised logging and structured log forwarding for every service.
2. Alerting rules and dashboards based on the exported Prometheus metrics.
3. Network policies between services once the stack is deployed on Kubernetes or
   Docker Swarm.
4. Automated secret rotation using a vault or cloud secret manager instead of
   static Docker secret files.

Treat this document as the starting point for operational runbooks as future
milestones introduce CI/CD and production infrastructure.
