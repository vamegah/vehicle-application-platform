# API Standards

## REST (gateway-exposed)
- Base path: `/api/v1/<context>/`
- All responses: `{ "data": ..., "meta": { "traceId": "...", "tenantId": "..." } }`
- Errors: RFC 9457 Problem Details (`application/problem+json`)
- Pagination: cursor-based only (`?cursor=<opaque>&limit=<int>`)

## Operator routes (`/admin/*`)
- `/admin/*` is an exception to the `/api/v1/<context>/` base-path rule. Phase 1 has two contracted operations in `contracts/openapi/admin.yaml`: `GET /admin/v1/layout/{tenantId}` (aggregate read-back of the layout across Vault and every process that caches it; read-only, owned by `legacy-integration`, routed by the gateway) and the internal-only `GET /admin/v1/layout-cache/{tenantId}` (served by each process that caches the layout, not routed by the gateway to external callers). `POST /admin/v1/layout/{tenantId}/refresh` is approved for Phase 2 and is not implemented in Phase 1.
- Admin routes are versioned immediately after the /admin/ prefix: /admin/v1/<resource>/{tenantId}. Tenant routes remain /api/v1/<context>/. The two namespaces are intentionally distinct: tenant routes are customer-facing and gated by tenant principal; admin routes are operator-facing and gated by platform-operator role. Versioning either namespace does not affect the other.
- Security scheme: `platformOperator`, bound to the `platform-operator` RBAC role. The role is distinct from the six tenant roles (release manager, firmware engineer, configuration engineer, data engineer, auditor, tenant administrator) and is not tenant-scoped.
- Extension: every `/admin/` operation declares `x-audit-event-required: true`.
- Responses keep the `{ "data": ..., "meta": { "traceId": "...", "targetTenantId": "...", "tenantId": null } }` envelope and `application/problem+json` errors. `tenantId` is `null` because the operator is not tenant-scoped, and `targetTenantId` carries the target tenant (`meta.tenantId = null`, `meta.targetTenantId = <tenantId>`).
- The gateway rejects `/admin/*` requests from any principal without the platform-operator role, including every tenant-scoped principal.
- OpenAPI lint rule: tenantId in a path parameter is forbidden unless the route path starts with /admin/. Any route whose path starts with /admin/ MUST declare the platform-operator security scheme and the audit-event-required extension.
- Audit: every `/admin/*` call emits `audit.event.recorded` with payload `{ operatorPrincipal, targetTenantId, action, result, occurredAt }`. The event envelope `tenantId` is the target tenant; the operator principal is the separate `operatorPrincipal` field.
- Internal cache route: `GET /admin/v1/layout-cache/{tenantId}` is served on the internal management port `admin-cache` (8081/TCP), restricted by NetworkPolicy to the aggregate caller and the operator gateway. Any admin-path HTTP failure returns 503 `application/problem+json` with no fallback and no cached value.

## gRPC (internal)
- Package: `autoreliance.<context>.v1`
- Every request includes `tenant_id` field
- Breaking changes require a new package version (`v2`), never mutation of `v1`
- Layout: a `v1` package lives in `contracts/proto/<context>/`; a `v<N>` package (N >= 2) lives in `contracts/proto/<context>/v<N>/`, because buf forbids two packages in one directory. CI runs `buf lint` and `buf breaking --against .git#branch=main` on every `contracts/proto/` change

## Kafka events
- Topic naming: `<domain>.<entity>.<action>` (past tense, e.g. `firmware.change.committed`)
- Documented naming exceptions (exactly these, no others):
  - `dlt.<consumer-group-id>` dead-letter topics.
  - `mes.quality.inspection.recorded` (four segments, approved as written).
  - `release.evidence.gap.detected` (four segments, from the original platform event catalog, approved as written on 2026-11-26).
  - Reserved Phase 2+ names from the same catalog, approved as written for when their phase implements them: `quality.failure.cluster.detected` (Phase 2), `dealer.service.event.recorded` (Phase 2), `ota.release.risk.scored` (Phase 3). They have no producer or consumer in Phase 1.
- `document.text.extracted` matches `<domain>.<entity>.<action>` and is not a naming exception. It is a document-specific topic: it must not be generalised into a generic record or document topic. ERP and MES records use their own domain topics.
- Base envelope (every topic): `{ "eventId", "eventType", "version", "tenantId", "occurredAt", "payload" }`
- Source-ingestion envelope (extension of the base envelope, required on the `legacy-integration` source topics `erp.masterdata.changed`, `erp.purchaseorder.updated`, `mes.workorder.reported`, `mes.quality.inspection.recorded`, and `document.text.extracted`): adds top-level `sourceSystem`, `naturalKey`, `contentHash`, `extractedAt`, and an optional `sourceRecordVersion`.
  - `sourceSystem`: the source system the record or document came from.
  - `naturalKey`: built by the connector from named source columns (a delimited string of the form `<sourceSystem>|<segment>|...`), never supplied by the source and never taken from a source field as-is. Each topic's AsyncAPI contract documents its column composition.
  - `contentHash`: SHA-256 (lowercase hex) of the record. For ERP and MES topics it is taken over the RFC 8785 canonical JSON form of the ACL-mapped `payload`. For `document.text.extracted` it is the SHA-256 of the PDF bytes.
  - `extractedAt`: RFC 3339 timestamp set by the connector when it extracted the record.
  - `sourceRecordVersion`: optional positive integer, monotonic per source record, present only when the source provides one.
- Consumers MUST be idempotent (dedupe on `eventId`). `naturalKey` and `contentHash` are never the idempotency key.
- Ordering of versions of one source record: use `sourceRecordVersion` when present, otherwise `(extractedAt, contentHash)`. An event whose `contentHash` equals the stored one is a no-op.
- Partition key: `{tenantId}:{canonicalId}` for platform events; `{tenantId}:{naturalKey}` for the four ERP and MES topics; `{tenantId}:{canonicalDocumentId}` for `document.text.extracted`.
