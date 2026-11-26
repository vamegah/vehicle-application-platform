# Requirements Document

## Introduction

AutoReliance AI is an AI-powered automotive engineering, quality, and release assurance platform. The central question is: "Has this automotive software or hardware change been adequately validated, what risks remain, and what evidence supports releasing it?"

This document covers Phase 1 only: Foundation and Release Wedge. Phase 1 delivers the shared platform foundation (API Gateway, Kafka backbone, audit sink, observability, multi-tenancy, local development environment) and five problem modules:

1. Data Readiness (problem 4): ingestion, normalization, entity resolution, canonical identity events.
2. Legacy Integration (problem 8): connector framework, anti-corruption layer, one sample ERP/MES connector.
3. Integration Intelligence (problem 1): Neo4j dependency graph, change-impact traversal, integration risk prediction.
4. Configuration Assurance (problem 6): rule engine validating vehicle configurations.
5. Release Assurance (problem 2): evidence-sufficiency scoring, coverage gap detection, AI test selection, release gate.

Phases 2 to 4 are documented only as architectural continuity (see Requirement 24) and are not implemented.

### Scope assumptions for review

- **Approved decisions (ADR-001 to ADR-024 in `design.md`).** Phase 1 has five modules, each its own bounded context with its own PostgreSQL schema and its own versioned contracts: `data-readiness`, `legacy-integration`, `integration-intelligence`, `configuration-assurance`, and `release-assurance`. Together with `api-gateway` and `audit-sink` there are seven bounded-context directories under `services/`. They are packaged into five deployables: `data-platform` (`data-readiness` plus `legacy-integration`), `integration-config` (`integration-intelligence` plus `configuration-assurance`), `release-assurance`, `api-gateway`, and `audit-sink`. Inside a shared deployable, cross-context calls use the same contracts as if the contexts were separate services. The full ten-context topology remains the target for Phases 2 to 4. The Definition of Done phrase "all five Phase 1 services" means all five Phase 1 modules, packaged as five deployables.
- Services use the languages from the brief: `data-readiness` is Python/FastAPI; `legacy-integration` is a Java connector runtime; `integration-intelligence`, `configuration-assurance`, `release-assurance`, `api-gateway`, and `audit-sink` are Java/Spring Boot, and `release-assurance` has a co-deployed Python inference sidecar that uses scikit-learn and xgboost.
- Only the technology listed in the brief is used, plus the libraries the user approved with conditions in ADR-003 (Spring Cloud Gateway through its release-train BOM, Flyway and Alembic, Spring Vault pinned to 4.1.2 (ADR-010) and hvac, openapi-generator-cli and openapi-typescript, buf), and the object-storage additions the user approved in ADR-012 (an S3-compatible object store, the AWS SDK for Java v2, and boto3), with Garage as the local S3-compatible backend (ADR-013; SeaweedFS runs as a digest-pinned CI smoke-test container (ADR-020) and is the approved dev-backend alternative that does not run in dev unless the ADR-019 switch trigger is met; Ceph RGW is production on-prem only; and MinIO is not approved). Any other additional infrastructure or library requires user approval. PDF bytes are stored in the S3-compatible object store and never in PostgreSQL, which holds metadata and the object URI only (ADR-012). The default layout is two shared buckets per environment (`autoreliance-raw-{env}` and `autoreliance-text-{env}`) with a tenant key prefix, so the object store's bucket permissions enforce the read-only, text-only access of `data-readiness` and prefix-scoped policies enforce tenant isolation on AWS S3 and Ceph RGW (ADR-014 as amended by ADR-018). Garage cannot scope by prefix, so tenant isolation in local development rests on the Storage_Provider check, which is a recorded dev-only limitation. A dedicated bucket pair per Tenant is an opt-in exception with a documented approval path (ADR-018). Garage is the current local backend until the ADR-019 switch trigger is met (ADR-019, ADR-020). Production encrypts objects with per-tenant SSE-KMS keys and refuses to start without the per-tenant key strategy (ADR-015). The four ERP and MES topics use a connector-built `naturalKey`, a `contentHash`, an `extractedAt` timestamp, and an optional `sourceRecordVersion` in a source-ingestion envelope (ADR-016, ADR-017).
- Spring Boot 4.1.x with Spring Cloud 2025.1.x replaces the earlier Spring Boot 3.x pin (ADR-006). Kubernetes packaging uses Kustomize and Helm is deferred (ADR-007). PDF text reaches `data-readiness` only through the `document.text.extracted` event, and ERP and MES records reach it only through four domain topics (`erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, `mes.quality.inspection.recorded`), with data paths Kafka-only and no service-initiated synchronous HTTP between bounded contexts for data-plane operations (the sole exception is the read-only `/admin/*` layout cache read of criterion 12.20, ADR-024) and no combined record topic (ADR-008, ADR-011). `legacy-integration` runs one replica and `data-readiness` runs one Celery beat process in Phase 1 (ADR-009).
- All seed data is fictional and labeled as fictional.
- The steering files in `.kiro/steering/` (`product.md`, `tech.md`, `structure.md`, `api-standards.md`, `security.md`), `AGENTS.md`, `DEPENDENCIES.lock.md`, and `validation.md` are authoritative. Where this document conflicts with them, they win. The stack is Java 21, Spring Boot 4.1.x with Spring Cloud 2025.1.x, Python 3.12, PostgreSQL 16, Neo4j 5.x Community Edition (label-based tenancy), and Apache Kafka 3.x (Requirement 26).
- The platform adds catalog extensions beyond the brief's event list so that `release-assurance` can read risk scores from a local projection instead of calling other services synchronously (see `AGENTS.md`). The flat `risk.score.computed` topic is replaced by three domain-prefixed topics, each with its own AsyncAPI file and payload schema: `integration.risk.scored` (producer `integration-intelligence`), `configuration.risk.scored` (producer `configuration-assurance`), and `release.risk.scored` (producer `release-assurance`). `release-assurance` consumes the first two and does not consume the third. The approved `config.validation.completed` event is kept.
- Redis is part of the stack. Phase 1 uses it for background jobs in `data-readiness` (Celery broker) and as a token and rate-limit cache in `api-gateway`. Production runs two Redis instances (see Requirement 27); local development runs one.

## Glossary

- **AutoReliance_Platform**: The complete set of Phase 1 services, gateway, event backbone, and web application.
- **API_Gateway**: The single entry point for all frontend traffic. Exposes REST endpoints described by OpenAPI 3.1, enforces SSO and RBAC, and propagates tenant and trace context.
- **Web_App**: The Next.js, React, TypeScript, and Tailwind CSS frontend in `apps/web`.
- **Event_Backbone**: The Apache Kafka cluster carrying all asynchronous domain events.
- **Event**: A versioned Kafka message with the envelope `{ eventId, eventType, version, tenantId, occurredAt, payload }`, with W3C trace context carried in the Kafka record headers.
- **Contract_Registry**: The `contracts/` directory holding OpenAPI 3.1, AsyncAPI 3.0, and protobuf definitions.
- **Bounded_Context**: A domain area with its own `services/<context>/` directory, its own PostgreSQL schema, and its own versioned OpenAPI, AsyncAPI, and protobuf contracts.
- **Deployable**: A packaging unit defined under `platform/` that co-packages one or more Bounded_Contexts. The Phase 1 deployables are `data-platform`, `integration-config`, `release-assurance`, `api-gateway`, and `audit-sink`.
- **Data_Readiness_Service**: The `data-readiness` Bounded_Context (Python/FastAPI) that owns Data Readiness. It is packaged in the `data-platform` Deployable.
- **Legacy_Integration_Service**: The `legacy-integration` Bounded_Context (Java connector runtime) that owns Legacy Integration. It is packaged in the `data-platform` Deployable.
- **Configuration_Service**: The `configuration-assurance` Bounded_Context that owns Configuration Assurance. It is packaged in the `integration-config` Deployable.
- **Configuration_Risk_Scorer**: The Configuration_Service component that derives a configuration risk score from a configuration validation result.
- **Release_Risk_Scorer**: The Release_Service component that derives a release risk score from the Release_Projection.
- **Redis_Broker**: The Redis instance used only as the Celery broker for `data-readiness` background jobs.
- **Redis_Cache**: The Redis instance used only for the `api-gateway` token cache and rate-limit counters.
- **Ingestion_Pipeline**: The Data_Readiness_Service component that accepts raw source records and normalizes them.
- **Entity_Resolver**: The Data_Readiness_Service component that maps source identifiers to canonical identifiers.
- **Connector_Framework**: The Legacy_Integration_Service component that defines the contract for source system connectors.
- **Anti_Corruption_Layer**: The Legacy Integration component that translates legacy source models into canonical models.
- **Object_Store**: The S3-compatible object storage (AWS S3 or another S3-compatible service in the cloud, Ceph RGW on-prem in production, Garage in the Local_Environment) that holds PDF bytes in the Raw_Bucket and large extracted text objects in the Text_Bucket, separated by Tenant through a key prefix. MinIO is not approved.
- **Raw_Bucket**: The Object_Store bucket that holds raw PDF bytes under the key prefix `<tenantId>/raw/`. By default it is the shared bucket `autoreliance-raw-<env>`; for a Tenant with an approved dedicated layout it is `autoreliance-raw-<env>-<tenantId>`.
- **Text_Bucket**: The Object_Store bucket that holds large extracted text objects under the key prefix `<tenantId>/text/`. By default it is the shared bucket `autoreliance-text-<env>`; for a Tenant with an approved dedicated layout it is `autoreliance-text-<env>-<tenantId>`.
- **Storage_Layout**: The per-Tenant configuration value (`shared` by default, or `dedicated` for an approved exception) from which the Storage_Provider resolves the bucket name and key prefix of each role. The layout is configuration and not a separate code path.
- **Key_Strategy**: The setting `storage.encryption.key-strategy` (`per-tenant`, `shared`, or `none`) that selects how the Storage_Provider chooses the server-side encryption key for an object.
- **Source_Ingestion_Envelope**: The base Event envelope extended with `sourceSystem`, `naturalKey`, `contentHash`, `extractedAt`, and an optional `sourceRecordVersion`, required on the five `legacy-integration` source topics.
- **Natural_Key**: A delimited string built by a connector from named source columns, identifying one source record within a source system. It is never supplied by the source.
- **Storage_Provider**: The port, with an S3-compatible adapter, through which a Bounded_Context puts, gets, heads, deletes, and lists objects older than a cutoff in the Object_Store.
- **Sample_Connector**: The fictional ERP/MES connector delivered with the Connector_Framework.
- **Integration_Service**: The `integration-intelligence` Bounded_Context that owns Integration Intelligence. It is packaged in the `integration-config` Deployable and is the only Phase 1 context that accesses Neo4j.
- **Dependency_Graph**: The Neo4j graph of ECUs, firmware versions, calibration files, sensors, cloud services, and their dependencies, owned by the Integration_Service.
- **Impact_Analyzer**: The Integration_Service component that traverses the Dependency_Graph to compute change impact.
- **Risk_Predictor**: The Integration_Service component that computes an integration risk score for a firmware change.
- **Config_Rule_Engine**: The Configuration_Service component that evaluates configuration rules against a canonical configuration snapshot.
- **Release_Service**: The `release-assurance` Bounded_Context and Deployable that owns Release Assurance.
- **Evidence_Scorer**: The Release_Service component that computes an evidence-sufficiency score for a release candidate.
- **Gap_Detector**: The Release_Service component that identifies missing or insufficient evidence.
- **Test_Selector**: The Release_Service component, backed by the Python inference sidecar, that recommends tests for a change.
- **Release_Gate**: The Release_Service component that issues a release verdict for a release candidate.
- **Release_Candidate**: A release proposed for approval, defined as the tuple of an ECU set, firmware versions, calibration IDs, and test evidence, typically created from a firmware change or configuration.
- **Release_Projection**: The local read model inside `release-assurance`, built only from consumed Kafka Events, from which every score, gap, and verdict is computed.
- **Sufficiency_Threshold**: The minimum evidence-sufficiency score, set by the Tenant's release policy, below which a release is blocked.
- **Problem_Details**: An RFC 9457 error body served as `application/problem+json`.
- **Platform_Operator**: The RBAC role `platform-operator`, distinct from the six tenant roles and not tenant-scoped. It is the only role allowed to call routes under `/admin/`.
- **Internal_Principal**: A short-lived signed token issued by the API_Gateway that carries the authenticated user, roles, and Tenant ID to downstream services and that downstream services verify.
- **Dependency_Ledger**: The file `DEPENDENCIES.lock.md`, which records the exact version of every dependency.
- **Evidence_Item**: A recorded artifact supporting release readiness, such as a test result, validation result, or dependency impact record.
- **Evidence_Chain**: The linked sequence commit, firmware build, test result, risk score, release decision, compliance record, OTA rollout.
- **Evidence_Gap**: A required evidence category or coverage target for which no sufficient Evidence_Item exists.
- **Audit_Sink**: The immutable, append-only store that consumes `audit.event.recorded` events.
- **Tenant**: An organization (OEM or Tier-1 supplier) whose data is isolated from every other organization.
- **Canonical_ID**: A platform-assigned identifier for a canonical vehicle, component instance, software artifact, or configuration snapshot.
- **Canonical_Vehicle**: A canonical record resolved from a VIN with model year, trim, plant, and build date.
- **Canonical_Component_Instance**: A canonical record resolved from part number and supplier batch.
- **Canonical_Software_Artifact**: A canonical record resolved from ECU, firmware version, and calibration ID.
- **Canonical_Configuration_Snapshot**: A canonical record resolved from vehicle, ECU set, firmware set, and regional configuration.
- **Seed_Data**: Fictional vehicles, ECUs, firmware versions, and test results loaded into the local environment, each labeled as fictional.
- **Local_Environment**: The Docker Compose stack in `platform/docker-compose.yml` containing PostgreSQL, Neo4j, Kafka, Redis, the Phase 1 services, and observability components.
- **Observability_Stack**: OpenTelemetry instrumentation with Prometheus and Grafana.
- **CI_Pipeline**: The GitHub Actions workflows that build, test, and validate the repository.

## Requirements

### Requirement 1: Canonical identity resolution

**User Story:** As a platform engineer, I want every source identifier resolved to a canonical identifier, so that all contexts reference the same vehicles, components, software, and configurations.

#### Acceptance Criteria

1. WHEN a source record containing a VIN is ingested, THE Entity_Resolver SHALL resolve the VIN to a Canonical_Vehicle containing model year, trim, plant, and build date.
2. WHEN a source record containing a part number and supplier batch is ingested, THE Entity_Resolver SHALL resolve the pair to a Canonical_Component_Instance.
3. WHEN a source record containing an ECU, firmware version, and calibration ID is ingested, THE Entity_Resolver SHALL resolve the triple to a Canonical_Software_Artifact.
4. WHEN a vehicle, ECU set, firmware set, and regional configuration are provided, THE Entity_Resolver SHALL resolve them to a Canonical_Configuration_Snapshot.
5. WHEN the Entity_Resolver receives the same source identifiers for the same Tenant more than once, THE Entity_Resolver SHALL return the same Canonical_ID each time.
6. WHEN a canonical entity is created or changed, THE Data_Readiness_Service SHALL publish a `vehicle.identity.resolved` Event, or an equivalent versioned identity Event, containing the Canonical_ID, entity type, and Tenant ID.
7. IF a source record cannot be resolved because a required identifier is missing or malformed, THEN THE Entity_Resolver SHALL reject the record, store the rejection reason, and publish no identity Event for the record.
8. IF a source record matches more than one existing canonical entity, THEN THE Entity_Resolver SHALL flag the record as ambiguous and withhold publication of an identity Event until the ambiguity is resolved.
9. THE Data_Readiness_Service SHALL ensure that other contexts receive only Canonical_IDs and not raw source identifiers as foreign keys.
10. FOR ALL valid canonical entities, serializing an identity Event then deserializing the Event SHALL produce an equivalent canonical entity (round-trip property).

### Requirement 2: Universal data ingestion and normalization

**User Story:** As a data engineer, I want data from ERP, MES, PLM, legacy databases, CAN logs, and documents ingested and normalized, so that downstream contexts work from consistent data.

#### Acceptance Criteria

1. WHEN a source record is submitted through the Ingestion_Pipeline, THE Ingestion_Pipeline SHALL store the raw record unchanged together with its source system, Tenant ID, and ingestion timestamp.
2. WHEN a raw record is stored, THE Ingestion_Pipeline SHALL produce a normalized record conforming to the canonical schema for its entity type.
3. WHEN a CAN log file in ASAM MDF format is submitted, THE Ingestion_Pipeline SHALL decode signals using the supplied DBC definition and store the decoded signals.
4. WHEN a `document.text.extracted` Event is consumed, THE Ingestion_Pipeline SHALL obtain the extracted text from the Event or, when the Event carries a text URI, from the Object_Store through its own read-only Storage_Provider adapter after verifying the text SHA-256, store the text linked to the canonical document identifier and the `objectStoreUri` in the Event, normalize it, and write the result to the canonical layer, without calling the Legacy_Integration_Service.
5. IF a source record fails schema validation, THEN THE Ingestion_Pipeline SHALL place the record in a dead-letter store with the validation errors and continue processing subsequent records.
6. WHEN the same source record is submitted more than once, THE Ingestion_Pipeline SHALL produce exactly one normalized record.
7. THE Ingestion_Pipeline SHALL record data lineage linking each normalized record to its raw record and source system.
8. THE Data_Readiness_Service SHALL provide a data quality report per source system containing record counts for accepted, rejected, and ambiguous records.
9. FOR ALL valid source records, normalizing then denormalizing to the source format SHALL preserve every mapped field value (round-trip property).
10. WHEN a `document.text.extracted`, `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, or `mes.quality.inspection.recorded` Event that was already processed is consumed again, THE Ingestion_Pipeline SHALL produce no additional state change and no additional Event.
11. WHEN an `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, or `mes.quality.inspection.recorded` Event is consumed, THE Ingestion_Pipeline SHALL normalize the record, resolve its identifiers through the Entity_Resolver, write the result to the canonical layer, and, when Events for the same `naturalKey` arrive out of order, retain the version chosen by `sourceRecordVersion` when both the Event and the stored record carry it and otherwise by the later `extractedAt` with ties broken by the larger `contentHash`, treat an Event whose `contentHash` equals the stored one as a no-op, and deduplicate on `eventId`, using one consumer group and one `dlt.<consumer-group-id>` dead-letter topic for each topic.

### Requirement 3: Legacy connector framework

**User Story:** As an integration engineer, I want a connector framework with an anti-corruption layer, so that legacy systems can be integrated without leaking legacy models into the platform.

#### Acceptance Criteria

1. THE Connector_Framework SHALL define a connector interface covering configuration, connection test, extraction, and checkpointing.
2. WHEN a connector extracts records, THE Anti_Corruption_Layer SHALL translate each legacy record into the canonical schema before the record leaves the Legacy_Integration_Service.
3. WHEN a connector run is interrupted and restarted, THE Connector_Framework SHALL resume extraction from the last stored checkpoint without producing duplicate normalized records.
4. IF a connector fails to reach its source system, THEN THE Connector_Framework SHALL retry with exponential backoff up to a configured maximum and record the failure with the connector name and Tenant ID.
5. THE Connector_Framework SHALL store connector credentials in Vault and not in connector configuration, logs, or Events.
6. THE Sample_Connector SHALL extract fictional ERP and MES records from the Seed_Data source and deliver them through the Anti_Corruption_Layer as `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, and `mes.quality.inspection.recorded` Events.
7. WHEN a connector run completes, THE Connector_Framework SHALL publish an `audit.event.recorded` Event containing the connector name, Tenant ID, record counts, and outcome.
8. WHERE an Azure DevOps or Jenkins connector is configured, THE Connector_Framework SHALL ingest build and test results from that system as `test.result.recorded` Events.
9. WHEN the Legacy_Integration_Service discovers a PDF document, THE Legacy_Integration_Service SHALL upload the raw bytes through the Storage_Provider to the Raw_Bucket under the Tenant's `<tenantId>/raw/` prefix, store only metadata (document identifier, object key, SHA-256, content type, size, and Tenant ID) in its own PostgreSQL schema, extract the text in a worker pool that is separate from HTTP request threads and bounded by a maximum pool size, queue capacity, PDF size, page count, per-document timeout, extracted text size, and attempt count, and publish a `document.text.extracted` Event containing the canonical document identifier, the `s3://` `objectStoreUri`, the SHA-256 of the PDF, the Tenant ID, and either the extracted text inline when its UTF-8 size is at most 64 KiB (configurable downward) or a text URI and the SHA-256 of the text when it is larger.
10. WHEN the same canonical document identifier and content digest are extracted more than once, THE Legacy_Integration_Service SHALL publish at most one `document.text.extracted` Event for that `(tenantId, canonicalDocumentId, contentSha256)` key.
11. IF a PDF is corrupt, encrypted, over a configured limit, or exceeds the per-document timeout, THEN THE Legacy_Integration_Service SHALL publish no `document.text.extracted` Event for it, record the failure reason, and after the attempt limit publish a record on the `dlt.legacy-integration-extraction` dead-letter topic.
12. THE Legacy_Integration_Service SHALL deliver translated connector records to the Data_Readiness_Service only as `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, and `mes.quality.inspection.recorded` Events, each carrying only fields that the Anti_Corruption_Layer mapped into the topic's contract shape, and SHALL NOT call the Data_Readiness_Service synchronously.
13. THE Legacy_Integration_Service SHALL run as exactly one replica in Phase 1, and the `data-readiness` context SHALL run exactly one Celery beat process, separate from its Celery worker replicas.
14. THE Legacy_Integration_Service SHALL write an object to the Object_Store before it commits the metadata row that references the object, SHALL commit the metadata row and the `document.text.extracted` outbox row in one database transaction, and SHALL use the shared layouts `s3://autoreliance-raw-<env>/<tenantId>/raw/documents/<documentId>/<sha256>.pdf` and `s3://autoreliance-text-<env>/<tenantId>/text/documents/<documentId>/<sha256>.txt`, or, for a Tenant with an approved dedicated layout, the same keys in the buckets `autoreliance-raw-<env>-<tenantId>` and `autoreliance-text-<env>-<tenantId>`.
15. WHEN the scheduled orphan reaper runs, THE Legacy_Integration_Service SHALL delete each object that has no committed metadata row and is older than a configurable grace period (default 24 hours), and SHALL NOT delete an object that has a committed metadata row or is younger than the grace period.
16. THE AutoReliance_Platform SHALL NOT store PDF bytes in a PostgreSQL `bytea` column, a PostgreSQL large object, or a mounted volume, and SHALL access the Object_Store only through the Storage_Provider, whose backend (endpoint, bucket, region, path-style flag, and credentials from Vault) is deploy-time configuration.
17. THE AutoReliance_Platform SHALL use, by default, two shared Object_Store buckets per environment (`autoreliance-raw-<env>` and `autoreliance-text-<env>`) with the Tenant as the first key segment, SHALL enforce tenant isolation inside them through prefix-scoped permissions with per-Tenant storage credentials on AWS S3 and Ceph RGW, and THE Storage_Provider SHALL additionally reject, as defence in depth on every backend, any operation whose bucket is not the one that the Tenant's Storage_Layout resolves to for the role or whose key does not start with `<tenantId>/<role>/` (`raw` or `text`) for the Tenant of the verified Internal_Principal or the Event.
18. THE `data-readiness` Bounded_Context SHALL use a storage credential that grants read access to the Text_Bucket of its Tenants only, with no write, delete, or list permission on any bucket and no read or list permission on any Raw_Bucket, so that a GetObject or ListBucket request on the Raw_Bucket is rejected by the Object_Store with an access-denied status on every backend, including Garage. Where the backend supports prefix-scoped permissions, the credential SHALL also be limited to the Tenant's `<tenantId>/text/` prefix.
19. WHEN a request for an object of Tenant A is sent to an Object_Store backend that supports prefix-scoped permissions (AWS S3 and Ceph RGW in production, a prefix-capable smoke-test backend in CI whose result is never release evidence, or a Tenant's dedicated buckets on any backend) with a storage credential of Tenant B, THE Object_Store SHALL reject the request with an access-denied or not-found status, independent of the Storage_Provider tenant check. Garage cannot scope permissions by prefix, so on Garage with the shared layout this criterion is not enforced by the Object_Store, the Storage_Provider tenant check applies, and the conformance suite SHALL report the store-level cross-tenant test as not applicable and not as passed, SHALL assert that a cross-tenant read made directly against Garage bypassing the Storage_Provider succeeds so that a change in Garage behavior fails loudly, and SHALL assert that the same read made through the Storage_Provider is refused with an access-denied or not-found status (known dev-only limitation).
20. WHILE the `prod` profile is active, THE Legacy_Integration_Service SHALL refuse to start if the Key_Strategy is not `per-tenant`, if the SSE-KMS key ARN of any configured Tenant cannot be resolved from Vault, if the KMS endpoint is unreachable at startup, or if evaluating any of these conditions fails, and SHALL encrypt each object with the SSE-KMS key of its Tenant.
21. THE Storage_Provider SHALL work without code change against Garage, SeaweedFS, Ceph RGW, and AWS S3 by using path-style addressing, a configurable region string, and checksum calculation and validation set to when-required, and THE CI_Pipeline SHALL run the Storage_Provider conformance suite against Garage on every change to a Storage_Provider adapter.
22. WHEN a connector publishes an `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, or `mes.quality.inspection.recorded` Event, THE Connector_Framework SHALL set `sourceSystem`, a `naturalKey` built from the named source columns defined in the topic's contract, a `contentHash` equal to the SHA-256 of the RFC 8785 canonical JSON form of the ACL-mapped payload, an `extractedAt` timestamp, and `sourceRecordVersion` only when the source provides a record version, and SHALL publish no Event for a record whose `contentHash` equals the last published `contentHash` for the same `naturalKey`.

23. THE Storage_Provider SHALL resolve the bucket name and key prefix of each Tenant from the Tenant's Storage_Layout, which is `shared` unless the Tenant has an approved exception, and SHALL provision a dedicated Raw_Bucket and Text_Bucket pair (`autoreliance-raw-<env>-<tenantId>` and `autoreliance-text-<env>-<tenantId>`) for a Tenant only when its Storage_Layout is `dedicated` with a stated reason (physical isolation, cost allocation, or a retention or immutability profile that a prefix cannot express) and an approval reference, recording an `audit.event.recorded` Event on provisioning; a `dedicated` Storage_Layout without a reason and an approval reference SHALL make the service refuse to start, and the same Storage_Provider code SHALL serve both layouts.

24. WHEN the Storage_Provider is initialized, THE Storage_Provider SHALL read the Storage_Layout of each configured Tenant from Vault once and cache it, SHALL NOT read Vault on the request path, and SHALL refuse a request for a Tenant that is not in the cached registry until the Storage_Provider is re-initialized.

25. WHEN a Tenant's Storage_Layout is changed through the exception path, THE exception path SHALL include a controlled restart or rollout of the affected deployables, and THE exception SHALL take effect only after the Storage_Provider is re-initialized.
26. WHEN the exception path is asked to set the dedicated Storage_Layout for a Tenant that has stored objects, THE exception path SHALL refuse the change with an error, SHALL fail closed, SHALL record an audit event, and SHALL return the stable error code `LAYOUT_CHANGE_REQUIRES_MIGRATION` with a message that names the Phase 2 three-phase migration path (ADR-022) as the resolution.
27. THE exception path SHALL set the dedicated Storage_Layout in Phase 1 only for a Tenant with zero stored objects.
28. WHEN the Storage_Layout of a Tenant that has stored objects is to be changed, THE platform SHALL perform the change as a three-phase operation (dual-write window, verified background migration, then flag flip and decommission), and THE platform SHALL NOT provide the flag flip path in Phase 1 without the migration path.
29. THE platform SHALL document a Tenant onboarding runbook that names the platform owner as the owner of the rollout trigger and records the rollout service level of 4 business hours from Vault provisioning to verified serving, during platform owner working hours, with Vault writes outside business hours deferred to the next business day and a revisit trigger of a second engineer or an on-call rotation being established (Phase 2), and the runbook SHALL allow the verification step to use either the `/admin/v1/layout/{tenantId}` read-back or the smoke ingest.
30. THE platform SHALL record the Phase 2 trigger for replacing read-once-at-startup of the Storage_Layout with an explicit operator-triggered `POST /admin/v1/layout/{tenantId}/refresh` endpoint that re-reads only that Tenant's layout from Vault, SHALL NOT use a time-to-live or any timer to refresh the Storage_Layout, and SHALL NOT implement the refresh endpoint in Phase 1.
31. WHEN the Storage_Provider is initialized and the layout entry of a Tenant is `dedicated` while the Tenant has stored objects under the shared layout, THE Storage_Provider SHALL refuse to serve that Tenant, SHALL fail closed, SHALL record an audit event, SHALL NOT fall back to the shared layout silently, and SHALL report the stable error code `LAYOUT_CHANGE_REQUIRES_MIGRATION` with a message that names the Phase 2 three-phase migration path (ADR-022) as the resolution.

### Requirement 4: Dependency graph of ECUs and firmware

**User Story:** As an integration architect, I want a graph of ECU, firmware, calibration, sensor, and cloud dependencies, so that integration relationships are queryable.

#### Acceptance Criteria

1. WHEN a `vehicle.identity.resolved` Event for a Canonical_Software_Artifact or Canonical_Configuration_Snapshot is consumed, THE Integration_Service SHALL create or update the corresponding nodes and relationships in the Dependency_Graph.
2. THE Dependency_Graph SHALL represent relationships of type depends-on, communicates-with, calibrated-by, and installed-on between ECUs, firmware versions, calibration files, sensors, and cloud services.
3. THE Integration_Service SHALL scope every Dependency_Graph node and query by Tenant ID using a label or database namespace used only by Integration_Service.
4. WHEN a duplicate or out-of-order identity Event is consumed, THE Integration_Service SHALL leave the Dependency_Graph in the same state as if the Events had been consumed once in version order.
5. IF a consumed Event references a Canonical_ID that is not yet known, THEN THE Integration_Service SHALL hold the Event for retry until the referenced entity arrives or a configured limit is reached, and then route the Event to a dead-letter topic.

### Requirement 5: Firmware change impact analysis

**User Story:** As a firmware engineer, I want to ask what breaks if I change a firmware version, so that I can see affected ECUs, vehicles, and configurations before release.

#### Acceptance Criteria

1. WHEN a firmware change is submitted through the API_Gateway or detected from a connector, THE Integration_Service SHALL record the change and publish a `firmware.change.committed` Event containing the Canonical_Software_Artifact ID, previous version, new version, and Tenant ID.
2. WHEN a `firmware.change.committed` Event is recorded, THE Impact_Analyzer SHALL traverse the Dependency_Graph and compute the set of directly and transitively affected ECUs, firmware versions, calibration files, and Canonical_Configuration_Snapshots.
3. WHEN the Impact_Analyzer completes a traversal, THE Integration_Service SHALL publish a `dependency.impact.computed` Event listing each affected entity with its dependency path and traversal depth.
4. WHEN a client requests the impact of a firmware change, THE API_Gateway SHALL return the affected entities together with the dependency path that explains each entry.
5. WHILE a traversal is running, THE Impact_Analyzer SHALL enforce a configurable maximum depth and report truncation in the result when the limit is reached.
6. WHEN the Impact_Analyzer computes impact for a change on a graph of 10,000 nodes, THE Impact_Analyzer SHALL complete the traversal within 2 seconds at the 95th percentile.
7. IF the changed artifact does not exist in the Dependency_Graph, THEN THE Impact_Analyzer SHALL return a not-found error and publish no `dependency.impact.computed` Event.
8. FOR ALL firmware changes, computing impact twice on an unchanged Dependency_Graph SHALL produce identical affected sets (idempotence property).

### Requirement 6: Integration risk prediction

**User Story:** As a release manager, I want an integration risk score for each firmware change, so that I can prioritize validation effort.

#### Acceptance Criteria

1. WHEN a `dependency.impact.computed` Event is recorded, THE Risk_Predictor SHALL compute an integration risk score between 0 and 100 for the change.
2. THE Risk_Predictor SHALL attach to each risk score the list of contributing factors with their weights and the identifiers of the Evidence_Items or graph entities supporting each factor.
3. THE Risk_Predictor SHALL assign a higher or equal score to a change affecting a superset of the entities affected by another change, all other factors being equal (monotonicity property).
4. IF the Risk_Predictor lacks the input data needed to compute a factor, THEN THE Risk_Predictor SHALL mark the factor as unavailable and lower the reported confidence of the score.
5. THE Risk_Predictor SHALL label every score as a model-generated estimate that requires human review.
6. WHEN a risk score is computed, THE Integration_Service SHALL publish an `integration.risk.scored` Event containing the change identifier, score, confidence, contributing factors, a non-empty list of citations, the labels `estimate` and `requiresHumanReview`, and model version, so that the Release_Service can project the score locally.

### Requirement 7: Configuration validation rules

**User Story:** As a configuration engineer, I want vehicle configurations validated against compatibility rules, so that invalid combinations are found before programming or release.

#### Acceptance Criteria

1. WHEN a Canonical_Configuration_Snapshot is created or a `dependency.impact.computed` Event lists the snapshot as affected, THE Config_Rule_Engine SHALL evaluate the snapshot against all rules enabled for the Tenant.
2. THE Config_Rule_Engine SHALL provide rules for ECU hardware revision compatibility, firmware dependency satisfaction, communication protocol compatibility, regional configuration validity, calibration file presence, and programming readiness.
3. WHEN evaluation completes, THE Config_Rule_Engine SHALL return a result containing, for each rule, a status of pass, fail, or not-evaluable, and for each failure the offending entities and the rule identifier.
4. WHEN evaluation completes, THE Configuration_Service SHALL publish a `config.validation.completed` Event containing the snapshot Canonical_ID, overall status, and failed rule identifiers.
5. IF a rule cannot be evaluated because required data is missing, THEN THE Config_Rule_Engine SHALL record the rule as not-evaluable with the missing data and SHALL NOT record the rule as pass.
6. WHEN a latency-sensitive caller requests configuration validation, THE Configuration_Service SHALL serve the request over gRPC in package `autoreliance.configuration.v1` and return a result within 500 milliseconds at the 95th percentile for a snapshot of up to 100 ECUs.
7. THE Config_Rule_Engine SHALL evaluate rules as deterministic functions so that the same snapshot and rule set always produce the same result.
8. WHEN a rule definition is added or changed, THE Config_Rule_Engine SHALL version the rule set and record the rule set version in each validation result.
9. THE configuration validation gRPC request message SHALL contain a `tenant_id` field, and WHEN the `tenant_id` differs from the Tenant of the authenticated Internal_Principal in the call metadata, THE Configuration_Service SHALL reject the call with a permission-denied status and publish an `audit.event.recorded` Event.
10. WHEN a configuration validation result is stored, THE Configuration_Risk_Scorer SHALL compute a configuration risk score between 0 and 100 from the per-rule results, attach the identifiers of the rule results that produced the score as a non-empty list of citations, label the score as a model-generated estimate that requires human review, lower the reported confidence for each not-evaluable rule, and publish a `configuration.risk.scored` Event through the transactional outbox.
11. WHEN the Config_Rule_Engine needs dependency graph facts for a snapshot, THE Configuration_Service SHALL obtain them through a versioned API of the Integration_Service and SHALL NOT access Neo4j directly.

### Requirement 8: Evidence ingestion for release assurance

**User Story:** As a release engineer, I want test results and validation outputs collected as evidence, so that release decisions rest on recorded facts.

#### Acceptance Criteria

1. WHEN a `test.result.recorded` Event is consumed, THE Release_Service SHALL store the result as an Evidence_Item linked to the Canonical_Software_Artifact and Release_Candidate it covers.
2. WHEN a `dependency.impact.computed`, `config.validation.completed`, `integration.risk.scored`, or `configuration.risk.scored` Event is consumed, THE Release_Service SHALL store the Event content in the Release_Projection as an Evidence_Item for the affected Release_Candidate.
3. WHEN a duplicate `test.result.recorded` Event is consumed, THE Release_Service SHALL keep exactly one Evidence_Item for the Event ID.
4. WHEN Events for the same test result arrive out of order, THE Release_Service SHALL retain the Evidence_Item with the highest `(version, occurrenceVersion)` pair, where `version` is the Event envelope version and `occurrenceVersion` is the payload's per-test-result sequence number.
5. IF a consumed Event fails schema validation against its AsyncAPI contract, THEN THE Release_Service SHALL route the Event to a dead-letter topic and record the validation error.
6. THE Release_Service SHALL link each Evidence_Item to the commit, firmware build, and test run identifiers that are available, for use in the Evidence_Chain.
7. THE Release_Service SHALL NOT subscribe to the `release.risk.scored` topic that it produces, so that no consumer in the Release_Service reads its own risk events.

### Requirement 9: Evidence-sufficiency scoring and gap detection

**User Story:** As a release manager, I want to know whether the evidence is sufficient and where it is missing, so that I judge validation completeness and not only test execution.

#### Acceptance Criteria

1. WHEN an Evidence_Item is stored or a Release_Candidate changes, THE Evidence_Scorer SHALL compute an evidence-sufficiency score between 0 and 100 for the Release_Candidate.
2. THE Evidence_Scorer SHALL compute the score from the required evidence categories defined by the Tenant's release policy, including test coverage of affected entities, configuration validation status, and recency of evidence.
3. WHEN the Gap_Detector finds an affected entity with no covering Evidence_Item, THE Gap_Detector SHALL record an Evidence_Gap identifying the entity and the missing category.
4. WHEN the Gap_Detector records a new Evidence_Gap, THE Release_Service SHALL publish a `release.evidence.gap.detected` Event containing the Release_Candidate ID, gap list, and Tenant ID.
5. WHEN an Evidence_Gap is later covered by new evidence, THE Release_Service SHALL mark the gap as closed and record the closing Evidence_Item.
6. THE Evidence_Scorer SHALL return, with each score, the test results (Evidence_Items) and the open coverage gaps that produced the score, together with the policy rules that contributed to it.
7. THE Evidence_Scorer SHALL assign a score that does not decrease when a passing Evidence_Item covering a previously uncovered affected entity is added (monotonicity property).
8. IF a covering Evidence_Item reports a failed result, THEN THE Gap_Detector SHALL treat the entity as uncovered.
9. THE Evidence_Scorer SHALL treat a test passing on a non-affected entity as contributing no coverage for an affected entity.
10. WHEN the evidence-sufficiency score of a Release_Candidate is below the Tenant's Sufficiency_Threshold, THE Release_Service SHALL block the release of that Release_Candidate.
11. THE Release_Service SHALL compute every evidence-sufficiency score, gap, and verdict from the Release_Projection and SHALL NOT make a synchronous call to any other service, including the inference sidecar, to compute a score.
12. WHEN the evidence-sufficiency score, the open gaps, or a consumed risk score of a Release_Candidate changes, THE Release_Risk_Scorer SHALL compute a release risk score between 0 and 100 from the Release_Projection, attach a non-empty list of citations to the Evidence_Items, gaps, and scores that produced it, and publish a `release.risk.scored` Event through the transactional outbox.

### Requirement 10: AI-assisted test selection

**User Story:** As a test engineer, I want recommended tests for a change, so that I close evidence gaps with the least effort.

#### Acceptance Criteria

1. WHEN a Release_Candidate has open Evidence_Gaps, THE Test_Selector SHALL return a ranked list of recommended tests that would cover the gaps.
2. THE Test_Selector SHALL attach to each recommendation the Evidence_Gap it addresses and the historical test results or dependency paths that justify the recommendation.
3. THE Test_Selector SHALL label each recommendation as AI-generated and subject to human acceptance.
4. IF the inference sidecar is unavailable, THEN THE Release_Service SHALL return a rule-based recommendation list derived from the Dependency_Graph impact and mark the response as a fallback.
5. WHEN the Test_Selector returns recommendations for the same Release_Candidate and unchanged inputs, THE Test_Selector SHALL return the same ranking.
6. THE Test_Selector SHALL exclude from recommendations any test that is not registered in the Tenant's test catalog.
7. THE inference sidecar SHALL run as a co-deployed local component of the Release_Service, and THE Release_Service SHALL remain able to compute scores, gaps, and verdicts while the sidecar is stopped.
8. THE inference sidecar SHALL produce deterministic output with all randomness seeded, and its unit tests SHALL make no live model call.
9. THE inference sidecar SHALL use scikit-learn for coverage analysis and xgboost for failure-likelihood risk scoring that ranks recommended tests, SHALL NOT use agent orchestration in Phase 1, and its outputs SHALL NOT feed the evidence-sufficiency score, the gap detection, the release gate verdict, or the `release.risk.scored` score.

### Requirement 11: Release gate

**User Story:** As a release authority, I want a release verdict with its evidence, so that release decisions are recorded and defensible.

#### Acceptance Criteria

1. WHEN a release verdict is requested, THE Release_Gate SHALL return one of the verdicts approve, conditional, or block for the Release_Candidate.
2. WHILE any Evidence_Gap marked blocking by the Tenant's release policy is open, THE Release_Gate SHALL return the verdict block.
3. WHEN the verdict is returned, THE Release_Gate SHALL include the evidence-sufficiency score, open Evidence_Gaps, integration risk score, configuration risk score, configuration validation result, and the citations of the Evidence_Items supporting each element.
4. WHEN a verdict is issued, THE Release_Service SHALL store the verdict with its inputs and policy version and publish an `audit.event.recorded` Event.
5. WHEN an authorized user records a human decision for a Release_Candidate, THE Release_Gate SHALL store the decision with the user identity, timestamp, and rationale.
6. THE Release_Gate SHALL present the verdict as decision support and SHALL NOT state or imply that the platform certifies the vehicle or software.
7. IF an input required by the release policy is unavailable, THEN THE Release_Gate SHALL return the verdict block and list the unavailable input.
8. FOR ALL Release_Candidates with identical inputs and policy version, THE Release_Gate SHALL return the same verdict.
9. WHILE the evidence-sufficiency score of a Release_Candidate is below the Tenant's Sufficiency_Threshold, THE Release_Gate SHALL return the verdict block and cite the score and the gaps that produced it.

### Requirement 12: API Gateway

**User Story:** As a frontend developer, I want a single gateway, so that the web application never calls services directly.

#### Acceptance Criteria

1. THE API_Gateway SHALL expose every endpoint as REST under the base path `/api/v1/<context>/`, described by an OpenAPI 3.1 definition in the Contract_Registry, where `<context>` is the bounded context name (`data-readiness`, `legacy-integration`, `integration-intelligence`, `configuration-assurance`, `release-assurance`, or `audit`).
2. THE Web_App SHALL send all requests to the API_Gateway and to no other service.
3. WHEN a request arrives without a valid SSO token, THE API_Gateway SHALL reject the request with HTTP 401.
4. WHEN an authenticated user lacks the RBAC role required for an endpoint, THE API_Gateway SHALL reject the request with HTTP 403 and publish an `audit.event.recorded` Event.
5. WHEN a request is authenticated, THE API_Gateway SHALL derive the Tenant ID from the token and attach a signed Internal_Principal carrying that Tenant ID to the downstream call, ignoring any Tenant ID supplied in the request body, path, or query.
6. WHEN a request arrives, THE API_Gateway SHALL start or continue an OpenTelemetry trace and propagate the trace context downstream.
7. IF a downstream service does not respond within the configured timeout, THEN THE API_Gateway SHALL return HTTP 504 as Problem_Details containing a correlation identifier.
8. THE API_Gateway SHALL provide RBAC roles for at least release manager, firmware engineer, configuration engineer, data engineer, auditor, and tenant administrator.
9. THE API_Gateway SHALL return every successful REST response as `{ "data": ..., "meta": { "traceId": "...", "tenantId": "..." } }`, with the `tenantId` taken from the authenticated principal.
10. THE API_Gateway and every domain service SHALL return every REST error, including 401, 403, 404, 413, and 504, as Problem_Details with content type `application/problem+json`, containing the status, a title, and a correlation identifier.
11. THE API_Gateway and every domain service SHALL paginate every REST list endpoint with cursor-based pagination only (`?cursor=<opaque>&limit=<int>`), return the cursor for the next page in the response `meta`, and reject offset-style and page-number parameters.
12. IF a request carries a `limit` above the configured maximum or a cursor that is malformed or expired, THEN THE service SHALL reject the request with HTTP 400 as Problem_Details.
13. THE API_Gateway SHALL provide the Platform_Operator RBAC role in addition to the six tenant roles of criterion 8, and a Platform_Operator principal SHALL NOT be tenant-scoped and SHALL carry no Tenant ID.
14. WHEN a request to a route under `/admin/` arrives from a principal without the Platform_Operator role, including any tenant-scoped principal, THE API_Gateway SHALL reject the request with HTTP 403 as Problem_Details before the request reaches any service, and publish an `audit.event.recorded` Event.
15. WHEN a Platform_Operator calls a route under `/admin/`, THE API_Gateway SHALL validate the `targetTenantId` taken from the path (format and existence), pass it to the service as an explicit target-tenant field alongside the operator principal and never as the principal's Tenant, and publish an `audit.event.recorded` Event containing `operatorPrincipal`, `targetTenantId`, `action`, `result`, and `occurredAt`.
16. IF a route that does not start with `/admin/` carries a Tenant ID in its path, THEN THE Contract_Registry lint rule SHALL fail the build and THE API_Gateway SHALL reject a request to such a route; and every route that starts with `/admin/` SHALL declare the `platformOperator` security scheme and the `x-audit-event-required` extension.
17. THE Legacy_Integration_Service SHALL expose the read-only operator route `GET /admin/v1/layout/{tenantId}` that reports, for the target Tenant, the Vault value of the Storage_Layout (with its KV v2 last-modified time and version) and the Storage_Layout cached by every process that caches it, each with the Vault version it loaded and its load time, and SHALL NOT return a credential or key ARN.
18. THE `GET /admin/v1/layout/{tenantId}` response SHALL include a `consistent` boolean that is true only when every registered cache holds the Vault value and Vault version, and a `recommendation` string that names each process that needs a restart and the layout version to load.
19. IF a registered layout cache endpoint or Vault is unreachable, does not answer within 2 seconds, or returns an error or a malformed body, THEN THE Legacy_Integration_Service SHALL return HTTP 503 as Problem_Details that names the unreachable process, SHALL NOT report `consistent` true on partial data, and SHALL NOT use a fallback or a cached value.
20. THE Legacy_Integration_Service and THE Data_Readiness_Service SHALL each expose the read-only, internal-only route `GET /admin/v1/layout-cache/{tenantId}` that returns the Storage_Layout the process loaded, with the same Platform_Operator role gate and audit event as other `/admin/` routes, THE API_Gateway SHALL NOT route it to external callers, it SHALL be served only on the internal management port `admin-cache` (8081/TCP), it SHALL return HTTP 503 as Problem_Details without a cached value when it cannot complete a call, and it SHALL carry no document or ingest payload.
21. THE platform SHALL keep a registry of every process that caches the Storage_Layout, and any process that instantiates a Storage_Provider SHALL be on that registry, so that the read-back can verify the onboarding service level.
22. THE platform SHALL restrict ingress on the `admin-cache` port, by a NetworkPolicy, to the `legacy-integration` pods and to the API_Gateway pods in the operator gateway namespace, and SHALL keep the Platform_Operator role gate in addition to that NetworkPolicy, so that the role gate answers who and the NetworkPolicy answers from where.

### Requirement 13: Kafka backbone and event contracts

**User Story:** As a service developer, I want every topic and event contract defined before implementation, so that producers and consumers integrate without drift.

#### Acceptance Criteria

1. THE Contract_Registry SHALL contain an AsyncAPI 3.0 definition for every Phase 1 Kafka topic before a producer or consumer for the topic is implemented.
2. THE Contract_Registry SHALL contain a protobuf definition for every gRPC service, in the directory `contracts/proto/<service>/` and in the package `autoreliance.<context>.v1`, before the service or its clients are implemented.
3. THE Event_Backbone SHALL name every topic `<domain>.<entity>.<action>` with the action in past tense, and SHALL carry the Phase 1 events `vehicle.identity.resolved`, `firmware.change.committed`, `dependency.impact.computed`, `test.result.recorded`, `release.evidence.gap.detected`, and `audit.event.recorded` using the names and producer-consumer relationships in the platform event catalog.
4. THE Contract_Registry SHALL define the Phase 1 additions `config.validation.completed`, `integration.risk.scored`, `configuration.risk.scored`, `release.risk.scored`, and a dead-letter topic named `dlt.<consumer-group-id>` for each consumer group, the additions `document.text.extracted`, `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, and `mes.quality.inspection.recorded`, and the dead-letter topics `dlt.data-readiness-document`, `dlt.data-readiness-erp-masterdata`, `dlt.data-readiness-erp-purchaseorder`, `dlt.data-readiness-mes-workorder`, `dlt.data-readiness-mes-quality`, and `dlt.legacy-integration-extraction`; and SHALL document the additions as extensions of the catalog, with the `dlt.` names and the four-segment name `mes.quality.inspection.recorded` documented as exceptions to the `<domain>.<entity>.<action>` naming rule.
5. THE AutoReliance_Platform SHALL carry every Event in the envelope `{ "eventId", "eventType", "version", "tenantId", "occurredAt", "payload" }`, and SHALL carry the trace context in the W3C `traceparent` and `tracestate` Kafka record headers and not in the envelope body.
6. WHEN a producer publishes an Event, THE producer SHALL validate the Event against its AsyncAPI schema and reject the Event if validation fails.
7. WHEN a consumer receives an Event, THE consumer SHALL validate the Event against its AsyncAPI schema and route invalid Events to the dead-letter topic.
8. WHEN a schema changes in an incompatible way, THE CI_Pipeline SHALL require a new Event `version` and keep the previous version available.
9. WHEN a consumer receives an Event with a `version` it does not support, THE consumer SHALL route the Event to the dead-letter topic and record the unsupported version.
10. THE Event_Backbone SHALL partition Events so that Events for the same Canonical_ID within a Tenant are delivered to the same partition.
11. WHEN a breaking change is made to a gRPC service, THE Contract_Registry SHALL introduce it in a new package version (`v2`) and SHALL NOT modify the `v1` package.
12. THE Contract_Registry SHALL contain, for each Phase 1 Bounded_Context, an OpenAPI definition at `contracts/openapi/<service>.yaml` where the service exposes REST, an AsyncAPI definition at `contracts/asyncapi/<service>.yaml` where the service produces or consumes Events, and a protobuf directory at `contracts/proto/<service>/` where the service exposes gRPC, plus the aggregate gateway definition at `contracts/openapi/gateway.yaml`.
13. THE Contract_Registry SHALL define `integration.risk.scored`, `configuration.risk.scored`, and `release.risk.scored` each in its own AsyncAPI 3.0 file named `contracts/asyncapi/<topic>.yaml`, each with its own payload schema, a score between 0 and 100, and a non-empty citations list, and SHALL NOT define a risk-score schema shared by more than one of the three topics.
14. THE Contract_Registry SHALL define a `receive` operation for `integration.risk.scored` and `configuration.risk.scored` by the `release-assurance` context only, and SHALL define no `receive` operation for `release.risk.scored` in the `release-assurance` context.
15. THE Contract_Registry SHALL define `document.text.extracted` in its own AsyncAPI 3.0 file `contracts/asyncapi/document.text.extracted.yaml`, with the Source_Ingestion_Envelope (with `contentHash` equal to the PDF SHA-256, `naturalKey` equal to the connector-built document key, and no `sourceRecordVersion`), the partition key `{tenantId}:{canonicalDocumentId}`, an `s3://` `objectStoreUri` in a Raw_Bucket under the Tenant's `<tenantId>/raw/` prefix, the PDF SHA-256, exactly one of inline `extractedText` (at most 64 KiB UTF-8) or a `textUri` in a Text_Bucket under the Tenant's `<tenantId>/text/` prefix (shared or dedicated bucket names, never a text location as raw or the reverse), the text SHA-256, a `send` operation by `legacy-integration`, and a `receive` operation by `data-readiness` in its own consumer group with a `dlt.<consumer-group-id>` dead-letter topic, and SHALL NOT define a `document.extraction.requested` topic.
16. THE Contract_Registry SHALL define `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, and `mes.quality.inspection.recorded` each in its own AsyncAPI 3.0 file named `contracts/asyncapi/<topic>.yaml`, each with its own payload schema, a `send` operation by `legacy-integration`, a `receive` operation by `data-readiness` in its own consumer group with a `dlt.<consumer-group-id>` dead-letter topic, the Source_Ingestion_Envelope with a documented `naturalKey` column composition, and the partition key `{tenantId}:{naturalKey}`; SHALL NOT share an ERP or MES payload schema between files; SHALL NOT define a combined `source.record.extracted` topic; and SHALL keep `contracts/asyncapi/legacy-integration.yaml` and `contracts/asyncapi/data-readiness.yaml` as per-context files that reference these topic files and do not redefine them.
17. THE Event envelope of the five `legacy-integration` topics (`document.text.extracted`, `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, and `mes.quality.inspection.recorded`) SHALL be the Source_Ingestion_Envelope, which adds `sourceSystem`, `naturalKey`, `contentHash`, `extractedAt`, and an optional `sourceRecordVersion` to the base envelope fields of criterion 5, and THE CI_Pipeline topic-name check SHALL accept exactly two exceptions to `<domain>.<entity>.<action>`: names starting with `dlt.` and the name `mes.quality.inspection.recorded`.

### Requirement 14: Contract enforcement in CI

**User Story:** As a maintainer, I want CI to fail when a service drifts from its contracts, so that integration breaks are caught before merge.

#### Acceptance Criteria

1. WHEN a pull request changes a service or the Contract_Registry, THE CI_Pipeline SHALL validate each producer and consumer against the AsyncAPI definitions.
2. WHEN a pull request changes a gateway endpoint, THE CI_Pipeline SHALL validate the implementation against the OpenAPI 3.1 definition.
3. WHEN a pull request changes a gRPC service, THE CI_Pipeline SHALL validate the service against the protobuf definition and run Pact contract tests for each synchronous service pair.
4. IF a service diverges from a definition in the Contract_Registry, THEN THE CI_Pipeline SHALL fail the build and report the diverging contract and element.
5. THE CI_Pipeline SHALL run unit tests for every rule engine and scoring function, and integration tests using Testcontainers for PostgreSQL, Neo4j, and Kafka.
6. WHEN a pull request changes a file under `contracts/proto/`, THE CI_Pipeline SHALL run `buf lint` and `buf breaking --against .git#branch=main` and SHALL fail the build when either reports a violation, so that a `v1` package is never mutated and breaking changes require a new package version.
7. WHEN a pull request changes a file under `contracts/openapi/`, THE CI_Pipeline SHALL regenerate the Java, Python, and TypeScript API clients and SHALL fail the build when the regenerated output differs from the committed output.

### Requirement 15: Multi-tenancy and tenant isolation (non-functional)

**User Story:** As a tenant administrator, I want strict data isolation between tenants, so that a Tier-1 supplier never sees OEM data.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL store a Tenant ID on every persisted entity and carry the Tenant ID in every Event.
2. THE AutoReliance_Platform SHALL enforce PostgreSQL row-level security on every tenant-scoped table, with the Tenant ID set per connection or transaction from the authenticated context.
3. THE Integration_Service SHALL scope every Neo4j query by Tenant ID through a label or database namespace.
4. WHEN a user from Tenant A requests an entity owned by Tenant B through any API_Gateway endpoint, THE AutoReliance_Platform SHALL return an HTTP 404 Problem_Details response that does not reveal the entity exists and is indistinguishable from the response for an entity that does not exist.
5. IF a database query is issued without a Tenant ID in context, THEN THE AutoReliance_Platform SHALL return no rows and record an error.
6. WHEN a consumer receives an Event whose Tenant ID does not match a Tenant the consumer is authorized to process, THE consumer SHALL discard the Event to the dead-letter topic and record an audit event.
7. THE AutoReliance_Platform SHALL encrypt tenant data with per-tenant keys managed in Vault.
8. WHEN the tenant isolation test suite runs, THE suite SHALL verify for every API_Gateway endpoint, every Kafka consumer, and every data store that Tenant A cannot read Tenant B data.
9. WHERE a Tenant is a Tier-1 supplier, THE AutoReliance_Platform SHALL restrict that Tenant to data shared with it by explicit grant.
10. THE AutoReliance_Platform SHALL NOT trust a Tenant ID supplied by a client, and every service, including internal service endpoints that receive a tenant header from the API_Gateway, SHALL derive the Tenant from a verified Internal_Principal and not from a bare header.
11. IF a Tenant ID in a header, request message, or Event does not match the Tenant of the verified Internal_Principal or the authorized consumer Tenants, THEN THE receiving service SHALL reject the request or Event, publish no state change, and record an audit event.
12. WHERE a request is an `/admin/` route called by a Platform_Operator, THE receiving service SHALL accept the target Tenant only from the explicit target-tenant field that the API_Gateway validated, SHALL NOT treat it as the Tenant of the principal, and criteria 10 and 11 SHALL continue to apply unchanged to every other route.

### Requirement 16: Audit sink and audit events

**User Story:** As an auditor, I want every access to release evidence recorded immutably, so that I can reconstruct who saw what.

#### Acceptance Criteria

1. WHEN a user or service reads release evidence, THE Release_Service SHALL publish an `audit.event.recorded` Event containing actor, Tenant ID, resource identifier, action, timestamp, and trace ID.
2. WHEN any context performs an authentication failure, authorization failure, verdict issuance, or connector run, THE context SHALL publish an `audit.event.recorded` Event.
3. WHEN an `audit.event.recorded` Event is consumed, THE Audit_Sink SHALL append the record to an immutable store.
4. THE Audit_Sink SHALL reject update and delete operations on stored audit records.
5. WHEN an auditor queries audit records, THE API_Gateway SHALL return only records of the auditor's Tenant and SHALL itself emit an audit event for the query.
6. IF the Audit_Sink is unavailable, THEN THE publishing service SHALL retain the audit Event for retry and SHALL NOT return release evidence to the caller before the audit Event is durably recorded or queued.
7. THE Audit_Sink SHALL chain each record to the hash of the preceding record so that tampering is detectable.
8. WHEN duplicate `audit.event.recorded` Events with the same event ID are consumed, THE Audit_Sink SHALL store one record.
9. WHEN a route under `/admin/` is called, THE API_Gateway SHALL durably record an `audit.event.recorded` Event with `operatorPrincipal`, `targetTenantId`, `action`, `result`, and `occurredAt` before returning the response, for allowed and for denied calls.

### Requirement 17: Idempotent and order-tolerant Kafka consumption (non-functional)

**User Story:** As a service developer, I want consumers to tolerate redelivery and reordering, so that the platform stays correct under at-least-once delivery.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL implement every Kafka consumer as idempotent, keyed by Event ID and Tenant ID.
2. WHEN a consumer receives an Event it has already processed, THE consumer SHALL produce no additional state change and no additional published Event.
3. WHEN a consumer receives Events for the same entity out of occurrence order, THE consumer SHALL reach the same final state as if the Events had been received in order.
4. WHEN a consumer fails while processing an Event, THE consumer SHALL leave no partial state change visible and SHALL retry the Event.
5. WHEN an Event fails processing after the configured retry limit, THE consumer SHALL route the Event to the dead-letter topic with the failure reason.
6. WHEN the consumer test suite replays a recorded Event stream with duplicates and permutations, THE suite SHALL verify the final state equals the state from a single in-order delivery.
7. WHERE a service writes state and publishes an Event for the same change, THE service SHALL ensure that both occur or neither occurs.

### Requirement 18: Evidence traceability (non-functional)

**User Story:** As a release manager, I want every conclusion traceable to its supporting evidence, so that I can verify and defend every score and verdict.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL attach to every risk score, evidence-sufficiency score, Evidence_Gap, test recommendation, and release verdict the identifiers of the Evidence_Items or graph entities that support the conclusion.
2. WHEN a client requests the Evidence_Chain for a Release_Candidate, THE API_Gateway SHALL return the linked sequence of commit, firmware build, test result, risk score, and release decision records that exist.
3. IF a link of the Evidence_Chain does not exist, THEN THE API_Gateway SHALL identify the missing link and SHALL NOT infer the link.
4. THE AutoReliance_Platform SHALL not present an AI-generated output without at least one citation to a stored Evidence_Item or graph entity.
5. IF an AI component produces output with no supporting citation, THEN THE AutoReliance_Platform SHALL discard the output and record an audit event.
6. THE AutoReliance_Platform SHALL label every AI-generated output as AI-generated.
7. THE AutoReliance_Platform SHALL retain each stored conclusion together with the model version, rule set version, and policy version used to produce it.

### Requirement 19: Observability and end-to-end tracing

**User Story:** As a platform operator, I want end-to-end traces of the evidence chain, so that I can diagnose latency and failures across services.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL propagate OpenTelemetry trace context across HTTP, gRPC, and Kafka headers.
2. WHEN a firmware change flows through the Phase 1 services, THE Observability_Stack SHALL record a single trace that contains explicit spans for firmware change commit, dependency impact computation, configuration validation, evidence scoring, and release verdict.
3. THE Observability_Stack SHALL expose the evidence-chain trace in a Grafana dashboard.
4. THE AutoReliance_Platform SHALL expose Prometheus metrics for request rate, error rate, and latency of each service, and for consumer lag and dead-letter counts of each Kafka consumer group.
5. THE AutoReliance_Platform SHALL include the trace ID in every log line and every audit event.
6. IF trace context is missing on an incoming Event, THEN THE consumer SHALL start a new trace and record a link attribute noting that the parent context was absent.

### Requirement 20: Security baseline

**User Story:** As a security officer, I want authentication, authorization, and secret handling built in, so that the platform meets baseline security expectations.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL authenticate users through SSO at the API_Gateway.
2. THE AutoReliance_Platform SHALL store secrets, connector credentials, and tenant encryption keys in Vault and not in source control, container images, or logs.
3. WHEN a service calls another service synchronously, THE calling service SHALL pass the Internal_Principal and trace context, and every gRPC request message SHALL carry a `tenant_id` field that the receiving service validates against the Internal_Principal.
4. THE AutoReliance_Platform SHALL validate input at the API_Gateway and at every service boundary against the contract schema.
5. IF a request exceeds the configured payload size limit, THEN THE API_Gateway SHALL reject the request with HTTP 413.

### Requirement 21: Service independence and data ownership

**User Story:** As an architect, I want each service independently deployable with its own data, so that contexts evolve without coupling.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL give each Bounded_Context its own PostgreSQL schema and its own database login role, including Bounded_Contexts packaged in the same Deployable, with no other Bounded_Context holding credentials to that schema.
2. THE AutoReliance_Platform SHALL make every cross-context data read occur through an Event or a versioned API, whether or not the two contexts are packaged in the same Deployable.
3. THE Integration_Service SHALL be the only Phase 1 Bounded_Context accessing the Neo4j instance.
4. WHERE a Deployable is built and deployed alone, THE Deployable SHALL start and pass its health check when the other Phase 1 Deployables are not running.
5. IF a dependency service is unavailable, THEN THE calling service SHALL return a defined error or degraded response and SHALL NOT block indefinitely.
6. THE AutoReliance_Platform SHALL store embeddings, when used by Phase 1 components, in the same PostgreSQL instance as their source records using pgvector.
7. THE AutoReliance_Platform SHALL package the Phase 1 Bounded_Contexts into the five Deployables `data-platform`, `integration-config`, `release-assurance`, `api-gateway`, and `audit-sink`, with the packaging defined under `platform/`, and SHALL keep one directory per Bounded_Context under `services/`.
8. WHERE two Bounded_Contexts are packaged in the same Deployable, THE calling context SHALL reach the other context only through the other context's published contract, using in-process dispatch behind that contract, so that moving a context into its own Deployable is a deployment change and not a code rewrite.
9. THE platform SHALL carry data-plane operations (extraction, ingest, query, and mutation) between Bounded_Contexts only through Kafka Events, and no service SHALL initiate synchronous HTTP to another Bounded_Context for a data-plane operation, except that routes under `/admin/` MAY use synchronous HTTP between services for read-only diagnostics when gated by the Platform_Operator role and audited, any admin-path HTTP failure SHALL return HTTP 503 with no fallback and no cached value, and the Data_Readiness_Service MAY read a text object that an Event references from the Object_Store through its own read-only Storage_Provider adapter; gateway-to-service routing and the gRPC contracts are not service-initiated synchronous HTTP under this criterion.

### Requirement 22: Web application views

**User Story:** As a release manager, I want a web view of the change, its impact, validation, and verdict, so that I can review release readiness in one place.

#### Acceptance Criteria

1. WHEN a user opens a firmware change, THE Web_App SHALL display the change details, the computed dependency impact with dependency paths, the configuration validation result, and the release verdict.
2. WHEN a release verdict has open Evidence_Gaps, THE Web_App SHALL list each gap with the affected entity, missing category, and recommended tests.
3. WHEN a user selects a score, verdict, or gap, THE Web_App SHALL display the supporting Evidence_Item citations.
4. THE Web_App SHALL display the AI-generated label and the decision-support statement on every AI-generated output and verdict.
5. WHILE data for a view is loading, THE Web_App SHALL display a loading state.
6. IF the API_Gateway returns an error, THEN THE Web_App SHALL display the error message and correlation identifier.
7. WHILE the user is authenticated for a Tenant, THE Web_App SHALL display data for that Tenant only.

### Requirement 23: Local development environment and seed data

**User Story:** As a developer, I want one command to start the full stack with seed data, so that I can develop and demonstrate Phase 1 locally.

#### Acceptance Criteria

1. WHEN a developer runs `docker compose up` in `platform/`, THE Local_Environment SHALL start PostgreSQL, Neo4j, Kafka, Redis, Vault, Garage (digest-pinned) as the Object_Store with exactly two buckets created (`autoreliance-raw-dev` and `autoreliance-text-dev`, with Seed_Data tenants as key prefixes) and the two storage keys created (`legacy-integration` read-write on both buckets, `data-readiness` read-only on the text bucket), the Phase 1 services, the API_Gateway, the Web_App, and the Observability_Stack.
2. WHEN the Local_Environment starts for the first time, THE Local_Environment SHALL load Seed_Data for at least two Tenants, including fictional vehicles, ECUs, firmware versions, calibration files, and test results.
3. THE Seed_Data SHALL label every record as fictional and SHALL contain no real automaker data.
4. THE Seed_Data SHALL include a firmware change whose dependency impact produces at least one configuration validation failure and at least one Evidence_Gap.
5. WHEN the Local_Environment has started, THE Local_Environment SHALL report each service as healthy through its health check.
6. THE Local_Environment SHALL include a seed-data-driven end-to-end test that verifies a firmware change propagates through the Dependency_Graph, configuration validation, and Release_Gate and produces the expected Evidence_Gaps.
7. WHEN the end-to-end test completes, THE Local_Environment SHALL make the resulting evidence-chain trace visible in Grafana.

### Requirement 24: Phased delivery and out-of-scope continuity

**User Story:** As a stakeholder, I want later phases documented without being implemented, so that Phase 1 decisions remain compatible with the full platform.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL implement only the Phase 1 modules and the shared foundation defined in this document.
2. THE Phase 1 documentation SHALL record Phase 2 as Quality Intelligence (problems 3, 5, 9), Connected Service Intelligence (15), and Diagnostic and Root-Cause (7), with no implementation in Phase 1.
3. THE Phase 1 documentation SHALL record Phase 3 as Security Intelligence (11), OTA Risk (12), Compliance Evidence (13), and Test Lab Orchestration (10), with no implementation in Phase 1.
4. THE Phase 1 documentation SHALL record Phase 4 as Knowledge and Copilot (14), with no implementation in Phase 1.
5. THE Contract_Registry SHALL reserve the names of the Phase 2 to 4 events in the platform event catalog without defining producers or consumers for them.
6. THE Phase 1 services SHALL treat the absence of Phase 2 to 4 services as a normal condition, and SHALL NOT fail when an Event consumer for a reserved event does not exist.
7. WHERE the platform produces compliance-relevant information, THE AutoReliance_Platform SHALL describe the information as assistance for compliance and SHALL NOT claim to certify a vehicle.

### Requirement 25: Definition of Done verification

**User Story:** As a project sponsor, I want the Phase 1 completion criteria verifiable, so that I can accept the release.

#### Acceptance Criteria

1. WHEN the Local_Environment is started with `docker compose up`, THE Local_Environment SHALL reach a state with all Phase 1 services healthy and Seed_Data loaded.
2. WHEN the seeded firmware change is opened in the Web_App, THE Web_App SHALL display the change, its dependency impact, the configuration validation result, and the release verdict with its listed Evidence_Gaps.
3. WHEN the Phase 1 Event flow runs, THE `data-platform`, `integration-config`, and `release-assurance` Deployables SHALL each publish or consume their contracted Kafka events and each start independently.
4. WHEN the evidence-chain flow runs, THE Observability_Stack SHALL show one end-to-end trace in Grafana.
5. WHEN the tenant isolation test suite runs, THE suite SHALL report that Tenant A cannot read Tenant B data through any API.
6. WHEN release evidence is read through any API, THE AutoReliance_Platform SHALL record one `audit.event.recorded` Event for each read.

### Requirement 26: Technology stack, repository layout, and dependency governance

**User Story:** As a maintainer, I want the stack, folder layout, and dependency versions fixed and verifiable, so that builds are reproducible and the steering rules hold.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL use Java 21 with Spring Boot 4.1.x and Spring Cloud 2025.1.x, Python 3.12 with FastAPI, PostgreSQL 16, Neo4j 5.x Community Edition with label-based tenancy, and Apache Kafka 3.x.
2. THE AutoReliance_Platform SHALL place Java service code under `services/<service>/src/main/java/com/autoreliance/<context>/` and Python service code under `services/<service>/app/<context>/` with `main.py` as the FastAPI entrypoint.
3. THE AutoReliance_Platform SHALL place `api-gateway` at `services/api-gateway/` and `audit-sink` at `services/audit-sink/`, both as Java Spring Boot services, and SHALL place `legacy-integration` at `services/legacy-integration/` (Java) and `configuration-assurance` at `services/configuration-assurance/` (Java), each in its own directory under `services/`.
4. THE AutoReliance_Platform SHALL pin every dependency to an exact version in its manifest, with no range operator, wildcard, or `latest`.
5. THE AutoReliance_Platform SHALL record every dependency, with its exact version, in the Dependency_Ledger before the dependency is used.
6. THE Dependency_Ledger SHALL list only dependencies that Phase 1 uses, and SHALL mark any entry reserved for a later phase as not used in Phase 1.
7. THE AutoReliance_Platform SHALL NOT add a library or infrastructure component outside the stack named in the brief without the user's approval.
8. THE AutoReliance_Platform SHALL NOT use a separate vector database, a shared database across bounded contexts, or a Phase 2 to 4 service.
9. THE AutoReliance_Platform SHALL satisfy the criteria in `validation.md` as the Definition of Done for every task: an OpenAPI entry for every new endpoint, an AsyncAPI entry for every new producer or consumer, an exact pin and ledger row for every dependency, a tenant A versus tenant B test for every tenant-scoped query, and a citation test for every AI-generated conclusion.
10. THE AutoReliance_Platform SHALL use Flyway for database migrations in Java services and Alembic for database migrations in Python services, SHALL NOT use one migration tool across both runtimes, and SHALL record the Spring Cloud release-train BOM version, and not the gateway starter version, in the Dependency_Ledger.
11. THE AutoReliance_Platform SHALL use the libraries approved beyond the brief (Spring Cloud Gateway, Flyway, Alembic, Spring Vault, hvac, openapi-generator-cli, openapi-typescript, buf, the AWS SDK for Java v2 S3 client, boto3, and the digest-pinned Garage image for local development) only under the conditions recorded in the Dependency_Ledger, and SHALL NOT use `langgraph` in Phase 1.
12. THE AutoReliance_Platform SHALL keep `xgboost` and `scikit-learn` in the Dependency_Ledger for the `release-assurance` inference sidecar and SHALL use them only in that sidecar.
13. THE AutoReliance_Platform SHALL use Jackson 3 as the JSON mapper in Java services, and no Java service SHALL depend on Jackson 2 `ObjectMapper` behavior.
14. THE AutoReliance_Platform SHALL package Kubernetes manifests under `platform/k8s/` as Kustomize `base/` and `overlays/dev` and `overlays/staging` with no raw duplicated manifests, SHALL NOT use Helm in Phase 1, and SHALL NOT add ShedLock, `celery-redbeat`, or Quartz in Phase 1.
15. THE AutoReliance_Platform SHALL pin `org.springframework.vault:spring-vault-core` explicitly to version 4.1.2 in every Java manifest that uses it, SHALL NOT use a Spring Cloud Vault starter, and SHALL verify with the dependency tree that 4.1.2 is the resolved version with no managed-version conflict against Spring Boot 4.1.x and the Spring Cloud 2025.1.x BOM.
16. THE AutoReliance_Platform SHALL NOT use MinIO in any image, client library, or Testcontainers module, and SHALL pin the local S3-compatible backend image by digest in the Dependency_Ledger.

### Requirement 27: Redis isolation and key discipline (non-functional)

**User Story:** As a platform operator, I want the job broker and the caches on separate Redis instances with explicit key lifetimes, so that cache eviction can never drop queued jobs.

#### Acceptance Criteria

1. THE AutoReliance_Platform SHALL run, in production configuration, two separate Redis instances: the Redis_Broker with `maxmemory-policy` set to `noeviction`, and the Redis_Cache with `maxmemory-policy` set to `allkeys-lru`.
2. THE AutoReliance_Platform SHALL give the Redis_Broker and the Redis_Cache distinct connection strings, and SHALL read both from Vault and not from source control, images, or logs.
3. THE `data-readiness` Bounded_Context SHALL use only the Redis_Broker, and THE `api-gateway` SHALL use only the Redis_Cache.
4. WHERE the Local_Environment runs a single Redis instance, THE Local_Environment SHALL set `maxmemory-policy` to `noeviction` on that instance.
5. THE AutoReliance_Platform SHALL set an explicit time-to-live on every key written to the Redis_Cache and SHALL NOT rely on eviction to bound cache size.
6. THE API_Gateway SHALL build every token cache key from the Tenant ID, the token's own expiry, and a digest of the token, SHALL NOT use a bare token string as a key, and SHALL set the key's time-to-live to no more than the token's remaining lifetime.
7. IF the Redis_Cache is unavailable or rejects a write, THEN THE API_Gateway SHALL treat the operation as a cache miss, validate the token against the identity provider, and record an error metric.
