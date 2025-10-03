#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="compose-mvp.yml"
ENV_FILE=".env"
DATA_DIR="data/cache"

ensure_api_key() {
  local supplied_key=""
  local explicit_override=false
  if [[ -n "${CLI_API_KEY:-}" ]]; then
    supplied_key="${CLI_API_KEY}"
    explicit_override=true
  elif [[ -n "${START_API_KEY:-}" ]]; then
    supplied_key="${START_API_KEY}"
    explicit_override=true
  elif [[ -n "${SCREENING_API_KEY:-}" ]]; then
    supplied_key="${SCREENING_API_KEY}"
  elif [[ -n "${API_KEY:-}" ]]; then
    supplied_key="${API_KEY}"
  fi

  if [[ -f "$ENV_FILE" ]]; then
    local existing_key=""
    existing_key=$(grep -E '^SCREENING_API_KEY=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)
    if [[ -z "$existing_key" || "$existing_key" == "replace-with-your-api-key" ]]; then
      existing_key=$(grep -E '^API_KEY=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)
    fi

    if [[ -n "$existing_key" && "$existing_key" != "replace-with-your-api-key" ]]; then
      if [[ "$explicit_override" == true ]]; then
        if [[ "$supplied_key" != "$existing_key" ]]; then
          write_env_file "$supplied_key"
          echo "$supplied_key"
          return
        fi
        existing_key="$supplied_key"
      fi

      local api_key_line
      api_key_line=$(grep -E '^API_KEY=' "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true)
      if [[ -z "$api_key_line" || "$api_key_line" != "$existing_key" ]]; then
        write_env_file "$existing_key"
      fi
      echo "$existing_key"
      return
    fi
  fi

  if [[ -z "$supplied_key" ]]; then
    if [[ -t 0 ]]; then
      read -rsp "Enter API key for the screening service: " supplied_key
      echo
    else
      echo "[start] SCREENING_API_KEY is required. Provide it via START_API_KEY, SCREENING_API_KEY or API_KEY environment variables." >&2
      exit 1
    fi
  fi

  if [[ -z "$supplied_key" ]]; then
    echo "[start] API key cannot be empty." >&2
    exit 1
  fi

  write_env_file "$supplied_key"
  echo "$supplied_key"
}

write_env_file() {
  local key="$1"

  if [[ -f "$ENV_FILE" ]]; then
    local backup="${ENV_FILE}.bak.$(date +%s)"
    cp "$ENV_FILE" "$backup"
    echo "[start] Existing $ENV_FILE detected. A backup was written to $backup" >&2
  fi

  local tmp
  tmp=$(mktemp)
  if [[ -f "$ENV_FILE" ]]; then
    { grep -Ev '^(SCREENING_API_KEY|API_KEY)=' "$ENV_FILE" 2>/dev/null || true; } >>"$tmp"
  fi
  printf 'SCREENING_API_KEY=%s\nAPI_KEY=%s\n' "$key" "$key" >>"$tmp"
  mv "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "[start] Environment written to $ENV_FILE"
}

usage() {
  cat <<'USAGE'
Usage: ./start.sh [--build] [--api-key <key>]

Builds (optional) and starts the InstaKYC Screening MVP stack using Docker Compose.
Pass --build to force a container rebuild before starting.
Provide the screening API key with --api-key when running in non-interactive environments.
The script writes/updates .env as needed and will prompt for the API key unless
an API key is supplied via --api-key or the START_API_KEY, SCREENING_API_KEY or API_KEY
environment variables.
USAGE
}

CLI_API_KEY=""
rebuild=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --build)
      rebuild=true
      shift
      ;;
    --api-key)
      if [[ $# -lt 2 ]]; then
        echo "[start] --api-key requires a value." >&2
        usage >&2
        exit 1
      fi
      CLI_API_KEY="$2"
      shift 2
      ;;
    --api-key=*)
      CLI_API_KEY="${1#*=}"
      shift
      ;;
    *)
      echo "[start] Unexpected arguments: $*" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "[start] Cannot find $COMPOSE_FILE. Run the script from the repository root." >&2
  exit 1
fi

api_key_value=$(ensure_api_key)

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[start] Failed to create $ENV_FILE." >&2
  exit 1
fi

set -o allexport
source "$ENV_FILE"
set +o allexport

if [[ -z "${SCREENING_API_KEY:-}" ]]; then
  SCREENING_API_KEY="$api_key_value"
fi

if [[ -z "${API_KEY:-}" ]]; then
  API_KEY="$api_key_value"
fi

export SCREENING_API_KEY
export API_KEY

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
