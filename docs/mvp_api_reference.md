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
    "min_score": 70
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
        "countries": ["GB"]
      }
    ]
  }
  ```
- **Notes**: The dataset is refreshed automatically every 12 hours and cached
  under `data/cache/` (or the volume mounted into the container).

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
        "snippet": "The company announced..."
      }
    ]
  }
  ```
- **Notes**: Safe-search is set to `moderate` by default. Results include the
  fields returned by DuckDuckGo's news API.

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
- Upstream HTTP errors from the TronScan API are surfaced as `502 Bad Gateway`.
- Validation errors (missing body fields, invalid address) return
  `400 Bad Request`.
