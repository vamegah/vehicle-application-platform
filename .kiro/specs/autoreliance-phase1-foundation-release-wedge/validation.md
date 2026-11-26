# Validation Criteria

## Must pass before any task is marked complete
- [ ] Every new API endpoint has an OpenAPI 3.1 entry in `contracts/openapi/`
- [ ] Every new Kafka producer/consumer has an AsyncAPI entry in `contracts/asyncapi/`
- [ ] Every dependency added has an exact pin in the manifest AND a row in `DEPENDENCIES.lock.md`
- [ ] Every tenant-scoped query has a test proving tenant A cannot read tenant B data
- [ ] Every AI-generated conclusion has a test asserting at least one evidence citation
- [ ] Redis broker and cache are separate instances in production config.
- [ ] Spring Cloud BOM version is pinned in the ledger.
- [ ] Flyway and Alembic are both configured (one per runtime).
- [ ] Generated OpenAPI clients are drift-checked in CI.
- [ ] buf breaking check runs on every contracts/proto/ change.
- [ ] release-assurance does not consume release.risk.scored.
- [ ] Phase 1 ML scope of the sidecar is documented.
- [ ] No service depends on Jackson 2 ObjectMapper behavior.
- [ ] Kustomize overlays exist for dev and staging; no raw duplicated manifests.
- [ ] Data paths are Kafka-only: no service-initiated synchronous HTTP exists between bounded contexts for data-plane operations (extraction, ingest, query, mutation). The sole exception is read-only /admin/* diagnostics, gated by platform-operator role and audited; any admin-path HTTP failure returns 503 with no fallback and no cached value.
- [ ] No HTTP client in any service targets another bounded context except the registered /admin/* cache-read client (repository test, task 7.18).
- [ ] The layout cache endpoint and the aggregate read-back return 503 on any admin-path failure, with no fallback and no cached value, and the cache endpoint carries no document or ingest payload.
- [ ] NetworkPolicy restricts cache routes to the aggregate caller and operator gateway; a test confirms a pod outside the allowlist is denied.
- [ ] legacy-integration is single-replica in Phase 1; data-readiness has a single Celery beat process.
- [ ] Spring Vault 4.1.2 resolves against Spring Boot 4.1.x without a managed-version conflict.
- [ ] ERP/MES records and PDF extraction use separate topics; no combined source.record.extracted topic exists.
- [ ] No PDF bytes are stored in PostgreSQL bytea or large objects.
- [ ] Object-store adapter is used in both prod (S3-compatible) and local (Garage).
- [ ] Orphaned-object reaper is implemented and tested.
- [ ] data-readiness credential cannot read the raw/ prefix (verified by a failing access test).
- [ ] A tenant B credential cannot read tenant A objects, verified at the storage layer (not only the adapter) on AWS S3 and Ceph RGW with prefix-scoped policies as the authoritative pre-production check, and on the Garage dedicated layout. A SeaweedFS CI run of the same test is a smoke test only and does not satisfy this item. On Garage with the shared layout this test is reported "not applicable", never "passed" (see Known Phase 1 limitations and the next two items).
- [ ] Tenant isolation within the shared text bucket is enforced by the adapter check in dev on Garage, and by prefix-scoped IAM on S3/Ceph RGW. Both the gap and the mitigation are covered by tests.
- [ ] Gap test `garage_shared_layout_cross_tenant_gap_is_documented` exists and asserts that a cross-tenant read directly against Garage (bypassing the adapter) succeeds; mitigation test exists and asserts the same read through the StorageProvider adapter fails with 403 or 404.
- [ ] The SeaweedFS smoke test runs against a digest-pinned image from `DEPENDENCIES.lock.md`; if the digest cannot be verified at CI time the test is recorded BLOCKED, never PASSED.
- [ ] The adapter performs no Vault read on the request path (Vault mock call count unchanged across N requests) and uses the layout cached at initialization; an unknown tenant is refused until re-initialization.
- [ ] prod profile refuses to start without per-tenant key strategy, not merely without KMS configuration.
- [ ] SeaweedFS dev-backend switch trigger is documented in ADR-019 and has not been met.
- [ ] The local S3 image is pinned by digest, and no MinIO image, client, or Testcontainers module is used.
- [ ] The four ERP/MES contracts carry naturalKey, contentHash, and extractedAt, make sourceRecordVersion optional, and contain no hash-based key field.
- [ ] The StorageProvider conformance suite passes against Garage in CI, under both the shared and the dedicated layout with the same adapter code. [Amended for ADR-018.]
- [ ] Production layout is two shared buckets per environment; tenant isolation is by prefix, verified by a cross-tenant read test.
- [ ] data-readiness IAM cannot read the raw/ prefix (failing-access test).
- [ ] A dedicated bucket pair is provisioned only via the documented exception path, not by default.

- [ ] Onboarding runbook exists and names the rollout trigger owner.
- [ ] Layout change is documented as a three-phase operation with data migration, not a flag flip.
- [ ] Phase 2 trigger for the explicit operator-triggered layout refresh is documented.
- [ ] Onboarding SLA is documented as 4 business hours during working hours, with a named Phase 2 revisit trigger.
- [ ] The four /admin/* operator-path tests exist and pass: tenant-scoped principal 403, non-operator 403, operator 200 with audit event, non-/admin/ path-borne tenant ID rejected by lint and gateway.
- [ ] Dedicated bucket pairs are provisioned only at onboarding for a tenant with no stored objects; the adapter fails closed on a layout change for a tenant with stored objects.
- [ ] The storage layout cache is read once at adapter startup; no TTL or timer-based refresh exists.
- [ ] Adapter rejects layout change on a tenant with objects under the old layout, with an error naming the Phase 2 migration path. Covered by a test.
- [ ] Read-back reports Vault value, data-readiness cache, and storage-adapter cache, each with loadedAt.
  - Note: "storage-adapter" is the StorageProvider adapter inside legacy-integration (process id `legacy-integration/storage-adapter`); the data-readiness cache is `data-readiness/storage-adapter`.
- [ ] Read-back includes consistent and recommendation fields, with a test for the divergent case.
- [ ] Aggregate read-back fails closed (returns 503 or a clear diagnostic) if a cache endpoint is unreachable, rather than reporting consistent:true on partial data.
- [ ] Admin routes use `/admin/v1/<resource>/{tenantId}` and the OpenAPI lint rule matches the `/admin/` prefix, not a hardcoded path (fixtures pass and fail as specified in tasks 2.4 and 7.15).
- [ ] Every process that caches the layout is on `platform/layout-cache-registry.yaml`, with a test that fails when a StorageProvider adapter instance exists in an unregistered process.

## Manual review gates (do not auto-approve)
- [ ] `design.md` does not propose a shared database
- [ ] `design.md` does not propose a separate vector database
- [ ] `tasks.md` contains no Phase 2–4 services

## Known Phase 1 limitations
- Storage credentials are static, long-lived, per-tenant access keys held in Vault (ADR-014). Per-request, short-lived per-tenant credentials (STS or session policies) are deferred to Phase 2.
- Local development has no server-side encryption: Garage supports SSE-C only and has no SSE-KMS, so the local key strategy is `none`. Only the `prod` profile enforces per-tenant SSE-KMS (ADR-015).
- The shared layout uses two buckets per environment regardless of the tenant count. Only dedicated exception tenants add buckets (two each) and count against the account bucket quota (default 10,000 general purpose buckets per AWS account, adjustable up to 1 million). [Amended for ADR-018: the earlier wording described two buckets per tenant.]
- Named dev limitation (ADR-020). Raw-versus-text separation is preserved on every backend, including Garage, because raw and text are separate buckets and Garage scopes keys to buckets: the `data-readiness` key is denied on the raw bucket by the store. Tenant-within-text isolation is NOT enforced by Garage's access control in dev, because Garage cannot scope permissions by prefix or apply bucket policies; the adapter's tenant-prefix check is the only barrier there. On AWS S3 and Ceph RGW the prefix-scoped IAM policy is the barrier and the adapter check is defence in depth. The adapter check is never to be described as replacing store-level isolation in production. This is weaker than the earlier requirement that the store itself deny tenant B for tenant A's object (ADR-014) and applies to local development and CI only. On Garage under the shared layout the store-level cross-tenant test is reported "not applicable" (via the `prefixPolicies` flag), never "passed"; the gap test and the mitigation test run there instead. Confirmed by the user (ADR-020).
- Garage supports no bucket policies, object versioning, or object lock, so the platform uses none of them in Phase 1.
- The dedicated-bucket exception has a single approver (the platform owner) in Phase 1. From the point a second engineer or a security reviewer joins (Phase 2 trigger), it needs two approvers, the platform owner and security. No two-approver workflow exists in Phase 1 (ADR-021).
- The per-tenant storage layout is read from Vault once at adapter initialization and cached. A layout change or a newly onboarded tenant takes effect only after a restart or rollout of the affected deployables, and an unknown tenant is refused until then (ADR-021).
- Whether Garage v2.6.0 accepts the default AWS SDK checksums was not established from its documentation. Both clients use the when-required setting, and the conformance suite confirms it.
- Ceph RGW and AWS S3 conformance runs (with prefix-scoped policies) are the authoritative proof of prefix-scoped isolation. They are pre-production checks and are not part of every CI run. SeaweedFS currently runs in CI as a digest-pinned test container for a SMOKE TEST of the cross-tenant behavior. It is not the authoritative proof: SeaweedFS prefix-scoped IAM has known bugs (for example seaweedfs issue 9788), so a green SeaweedFS run is never release evidence and the Release_Gate and the pre-production checklist must not accept it. If the SeaweedFS image digest pinned in `DEPENDENCIES.lock.md` cannot be verified at CI time, the smoke test is recorded as BLOCKED, never PASSED. SeaweedFS is not the dev backend while the ADR-019 switch trigger is unmet (ADR-019, ADR-020).

- Layout change for a tenant with stored objects is refused in Phase 1 (fail closed, audit event) until the migration path exists; Phase 1 builds only scaffolding for it. The dedicated layout may be set only for a tenant with zero stored objects (ADR-021, ADR-022).
- The explicit operator-triggered layout refresh (`POST /admin/v1/layout/{tenantId}/refresh`) is a Phase 2 item with the trigger recorded in ADR-022 and is not implemented in Phase 1. The storage layout cache is read once at adapter startup and has no TTL or timer (ADR-021).
- Operator routes under `/admin/*` share the gateway listener in Phase 1, with role gating only. Moving them to a separate listener or subdomain is a Phase 2 item (ADR-023).

## Notes
- Data-path rule (ADR-024): gateway-to-service routing is not service-initiated, and the gRPC contracts (configuration validation, graph facts) are not "synchronous HTTP" under the rule. The one admin-path HTTP call is `GET /admin/v1/layout-cache/{tenantId}` from legacy-integration to data-readiness, used by the layout read-back; it is served on the `admin-cache` port (8081/TCP) behind a NetworkPolicy. Storage adapters never read Vault per request, while the /admin/v1/layout/{tenantId} handler reads Vault on invocation (operator-triggered, low-frequency).
- Do not change the docker-compose Garage image without recording a new dated decision (ADR-019). The CI dependency-pin check (task 1.4) fails when the compose image reference differs from the `DEPENDENCIES.lock.md` row. The ADR-019 trigger to switch dev to SeaweedFS stands (ADR-020 does not withdraw it); a change of the dev backend needs a new dated decision.
- Phase 1 release-assurance sidecar uses scikit-learn and xgboost for risk scoring and coverage analysis. No agent orchestration in Phase 1. langgraph is deferred to Phase 2.

