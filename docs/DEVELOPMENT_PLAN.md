# Development & Deployment Roadmap

This document breaks down the implementation described in the README into actionable milestones. Each milestone contains a set of tasks that can be tracked during development and deployment. Details are preserved from the original design to retain context and nuance.

## Milestone 1: Host Provisioning & Base Tooling
- [ ] Install Debian 12 on the target host and apply security patches.
- [ ] Enable rootless Docker with `dockerd-rootless-setuptool.sh install` and install Docker Engine and docker compose.
- [ ] Install Ansible 8.x on the control node.
- [ ] Prepare separate sub-nets and configure least-privilege users for containers.

## Milestone 2: Sanctions / PEP Engine
- [x] Nightly build of `zavod` dataset:
  - [x] Create `docker/opensanctions/zavod` image with `docker build --build-arg ZAVOD_VERSION=latest`.
  - [x] Run ETL to export `/srv/opensanctions/data/export.tar.gz`.
  - [x] Schedule via cron `02:15 UTC` (see `docker/opensanctions/zavod.cron`) and push to local registry for immutability.
- [ ] Deploy `yente` API (`sanctions_core`):
  - Mount read-only volume with export tarball.
  - Configure environment variables:
    - `YENTE_INDEX_URL=http://elasticsearch:9200`
    - `YENTE_DATA_PATH=/data/export.tar.gz`
    - `YENTE_SCHEDULE="0 */6 * * *"`
    - `YENTE_AUTO_REINDEX="true"`
  - Ensure `GET /entities/{id}`, `GET /search`, and `POST /match` endpoints are reachable behind the API gateway.

## Milestone 3: Blockchain Screening (GraphSense)
- [ ] Deploy `graphsense_api` for REST access and `graphsense_ingest` for ETL workers.
- [ ] Persist data on dedicated volumes (`keyspace-data:`) and backup with `nodetool snapshot`.
- [ ] Verify `/health` endpoint returns `READY`.

## Milestone 4: Open-Web Adverse-Media Search
- [ ] Build `puppeteer_srv` container (`Node18 + Puppeteer + local llama.cpp`).
- [ ] Set environment variables:
  - `PUPPETEER_HEADLESS=true`
  - `REDIS_URL=redis://redis:6379/0`
- [ ] Implement proxy rotation via `npm run rotate`.
- [ ] Store transient screenshots in `/tmp/webshot` and ensure cron task wipes files older than five minutes.

## Milestone 5: Unified API Gateway
- [x] Build FastAPI gateway (`uvicorn`) with Swagger docs and authentication middleware.
- [ ] Configure environment variables:
  - `SANCTIONS_URL=http://sanctions_core:8000`
  - `CRYPTO_URL=http://graphsense_api:8000`
  - `WEB_URL=http://puppeteer_srv:7000`
  - `API_KEY=change_me`
- [ ] Integrate Redis queue for short-lived tasks and expose final REST API.

## Milestone 6: Docker Compose Orchestration
- [x] Assemble `compose-sanctions.yml` with services:
  - `sanctions_core`, `sanctions_build`, `graphsense_api`, `graphsense_ingest`, `puppeteer_srv`, `api_gateway`, `redis`, `traefik/nginx`.
- [ ] Run `docker compose --profile builder up sanctions_build` nightly and `docker compose up -d` for runtime services.
- [ ] Apply TLS ingress, rate limiting, and network isolation.

## Milestone 7: Data Retention & Security Controls
- [ ] Configure Redis: `--maxmemory 256mb --maxmemory-policy allkeys-lru`.
- [ ] Use `tmpfs` for `/tmp/webshot` and wipe with `find /tmp/webshot -type f -mmin +5 -delete`.
- [ ] Enable disk encryption (`dmcrypt`) for Docker volumes and rotate logs older than 14 days (`logrotate.d/kyc`).
- [ ] Block outbound packets except to sanctions sources, blockchain nodes, and search engines.

## Milestone 8: CI / CD Pipeline
- [ ] Implement GitLab CI with stages: `lint` → `build` → `deploy`.
- [ ] Tag container images with git SHA and sign digests using `cosign`.
- [ ] Run `ansible-playbook --check -e env=staging` in pipeline; deploy to staging on success.
- [ ] Require manual approval for promotion to production.

## Milestone 9: Operations & Monitoring
- [ ] Reference operational commands:
  - `docker compose restart sanctions_core` for hot reload.
  - `curl /health` for GraphSense status.
  - `docker exec puppeteer_srv bash -c "npm run rotate"` to rotate proxies.
  - `docker image prune -af` weekly; backup keyspace snapshots offline.
- [ ] Deploy Prometheus + Grafana sidecar with scrape targets:
  - `sanctions_core` latency histogram.
  - `graphsense_api` 5xx rate.
  - `puppeteer_srv` BullMQ queue length.
  - Host metrics (disk I/O, CPU).
- [ ] Configure alerting rules:
  - `sanctions_core` 5xx > 2% for 5 min.
  - GraphSense ingest lag > 12 h.
  - `puppeteer_srv` captcha errors.

## Milestone 10: Security Hardening
- [ ] Set `no-new-privileges: true` and `docker/default.json` seccomp profile for all services.
- [ ] Apply WAF rules in `traefik` against path traversal.
- [ ] Run quarterly `trivy fs /opt/kyc` scans and subscribe to OpenSanctions/GraphSense CVE feeds.
- [ ] Reject IPv6 NAT egress to avoid search engine IP leakage.

## Milestone 11: Future Extensions
- [ ] Integrate `followthemoney-resolvers` with customer CRM for pre-ingest cross-matching.
- [ ] Evaluate switching GraphSense backend to Apache Cassandra 5 to reduce storage.
- [ ] Replace `llama.cpp` with `Mistral 7B Instruct` quant-4 when licensing permits.
- [ ] Provide gRPC mirror of REST spec for high-volume clients.

---

Use this roadmap as a living document to track progress and assign responsibilities. Update task checkboxes as work is completed.
