# Dependency Ledger — resolved by task 1.4 on 2026-11-26

Every version in this file was read on 2026-11-26 from the official registry or vendor page named in the Notes column (Maven Central metadata and POMs, PyPI JSON, the npm registry, the Docker Hub registry API, the Terraform registry and HashiCorp checkpoint API, the GitHub releases API, dl.k8s.io, maven.apache.org, docs.spring.io), with TLS verification on. Nothing was taken from memory. A few rows carry an earlier date (2026-11-25) where that reading was repeated and matched.

Rules (enforced by `scripts/check-dependency-pins`, run in CI by `.github/workflows/dependency-pins.yml`):

- Maven: every `<version>` is exact (no range, `LATEST`, `RELEASE`, `SNAPSHOT`). The only artifacts without a `<version>` are those managed by the Spring Boot parent or by an imported BOM whose exact version has a row below (Spring Cloud, AWS SDK, OpenTelemetry instrumentation). Every explicit version equals the version in its row.
- Python: every dependency uses `==` with the version in its row. No `>=`, `~=`, `<`, `*`, or unpinned name.
- Node: every dependency uses the exact version in its row. No `^`, `~`, `*`, `latest`, or range.
- A manifest dependency with no row here fails the check. A BOM-managed artifact is covered by its BOM row or its own row.
- A row marked `UNVERIFIED` fails the check when any manifest uses it. No row is `UNVERIFIED` today.
- A row that no manifest uses fails the check once service manifests exist, unless it is in the "Not used in Phase 1" section or its Notes contain `Planned (task N.M)`. Manifests under `scripts/verification/` prove compatibility only and do not count as use.
- `langgraph` is in no manifest. `xgboost` and `scikit-learn` are only in the `release-assurance` inference sidecar manifest. MinIO and `testcontainers-minio` are in no manifest, image, or compose file.
- Spring Boot 3.x and 4.0.x, Spring Cloud trains before 2025.1, and the old `spring-cloud-starter-gateway` artifact are in no manifest.

Spring line (ADR-006): Spring Boot 4.1.x with Spring Cloud 2025.1.x (Oakwood). Spring Boot 3.x and earlier Spring Cloud trains are not used anywhere.

## Java (Spring Boot 4.1.x)
| Artifact | Version | Notes |
|---|---|---|
| org.springframework.boot:spring-boot-starter-parent / org.springframework.boot:spring-boot-dependencies (BOM) | 4.1.3 | ADR-006. Latest 4.1.x patch on Maven Central on 2026-11-26. Do not use 4.0.x; Boot 4.2.0 also exists on Central and is not selected (the user fixed the 4.1 line). System requirements (docs.spring.io/spring-boot/4.1/system-requirements.html, read 2026-11-26): Java 17 through 27 (Java 21 is supported), Servlet 6.1 (Tomcat 11.0.x), Maven 3.6.3 or later is the minimum, Gradle 8.14 or later and 9.x. OSS support for 4.1 ends 2027-07-31 (endoflife.date/api/spring-boot.json, read 2026-11-26; spring.io's own support tab is not machine readable, so confirm there before relying on the date). Manages Spring Framework 7.0.11, Tomcat 11.0.27, Hibernate 7.4.15.Final, Micrometer 1.17.3. Parent-managed plugins used in the smoke build: maven-compiler-plugin 3.15.0, maven-resources-plugin 3.5.0, maven-surefire-plugin 3.5.6. |
| org.springframework:spring-framework-bom | 7.0.11 | Boot-managed (`spring-framework.version`). Spring Framework 7. |
| org.springframework.cloud:spring-cloud-dependencies (BOM) | 2025.1.5 | ADR-006. Oakwood train. Latest 2025.1.x on Maven Central on 2026-11-26 (2026.0.0 also exists; it is the Boot 4.2 train and is not used). The user's minimum is 2025.1.2. Imported in `dependencyManagement`; artifacts it manages carry no `<version>`. Record the BOM version, never the starter version. The 2025.1.5 BOM is built against Boot 4.0.10 while the supported-versions table lists Boot 4.1.x for Oakwood. Task 1.4 smoke result: the gateway application context starts on Boot 4.1.3 with this BOM and loads a configured route (`GatewayAndJacksonSmokeTest`, run 2026-11-26, passed). |
| org.springframework.cloud:spring-cloud-starter-gateway-server-webflux | 5.0.5 | ADR-003, ADR-006. api-gateway only. Version managed by the Spring Cloud BOM 2025.1.5. Gateway 5.1.0 exists on Central and belongs to the 2026.0 train; it is not used. The old `spring-cloud-starter-gateway` artifact is not used. |
| org.springframework.vault:spring-vault-core | 4.1.2 | ADR-003, ADR-006, ADR-010 (decided by the user). Explicit `<version>` in every manifest that uses it. Not managed by the Boot BOM. The Spring Cloud 2025.1.x BOM manages a 4.0.x `spring-vault-core` through Spring Cloud Vault dependencies; the explicit 4.1.2 pin overrides that managed version, and no Spring Cloud Vault starter is used. Spring Vault core has no 5.0.x release. Task 1.4 result (2026-11-26): `mvn dependency:tree` on the smoke module resolves 4.1.2, the runtime jar reports Implementation-Version 4.1.2 (`VaultVersionSmokeTest`), and no `spring-cloud-starter-vault-config` is present. |
| software.amazon.awssdk:bom | 2.59.10 | ADR-012. Approved by user, Decision 3. Imported in `dependencyManagement` of `legacy-integration`; the `s3` artifact then carries no `<version>`. Latest release in Maven Central metadata on 2026-11-26. |
| software.amazon.awssdk:s3 | 2.59.10 | ADR-012, ADR-013. Approved by user, Decision 3. AWS SDK for Java v2, `legacy-integration` only (S3-compatible `StorageProvider` adapter). Client MUST set `requestChecksumCalculation(WHEN_REQUIRED)` and `responseChecksumValidation(WHEN_REQUIRED)`. Task 1.4 result: resolves to 2.59.10 through the BOM; it brings no `com.fasterxml.jackson.databind` (it uses the shaded `third-party-jackson-core`). Against Garage v2.6.0 the Java client with SDK default checksums is rejected (`InvalidRequestException` on PutObject); with when-required it passes put, get, head, delete. |
| software.amazon.awssdk:apache5-client | 2.59.10 | ADR-013. Approved by user, Decision 3. The pinned HTTP client artifact. In 2.59.x the `s3` artifact brings `apache5-client` at runtime; the manifest declares it explicitly and excludes `software.amazon.awssdk:netty-nio-client` so the HTTP client is deterministic. Version managed by the AWS SDK BOM. |
| org.flywaydb:flyway-core | 12.4.0 | APPROVED beyond the brief (ADR-003). Condition: Java runtime only; Python services use Alembic, never one cross-runtime tool. Version equals `flyway.version` managed by Spring Boot 4.1.3. |
| org.flywaydb:flyway-database-postgresql | 12.4.0 | APPROVED with Flyway. Same version as `flyway-core`. |
| org.springframework.boot:spring-boot-starter-flyway | 4.1.3 | Boot 4 starter that enables Flyway auto-configuration. Boot-managed. |
| org.springframework.kafka:spring-kafka | 4.1.3 | Boot-managed (`spring-kafka.version`). |
| org.apache.kafka:kafka-clients | 4.2.2 | Boot-managed (`kafka.version`). The platform broker stays Apache Kafka 3.x per `tech.md`. Task 1.4 result (2026-11-26): a kafka-clients 4.2.2 producer and consumer round trip passes against the pinned `apache/kafka:3.9.2` image (`DockerBackedCompatibilityTest`). |
| org.neo4j.driver:neo4j-java-driver | 6.1.0 | Boot-managed (`neo4j-java-driver.version`). The Neo4j server stays 5.x Community. Task 1.4 result (2026-11-26): driver 6.1.0 connects, runs `RETURN 1`, and reports a 5.x server against the pinned `neo4j:5.26.34-community` image. |
| org.postgresql:postgresql | 42.7.14 | Boot-managed (`postgresql.version`). |
| io.grpc:grpc-bom | 1.84.1 | Boot-managed (`grpc-java.version`). Artifacts used: `io.grpc:grpc-protobuf`, `io.grpc:grpc-stub`. |
| org.springframework.boot:spring-boot-starter-grpc-server / org.springframework.boot:spring-boot-starter-grpc-client | 4.1.3 | Boot 4.1 ships gRPC server and client starters (managed at 4.1.3). They replace the old `org.springframework.grpc:spring-grpc-*-spring-boot-starter` artifacts, which stop at 1.0.3 on Central. |
| org.springframework.grpc:spring-grpc-dependencies | 1.1.2 | Boot-managed (`spring-grpc.version`). Spring gRPC core `org.springframework.grpc:spring-grpc-core` is 1.1.2. |
| com.google.protobuf:protobuf-java | 4.36.2 | Boot-managed. |
| com.google.protobuf:protoc | 4.36.2 | Same version as `protobuf-java`. Resolved from Central (POM present 2026-11-26). Used by the protobuf Maven plugin; buf lint and breaking use `buf` below. Task 2.3 result (2026-11-26): generates Java for both Phase 1 protos in `contracts/proto-java` (`mvn verify`, 4 tests passed). |
| io.grpc:protoc-gen-grpc-java | 1.84.1 | Same version as grpc-java. Resolved from Central (POM present 2026-11-26). Task 2.3 result (2026-11-26): generates the `ConfigValidationServiceGrpc` and `GraphFactsServiceGrpc` stubs, which compile against `grpc-stub` 1.84.1. |
| io.github.ascopes:protobuf-maven-plugin | 5.1.13 | Latest on Central 2026-11-26. Chosen over `org.xolstice.maven.plugins:protobuf-maven-plugin` 0.6.1 (no newer release). Task 2.3 result (2026-11-26): build-tested in `contracts/proto-java`. It requires Maven 3.9.6 or later, so it fails on Maven 3.9.5 and works on the pinned 3.9.16; every build must use the pinned Maven. |
| tools.jackson:jackson-bom (Jackson 3) | 3.1.8 | ADR-006. Boot-managed (`jackson-bom.version`). Jackson 3 is the default mapper in Boot 4. Package root is `tools.jackson`; `com.fasterxml.jackson.annotation` annotations stay. Task 1.4 result: the application `JsonMapper` bean is `tools.jackson.databind.json.JsonMapper` and `com.fasterxml.jackson.databind.ObjectMapper` is not on the classpath (`GatewayAndJacksonSmokeTest`, passed). |
| com.fasterxml.jackson:jackson-bom (Jackson 2) | 2.21.8 | Boot-managed (`jackson-2-bom.version`). Transitive only (`jackson-annotations` 2.21 arrives through Testcontainers). Not a direct dependency of any module. The pin check fails on a direct `com.fasterxml.jackson.core:jackson-databind` dependency and on any import of `com.fasterxml.jackson.databind`. |
| org.testcontainers:testcontainers | 2.0.5 | Boot-managed. Testcontainers 2.x renamed modules (`testcontainers-postgresql`, `testcontainers-kafka`, `testcontainers-neo4j`, `testcontainers-junit-jupiter`, all 2.0.5) and packages. Object-store tests use a `GenericContainer` with the digest-pinned Garage image; no object-store-specific module is used (`GarageS3SmokeTest`). |
| org.testcontainers:testcontainers-junit-jupiter / org.testcontainers:testcontainers-postgresql / org.testcontainers:testcontainers-kafka / org.testcontainers:testcontainers-neo4j | 2.0.5 | Boot-managed through the Testcontainers BOM. Module artifacts under their 2.x names. |
| org.junit.jupiter:junit-jupiter | 6.0.3 | Boot-managed `junit-jupiter.version` (JUnit 6; the task text says JUnit 5, and the Boot 4.1.3 line is JUnit 6). The JUnit Platform resolves to 6.0.3 as well. |
| org.assertj:assertj-core | 3.27.7 | Boot-managed. Latest stable on Central 2026-11-26 (4.0.0 exists only as a milestone). |
| net.jqwik:jqwik | 1.10.2 | Latest on Central 2026-11-26. Compatibility result (2026-11-26): `jqwik-engine` 1.10.2 declares JUnit Platform 1.14.4 but runs on the Boot-managed platform 6.0.3; a `@Property` runs in `TestFrameworkCompatibilityTest` (passed). |
| au.com.dius.pact.consumer:junit5 / au.com.dius.pact.provider:junit5 | 4.7.7 | Pact JVM, latest on Central 2026-11-26. Compatibility result (2026-11-26): the consumer module declares JUnit Jupiter 5.14.4 but runs on the Boot-managed 6.0.3; a V4 consumer test with the mock server passes (`PactConsumerSmokeTest`). The provider modules were resolved but not exercised. `au.com.dius.pact.provider:spring7` 4.7.7 exists for Spring Framework 7. |
| org.apache.pdfbox:pdfbox | 3.0.8 | Apache PDFBox, latest on Central 2026-11-26. `legacy-integration` only. |
| io.opentelemetry:opentelemetry-bom | 1.62.0 | Boot-managed (`opentelemetry.version`). Java API and SDK. Newer releases exist (1.68.0) and are not used because Boot manages 1.62.0. |
| io.opentelemetry.instrumentation:opentelemetry-instrumentation-bom | 2.28.0 | The instrumentation release whose BOM imports `opentelemetry-bom` 1.62.0 (read from the 2.28.0 POM on 2026-11-26), so it matches the Boot-managed SDK. Releases 2.29.0 to 2.32.0 import SDK 1.63.0 to 1.66.0 (read from their POMs) and later releases up to 2.34.0 are newer still; none are used. Imported in `dependencyManagement`; instrumentation artifacts then carry no `<version>`. |
| io.micrometer:micrometer-registry-prometheus | 1.17.3 | Boot-managed (`micrometer.version`). Java Prometheus metrics. |
| io.prometheus:prometheus-metrics-core | 1.7.0 | Boot-managed (`prometheus-client.version`). |

Pact JVM and jqwik are not managed by Boot. Both were resolved against the Boot 4.1.3 JUnit 6.0.3 platform and run (see the rows above). Recorded limit: both declare JUnit 5.14.x / Platform 1.14.4 in their POMs, so they work only because Boot's dependency management overrides them to 6.0.3; build files must not pin JUnit separately.

## Python (FastAPI services)
Toolchain: Python 3.12.16 (latest 3.12.x on endoflife.date/api/python.json, read 2026-11-26; 3.12 is supported to 2028-10-31). Resolution of the full set below was checked with `pip install --dry-run --python-version 3.12 --only-binary=:all:` on 2026-11-26 with no conflict.

| Package | Version | Notes |
|---|---|---|
| fastapi | 0.165.0 | PyPI, 2026-11-26. Requires Python 3.11 or later. |
| uvicorn | 0.54.0 | PyPI, 2026-11-26. |
| pydantic | 2.14.4 | PyPI, 2026-11-26. FastAPI dependency, pinned because services import it directly. |
| httpx | 0.29.0 | PyPI, 2026-11-26. Test client for FastAPI. |
| SQLAlchemy | 2.1.9 | PyPI, 2026-11-26. Chosen Python PostgreSQL ORM layer; used with `psycopg`. |
| psycopg | 3.3.9 | PyPI, 2026-11-26. Chosen Python PostgreSQL driver (psycopg 3). |
| psycopg-binary | 3.3.9 | PyPI, 2026-11-26. Same version as `psycopg`. |
| alembic | 1.20.1 | APPROVED beyond the brief (ADR-003). Condition: Python runtime only (`data-readiness`, inference sidecar if it owns tables); Java services use Flyway. Verified on PyPI (requires Python 3.10 or later). |
| pgvector | 0.5.1 | PyPI, 2026-11-26. The Python client for pgvector inside PostgreSQL (no separate vector database). |
| celery | 5.7.0 | PyPI, 2026-11-26 (requires Python 3.10 or later). `data-readiness` only. Runs worker replicas and exactly one beat process (ADR-009). No `celery-redbeat` (not approved). |
| redis | 8.2.0 | PyPI, 2026-11-26. Python Redis client. |
| hvac | 2.4.0 | APPROVED beyond the brief (ADR-003). Vault client for Python services. Verified on PyPI (released 2025-10-30), still the latest on 2026-11-26. |
| boto3 | 1.44.12 | ADR-012, ADR-013. Approved by user, Decision 3. `data-readiness` only, for the read-only `StorageProvider` adapter. The client MUST be built with `botocore.config.Config(request_checksum_calculation='when_required', response_checksum_validation='when_required', s3={'addressing_style': 'path'})`. Task 1.4 result (2026-11-26): put, get, head, delete pass against the pinned Garage image with the when-required settings; Garage also accepted the boto3 default checksums on a put. |
| botocore | 1.44.12 | Pinned exactly with boto3 (ADR-013). Approved by user, Decision 3 (as part of boto3). |
| s3transfer | 0.19.3 | Pinned exactly with boto3 (ADR-013). Approved by user, Decision 3 (as part of boto3). |
| grpcio | 1.85.4 | PyPI, 2026-11-26. |
| grpcio-tools | 1.85.4 | PyPI, 2026-11-26. Same version as `grpcio`. |
| protobuf | 7.36.2 | PyPI, 2026-11-26. Python protobuf runtime (the 7.x series matches the 4.36 Java line). |
| opentelemetry-api | 1.45.2 | PyPI, 2026-11-26. |
| opentelemetry-sdk | 1.45.2 | PyPI, 2026-11-26. |
| opentelemetry-exporter-otlp-proto-grpc | 1.45.2 | PyPI, 2026-11-26. |
| opentelemetry-instrumentation-fastapi | 0.66b2 | PyPI, 2026-11-26. A beta-numbered release: the Python OpenTelemetry instrumentation packages are published as 0.NNbN alongside the stable 1.45.x API. This is the current release, not a pre-release choice. |
| prometheus-client | 0.26.0 | PyPI, 2026-11-26. |
| asammdf | 8.8.34 | PyPI, 2026-11-26. ASAM MDF reader. |
| cantools | 45.2.0 | PyPI, 2026-11-26. |
| python-can | 4.6.1 | PyPI, 2026-11-26. |
| xgboost | 3.4.1 | KEPT (ADR-004). Re-verified on PyPI 2026-11-26 (requires Python 3.12 or later). Used only in the release-assurance inference sidecar, for risk scoring (failure-likelihood ranking of tests). Seeded and deterministic. The pin check rejects it in any other manifest. |
| scikit-learn | 1.9.1 | KEPT (ADR-004). Re-verified on PyPI 2026-11-26. Used only in the release-assurance inference sidecar, for coverage analysis. Seeded and deterministic. The pin check rejects it in any other manifest. |
| pytest | 9.2.0 | PyPI, 2026-11-26. |
| pytest-asyncio | 1.5.0 | PyPI, 2026-11-26. |
| hypothesis | 6.170.17 | PyPI, 2026-11-26. |
| pact-python | 4.2.0 | PyPI, 2026-11-26 (requires Python 3.11 or later). |
| testcontainers | 4.15.0 | PyPI, 2026-11-26. Python Testcontainers. Object-store tests use `DockerContainer` with the digest-pinned Garage image; no object-store-specific module (`scripts/verification/python/test_garage_boto3_smoke.py`). |
| PyYAML | 6.0.4 | APPROVED by the user on 2026-11-26 for the contract tests (task 2.1). Reads the AsyncAPI YAML contracts. PyPI, 2026-11-26 (requires Python 3.10 or later). Used only in `contracts/tests/requirements.txt`. |
| jsonschema | 4.26.0 | APPROVED by the user on 2026-11-26 for the contract tests (task 2.1). Validates golden examples against the AsyncAPI payload schemas (Draft 7). PyPI, 2026-11-26 (requires Python 3.10 or later). Its `date-time` check needs an extra package, so the tests use a standard-library check instead. Used only in `contracts/tests/requirements.txt`. |
| attrs | 26.1.0 | Pinned exactly as a dependency of jsonschema and referencing (task 2.1, approved with jsonschema). PyPI, 2026-11-26. |
| jsonschema-specifications | 2025.9.1 | Pinned exactly as a dependency of jsonschema (task 2.1, approved with jsonschema). PyPI, 2026-11-26. |
| referencing | 0.37.0 | Pinned exactly as a dependency of jsonschema; the contract tests also use it to resolve `$ref` across contract files (task 2.1, approved with jsonschema). PyPI, 2026-11-26. |
| rpds-py | 2026.9.1 | Pinned exactly as a dependency of jsonschema and referencing (task 2.1, approved with jsonschema). PyPI, 2026-11-26 (requires Python 3.11 or later; wheels for 3.11 and 3.12). |
| typing-extensions | 4.16.0 | Pinned exactly as a dependency of referencing on Python below 3.13 (task 2.1, approved with jsonschema). PyPI, 2026-11-26. `pip freeze` of a clean virtual environment installed from `contracts/tests/requirements.txt` shows exactly these seven packages, and `pip check` reports no broken requirement. |

No Python Kafka client is named in the spec and none is recorded here. Adding one needs its own row and a user decision (the spec names only the Java Kafka clients).

## Node (web)
Toolchain: Node 24.22.3 (Active LTS, 2025-10-28 to 2028-04-30; read from nodejs.org/dist/index.json and endoflife.date on 2026-11-26). Node 26.13.1 also became LTS on 2026-10-28 and is not selected. Every package below declares an engines range that includes Node 24.22.3 (checked with `npm view` on 2026-11-26). `npm install --package-lock-only` over the whole set below resolved with no peer conflict.

| Package | Version | Notes |
|---|---|---|
| next | 16.4.6 | npm, 2026-11-26. React/Next.js only (`tech.md`). |
| react | 19.3.1 | npm, 2026-11-26. |
| react-dom | 19.3.1 | npm, 2026-11-26. |
| typescript | 5.9.3 | Latest 5.x. Not 7.0.2 (the latest tag): `openapi-typescript` 7.13.0 declares a peer dependency of `typescript@^5.x`, so npm refuses 7.x. |
| tailwindcss | 4.3.5 | npm, 2026-11-26. Tailwind 4 uses `@tailwindcss/postcss`, not `postcss` plus `autoprefixer`. |
| @tailwindcss/postcss | 4.3.5 | npm, 2026-11-26. |
| @types/react | 19.3.3 | npm, 2026-11-26. |
| @types/react-dom | 19.3.0 | npm, 2026-11-26. |
| @types/node | 24.19.4 | Latest 24.x, to match the Node 24 toolchain. |
| vitest | 5.1.2 | npm, 2026-11-26. |
| @vitejs/plugin-react | 6.3.0 | npm, 2026-11-26. |
| @testing-library/react | 16.3.3 | npm, 2026-11-26. |
| @testing-library/dom | 10.4.2 | Required peer of `@testing-library/react` (`^10`); latest 10.x. |
| @testing-library/jest-dom | 8.0.0 | npm, 2026-11-26 (requires Node 22 or later). |
| @testing-library/user-event | 14.6.13 | npm, 2026-11-26. |
| jsdom | 31.0.1 | npm, 2026-11-26. |
| fast-check | 4.11.0 | npm, 2026-11-26. Property-based tests for the web app. |
| openapi-typescript | 7.13.0 | APPROVED beyond the brief (ADR-003). Generates the typed `apps/web` client from `contracts/openapi/gateway.yaml`. Condition: CI regenerates on every change to `contracts/openapi/` and fails on any diff. Latest on npm 2026-11-26. Peer: `typescript@^5.x`. |
| @asyncapi/cli | 6.3.1 | APPROVED by the user on 2026-11-26 for contract validation (task 2.1). The official AsyncAPI 3.0 validator. Latest on npm 2026-11-26; requires Node 24.11 or later, so the Node 24.22.3 toolchain fits. Used only in `contracts/package.json`; its transitive tree is fixed by `contracts/package-lock.json` (`npm ci`). Run with `ASYNCAPI_TELEMETRY=false`. All 15 AsyncAPI documents validate with 0 errors and 0 warnings; the one information message is that AsyncAPI 3.1.0 exists. |

## Build and CI tooling
| Tool | Version | Notes |
|---|---|---|
| Apache Maven (build and CI) | 3.9.16 | maven.apache.org/download.cgi, read 2026-11-26. Spring Boot 4.1.3 documents 3.6.3 or later as the minimum. 3.9.16 is the previous stable minor line and is still maintained; 3.10.2 is the current release and is not selected (CI stays on the line the local smoke build used, 3.9.x). Archive sha512 (downloads.apache.org, TLS): `831a8591fe20c8243b1dbe7d71e3244f31d1665b0804b2e825e38cbbe5ce0cafb8338851f90780735568773e0a6cd07bbec107cda0b896b008b861075358b6f6` for `apache-maven-3.9.16-bin.tar.gz`. |
| @openapitools/openapi-generator-cli | 2.44.0 | APPROVED beyond the brief (ADR-003). npm wrapper that generates Java and Python clients. Requires Node 22 or later. Condition: CI regenerates clients on every change to `contracts/openapi/` and fails on any diff. npm registry read 2026-11-26 (2.44.0 was published that day; the earlier reading 2026-11-25 was 2.43.0). |
| openapi-generator (jar run by the CLI wrapper, set in `openapitools.json`) | 7.28.0 | `org.openapitools:openapi-generator-cli` 7.28.0 on Central (released 2026-11-26). The wrapper version does not fix the generator version, so `openapitools.json` must pin this. Jackson 3 check (2026-11-26): `java -jar openapi-generator-cli-7.28.0.jar config-help -g java` lists the `useJackson3` option for the `native`, `webclient`, `restclient`, `resttemplate`, `jersey3`, and `okhttp` libraries (Spring libraries also need `useSpringBoot4=true`, and `openApiNullable` must be off). Generated Java clients therefore target Jackson 3 when generated with `useJackson3=true`. |
| buf | 1.75.0 | APPROVED and mandatory (ADR-003). CI runs `buf lint` and `buf breaking --against .git#branch=main` on every `contracts/proto/` change. Re-verified on the bufbuild/buf GitHub releases API 2026-11-26 (released 2026-10-22). Release `sha256.txt` (read 2026-11-26): `buf-Linux-x86_64` `fad1e38d6909bbb583a4da81d8c02a01046e2cd663bde7e337dd24277393764b` (used by CI), `buf-Windows-x86_64.exe` `de35b288e7962ac72aefee5048aff80551a4f0e6ac865a21f838693461ac8b8d`. Config: repository-root `buf.yaml` (task 2.3), lint STANDARD except PACKAGE_DIRECTORY_MATCH, breaking FILE. |
| Kustomize (built into `kubectl kustomize`) | no separate install | ADR-007. Tooling note, not a library dependency. |
| kubectl | v1.37.3 | `dl.k8s.io/release/stable.txt` read 2026-11-26. This is the version CI runs `kubectl kustomize` with (task 1.6). No overlay exists yet, so no lower minimum can be shown to work; the recorded minimum is the tested version, v1.37.3. Task 1.6 may lower it only after running the overlays on the older version. |
| Terraform CLI | 1.17.2 | `checkpoint-api.hashicorp.com/v1/check/terraform` and the hashicorp/terraform GitHub release, read 2026-11-26. Task 1.8. |
| hashicorp/aws (Terraform provider) | 6.74.0 | `registry.terraform.io/v1/providers/hashicorp/aws`, published 2026-11-23, read 2026-11-26. Task 1.8. |
| Python (toolchain) | 3.12.16 | See the Python section. |
| Node (toolchain) | 24.22.3 | See the Node section. |
| Java (toolchain) | 21 | `tech.md`. The smoke build ran on Oracle JDK 21.0.3. Boot 4.1.3 supports Java 17 to 27. |
| actions/checkout | v7.0.1 | GitHub Actions only (`tech.md`). GitHub releases API, read 2026-11-26. Used by `.github/workflows/dependency-pins.yml`. |
| actions/setup-python | v7.1.0 | GitHub releases API, read 2026-11-26. |
| actions/setup-node | v7.1.0 | GitHub releases API (public, read anonymously), latest release published 2026-10-08, read 2026-11-26. Used by `.github/workflows/contracts.yml` (task 2.1). |
| actions/setup-java | v6.3.0 | GitHub releases API, read 2026-11-26. |

## Container images and infrastructure
| Image | Version | Notes |
|---|---|---|
| Garage (local development and Testcontainers; default S3-compatible object store, AGPL-3.0, run only as a separate dev container, never linked or redistributed) | `dxflrs/garage:v2.6.0@sha256:4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013` | ADR-013 (Decision 1). Re-read on 2026-11-26 from the Docker Hub registry API (`registry-1.docker.io/v2/dxflrs/garage/manifests/v2.6.0`, `Docker-Content-Digest` header, TLS verification on): the digest is unchanged. It is the manifest-list digest of tag `v2.6.0`; platform digests are linux/amd64 `sha256:353a3f29291482faa51ef34de76508e0df448d37842eeeef5f0b69a5f9274eb3` and linux/arm64 `sha256:5de822389154e6c59bf8906097ec1ed48adcc9d159f08f8691b73654e2573a4b`. `v2.6.0` (pushed 2026-11-24) is still the newest `v2.x` tag on Docker Hub, so no newer tag is recorded. Compose and Testcontainers reference `dxflrs/garage:v2.6.0@sha256:4b5a318f...` and never a bare tag or `latest`. ADR-019 (2026-11-25): Garage stays the dev backend; do not change this image without recording a new dated decision, and the CI pin check compares every compose and Testcontainers reference with this row. The ADR-019 trigger to switch dev to SeaweedFS stands and has not been met. Garage has no bucket policies, no prefix-scoped permissions, and no SSE-KMS (permissions are per access key per bucket; SSE-C only), so the platform uses separate raw and text buckets (ADR-014, amended by ADR-018) and local key strategy `none` (ADR-015). Region string for clients is `garage`. Task 1.4 result (2026-11-26): Garage v2.6.0 serves the S3 API to both clients with path-style and region `garage`: the Java client (AWS SDK 2.59.10) and boto3 1.44.12 both pass put, get, head, delete with the when-required settings. With SDK default checksums, Garage rejected the Java put (`InvalidRequestException`) and accepted the boto3 put, so the when-required setting is needed on the Java client and stays on both. |
| SeaweedFS (current CI smoke-test container for the cross-tenant test of task 7.9; approved dev-backend alternative under the ADR-019 switch trigger, not running in dev and not configured in compose) | `chrislusf/seaweedfs:4.55@sha256:7ca46aeae2f223b37e5d91593c17ab37738eec6df6ab69b48a0487f7643342b9` | ADR-013, ADR-018, ADR-019, ADR-020. Apache-2.0. Re-read on 2026-11-26 from the Docker Hub registry API (`registry-1.docker.io/v2/chrislusf/seaweedfs/manifests/4.55`, `Docker-Content-Digest` header, TLS verification on): the OCI index digest is unchanged. Platform digests: linux/amd64 `sha256:340bc0cbb1eb0da6472bd45a7225dd9a48bae6d72771c98ead52200b5abd4352`, linux/arm64 `sha256:1d857dc0ff7f0829e5f0228c7dd8d6907b4d1e7b01b553eb5c05c17c9a9a7b49`. 4.55 is still the latest release on the seaweedfs/seaweedfs GitHub releases API (published 2026-11-23), so no newer tag is recorded. If the digest cannot be verified at CI time, task 7.9 records the SeaweedFS smoke test as BLOCKED, never PASSED. The test is a smoke test and not the authoritative proof of prefix-scoped isolation (SeaweedFS prefix-scoped IAM has known bugs, for example seaweedfs issue 9788); the authoritative runs are AWS S3 and Ceph RGW before production, and a SeaweedFS green run is never release evidence. Do not use `latest`, a bare tag, or any other digest. |
| Apache Kafka broker (compatibility test for kafka-clients; Kafka 3.x per `tech.md`) | `apache/kafka:3.9.2@sha256:05b4616e0702ef2729327705d54ad6b50ea70b271c4b730fabd2320789fb7b02` | Latest 3.x tag on Docker Hub (pushed 2026-02-21; the 4.x tags are not used). OCI index digest read from the Docker Hub registry API on 2026-11-26 with TLS verification on; platform digests linux/amd64 `sha256:f5f8605794dce59d1d566f63667682771c2fec9e96088b0d6a5ef0f8476dd4b2`, linux/arm64 `sha256:ddc235acd57d0fec5b21eedd46dcaf4e89a7569ff1c9890c5597c6d9561c59b0`. Task 1.2 reuses this reference for compose unless it records a new dated decision. |
| Neo4j Community (compatibility test for the Java driver; Neo4j 5.x per `tech.md`) | `neo4j:5.26.34-community@sha256:2c48628bc28c68d7e2787f76262dfc9d7c21a8f7f290e30da901c489aa7fe50d` | Latest 5.x tag on Docker Hub (pushed 2026-11-24). Index digest read from the Docker Hub registry API on 2026-11-26 with TLS verification on; linux/amd64 platform digest `sha256:90b3a90c99b2550f3dd778d517c9d9fe5644ef49a457d7670556a7f10df4ac4b`. Task 1.2 reuses this reference for compose unless it records a new dated decision. |
| Ceph RGW (production on-prem only; never local development) | deployment-managed | ADR-013. Supports S3 bucket policies and per-user grants; the platform uses bucket-level grants for the raw and text separation and prefix-scoped policies for tenant isolation in the shared buckets (ADR-018). Conformance with the adapter suite is a pre-production check (task 7.9). |

PostgreSQL 16 (pgvector), Redis, and Vault image tags and digests are resolved by task 1.2, which owns `platform/docker-compose.yml`. They are not recorded here and no compose file exists yet.

## MCP servers (`.kiro/settings/mcp.json`, not edited by the spec work)
| Server | Pin status | Notes |
|---|---|---|
| context7 | PINNED | `@upstash/context7-mcp@4.8.0` is pinned in `args`. |
| postgres-schema | PINNED | `@bytebase/dbhub@0.6.2` is pinned in `args`. |
| neo4j-schema (neo4j-mcp) | UNPINNED - known gap | Started from a locally installed `neo4j-mcp` binary. The version v1.6.1 appears only in the `description` text and is not enforced. Record the installed version outside `mcp.json` or pin the install. |

## Not used in Phase 1 (do not add to a manifest)
| Item | Reason |
|---|---|
| langgraph | No agent orchestration in Phase 1 (ADR-004). Deferred to Phase 2; not recorded with a version. |
| ShedLock, celery-redbeat, Quartz | Not approved. Single-replica scheduling constraint instead (ADR-009). |
| org.springframework.cloud:spring-cloud-starter-vault-config (Spring Cloud Vault starters) | Not used. Vault access is through `spring-vault-core` 4.1.2 directly (ADR-010). |
| PostgreSQL `bytea` columns, large objects, or a mounted volume as storage for PDF bytes | Prohibited. PDF bytes live only in the S3-compatible object store (ADR-012). |
| MinIO (any image, client, or Testcontainers module `testcontainers-minio`) | Not approved. MinIO is archived and no official image is pullable (ADR-013, Decision 1). Local development uses Garage. |
| Helm | Approved for Phase 2+ only (ADR-007). |
| Spring Boot 3.x, Spring Boot 4.0.x, earlier Spring Cloud trains, `spring-cloud-starter-gateway` (old name) | Replaced by ADR-006. |
| Spring Boot 4.2.x, Spring Cloud 2026.0.x, Spring Cloud Gateway 5.1.x | Newer lines that exist on Maven Central. The user fixed Boot 4.1 with Cloud 2025.1 (ADR-006). |
| org.springframework.grpc:spring-grpc-server-spring-boot-starter, org.springframework.grpc:spring-grpc-client-spring-boot-starter | Old artifact names that stop at 1.0.3. Boot 4.1 provides `spring-boot-starter-grpc-server` and `-client`. |
| openapi-generator-cli 2.43.0 | Superseded by 2.44.0 above. |
