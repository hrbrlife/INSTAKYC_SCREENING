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

- **`api_gateway`** – FastAPI application that enforces scoped API keys,
  exposes `/metrics` and `/healthz`, and forwards requests to downstream
  services with service-to-service authentication headers. It also seeds a
  Redis-backed task placeholder.
- **`sanctions_core`** – Pulls the public `opensanctions/yente` image. The stack
  assumes that an `export.tar.gz` dataset already exists on a mounted volume but
  does not provide automation to build or refresh it.
- **`sanctions_build`** – Optional build container for running the `zavod`
  crawler. The provided shell script requires a local Docker registry and manual
  scheduling; no CI automation is present.
- **`graphsense_api` / `graphsense_ingest`** – References upstream GraphSense
  images but does not provision Cassandra/Keyspace data or blockchain ETL jobs.
  The newly documented plan in `docs/blockchain_strategy.md` outlines the
  infrastructure and ETL work required to operationalise these services.
- **`puppeteer_srv`** – Queue-driven Puppeteer worker that captures Google News
  results, sanitised HTML snapshots, and screenshots for each queued adverse
  media search. Every request must include the `X-Service-Token` secret and the
  service publishes Prometheus metrics for scraping throughput. Maintenance
  scripts handle artefact retention and user-agent rotation hooks.
- **`redis`** – Shared state for the task queue example. The compose stack now
  enables append-only persistence and sets a development password by default so
  the queue can be accessed safely when the port is published.

## Readiness assessment
| Area | Status | Notes |
| --- | --- | --- |
| API gateway | ✅ Prototype ready | FastAPI app boots with default secrets, enforces scoped API keys, emits Prometheus metrics, and publishes `/healthz` for container orchestration checks. Unit tests cover request forwarding, the Redis-backed queue mock, and scope enforcement. |
| Sanctions data | ⚠️ Incomplete | Compose expects a pre-built OpenSanctions export at `/data/export.tar.gz`. The repository only supplies a generic `zavod` Dockerfile and manual build script; no data is shipped or downloaded automatically. |
| Blockchain screening | ❌ Missing critical pieces | GraphSense services require Cassandra, Spark ETL, and many terabytes of chain data. None of these dependencies or configuration steps are present, so the containers will fail immediately without manual provisioning. |
| Open-web search | ⚠️ Limited | `puppeteer_srv` runs Puppeteer inside a queue-backed worker, storing sanitised HTML and full page screenshots per request. Calls now require a service token and expose Prometheus metrics, but proxy management and durable artefact storage still need to be integrated. |
| Infrastructure automation | ❌ Not started | README references Ansible and hardened networking, but the repository only includes a single docker-compose file. There are no playbooks or security hardening assets. |
| Monitoring & security | ⚠️ Partial | Scoped API keys, service tokens, Docker secrets, and Prometheus metrics are available. Centralised logging, alerting, and production secret storage are still pending. |

Overall the repository demonstrates integration points but is far from a
production deployment. Standing up a real sanctions or blockchain screening
service still requires significant engineering effort.

## Getting started
### Prerequisites
- Python 3.11+
- Node.js 18+ (for the Puppeteer worker service)
- Docker (optional, required only if you want to experiment with the compose
  file knowing that several services will not run without additional data)

### Run the automated tests
The available tests exercise the FastAPI gateway and the Puppeteer worker
(running in a mocked, memory-backed mode).

```sh
pip install -r requirements-test.txt
pytest
```

The test suite starts a local instance of the Puppeteer worker (with a memory
queue and fake artefact mode) and does not touch the Docker services.

### Running the services locally
1. The FastAPI gateway ships with sensible defaults so it can boot with no
   environment variables defined. Override them as needed in a local `.env`
   file or by replacing the Docker secret templates in `secrets/`:
   ```sh
   SANCTIONS_URL=http://localhost:8001  # optional override
   API_KEYS="team_reader:sanctions:search|web:read"
   REDIS_URL=redis://:supersecret@localhost:6379/0
   WEB_TOKEN=supersecretworker
   ```
2. Launch the development stack. The Compose file maps the API gateway to
   `http://localhost:8000`, enables Redis persistence with a password, and keeps
   the rest of the services on the internal Docker network. Secrets are mounted
   via Docker secrets; copy the templates in `secrets/` before running on shared
   environments.
   ```sh
   docker compose -f compose-sanctions.yml up --build
   ```
3. Interact with the API gateway using the `X-API-KEY` header. Keys and scopes
   are defined in the Docker secret `api_gateway_keys`. The default
   `change_me_admin` key grants full access in development.

4. Monitor the stack using the new observability endpoints:
   - `GET /healthz` on the API gateway verifies Redis connectivity.
   - `GET /metrics` on the API gateway (requires the `metrics:read` scope)
     exposes Prometheus counters and histograms.
   - `GET /metrics` on the Puppeteer service (requires the service token)
     exposes queue and HTTP request metrics.

5. Build the sanctions dataset before relying on the Yente API. A helper CLI is
   bundled with the repository:

   ```sh
   python -m sanctions_pipeline.build --dataset sanctions --export-path data/opensanctions/export.tar.gz
   ```

   The command downloads/crawls the OpenSanctions data and writes an
   `export.tar.gz` archive at `data/opensanctions/`. Mount the same directory as
   the `sanctions_data` volume when running Docker Compose so that the Yente
   container can load it.

6. Once the archive has been mounted run the smoke tests to confirm that Yente
   is responding as expected:

   ```sh
   python -m sanctions_pipeline.validate http://localhost:8001 --search-query "John Smith"
   ```

   Supply `--api-key` if the upstream instance enforces authentication.

### What currently works
- `/tasks` creates ephemeral queue items in Redis. Because Redis now persists to
  disk you can restart the service without losing recently enqueued tasks.
- `/web/search` proxies to the Puppeteer worker queue. Each request is executed
  via headless Chromium, producing sanitised HTML, a JSON summary, and a
  full-page screenshot stored under `WEBSHOT_DIR`.
- `/metrics` endpoints on the gateway and the Puppeteer worker expose
  Prometheus-formatted counters and histograms.
- `python -m sanctions_pipeline.build` automates the creation of the
  `export.tar.gz` artefact that powers the sanctions service. Use
  `python -m sanctions_pipeline.validate` to run the end-to-end smoke tests once
  the archive has been deployed to `sanctions_core`.

### Known limitations when running the stack
- `sanctions_core` still expects an OpenSanctions export at `/data/export.tar.gz`
  and will return errors until Milestone 2 automates the dataset build.
- `graphsense_api`/`graphsense_ingest` require Cassandra and Spark clusters that
  are **not** provisioned by this repository. The containers will stay in a
  crash loop until those dependencies are provided or the service is replaced.
- The Puppeteer worker currently targets Google News headlines only and expects
  outbound internet access. Persisting artefacts beyond the local filesystem is
  left to future milestones.

## Directory layout
```
api_gateway/        FastAPI proxy application and container definition
compose-sanctions.yml  Docker Compose stack wiring the services together
docker/opensanctions/  Dockerfile and helper script for running zavod builds
docker/puppeteer/   Puppeteer-based adverse media worker and maintenance scripts
docs/               Project planning notes and roadmap
tests/              FastAPI and Puppeteer worker regression tests
```

## Contributing & next steps
If you plan to continue the project, prioritise the following tasks:

1. Decide on a data refresh strategy for OpenSanctions and automate the
   pipeline (cron job, storage location, credentials management).
2. Follow the blockchain rollout blueprint in `docs/blockchain_strategy.md`
   before attempting to run GraphSense locally. Provision Cassandra, schedule
   the Prefect ETL, and wire the API gateway once data is available.
3. Harden the new adverse media workflow with authentication, proxy rotation,
   and durable artefact archiving.
4. Extend the observability and security baseline described in
  `docs/platform_security.md` with centralised logging, alert routing, and
  production secret management.

Pull requests should include tests where possible and update the documentation
accordingly.
