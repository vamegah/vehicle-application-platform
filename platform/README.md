# Local development environment (`platform/`)

Task 1.2. All data is fictional.

## Start

```
python platform/scripts/init-env.py      # once: writes the untracked platform/.env with every local secret
cd platform
docker compose up -d                     # infrastructure, then the one-shot vault-init and garage-bootstrap jobs
docker compose ps -a                     # every service healthy; vault-init and garage-bootstrap exited 0
```

`docker compose down -v` removes the volumes. After `init-env.py --force` (new secrets), always run `down -v`, because Garage keeps the old keys on its volume.

## Components

| Service | Image (pinned in `DEPENDENCIES.lock.md`) | Host port (127.0.0.1 only) |
|---|---|---|
| postgres | PostgreSQL 16.16 with pgvector 0.8.7 (`vector` extension enabled in `autoreliance`) | 5432 |
| kafka | Apache Kafka 3.9.2, single KRaft node, topic auto-creation off | 9094 (`localhost:9094`) |
| neo4j | Neo4j 5.26 Community | 7474, 7687 |
| redis | Redis 8.12, one instance, `noeviction`; DB 0 broker, DB 1 cache (ADR-002) | 6379 |
| garage | Garage v2.6.0, single node, region `garage`, path-style | 3900 (S3 API only) |
| vault | Vault 2.2.2 dev server (in memory) | 8200 |
| otel-collector | OpenTelemetry Collector contrib 0.166.0 | 4317, 4318, 13133 (health) |
| prometheus | Prometheus v3.16.0 | 9090 |
| grafana | Grafana 13.3.2, Prometheus datasource | 3000 |

The deployable container groups, the web app, and the per-deployable compose profiles are added by task 1.6.

## Secrets

Every secret is generated into `platform/.env` by `scripts/init-env.py` and reaches containers through compose variables. `env.template` lists the names only. No secret is in a committed file, an image, or a log: the Vault dev server's printed root token and unseal key are redacted, and the smoke test checks files, logs, and image layers. Garage logs access key IDs per request; they are identifiers, not secrets.

## Init jobs

Both jobs are idempotent and run on every `docker compose up`.

- `vault-init` (`vault/init.sh`) enables the KV version 2 mount `kv/` and transit, and creates what is missing: a transit key per seed tenant (`tenant-<tenantId>`), the gateway's Internal_Principal signing key (`internal-principal`, ed25519), `kv/platform/redis/broker` and `kv/platform/redis/cache`, `kv/platform/storage/settings` (endpoint `http://garage:3900`, region `garage`, path-style), and for each seed tenant `kv/tenants/<tenantId>/storage/legacy-integration`, `.../data-readiness`, and `.../layout` (`storage.layout=shared`). No KMS key is seeded (local key strategy `none`, ADR-015).
- `garage-bootstrap` (`garage/bootstrap.sh`) runs in the pinned Vault image and drives Garage's admin API v2 (the Garage image has no shell, and `garage key import` fails with 409 on a repeat). It creates exactly two buckets, `autoreliance-raw-dev` and `autoreliance-text-dev`, imports the two keys from `platform/.env`, grants `legacy-integration` read and write on both buckets, and grants `data-readiness` read on the text bucket only.

Seed tenants (fictional, key prefixes, never buckets): `0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d` and `7f6e5d4c-3b2a-4190-8f7e-6d5c4b3a2910`.

## Known dev-only limitation (ADR-020)

Garage scopes access keys per bucket, not per key prefix. In this environment:

- raw-versus-text separation **is** enforced by the store: raw and text are separate buckets, and the `data-readiness` key has no access to the raw bucket (403 on `GetObject` and `ListBucket`) and cannot write the text bucket (403);
- tenant-within-text isolation is **not** enforced by the store: the `data-readiness` key can read another tenant's prefix in the shared text bucket. The adapter tenant-prefix check (task 7.7) and the CI cross-tenant test (task 7.9) are the only barrier here.

The smoke test records the cross-tenant read as an expected result, so a backend change that fixes it is noticed. Authoritative proof of prefix-scoped isolation runs against AWS S3 and Ceph RGW before production.

## Tests

```
python -m unittest discover -s platform/tests -p "test_compose_static.py"         # no Docker
pip install -r platform/tests/requirements.txt
AR_COMPOSE_SMOKE=1 python -m unittest discover -s platform/tests -p "test_compose_smoke.py" -v
```

CI runs both in `.github/workflows/compose.yml`.
