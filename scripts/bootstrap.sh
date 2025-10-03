#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <api-key>" >&2
  exit 1
fi

API_KEY="$1"
ENV_FILE=".env"
DATA_DIR="data/cache"

mkdir -p "$DATA_DIR"

cat > "$ENV_FILE" <<EOT
API_KEY=$API_KEY
SCREENING_API_KEY=$API_KEY
EOT

chmod 600 "$ENV_FILE"

echo "Environment written to $ENV_FILE"
echo "Dataset cache directory ensured at $DATA_DIR"
echo "Run 'docker compose -f compose-mvp.yml up --build -d' to start the stack."
