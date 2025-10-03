#!/usr/bin/env bash
#
# Smoke-test helper for the InstaKYC Screening sanctions endpoint.
# Performs two lookups so operators can quickly validate the
# sanctions workflow against known queries.

set -euo pipefail

API_KEY="${1:-${API_KEY:-${SCREENING_API_KEY:-}}}"
if [[ -z "${API_KEY}" ]]; then
  echo "Error: API key must be supplied as the first argument or via the API_KEY/SCREENING_API_KEY environment variables." >&2
  exit 1
fi

BASE_URL="${BASE_URL:-http://localhost:8000}"

if [[ ! -t 1 ]]; then
  JQ_OPTS=""
else
  JQ_OPTS="-C"
fi

pretty_print() {
  if command -v jq >/dev/null 2>&1; then
    jq ${JQ_OPTS} .
  else
    cat
  fi
}

run_search() {
  local query="$1"
  local dob="${2:-}"
  local payload
  payload=$(python - <<'PY'
import json
import sys
query = sys.argv[1]
dob = sys.argv[2]
data = {"query": query}
if dob:
    data["date_of_birth"] = dob
print(json.dumps(data))
PY
"$query" "$dob")

  echo "\n🔍 Searching sanctions for: ${query}${dob:+ (DOB: ${dob})}"
  curl --fail --show-error --silent \
    -H "X-API-Key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -X POST "${BASE_URL}/sanctions/search" \
    -d "${payload}" \
    | pretty_print
}

run_search "Alexei Karpov" "1987-03-11"
run_search "Vladimir Putin"
