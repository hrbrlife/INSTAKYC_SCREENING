# Adverse media browser worker

This service provides an HTTP gateway and worker for running open-web adverse media
searches. Requests are enqueued in Redis using [BullMQ](https://docs.bullmq.io/),
processed by a shared headless Chromium instance via Puppeteer, and the resulting
artefacts (HTML snapshot, JSON summary, screenshot) are stored in a retention-
managed directory.

## Features

- Queue-driven scraping with retry/backoff and configurable concurrency.
- Screenshot capture and sanitised HTML snapshot per search run.
- Downloadable artefacts served through authenticated-friendly HTTP endpoints.
- Simple user-agent rotation hook to integrate with proxy pools.
- Retention-aware cleanup script for wiping expired artefacts.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | `redis://127.0.0.1:6379` | Redis connection string for BullMQ. |
| `MEDIA_QUEUE_NAME` | `adverse-media-search` | Queue name for submitted jobs. |
| `PUPPETEER_HEADLESS` | `true` | Set to `false` to run Chromium with UI. |
| `WEBSHOT_DIR` | `/tmp/webshot` | Directory used to store artefacts. |
| `SCRAPE_CONCURRENCY` | `2` | Number of concurrent browser jobs. |
| `SCRAPE_MAX_ATTEMPTS` | `3` | Maximum retries per job. |
| `NAVIGATION_TIMEOUT_MS` | `20000` | Timeout for page navigation/wait conditions. |
| `ARTIFACT_RETENTION_HOURS` | `24` | Retention window used by the cleanup script. |
| `DEFAULT_MAX_ARTICLES` | `5` | Default number of headlines collected per query. |
| `USER_AGENT_FILE` | `<WEBSHOT_DIR>/user-agent.txt` | Optional user-agent override produced by `npm run rotate`. |

## API

### Submit a search

```http
POST /tasks
Content-Type: application/json

{
  "query": "ACME Corp corruption",
  "locale": "en-US",
  "maxArticles": 5,
  "metadata": { "caseId": "kyc-123" }
}
```

Returns `202 Accepted` with the job identifier.

### Check job status

```http
GET /tasks/<jobId>
```

Shows the queue state and, when complete, includes the summary object returned by
Puppeteer.

### Download artefacts

```http
GET /tasks/<jobId>/artifacts/{html|screenshot|summary}
```

Streams the stored snapshot, image, or summary JSON.

## Maintenance scripts

- `npm run cleanup` – removes artefacts that have aged past the retention window.
- `npm run rotate` – writes a random desktop browser user-agent string to
  `${USER_AGENT_FILE}`. Integrate this with proxy rotation or scheduled jobs.

## Local development

Install dependencies and start the worker locally:

```bash
npm install
npm start
```

Ensure a Redis instance is available (for example, `docker run -p 6379:6379 redis:7`).
