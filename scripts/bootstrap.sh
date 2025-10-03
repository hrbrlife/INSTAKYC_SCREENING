#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <api-key>" >&2
  exit 1
fi

API_KEY="$1"
ENV_FILE=".env"

cat > "$ENV_FILE" <<EOT
API_KEY=$API_KEY
SCREENING_API_KEY=$API_KEY
EOT

echo "Environment written to $ENV_FILE"
echo "Run 'docker compose -f compose-mvp.yml up --build -d' to start the stack."
