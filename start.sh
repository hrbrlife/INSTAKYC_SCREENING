#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="compose-mvp.yml"
ENV_FILE=".env"
DATA_DIR="data/cache"

usage() {
  cat <<USAGE
Usage: ./start.sh [--build]

Builds (optional) and starts the InstaKYC Screening MVP stack using Docker Compose.
Pass --build to force a container rebuild before starting.
USAGE
}

if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
  usage
  exit 0
fi

rebuild=false
if [[ ${1-} == "--build" ]]; then
  rebuild=true
  shift || true
fi

if [[ $# -gt 0 ]]; then
  echo "[start] Unexpected arguments: $*" >&2
  usage >&2
  exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[start] Cannot find $COMPOSE_FILE. Run the script from the repository root." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[start] Missing $ENV_FILE. Copy .env.example and update the values before starting." >&2
  exit 1
fi

set -o allexport
source "$ENV_FILE"
set +o allexport

if [[ -z "${SCREENING_API_KEY:-}" ]]; then
  echo "[start] SCREENING_API_KEY is not set in $ENV_FILE." >&2
  exit 1
fi

mkdir -p "$DATA_DIR"

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    compose_cmd=(docker compose)
  else
    echo "[start] docker compose plugin is required." >&2
    exit 1
  fi
else
  echo "[start] docker is required to run the stack." >&2
  exit 1
fi

compose_args=("-f" "$COMPOSE_FILE" "up")
if [[ "$rebuild" == true ]]; then
  compose_args+=("--build")
fi
compose_args+=("-d")

"${compose_cmd[@]}" "${compose_args[@]}"

echo "[start] Stack running. Use '${compose_cmd[*]} -f ${COMPOSE_FILE} ps' to check status."
