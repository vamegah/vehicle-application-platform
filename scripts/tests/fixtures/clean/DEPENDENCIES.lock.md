# Fixture ledger (test data for scripts/check-dependency-pins; not the real ledger)

## Java (Spring Boot 4.1.x)
| Artifact | Version | Notes |
|---|---|---|
| org.springframework.boot:spring-boot-starter-parent | 4.1.3 | Boot parent. |
| org.springframework.cloud:spring-cloud-dependencies | 2025.1.5 | Oakwood BOM. |
| org.springframework.cloud:spring-cloud-starter-gateway-server-webflux | 5.0.5 | Managed by the Cloud BOM. |
| org.springframework.vault:spring-vault-core | 4.1.2 | Overrides the Spring Cloud BOM's managed 4.0.x. |
| software.amazon.awssdk:bom | 2.59.10 | Approved by user, Decision 3. |
| software.amazon.awssdk:s3 | 2.59.10 | Approved by user, Decision 3. |
| org.apache.kafka:kafka-clients | 4.2.2 | Boot-managed. |

## Python
| Package | Version | Notes |
|---|---|---|
| fastapi | 0.165.0 | |
| boto3 | 1.44.12 | Approved by user, Decision 3. |
| xgboost | 3.4.1 | Sidecar only. |
| scikit-learn | 1.9.1 | Sidecar only. |

## Node
| Package | Version | Notes |
|---|---|---|
| next | 16.4.6 | |

## Container images and infrastructure
| Image | Version | Notes |
|---|---|---|
| Garage | `dxflrs/garage:v2.6.0@sha256:4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013` | Dev S3. |
| SeaweedFS | `chrislusf/seaweedfs:4.55@sha256:7ca46aeae2f223b37e5d91593c17ab37738eec6df6ab69b48a0487f7643342b9` | CI smoke test. |

## Not used in Phase 1 (do not add to a manifest)
| Item | Reason |
|---|---|
| langgraph | Phase 2. |
| MinIO (any image, client, or Testcontainers module `testcontainers-minio`) | Not approved. |
