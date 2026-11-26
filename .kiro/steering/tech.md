# Technology Stack (LOCKED — do not substitute)

## Backend
- Java 21 + Spring Boot 4.1 (Spring Cloud 2025.1 "Oakwood", Jackson 3) — transactional/rule-heavy services
- Python 3.12 + FastAPI — AI-native services
- gRPC (protobuf) for service-to-service; REST/OpenAPI 3.1 at gateway

## Data
- PostgreSQL 16 (system of record)
- Neo4j 5.x (dependency graph — Integration Intelligence + Knowledge only)
- pgvector (inside PostgreSQL — DO NOT add Pinecone, Weaviate, Qdrant, etc.)
- Apache Kafka 3.x (event backbone)
- Redis + Celery (background jobs)
- S3-compatible object store = the binary-document store (PDF bytes, large extracted text). PostgreSQL holds metadata and the object URI only, never document bytes.

## Object storage
- Production layout: two shared buckets per environment, `autoreliance-raw-{env}` (original PDFs) and `autoreliance-text-{env}` (extracted text). Tenant separation is a key prefix: `{tenantId}/raw/...` and `{tenantId}/text/...`. Raw and text are separate buckets because their reader sets differ (only legacy-integration reads raw; data-readiness reads text only).
- Tenant isolation: prefix-scoped IAM or bucket policies with per-tenant credentials on AWS S3 and Ceph RGW (e.g. `arn:aws:s3:::autoreliance-text-{env}/{tenantId}/text/*`). The adapter's tenant-prefix check is defence in depth on every backend. Where a backend cannot scope by prefix, the adapter check is the only tenant barrier there (known dev-only limitation).
- Dedicated bucket pair per tenant (`autoreliance-raw-{env}-{tenantId}`, `autoreliance-text-{env}-{tenantId}`) is an opt-in exception only, for physical isolation, separate cost allocation, or a retention/immutability profile a prefix cannot express. It needs a stated reason, an approval reference, and the documented provisioning path. It is never the default.
- Current dev S3 backend: Garage (digest-pinned). Current CI test container: SeaweedFS (digest-pinned). SeaweedFS is also the approved dev-backend alternative if the switch trigger in ADR-019 is met; until then it does not run in dev. Production: S3 (cloud) or Ceph RGW (on-prem). MinIO: not approved (archived February 2026).
- Do not change the docker-compose image without recording a new dated decision. Garage's permission model is per bucket, NOT per prefix, so it cannot enforce tenant isolation inside a shared bucket (raw-versus-text separation still holds because they are separate buckets). The adapter tenant-prefix check is the only barrier for tenants within the text bucket where the backend is Garage. Authoritative proof of prefix-scoped tenant isolation runs against AWS S3 and Ceph RGW before production.
- Approved S3 clients: AWS SDK for Java v2 S3 client (Java services) and boto3 (Python services). Both are configured with checksum behavior `when_required` for S3-compatible backends.
- Server-side encryption: production uses per-tenant SSE-KMS keys referenced from Vault. Local dev has no KMS (key strategy `none`).

## AI
- LangGraph (agent orchestration)
- PyTorch, XGBoost, scikit-learn
- python-can, cantools, ASAM MDF (automotive protocols)

## Infra
- Docker, Kubernetes, Terraform
- Kustomize (built into `kubectl`, no extra install) for `platform/k8s/` base and overlays in Phase 1
- GitHub Actions (do not introduce GitLab CI, CircleCI, etc.)
- OpenTelemetry, Prometheus, Grafana
- Vault (secrets), SSO, RBAC

## Approved for Phase 2+
- Helm (not used in Phase 1; introduce only when the trigger in the design document is met)
- Per-request, short-lived per-tenant storage credentials (STS or equivalent)

## Prohibited substitutions
- No MongoDB, DynamoDB, or other NoSQL for system of record
- No separate vector database
- No alternative agent framework (no LangChain agents, CrewAI, AutoGen)
- No alternative frontend framework (React/Next.js only)
- No MinIO (any image, client module, or Testcontainers module)
