# Security Constraints (NON-NEGOTIABLE)

- Every entity carries `tenant_id`; every Kafka message carries `tenantId`
- PostgreSQL row-level security on every table
- Neo4j queries must be scoped to the tenant's namespace/label
- Every read of release evidence, warranty data, or SBOM emits
  `audit.event.recorded` to the immutable audit topic
- No secrets in code; Vault only
- SSO + RBAC at gateway; no service trusts a tenant ID from the client
  without validating it against the authenticated principal
- Tenant ID in a request path is forbidden for tenant-facing routes. The exception is routes under /admin/*, which are reachable only by principals with the platform-operator role. Every /admin/* call is audited with operatorPrincipal, targetTenantId, action, and result. The rule for tenant-facing routes is unchanged.

## Data paths and admin paths
Data paths are Kafka-only. No service-initiated synchronous HTTP exists between bounded contexts for data-plane operations (extraction, ingest, query, mutation). Admin paths under /admin/* are the sole exception: they may use synchronous HTTP between services for read-only diagnostics, gated by platform-operator role and audited. Any admin-path HTTP failure returns 503 to the caller; no fallback, no cached value.

- Scope: gateway-to-service request routing is not service-initiated, and the gRPC contracts (configuration validation, graph facts) are not "synchronous HTTP" under this rule.
- Role gate answers who; NetworkPolicy answers from where. Both required. Internal admin routes (`GET /admin/v1/layout-cache/{tenantId}`) are served on the `admin-cache` management port and restricted by NetworkPolicy to the aggregate caller and the operator gateway.
- Admin audit: every /admin/* call emits `audit.event.recorded`. The event's envelope `tenantId` is the target tenant. The operator principal is carried in the separate `operatorPrincipal` field.
- Storage adapters never read Vault per request (cache only). The /admin/v1/layout/{tenantId} handler reads Vault on invocation (operator-triggered, low-frequency).