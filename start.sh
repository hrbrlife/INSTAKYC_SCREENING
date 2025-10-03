#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="compose-mvp.yml"
ENV_FILE=".env"
DATA_DIR="data/cache"

log_info() {
  echo "[start] $*"
}

log_warn() {
  echo "[start][warn] $*" >&2
}

log_error() {
  echo "[start][error] $*" >&2
}

SUDO=""
if [[ $(id -u) -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    log_warn "Running without root privileges and sudo is unavailable. Operations requiring elevated privileges may fail."
  fi
fi

run_privileged() {
  if [[ -n "$SUDO" ]]; then
    "$SUDO" -E "$@"
  else
    "$@"
  fi
}

require_privileged() {
  if [[ $(id -u) -eq 0 || -n "$SUDO" ]]; then
    return
  fi
  log_error "This operation requires administrator privileges. Re-run with sudo or as root."
  exit 1
}

generate_dev_api_key() {
  tr -dc 'A-Za-z0-9' </dev/urandom | head -c 40
}

ensure_prerequisites() {
  if ! command -v apt-get >/dev/null 2>&1; then
    log_warn "apt-get not found. Skipping automatic dependency installation."
    return
  fi

  local packages=(ca-certificates curl gnupg lsb-release)
  local to_install=()

  for pkg in "${packages[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      to_install+=("$pkg")
    fi
  done

  if [[ ${#to_install[@]} -eq 0 ]]; then
    return
  fi

  log_info "Installing prerequisite packages: ${to_install[*]}"
  require_privileged
  run_privileged apt-get update
  DEBIAN_FRONTEND=noninteractive run_privileged apt-get install -y "${to_install[@]}"
}

add_docker_repository() {
  require_privileged

  run_privileged install -m 0755 -d /etc/apt/keyrings

  local gpg_tmp
  gpg_tmp=$(mktemp)
  curl -fsSL https://download.docker.com/linux/debian/gpg -o "$gpg_tmp"

  local key_tmp
  key_tmp=$(mktemp)
  gpg --dearmor --yes --output "$key_tmp" "$gpg_tmp"
  run_privileged install -m 0644 "$key_tmp" /etc/apt/keyrings/docker.gpg
  rm -f "$gpg_tmp" "$key_tmp"

  local arch
  arch=$(dpkg --print-architecture)
  local codename=""
  if command -v lsb_release >/dev/null 2>&1; then
    codename=$(lsb_release -cs)
  elif [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    codename="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"
  fi
  if [[ -z "$codename" ]]; then
    codename="bookworm"
    log_warn "Unable to detect Debian codename automatically. Defaulting to 'bookworm'."
  fi

  local repo_entry="deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian ${codename} stable"
  echo "$repo_entry" | run_privileged tee /etc/apt/sources.list.d/docker.list >/dev/null
}

ensure_docker_running() {
  if command -v systemctl >/dev/null 2>&1; then
    if ! run_privileged systemctl is-active --quiet docker; then
      log_info "Starting docker service via systemd"
      if ! run_privileged systemctl enable --now docker; then
        log_warn "Failed to start docker with systemd."
      fi
    fi
  elif command -v service >/dev/null 2>&1; then
    log_info "Starting docker service via service command"
    if ! run_privileged service docker start >/dev/null 2>&1; then
      log_warn "Failed to start docker service."
    fi
  else
    log_warn "No known service manager found to start docker automatically."
  fi
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && run_privileged docker compose version >/dev/null 2>&1; then
    ensure_docker_running
    return
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    log_error "Docker is not installed and automatic installation is unavailable without apt-get."
    exit 1
  fi

  log_info "Docker not detected. Installing Docker Engine and Compose plugin."
  ensure_prerequisites
  add_docker_repository
  run_privileged apt-get update
  DEBIAN_FRONTEND=noninteractive run_privileged apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  ensure_docker_running

  if ! command -v docker >/dev/null 2>&1; then
    log_error "Docker installation failed."
    exit 1
  fi

  if ! run_privileged docker compose version >/dev/null 2>&1; then
    log_error "Docker Compose plugin installation failed."
    exit 1
  fi
}

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
      log_warn "No API key provided via environment. Generating a local development key."
      supplied_key=$(generate_dev_api_key)
    fi
  fi

  if [[ -z "$supplied_key" ]]; then
    log_warn "Empty API key supplied. Generating a local development key."
    supplied_key=$(generate_dev_api_key)
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

ensure_docker

if ! command -v docker >/dev/null 2>&1; then
  log_error "Docker binary not found after installation."
  exit 1
fi

DOCKER_PREFIX=()
if [[ $(id -u) -ne 0 ]]; then
  if id -nG "$(id -un)" 2>/dev/null | tr ' ' '\n' | grep -qx docker; then
    :
  elif [[ -n "$SUDO" ]]; then
    DOCKER_PREFIX=("$SUDO")
  else
    log_error "Current user is not in the docker group and sudo is unavailable."
    exit 1
  fi
fi

if ! "${DOCKER_PREFIX[@]}" docker compose version >/dev/null 2>&1; then
  log_error "docker compose plugin is required."
  exit 1
fi

compose_cmd=("${DOCKER_PREFIX[@]}" docker compose)

if ! "${DOCKER_PREFIX[@]}" docker info >/dev/null 2>&1; then
  log_warn "Docker daemon is not responding. Attempting to start the service."
  ensure_docker_running
  if ! "${DOCKER_PREFIX[@]}" docker info >/dev/null 2>&1; then
    log_error "Unable to communicate with the Docker daemon."
    exit 1
  fi
fi

compose_args=("-f" "$COMPOSE_FILE" "up")
if [[ "$rebuild" == true ]]; then
  compose_args+=("--build")
fi
compose_args+=("-d")

"${compose_cmd[@]}" "${compose_args[@]}"

echo "[start] Stack running. Use '${compose_cmd[*]} -f ${COMPOSE_FILE} ps' to check status."
