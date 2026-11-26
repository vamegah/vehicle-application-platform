# Dependency verification (task 1.4)

Nothing here ships. These modules prove, with real resolution and real tests, that the versions in `DEPENDENCIES.lock.md` work together. Task 1.1 writes the real service manifests from the ledger.

| Path | What it proves | Needs |
|---|---|---|
| `scripts/check-dependency-pins` | Pin rules over every manifest, compose file, and Testcontainers reference, plus the Jackson 2 import check. Run `python scripts/check-dependency-pins` (bash or PowerShell). | Python 3.11+ (stdlib only) |
| `scripts/tests/test_check_dependency_pins.py` | Fixture tests for the script. `python -m unittest discover -s scripts/tests -p "test_check_dependency_pins.py" -v` | Python 3.11+ |
| `scripts/tests/test_vault_dependency_tree.py` | `mvn dependency:tree` resolves `spring-vault-core` 4.1.2 with no conflict and no Cloud Vault starter; three bad fixtures must fail. | Maven, network |
| `dependency-smoke/` | Boot 4.1.3 + Cloud 2025.1.5 gateway context starts; `JsonMapper` is Jackson 3; Vault runtime 4.1.2; AWS SDK when-required checksums on the wire; jqwik and Pact on JUnit 6; kafka-clients 4.2.2 against `apache/kafka:3.9.2`; Neo4j driver 6.1.0 against Neo4j 5.26; put/get/head/delete against the pinned Garage image. `mvn -B -ntp test` | Java 21, Maven, Docker |
| `python/` | boto3 client configuration on the wire; put/get/head/delete against Garage with boto3. `python -m unittest discover -s scripts/verification/python -v` after `pip install -r scripts/verification/python/requirements-verification.txt` | Python, Docker |

CI runs all of them in `.github/workflows/dependency-pins.yml` and fails if a Docker-backed test is skipped.

## Local notes (Windows with a TLS-inspecting proxy)

Certificate verification stays on. If Java or pip cannot validate the proxy's CA, point them at the Windows trust store instead of disabling checks:

- Maven: `MAVEN_OPTS=-Djavax.net.ssl.trustStoreType=Windows-ROOT -Djavax.net.ssl.trustStore=NUL`
- Node: `NODE_OPTIONS=--use-system-ca`
- pip: export the Windows roots to a PEM file and set `PIP_CERT`.
- The Python Docker client may need `DOCKER_CONFIG` pointing at a folder holding `{}` as `config.json` when `docker-credential-desktop` is not on `PATH`.

## Results recorded on 2026-11-26

- Garage v2.6.0 rejects the AWS SDK for Java default checksums (`InvalidRequestException` on PutObject) and accepts the boto3 default checksums. Both clients use the when-required settings, which pass.
- jqwik 1.10.2 and Pact JVM 4.7.7 declare JUnit 5.14.x but run on the Boot-managed JUnit 6.0.3.
- `openapi-typescript` 7.13.0 declares peer `typescript@^5.x`, so the web toolchain uses TypeScript 5.9.3, not 7.x.
- openapi-generator 7.28.0 offers `useJackson3` for the Java client libraries.
