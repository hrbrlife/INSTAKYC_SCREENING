# Development roadmap

This roadmap reflects the current state of the repository and the work required
to transform the proof of concept into a usable compliance screening platform.
Tasks are grouped by milestone so that progress can be tracked incrementally.

## Milestone 1 – Stabilise the existing prototype
- [x] Provide default environment variable handling for the API gateway so it
  can start without manual `.env` injection during development.
- [x] Containerise Redis persistence and add basic authentication if the queue
  is exposed outside the Docker network.
- [x] Remove the placeholder `traefik` proxy to reduce confusion until routing
  and TLS requirements are defined.
- [x] Document how to run the stack end-to-end, including expected failure modes
  for unimplemented services.

## Milestone 2 – Sanctions data ingestion
- [x] Confirm the desired OpenSanctions subset and the storage capacity
  available for exported datasets. Documented in `docs/sanctions_ingestion.md`.
- [x] Automate `zavod` execution (cron, CI job, or manual playbook) and publish
  the resulting archive to the volume mounted by `sanctions_core` via the
  `sanctions_pipeline.build` helper.
- [x] Validate the `yente` API by smoke-testing `/entities/{id}`, `/search`, and
  `/match` endpoints using the `sanctions_pipeline.validate` CLI.

## Milestone 3 – Blockchain screening strategy
- [x] Determine whether GraphSense is still the preferred stack given the
  infrastructure requirements. If not, research alternative services or API
  providers. See `docs/blockchain_strategy.md` for the evaluation and decision.
- [x] When proceeding with GraphSense, design the Cassandra deployment
  (replication factor, disk size, backup plan) and secure access to blockchain
  nodes or public datasets. Detailed sizing and network requirements are
  captured in `docs/blockchain_strategy.md`.
- [x] Implement and schedule the ETL jobs that feed the REST API; document the
  refresh cadence. A Prefect-based orchestration plan, operational runbook, and
  cronfall-back are included in `docs/blockchain_strategy.md`.

## Milestone 4 – Open-web adverse media
- [x] Replace the Node stub with a browser automation service (Puppeteer, Playwright,
  or a managed alternative) capable of fetching search results and screenshots.
- [x] Introduce a real task queue/worker model so that scraping is resilient and
  throughput can scale horizontally.
- [x] Capture artefacts (HTML, screenshots, summaries) in a location governed by
  retention policies and add a sanitisation routine.

The resulting workflow and operational guidance are documented in
`docs/adverse_media_workflow.md`.

## Milestone 5 – Platform operations and security
- [x] Implement authentication and authorisation for every service exposed by
  the stack. Scoped API keys protect the FastAPI gateway while the Puppeteer
  worker now requires a service token on every request.
- [x] Instrument key services with request metrics and health checks; publish
  dashboards and alerts. Both the gateway and Puppeteer worker expose
  Prometheus metrics alongside health endpoints for orchestration checks.
- [x] Harden container configurations (least privilege users, resource limits,
  network policies) and ensure secrets are managed through vaulting or Docker
  secrets. Containers now run as non-root users and the Docker Compose plugin
  consumes Docker secrets for API keys, Redis credentials, and service tokens.

## Milestone 6 – Delivery pipeline
- [ ] Add automated testing, linting, and image builds to a CI system.
- [ ] Produce versioned container images and deploy them to a registry.
- [ ] Create infrastructure-as-code or Ansible playbooks so that environments
  can be recreated consistently.

Revisit and refine this roadmap as architectural decisions are made. Each
milestone should be considered complete only once the associated documentation
and runbooks have been updated.
