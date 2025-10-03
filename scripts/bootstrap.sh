#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 <api-key>

Bootstraps the InstaKYC screening MVP by writing the .env file and ensuring
that the persistent data directory exists. Provide the single API key that will
be required for all requests to the service.
USAGE
}

if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 1
fi

API_KEY="$1"
if [[ -z "$API_KEY" ]]; then
  echo "[bootstrap] Error: API key cannot be empty." >&2
  exit 1
fi

ENV_FILE=".env"
DATA_DIR="data/cache"

if [[ -e "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "${ENV_FILE}.bak"
  echo "[bootstrap] Existing $ENV_FILE detected. A backup was written to ${ENV_FILE}.bak" >&2
fi

mkdir -p "$DATA_DIR"

cat > "$ENV_FILE" <<EOT
API_KEY=$API_KEY
SCREENING_API_KEY=$API_KEY
EOT

chmod 600 "$ENV_FILE"

echo "[bootstrap] Environment written to $ENV_FILE"
echo "[bootstrap] Dataset cache directory ensured at $DATA_DIR"

docker_available=true
if ! command -v docker >/dev/null 2>&1; then
  docker_available=false
  echo "[bootstrap] Warning: docker is not installed or not in PATH." >&2
fi

compose_cmd="docker compose"
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    compose_cmd="docker-compose"
  else
    compose_cmd="docker compose"
    echo "[bootstrap] Warning: docker compose command not detected. Install Docker Desktop or docker-compose." >&2
  fi
fi

if [[ "$docker_available" == true ]]; then
  echo "[bootstrap] Next step: start the stack with '$compose_cmd -f compose-mvp.yml up --build -d'"
else
  echo "[bootstrap] Install Docker and rerun the compose command to start the stack." >&2
fi
