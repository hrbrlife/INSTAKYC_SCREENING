# InstaKYC Screening MVP API reference

The consolidated FastAPI service exposes three screening workflows guarded by a
single API key. All requests must include the `X-API-Key` header populated with
the value supplied when running `./start.sh`.

## `POST /sanctions/search`
- **Purpose**: Fuzzy-match names against the cached OpenSanctions
  `targets.simple.csv` export.
- **Body**:
  ```json
  {
    "query": "Jane Doe",
    "limit": 5,
    "min_score": 70,
    "date_of_birth": "1980-01-01"
  }
  ```
- **Response**:
  ```json
  {
    "query": "Jane Doe",
    "count": 1,
    "matches": [
      {
        "entity_id": "GB1234",
        "name": "Jane Doe",
        "score": 92,
        "datasets": ["ofac", "uk_hmt"],
        "topics": ["terrorism"],
        "countries": ["GB"],
        "birth_dates": ["1980-01-01"]
      }
    ]
  }
  ```
- **Notes**: The dataset is refreshed automatically every 12 hours and cached
  under `data/cache/` (or the mounted volume). When the download fails or the
  cache is unavailable the endpoint will respond with `503 Service Unavailable`
  until a fresh copy is retrieved.

## `POST /web/reputation`
- **Purpose**: Return the top DuckDuckGo News articles for an entity or keyword.
- **Body**:
  ```json
  {
    "query": "Acme Corporation"
  }
  ```
- **Response**:
  ```json
  {
    "query": "Acme Corporation",
    "count": 3,
    "results": [
      {
        "title": "Acme expands into new markets",
        "url": "https://example.com/story",
        "published": "2024-01-02T08:00:00Z",
        "source": "Example News",
        "snippet": "The company announced...",
        "html": {
          "path": "20240515/120102_acme-expands-into-new-markets_ab12cd34.html",
          "absolute_path": "/app/data/web/20240515/120102_acme-expands-into-new-markets_ab12cd34.html",
          "content_type": "text/html",
          "size_bytes": 10428
        },
        "text": {
          "path": "20240515/120102_acme-expands-into-new-markets_ab12cd34.txt",
          "absolute_path": "/app/data/web/20240515/120102_acme-expands-into-new-markets_ab12cd34.txt",
          "content_type": "text/plain",
          "size_bytes": 2580
        },
        "screenshot": {
          "path": "20240515/120102_acme-expands-into-new-markets_ab12cd34.png",
          "absolute_path": "/app/data/web/20240515/120102_acme-expands-into-new-markets_ab12cd34.png",
          "content_type": "image/png",
          "size_bytes": 52312
        }
      }
    ]
  }
  ```
- **Notes**: Safe-search is set to `moderate` by default. Results include the
  fields returned by DuckDuckGo's news API and, when retrieval succeeds, the
  artefact metadata for the sanitised HTML snapshot, extracted plain-text
  summary, and captured screenshot. The `path` field is relative to the
  configured `WEB_ARTIFACT_DIR`, allowing downstream services to expose the
  files via HTTP if required. If DuckDuckGo cannot be reached a `503 Service
  Unavailable` response is returned describing the upstream error.

## `POST /tron/reputation`
- **Purpose**: Profile a Tron address using the public TronScan API and return a
  deterministic risk score.
- **Body**:
  ```json
  {
    "address": "TMwFHYXLJaRUPeW6421aqXL4ZEzPRFGkGT"
  }
  ```
- **Response**:
  ```json
  {
    "address": "TMwFHYXLJaRUPeW6421aqXL4ZEzPRFGkGT",
    "risk": "medium",
    "score": 45,
    "reasons": [
      "Active address with many transfers",
      "TRX balance exceeds 100k tokens"
    ],
    "stats": {
      "transaction_count": 1200,
      "trx_balance": 250000.0,
      "recent_in": 5,
      "recent_out": 10,
      "trc20_tokens": 2
    }
  }
  ```
- **Notes**: The raw TronScan payload is included in the response for forensic
  follow-ups, and HTTP timeouts are capped at 12 seconds by default.

## Health endpoint
- **`GET /healthz`** returns service status along with the sanctions dataset
  metadata and timestamp of the last refresh.

## Error handling
- Requests without the `X-API-Key` header return `401 Unauthorized`.
- DuckDuckGo and OpenSanctions outages surface as `503 Service Unavailable`
  responses that include a human-readable error message.
- Upstream HTTP errors from the TronScan API are surfaced as `502 Bad Gateway`.
- Validation errors (missing body fields, invalid address) return
  `400 Bad Request`.
