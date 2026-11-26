# Dependency Ledger — resolved at spec approval

Versions in this file were verified on 2026-11-25 against Maven Central (metadata and POMs), the Spring Cloud supported-versions wiki, or the upstream registry named in the Notes column. A row marked `UNVERIFIED - resolve at task 1.4` has no verified version yet. Task 1.4 resolves every remaining row and adds the rest of the Phase 1 libraries.

Spring line (ADR-006): Spring Boot 4.1.x with Spring Cloud 2025.1.x (Oakwood). Spring Boot 3.x and earlier Spring Cloud trains are not used anywhere.

## Java (Spring Boot 4.1.x)
| Artifact | Version | Notes |
|---|---|---|
| org.springframework.boot:spring-boot-starter-parent / spring-boot-dependencies (BOM) | 4.1.3 | ADR-006. Latest 4.1.x patch on Maven Central on 2026-11-25. Do not use 4.0.x. Boot 4.2.0 also exists on Central and is not selected (the user fixed the 4.1 line). Java 21 is within the supported range (Boot 4.x requires Java 17 or later). Manages Spring Framework 7.0.11, Tomcat 11.0.27 (Servlet 6.1), Hibernate 7.4.15.Final, Micrometer 1.17.3. |
| org.springframework.cloud:spring-cloud-dependencies (BOM) | 2025.1.5 | ADR-006. Oakwood train. Latest 2025.1.x on Maven Central on 2026-11-25; the user's minimum is 2025.1.2. Imported in `dependencyManagement`; artifacts it manages carry no `<version>`. Record the BOM version, never the starter version. KNOWN INCONSISTENCY: the 2025.1.5 BOM is built against Spring Boot 4.0.10 and the 2025.1.5 release post says it is compatible with Boot 4.0, while the Spring Cloud supported-versions wiki says Oakwood supports Boot 4.1.x and 4.0.x. Task 1.4 runs a build-and-start check of the gateway on Boot 4.1.3 with this BOM before the pin is final. |
| org.springframework.cloud:spring-cloud-starter-gateway-server-webflux | 5.0.5 | ADR-003, ADR-006. api-gateway only. Version managed by the Spring Cloud BOM 2025.1.5 (Spring Cloud Gateway 5.0.x). The Boot 4 generation renames the old `spring-cloud-starter-gateway` starter to `spring-cloud-starter-gateway-server-webflux`. |
| org.springframework.vault:spring-vault-core | 4.1.2 | ADR-003, ADR-006, ADR-010 (decided by the user). Explicit `<version>` in every manifest that uses it, because Spring Vault is not managed by the Spring Boot 4.1.3 BOM. The Spring Cloud 2025.1.x BOM manages `spring-vault-core` 4.0.x through Spring Cloud Vault dependencies; the explicit 4.1.2 pin overrides that managed version, and no Spring Cloud Vault starter is used. Task 1.4 asserts with `mvn dependency:tree` that 4.1.2 is the resolved version with no conflict. Verified 2026-11-25: 4.1.2 is on Maven Central and its release notes list Spring Framework 7.0.11 and Spring Data 2026.0.3 (the versions Boot 4.1.3 manages), a fix for concurrent failed certificate rotations overwriting a pending retry (#1100), and explicit charsets in place of the platform default (#1098, #1099). Spring Vault core has no 5.0.x release; 5.0.x is Spring Cloud Vault, which is not used. |
| software.amazon.awssdk:bom | 2.59.10 | ADR-012. Approved by user, Decision 3. Imported in `dependencyManagement` of `legacy-integration`; the `s3` artifact then carries no `<version>`. Latest release in Maven Central metadata on 2026-11-25. |
| software.amazon.awssdk:s3 | 2.59.10 | ADR-012, ADR-013. Approved by user, Decision 3. AWS SDK for Java v2, `legacy-integration` only (S3-compatible `StorageProvider` adapter). Chosen because it is the reference S3 client, supports an endpoint override and a path-style flag for Garage, SeaweedFS, and Ceph RGW, and supports SSE-KMS in production. The client MUST set `requestChecksumCalculation(WHEN_REQUIRED)` and `responseChecksumValidation(WHEN_REQUIRED)` (SDK 2.30 and later send flexible checksums by default, which some S3-compatible stores reject; ADR-013). Task 1.4 confirms with `mvn dependency:tree` that it brings no direct `com.fasterxml.jackson.databind` dependency (the SDK shades its Jackson core) and that its HTTP client choice is pinned. |
| org.flywaydb:flyway-core | 12.4.0 | APPROVED beyond the brief (ADR-003). Condition: Java runtime only; Python services use Alembic, never one cross-runtime tool. Version equals `flyway.version` managed by Spring Boot 4.1.3. Boot 4 needs `spring-boot-starter-flyway` (4.1.3) for auto-configuration. |
| org.flywaydb:flyway-database-postgresql | 12.4.0 | APPROVED with Flyway. Same version as `flyway-core`. Verified on Maven Central. |
| org.springframework.boot:spring-boot-starter-flyway | 4.1.3 | Boot 4 starter that enables Flyway auto-configuration. Boot-managed. |
| org.springframework.kafka:spring-kafka | 4.1.3 | Boot-managed. |
| org.apache.kafka:kafka-clients | 4.2.2 | Boot-managed. The platform broker stays Apache Kafka 3.x per `tech.md`; kafka-clients 4.x talks to brokers 2.1 and later. Task 1.4 runs a producer and consumer test against the pinned 3.x broker image. |
| org.neo4j.driver:neo4j-java-driver | 6.1.0 | Boot-managed. The Neo4j server stays 5.x Community. Task 1.4 verifies driver 6.x against the pinned 5.x server. |
| io.grpc (grpc-java) | 1.84.1 | Boot-managed (`grpc-java.version`). Artifact set resolved at task 1.4. |
| org.springframework.grpc (Spring gRPC) | 1.1.2 | Boot-managed (`spring-grpc.version`). Exact artifact names (server and client starters) resolved at task 1.4. |
| com.google.protobuf:protobuf-java | 4.36.2 | Boot-managed. Resolved at task 1.4 together with the protoc version used by buf and the Maven plugin. |
| tools.jackson (Jackson 3 BOM `jackson-bom`) | 3.1.8 | ADR-006. Jackson 3 is the default mapper in Boot 4. Package root is `tools.jackson`; `com.fasterxml.jackson.annotation` annotations stay. No service uses the Jackson 2 `ObjectMapper`. |
| com.fasterxml.jackson (Jackson 2 BOM `jackson-2-bom`) | 2.21.8 | Transitive only, kept by Boot for annotations and libraries not yet on Jackson 3. Not a direct dependency of any Phase 1 module. A repository check fails on a direct import of `com.fasterxml.jackson.databind`. |
| org.testcontainers:testcontainers | 2.0.5 | Boot-managed. Testcontainers 2.x renamed modules and packages (for example `org.testcontainers.postgresql.PostgreSQLContainer`); every module artifact is pinned at task 1.4. Object-store integration tests use a `GenericContainer` with the digest-pinned Garage image (ADR-013); no object-store-specific Testcontainers module is used. |
| org.junit.jupiter (JUnit 5/6 line) | 6.0.3 | Boot-managed `junit-jupiter.version`. |
| org.postgresql:postgresql | 42.7.14 | Boot-managed. |

Pact JVM and jqwik are not managed by Boot. Their versions are `UNVERIFIED - resolve at task 1.4`, and task 1.4 must confirm each works on JUnit 6 and Spring Framework 7 before pinning.

## Python (FastAPI services)
| Package | Version | Notes |
|---|---|---|
| fastapi | 0.114.2 | |
| pgvector | 0.3.2 | |
| xgboost | 2.1.1 | KEPT (ADR-004). Used only in the release-assurance inference sidecar, for risk scoring (failure-likelihood ranking of tests). Seeded and deterministic. |
| scikit-learn | 1.5.1 | KEPT (ADR-004). Used only in the release-assurance inference sidecar, for coverage analysis. Seeded and deterministic. |
| alembic | 1.20.1 | APPROVED beyond the brief (ADR-003). Condition: Python runtime only (`data-readiness`, inference sidecar if it owns tables); Java services use Flyway. Verified on PyPI (requires Python >=3.10). Requires SQLAlchemy; its exact pin is resolved in task 1.4. |
| hvac | 2.4.0 | APPROVED beyond the brief (ADR-003). Vault client for Python services. Verified on PyPI (released 2025-10-30, requires Python >=3.8). |
| boto3 | 1.44.12 | ADR-012, ADR-013. Approved by user, Decision 3. `data-readiness` only, for the read-only `StorageProvider` adapter that fetches large extracted text from the text bucket under the tenant's `text/` prefix (works with Garage, SeaweedFS, Ceph RGW, and S3 through `endpoint_url`). The client MUST be built with `botocore.config.Config(request_checksum_calculation='when_required', response_checksum_validation='when_required', s3={'addressing_style': 'path'})` for S3-compatible backends. Chosen because `legacy-integration` uses the AWS SDK and boto3 is the matching reference client for the Python runtime. Verified on PyPI on 2026-11-25 (requires Python >=3.10). `botocore` and `s3transfer` are transitive and are pinned exactly at task 1.4. |
| celery | UNVERIFIED - resolve at task 1.4 | `data-readiness` only. Runs worker replicas and exactly one beat process (ADR-009). No `celery-redbeat` (not approved). |

## Node (web)
| Package | Version | Notes |
|---|---|---|
| next | 14.2.10 | |
| react | 18.3.1 | |
| tailwindcss | 3.4.10 | |
| openapi-typescript | 7.13.0 | APPROVED beyond the brief (ADR-003). Generates the typed `apps/web` client from `contracts/openapi/gateway.yaml`. Condition: CI regenerates on every change to `contracts/openapi/` and fails on any diff. Verified on npm. |

## Build and CI tooling
| Tool | Version | Notes |
|---|---|---|
| Apache Maven | UNVERIFIED - resolve at task 1.4 | Boot 4.2 documents Maven 3.6.3 or later as the minimum. Task 1.4 confirms the minimum for Boot 4.1.3 and pins the build version. |
| @openapitools/openapi-generator-cli | 2.43.0 | APPROVED beyond the brief (ADR-003). npm wrapper that generates Java and Python clients. Requires Node >=22. Condition: CI regenerates clients on every change to `contracts/openapi/` and fails on any diff. Wrapper version verified on npm. |
| openapi-generator (jar run by the CLI wrapper, set in `openapitools.json`) | UNVERIFIED - resolve at task 1.4 | The wrapper version does not fix the generator version. Task 1.4 must pin the generator jar version explicitly. Generated Java clients must target Jackson 3 (`tools.jackson`); task 1.4 verifies the generator supports it and records the setting. |
| buf | 1.75.0 | APPROVED and mandatory (ADR-003). CI runs `buf lint` and `buf breaking --against .git#branch=main` on every `contracts/proto/` change. Verified on the bufbuild/buf GitHub releases page. |
| Kustomize (built into `kubectl kustomize`) | no separate install | ADR-007. Tooling note, not a library dependency. Approved for Phase 1 with no new dependency. Latest stable kubectl on dl.k8s.io on 2026-11-25 is v1.37.3. The minimum kubectl version that the Phase 1 overlays need is `UNVERIFIED - resolve at task 1.6`; task 1.6 records the version the CI job runs. |
| Helm | not used in Phase 1 | ADR-007. Approved for Phase 2+ only (see `tech.md`). Do not add a Helm dependency or chart in Phase 1. |

## Container images and infrastructure
| Image | Version | Notes |
|---|---|---|
| Garage (local development and Testcontainers; default S3-compatible object store, AGPL-3.0, run only as a separate dev container, never linked or redistributed) | `dxflrs/garage:v2.6.0@sha256:4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013` | ADR-013 (Decision 1). The digest is the multi-platform manifest-list digest of tag `v2.6.0`, read from the Docker Hub registry API (`registry-1.docker.io/v2/dxflrs/garage/manifests/v2.6.0`) on 2026-11-25 with TLS verification on; its platform digests are linux/amd64 `sha256:353a3f29291482faa51ef34de76508e0df448d37842eeeef5f0b69a5f9274eb3`, linux/arm64 `sha256:5de822389154e6c59bf8906097ec1ed48adcc9d159f08f8691b73654e2573a4b`. Compose and Testcontainers reference `dxflrs/garage:v2.6.0@sha256:4b5a318f...` and never a bare tag or `latest`. ADR-019 (2026-11-25): Garage stays the dev backend; do not change this image without recording a new dated decision, and the CI pin check compares the compose reference with this row. The ADR-019 trigger to switch dev to SeaweedFS stands (ADR-020 does not withdraw it): dev stays on Garage until the trigger is met, and a change needs a new dated decision. Garage has no bucket policies, no prefix-scoped permissions, and no SSE-KMS (permissions are per access key per bucket; SSE-C only), so the platform uses separate raw and text buckets (ADR-014, amended by ADR-018: two shared buckets per environment with tenant prefixes, so on Garage the tenant prefix separation is not store-enforced, a recorded dev-only limitation) and local key strategy `none` (ADR-015). Region string for clients is `garage`. Task 1.4 re-verifies the digest, runs the adapter conformance suite (task 7.9) against it, and confirms the checksum settings on the AWS SDK for Java v2 and boto3 clients. |
| SeaweedFS (current CI smoke-test container for the cross-tenant test of task 7.9; approved dev-backend alternative under the ADR-019 switch trigger, not running in dev and not configured in compose) | `chrislusf/seaweedfs:4.55@sha256:7ca46aeae2f223b37e5d91593c17ab37738eec6df6ab69b48a0487f7643342b9` | ADR-013, ADR-018, ADR-019, ADR-020. Apache-2.0. Digest is the OCI index (manifest list) digest of tag `4.55`, read from the Docker Hub registry API (`registry-1.docker.io/v2/chrislusf/seaweedfs/manifests/4.55`, `Docker-Content-Digest` header, TLS verification on) on 2026-11-25; 4.55 is also the latest GitHub release at that date. Task 1.4 re-reads the digest and confirms the tag is still the latest stable release or records a newer tag and digest. SeaweedFS image digest is pinned in this ledger (pinned 2026-11-25). If the digest cannot be verified at CI time, the SeaweedFS test is recorded as BLOCKED, not PASSED. The test is a smoke test and not the authoritative proof of prefix-scoped isolation (SeaweedFS prefix-scoped IAM has known bugs, for example seaweedfs issue 9788); the authoritative runs are AWS S3 and Ceph RGW before production, and a SeaweedFS green run is never release evidence. Do not use `latest`, a bare tag, or any other digest. |
| Terraform and its AWS provider (task 1.8, `platform/terraform/storage/`) | UNVERIFIED - resolve at task 1.4 | Terraform is in the approved stack (`tech.md`). Exact versions of the Terraform CLI and the AWS provider are resolved and pinned at task 1.4; task 1.8 is blocked while this row is `UNVERIFIED`. |
| Ceph RGW (production on-prem only; never local development) | deployment-managed | ADR-013. Supports S3 bucket policies and per-user grants; the platform uses bucket-level grants for the raw and text separation and prefix-scoped policies for tenant isolation in the shared buckets (ADR-018). Conformance with the adapter suite is a pre-production check (task 7.9). |

## MCP servers (`.kiro/settings/mcp.json`, not edited by the spec work)
| Server | Pin status | Notes |
|---|---|---|
| context7 | PINNED | `@upstash/context7-mcp@4.8.0` is pinned in `args`. |
| postgres-schema | PINNED | `@bytebase/dbhub@0.6.2` is pinned in `args`. |
| neo4j-schema (neo4j-mcp) | UNPINNED - known gap | Started from a locally installed `neo4j-mcp` binary. The version v1.6.1 appears only in the `description` text and is not enforced. Record the installed version outside `mcp.json` or pin the install. |

## Not used in Phase 1 (do not add to a manifest)
| Item | Reason |
|---|---|
| langgraph 0.2.28 | No agent orchestration in Phase 1 (ADR-004). Deferred to Phase 2. |
| ShedLock, celery-redbeat, Quartz | Not approved. Single-replica scheduling constraint instead (ADR-009). |
| Spring Cloud Vault starters (`spring-cloud-starter-vault-config`) | Not used. Vault access is through `spring-vault-core` 4.1.2 directly (ADR-010). |
| PostgreSQL `bytea` columns, large objects, or a mounted volume as storage for PDF bytes | Prohibited. PDF bytes live only in the S3-compatible object store (ADR-012). |
| MinIO (any image, client, or Testcontainers module `testcontainers-minio`) | Not approved. MinIO is archived and no official image is pullable (ADR-013, Decision 1). Local development uses Garage. |
| Helm | Approved for Phase 2+ only (ADR-007). |
| Spring Boot 3.x, earlier Spring Cloud trains, `spring-cloud-starter-gateway` (old name) | Replaced by ADR-006. |
