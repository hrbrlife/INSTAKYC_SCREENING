#!/usr/bin/env bash
set -euo pipefail

# Containerised wrapper that reuses the Python helper living in
# ``sanctions_pipeline.build``. This keeps the build behaviour identical across
# bare-metal, CI and Docker workflows while still producing the ``export.tar.gz``
# archive expected by the Yente service.

TAG="$(date +%Y%m%d)"

docker build \
  --build-arg ZAVOD_VERSION=latest \
  -t "registry.local/opensanctions/zavod:${TAG}" \
  -f ./docker/opensanctions/zavod/Dockerfile .

docker run --rm \
  -v "$(pwd)":/workspace \
  -v /srv/opensanctions/data:/data \
  -w /workspace \
  "registry.local/opensanctions/zavod:${TAG}" \
  python -m sanctions_pipeline.build \
    --dataset sanctions \
    --export-path /data/export.tar.gz \
    --cache-path /data/.cache

docker push "registry.local/opensanctions/zavod:${TAG}"
echo "Build complete: ${TAG}"
