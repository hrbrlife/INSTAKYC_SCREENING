# Open-web adverse media workflow

The adverse media subsystem now consists of three cooperating components:

1. **HTTP gateway** – Accepts screening requests and exposes task status/artefact
   retrieval endpoints. Requests are persisted to Redis via BullMQ.
2. **Worker pool** – A configurable set of Puppeteer workers that reuse a shared
   Chromium instance. The workers extract Google News search results, capture a
   sanitised HTML snapshot, and produce full-page screenshots for audit trails.
3. **Artefact retention** – All outputs are written to `WEBSHOT_DIR` with a
   retention horizon (`ARTIFACT_RETENTION_HOURS`). The `cleanup` script is safe to
   run from cron or a container sidecar to purge expired artefacts.

## Job lifecycle

1. The gateway receives a request (`POST /tasks`) with `query`, optional `locale`,
   and `maxArticles` hints. The job is enqueued with retry/backoff parameters.
2. A worker dequeues the job, rotates the user-agent if configured, and navigates
   to Google News. Links are harvested from `<article>` cards.
3. The worker stores:
   - `page.html` – Sanitised using `sanitize-html` to remove scripts and unknown tags.
   - `screenshot.png` – Full-page PNG capture for visual auditability.
   - `summary.json` – Structured metadata with article headlines, URLs, timestamps,
     and retention deadlines.
4. The worker returns the `summary` payload to BullMQ. `/tasks/<id>` surfaces that
   payload and exposes direct download links for the artefacts.

## Operations

- **Scaling** – Increase `SCRAPE_CONCURRENCY` to add more simultaneous browser pages.
  For horizontal scaling, run additional replicas pointing at the same Redis queue.
- **Security** – Every HTTP call must include the `X-Service-Token` secret. The
  FastAPI gateway injects this automatically, and Docker secrets make it easy to
  rotate across environments. Artefacts are stored with predictable names that
  can be synced to durable storage (S3, GCS) using standard tooling.
- **Maintenance** – Schedule `npm run cleanup` (e.g. hourly) to enforce retention
  and `npm run rotate` to refresh the user-agent file when integrating proxy pools.
- **Extensibility** – Swap `captureSearch` in `server.js` to target other search
  engines or perform article content scraping before writing the summary.
- **Observability** – Scrape `GET /metrics` with Prometheus to collect request
  rates, durations, and queue behaviour. `/healthz` indicates readiness for the
  orchestration layer.
