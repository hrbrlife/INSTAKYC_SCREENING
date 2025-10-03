# InstaKYC Screening

## Project overview
InstaKYC Screening is a proof-of-concept stack that aims to unify sanctions
lookups, blockchain risk checks, and open-web adverse media triage under a
single API gateway. The current repository provides Docker assets, a FastAPI
proxy, and lightweight stubs that mimic the external services the gateway would
call. It does **not** contain production-ready data pipelines or scraping logic
— the project is at an early prototyping stage.

## Current architecture
The repository is organised around a docker-compose stack. Each service is
expected to run on the same host and communicate over the default Docker
network:

- **`api_gateway`** – FastAPI application that enforces an `X-API-KEY` header
  and forwards requests to downstream services. It also seeds a Redis-backed
  task placeholder.
- **`sanctions_core`** – Pulls the public `opensanctions/yente` image. The stack
  assumes that an `export.tar.gz` dataset already exists on a mounted volume but
  does not provide automation to build or refresh it.
- **`sanctions_build`** – Optional build container for running the `zavod`
  crawler. The provided shell script requires a local Docker registry and manual
  scheduling; no CI automation is present.
- **`graphsense_api` / `graphsense_ingest`** – References upstream GraphSense
  images but does not provision Cassandra/Keyspace data or blockchain ETL jobs.
  The containers will not be usable until data stores and ingestion scripts are
  supplied.
- **`puppeteer_srv`** – Minimal Node.js HTTP server that writes a text artefact
  for every `/search` request. It does not run a browser or capture screenshots.
  Cleanup and proxy rotation scripts are simple placeholders.
- **`redis`** – Shared state for the task queue example. No persistence or
  authentication is configured.
- **`traefik`** – Basic reverse proxy definition without TLS or routing rules.
  It simply exposes the gateway on port 80.

## Readiness assessment
| Area | Status | Notes |
| --- | --- | --- |
| API gateway | ✅ Prototype ready | FastAPI app boots when all environment variables are defined (`SANCTIONS_URL`, `CRYPTO_URL`, `WEB_URL`, `API_KEY`, `REDIS_URL`). Unit tests cover request forwarding and the Redis-backed queue mock. |
| Sanctions data | ⚠️ Incomplete | Compose expects a pre-built OpenSanctions export at `/data/export.tar.gz`. The repository only supplies a generic `zavod` Dockerfile and manual build script; no data is shipped or downloaded automatically. |
| Blockchain screening | ❌ Missing critical pieces | GraphSense services require Cassandra, Spark ETL, and many terabytes of chain data. None of these dependencies or configuration steps are present, so the containers will fail immediately without manual provisioning. |
| Open-web search | ⚠️ Stub only | `puppeteer_srv` records the query to a text file and returns an empty result list. There is no headless browser, scraping logic, or summary generation. |
| Infrastructure automation | ❌ Not started | README references Ansible and hardened networking, but the repository only includes a single docker-compose file. There are no playbooks or security hardening assets. |
| Monitoring & security | ❌ Not started | No metrics, alerting, API rate limiting, or secret management is implemented. |

Overall the repository demonstrates integration points but is far from a
production deployment. Standing up a real sanctions or blockchain screening
service still requires significant engineering effort.

## Getting started
### Prerequisites
- Python 3.11+
- Node.js 18+ (for the stub Puppeteer service)
- Docker (optional, required only if you want to experiment with the compose
  file knowing that several services will not run without additional data)

### Run the automated tests
The available tests exercise the FastAPI gateway and the placeholder Node
service.

```sh
pip install -r requirements-test.txt
pytest
```

The test suite starts a local instance of the Node stub; it does not touch the
Docker services.

### Running the services locally
1. Provide the required environment variables before launching the API gateway:
   ```sh
   export SANCTIONS_URL=http://sanctions_core:8000
   export CRYPTO_URL=http://graphsense_api:8000
   export WEB_URL=http://puppeteer_srv:7000
   export API_KEY=change_me
   export REDIS_URL=redis://redis:6379/0
   ```
2. Start Redis and the placeholder services (e.g. via Docker Compose). Be aware
   that `graphsense_api` and `sanctions_core` will not return useful results
   without additional data pipelines.
3. Interact with the API gateway using the `X-API-KEY` header.

Because the downstream services are incomplete, only the `/tasks` endpoint and
`/web/search` stub will respond successfully out of the box.

## Directory layout
```
api_gateway/        FastAPI proxy application and container definition
compose-sanctions.yml  Docker Compose stack wiring the services together
docker/opensanctions/  Dockerfile and helper script for running zavod builds
docker/puppeteer/   Node.js stub service plus cleanup utilities
docs/               Project planning notes and roadmap
tests/              FastAPI and Node stub regression tests
```

## Contributing & next steps
If you plan to continue the project, prioritise the following tasks:

1. Decide on a data refresh strategy for OpenSanctions and automate the
   pipeline (cron job, storage location, credentials management).
2. Scope the infrastructure required for GraphSense (Cassandra cluster, Spark
   jobs, blockchain node access) or replace it with a lighter-weight alternative
   if that scope is infeasible.
3. Replace the Node stub with a real scraping worker and design a task queue
   that can handle browser automation safely.
4. Add observability, security controls, and documentation for operating the
   system in production.

Pull requests should include tests where possible and update the documentation
accordingly.
