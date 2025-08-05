#!/usr/bin/env bash
set -euo pipefail
TAG="$(date +%Y%m%d)"
docker build \
  --build-arg ZAVOD_VERSION=latest \
  -t registry.local/opensanctions/zavod:$TAG \
  -f ./docker/opensanctions/zavod/Dockerfile .
docker run --rm \
  -v /srv/opensanctions/data:/data \
  registry.local/opensanctions/zavod:$TAG \
  zavod crawl all --export /data/export.tar.gz
echo "Build complete: $TAG"
