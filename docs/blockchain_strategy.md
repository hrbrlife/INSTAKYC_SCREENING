# Blockchain screening strategy

## Executive summary
GraphSense remains the most viable option for delivering on-chain risk
analytics without signing commercial SaaS agreements. A discovery exercise
compared self-hosting GraphSense with commercially managed platforms such as
Chainalysis KYT, TRM Labs, Merkle Science, and Bitquery. None of the
third‑party APIs offer redistribution rights that align with the open-stack
ethos of InstaKYC, and the per-lookup costs would quickly exceed the
prototyping budget. The team will therefore proceed with an open-source,
self-managed GraphSense deployment backed by dedicated infrastructure and a
repeatable ETL process.

The selected architecture provisions a three-node Cassandra cluster, a
separate Spark-based ETL environment, and object storage for raw blockchain
dumps. Prefect is introduced to orchestrate the ingestion workflow and to
record operational metadata. The resulting plan describes the exact resource
sizes, network layout, security controls, and scheduling cadence required to
bring the dormant `graphsense_api` and `graphsense_ingest` containers to life.

## Requirements recap
- Evaluate alternatives to confirm GraphSense is still the preferred solution.
- Design infrastructure capable of hosting production-grade GraphSense
  services, including data retention and backup strategies.
- Provide an actionable ETL implementation plan with automation and
  documentation so that the dataset powering the REST API remains fresh.

## Option assessment
| Option | Pros | Cons | Decision |
| --- | --- | --- | --- |
| Self-host GraphSense | Open-source stack, unrestricted data residency, tight
integration with existing Compose services, strong community support. | Requires
Cassandra expertise, Spark cluster management, large storage footprint, complex
ETL. | **Proceed.** Most control and aligns with open-source policy. |
| GraphSense Cloud (managed) | Operated by the GraphSense maintainers, rapid
setup. | No EU-hosted region guaranteeing data residency, commercial contract
required, limited ability to customise ETL cadence. | Rejected – similar effort
is needed to integrate, but long-term costs exceed self-hosting. |
| Chainalysis KYT / TRM Labs / Merkle Science | Rich risk scores, KYT case
management features, SLAs. | High per-query cost, closed-source, contractual
constraints prevent bundling with InstaKYC demo environments. | Rejected – not
compatible with the project's open distribution goals. |
| Bitquery AML API | Lightweight API, granular address labelling. | Requires
continuous paid access and rate limiting, incomplete coverage for privacy
coins, no bulk export rights. | Rejected – API-first approach incompatible with
offline analytics and internal investigations. |

## Target architecture
### High-level components
1. **Cassandra cluster** – Stores the GraphSense keyspace. Three c6i.4xlarge
   instances (16 vCPU, 32 GiB RAM) per environment with 4 TB gp3 volumes each
   provide enough throughput for Bitcoin, Ethereum, and Litecoin datasets with
   headroom for two-year growth. Replication factor is set to 3 using the
   `NetworkTopologyStrategy` across two availability zones.
2. **Spark ETL environment** – Managed EMR (or Dataproc) cluster spun up on
   demand for ingestion runs. A single `m6i.2xlarge` driver with three
   `r6i.4xlarge` workers yields ~48 vCPU/192 GiB RAM, matching GraphSense's
   reference sizing.
3. **Object storage** – Versioned S3 bucket `instakyc-graphsense-raw` stores
   blockchain dumps downloaded from BigQuery via the
   `blockchain-etl` public dataset. Lifecycle rules transition artefacts older
   than 30 days to infrequent access and delete after 180 days once data has
   been compacted into Cassandra.
4. **Prefect server** – New `prefect` service orchestrates ETL flows and keeps
   run metadata. It reuses the existing Redis deployment for the orchestration
   queue and writes flow logs to CloudWatch.
5. **graphsense_api / graphsense_ingest containers** – Updated to authenticate
   against Cassandra via IAM-authenticated users and to expose TLS through the
   existing API gateway once milestone 5 introduces service-to-service auth.

### Network and security controls
- Place Cassandra nodes in private subnets with security groups allowing only
  the GraphSense API tasks, ETL nodes, and bastion hosts. SSH access requires
  MFA-backed SSM Session Manager.
- Enable TLS (via `client_encryption_options`) and role-based authentication in
  Cassandra. Application credentials are issued via AWS Secrets Manager and
  rotated quarterly.
- Spark cluster runs in a dedicated subnet and accesses S3 through VPC
  endpoints to avoid public internet exposure.
- Object storage buckets enforce server-side encryption with AWS KMS keys and
  block public access. CloudTrail is configured to monitor data access.
- Daily snapshots of Cassandra volumes are captured using AWS Backup with a
  35-day retention policy and weekly copies to a disaster-recovery region.

## ETL implementation plan
### Data sources and preparation
- Bitcoin, Ethereum, and Litecoin datasets are sourced from
  `bigquery-public-data.crypto_*` tables maintained by the
  `blockchain-etl` project. Export manifests are generated using the
  `google-cloud-bigquery` Python client.
- Raw parquet exports are staged to `s3://instakyc-graphsense-raw/{chain}/` with
  partitioning by block height range (e.g. `h=00000000-00999999`).
- Ancillary datasets (sanctioned address lists, exchange ownership metadata)
  are stored alongside the raw chain data and versioned independently.

### Prefect flow
A new `blockchain_pipeline` Python package contains a Prefect flow that
coordinates ingestion. Each run performs:
1. **Extract** – Launches a temporary Dataproc cluster and triggers the
   `graphsense-etl` Spark job using chain-specific YAML configs committed in
   `blockchain_pipeline/config/`. Credentials for BigQuery and AWS are injected
   through Prefect blocks.
2. **Load** – Once parquet outputs land in S3, the flow spins up a transient
   `graphsense_ingest` task container (via ECS Fargate) to import data into the
   Cassandra keyspace. Imports execute within the VPC and authenticate using the
   `graphsense_ingest` service account.
3. **Post-processing** – After each successful load, the flow computes rollup
   statistics (total entities, risk labels imported) and publishes them to the
   monitoring topic defined in milestone 5.
4. **Validation** – Prefect tasks invoke the `/health` and `/status` endpoints
   of the `graphsense_api` service to confirm the dataset version matches the
   ingestion timestamp.

The module also exposes a CLI (`python -m blockchain_pipeline.schedule`) that
falls back to generating a cron entry for environments where Prefect cannot be
used. This ensures the ETL cadence can be reproduced locally.

### Scheduling
- **Cadence** – Bitcoin and Ethereum refresh nightly at 02:00 UTC. Litecoin
  runs twice per week due to lower transaction volume.
- **Runtime expectations** – Each nightly pipeline run processes roughly 24
  hours of data (≈1.5M Bitcoin transactions, 1.8M Ethereum transactions) in ~90
  minutes, including Spark cluster provisioning. Litecoin updates complete in ~
  40 minutes.
- **Failure handling** – Prefect retries individual tasks up to three times with
  exponential backoff. If a run fails, alerts are pushed to PagerDuty and the
  flow can be rerun from the failed task to avoid reprocessing historical data.

### Operational runbook
1. On-call engineer receives an alert when a Prefect flow run fails or when
   validation detects stale data (>36 hours old).
2. Use Prefect UI to inspect task logs. If Spark job errors originate from
   BigQuery export rate limits, trigger the manual backfill by running
   `python -m blockchain_pipeline.backfill --chain bitcoin --start-date ...`.
3. If Cassandra ingestion fails, verify node health via `nodetool status`. Drain
   and replace unhealthy nodes using the infrastructure-as-code module documented
   in milestone 6.
4. Post-incident, document the root cause in the `docs/operations/runbooks/`
   folder and schedule corrective actions.

## Next steps
- Commit infrastructure-as-code templates (Terraform) expressing the above
  topology. Target completion alongside milestone 6.
- Extend the API gateway with `/crypto/address/{hash}` and `/crypto/entity/{id}`
  endpoints once the GraphSense REST API is populated.
- Integrate Prefect health metrics with the monitoring stack introduced in
  milestone 5.
- Evaluate adding Monero support after initial launch; this requires additional
  storage and anonymisation heuristics beyond the baseline plan.
