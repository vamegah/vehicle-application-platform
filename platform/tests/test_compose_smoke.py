"""Task 1.2 scripted smoke test of platform/docker-compose.yml. Needs Docker, platform/.env, and boto3.

    python platform/scripts/init-env.py
    pip install -r platform/tests/requirements.txt
    AR_COMPOSE_SMOKE=1 python -m unittest discover -s platform/tests -p "test_compose_smoke.py" -v

The test starts the stack (`docker compose up -d`), waits for every health check, and leaves it running unless
AR_COMPOSE_DOWN=1. Without AR_COMPOSE_SMOKE=1 it is skipped; CI sets it and fails on any skip.
S3 checks use raw boto3 requests (no platform adapter) with the when-required checksum settings (ADR-013).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
REPO = PLATFORM.parent
ENV_FILE = PLATFORM / ".env"
TENANT_A = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
TENANT_B = "7f6e5d4c-3b2a-4190-8f7e-6d5c4b3a2910"
RAW, TEXT = "autoreliance-raw-dev", "autoreliance-text-dev"
LONG_RUNNING = {"postgres", "kafka", "neo4j", "redis", "garage", "vault", "otel-collector", "prometheus", "grafana"}
WITH_HEALTHCHECK = LONG_RUNNING - {"otel-collector"}
ONE_SHOT = {"vault-init", "garage-bootstrap"}
VAULT = "http://127.0.0.1:8200"
SECRET_PATTERNS = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Vault service token": re.compile(r"\bhvs\.[A-Za-z0-9_-]{20,}\b"),
    "Garage access key id": re.compile(r"\bGK[0-9a-f]{24}\b"),
}

SMOKE = os.environ.get("AR_COMPOSE_SMOKE") == "1"


def env_values() -> dict[str, str]:
    out = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def compose(*args: str, check: bool = True, timeout: int = 900, env: dict | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(["docker", "compose", *args], cwd=PLATFORM, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env=None if env is None else {**os.environ, **env})
    if check and proc.returncode != 0:
        raise AssertionError(f"docker compose {' '.join(args)} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    return proc


def service_states() -> dict[str, dict]:
    proc = compose("ps", "-a", "--format", "json")
    rows = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    return {r["Service"]: r for r in rows}


def http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def wait_for_stack(timeout: float = 600) -> None:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        last = service_states()
        healthy = all(last.get(s, {}).get("Health") == "healthy" for s in WITH_HEALTHCHECK)
        running = all(last.get(s, {}).get("State") == "running" for s in LONG_RUNNING)
        done = all(last.get(s, {}).get("State") == "exited" for s in ONE_SHOT)
        failed = [s for s in ONE_SHOT if last.get(s, {}).get("State") == "exited" and last[s].get("ExitCode") != 0]
        if failed:
            logs = compose("logs", *failed, check=False).stdout
            raise AssertionError(f"one-shot job failed: {failed}\n{logs}")
        if healthy and running and done and http_status("http://127.0.0.1:13133/") == 200:
            return
        time.sleep(3)
    raise AssertionError(f"stack not healthy within {timeout}s: " +
                         json.dumps({k: [v.get('State'), v.get('Health'), v.get('ExitCode')] for k, v in last.items()}))


def vault_get(path: str, token: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"{VAULT}/v1/{path}", headers={"X-Vault-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def s3(key_id: str, secret: str):
    import boto3
    from botocore.config import Config

    cfg = Config(request_checksum_calculation="when_required", response_checksum_validation="when_required",
                 s3={"addressing_style": "path"}, retries={"max_attempts": 2})
    return boto3.client("s3", endpoint_url="http://127.0.0.1:3900", region_name="garage", aws_access_key_id=key_id,
                        aws_secret_access_key=secret, config=cfg)


def error_code(exc) -> str:
    return exc.response.get("Error", {}).get("Code", "") + "/" + str(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode"))


@unittest.skipUnless(SMOKE, "set AR_COMPOSE_SMOKE=1 to run the compose smoke test (needs Docker)")
class ComposeSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENV_FILE.is_file():
            raise AssertionError("platform/.env missing: run python platform/scripts/init-env.py")
        cls.env = env_values()
        compose("up", "-d")
        wait_for_stack()
        cls.li = s3(cls.env["LEGACY_INTEGRATION_ACCESS_KEY_ID"], cls.env["LEGACY_INTEGRATION_SECRET_ACCESS_KEY"])
        cls.dr = s3(cls.env["DATA_READINESS_ACCESS_KEY_ID"], cls.env["DATA_READINESS_SECRET_ACCESS_KEY"])
        cls.run_id = uuid.uuid4().hex[:12]
        cls.created: list[tuple[str, str]] = []

    @classmethod
    def tearDownClass(cls):
        for bucket, key in getattr(cls, "created", []):
            try:
                cls.li.delete_object(Bucket=bucket, Key=key)
            except Exception:
                pass
        if os.environ.get("AR_COMPOSE_DOWN") == "1":
            compose("down", "-v", check=False)

    def put(self, bucket: str, tenant: str, kind: str, body: bytes) -> str:
        key = f"{tenant}/{kind}/documents/smoke-{self.run_id}/{uuid.uuid4().hex}.{'pdf' if kind == 'raw' else 'txt'}"
        self.li.put_object(Bucket=bucket, Key=key, Body=body)
        type(self).created.append((bucket, key))
        return key

    # --------------------------------------------------------------------------------------- health

    def test_01_every_component_is_healthy_and_init_jobs_succeeded(self):
        states = service_states()
        for s in WITH_HEALTHCHECK:
            with self.subTest(service=s):
                self.assertEqual(states[s]["Health"], "healthy")
        for s in ONE_SHOT:
            with self.subTest(job=s):
                self.assertEqual((states[s]["State"], states[s]["ExitCode"]), ("exited", 0))
        self.assertEqual(http_status("http://127.0.0.1:13133/"), 200, "otel-collector health_check extension")

    # --------------------------------------------------------------------------------------- Vault

    def test_02_vault_kv_mount_is_version_2_and_transit_is_enabled(self):
        status, body = vault_get("sys/mounts", self.env["VAULT_DEV_ROOT_TOKEN"])
        self.assertEqual(status, 200)
        mounts = body.get("data", body)
        self.assertEqual(mounts["kv/"]["type"], "kv")
        self.assertEqual(mounts["kv/"]["options"]["version"], "2", "the kv mount must be KV version 2 (ADR-021)")
        self.assertEqual(mounts["transit/"]["type"], "transit")

    def test_03_transit_key_per_seed_tenant_and_signing_key(self):
        token = self.env["VAULT_DEV_ROOT_TOKEN"]
        for tenant in (TENANT_A, TENANT_B):
            with self.subTest(tenant=tenant):
                self.assertEqual(vault_get(f"transit/keys/tenant-{tenant}", token)[0], 200)
        status, body = vault_get("transit/keys/internal-principal", token)
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["type"], "ed25519")

    def test_04_redis_connection_strings_are_two_paths_on_the_one_local_instance(self):
        token = self.env["VAULT_DEV_ROOT_TOKEN"]
        broker = vault_get("kv/data/platform/redis/broker", token)[1]["data"]["data"]["url"]
        cache = vault_get("kv/data/platform/redis/cache", token)[1]["data"]["data"]["url"]
        self.assertNotEqual(broker, cache)
        self.assertTrue(broker.endswith("@redis:6379/0"))
        self.assertTrue(cache.endswith("@redis:6379/1"))

    def test_05_storage_settings_and_per_tenant_credentials(self):
        token = self.env["VAULT_DEV_ROOT_TOKEN"]
        settings = vault_get("kv/data/platform/storage/settings", token)[1]["data"]["data"]
        self.assertEqual(settings, {"endpoint": "http://garage:3900", "region": "garage", "pathStyle": "true"})
        for tenant in (TENANT_A, TENANT_B):
            for ctx, prefix in (("legacy-integration", "LEGACY_INTEGRATION"), ("data-readiness", "DATA_READINESS")):
                with self.subTest(tenant=tenant, context=ctx):
                    data = vault_get(f"kv/data/tenants/{tenant}/storage/{ctx}", token)[1]["data"]["data"]
                    self.assertEqual(data["accessKeyId"], self.env[f"{prefix}_ACCESS_KEY_ID"])
                    self.assertEqual(data["secretAccessKey"], self.env[f"{prefix}_SECRET_ACCESS_KEY"])

    def test_06_layout_metadata_has_version_and_updated_time(self):
        # ADR-021 prerequisite of the layout read-back (task 7.15): a KV v1 mount has no metadata and fails here.
        for tenant in (TENANT_A, TENANT_B):
            with self.subTest(tenant=tenant):
                status, body = vault_get(f"kv/metadata/tenants/{tenant}/storage/layout", self.env["VAULT_DEV_ROOT_TOKEN"])
                self.assertEqual(status, 200)
                self.assertGreaterEqual(body["data"]["current_version"], 1)
                self.assertRegex(body["data"]["updated_time"], r"^\d{4}-\d{2}-\d{2}T")

    def test_07_no_kms_key_is_seeded_locally(self):
        status, _ = vault_get(f"kv/data/tenants/{TENANT_A}/storage/kms", self.env["VAULT_DEV_ROOT_TOKEN"])
        self.assertEqual(status, 404)

    # --------------------------------------------------------------------------------------- Garage

    def test_08_exactly_the_two_shared_buckets_exist(self):
        out = compose("exec", "-T", "garage", "/garage", "bucket", "list").stdout
        names = set(re.findall(r"\bautoreliance-[a-z0-9-]+\b", out))
        self.assertEqual(names, {RAW, TEXT}, out)
        for name in re.findall(r"(?m)^\S+\s+(\S+)", out):
            self.assertNotRegex(name, r"[0-9a-f]{8}-[0-9a-f]{4}-", "no per-tenant bucket")

    def test_09_legacy_integration_writes_and_reads_both_buckets(self):
        for bucket, kind in ((RAW, "raw"), (TEXT, "text")):
            with self.subTest(bucket=bucket):
                body = f"fictional smoke object {kind}".encode()
                key = self.put(bucket, TENANT_A, kind, body)
                self.assertEqual(self.li.get_object(Bucket=bucket, Key=key)["Body"].read(), body)
                self.assertEqual(self.li.head_object(Bucket=bucket, Key=key)["ContentLength"], len(body))

    def test_10_data_readiness_reads_text_but_is_denied_writes_and_raw(self):
        from botocore.exceptions import ClientError

        text_key = self.put(TEXT, TENANT_A, "text", b"fictional extracted text")
        raw_key = self.put(RAW, TENANT_A, "raw", b"%PDF-1.7 fictional")
        self.assertEqual(self.dr.get_object(Bucket=TEXT, Key=text_key)["Body"].read(), b"fictional extracted text")
        denied = {
            "PutObject text": lambda: self.dr.put_object(Bucket=TEXT, Key=f"{TENANT_A}/text/documents/x/{uuid.uuid4().hex}.txt", Body=b"x"),
            "GetObject raw": lambda: self.dr.get_object(Bucket=RAW, Key=raw_key),
            "ListObjectsV2 raw": lambda: self.dr.list_objects_v2(Bucket=RAW),
        }
        for name, call in denied.items():
            with self.subTest(operation=name):
                with self.assertRaises(ClientError) as ctx:
                    call()
                self.assertTrue(error_code(ctx.exception).endswith("/403"), error_code(ctx.exception))

    def test_11_known_dev_limitation_cross_tenant_prefix_read_is_not_denied_by_garage(self):
        # Expected result, recorded so a backend change that fixes it is noticed (ADR-020). On Garage the adapter
        # tenant-prefix check (task 7.7) and the CI cross-tenant test (task 7.9) are the only barrier. If this
        # assertion starts failing, Garage enforces prefix isolation: update the README and ADR-020.
        key = self.put(TEXT, TENANT_B, "text", b"fictional tenant B text")
        body = self.dr.get_object(Bucket=TEXT, Key=key)["Body"].read()
        self.assertEqual(body, b"fictional tenant B text",
                         "KNOWN DEV LIMITATION: Garage does not deny a cross-tenant prefix read with the shared dev key")

    # --------------------------------------------------------------------------------------- idempotency

    def test_12_init_jobs_are_idempotent(self):
        from botocore.exceptions import ClientError

        for job in ("vault-init", "garage-bootstrap"):
            with self.subTest(job=job):
                proc = compose("run", "--rm", "--no-deps", job, check=False)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        out = compose("exec", "-T", "garage", "/garage", "bucket", "list").stdout
        self.assertEqual(set(re.findall(r"\bautoreliance-[a-z0-9-]+\b", out)), {RAW, TEXT})
        with self.assertRaises(ClientError):
            self.dr.put_object(Bucket=TEXT, Key=f"{TENANT_A}/text/documents/x/{uuid.uuid4().hex}.txt", Body=b"x")

    # --------------------------------------------------------------------------------------- PostgreSQL (task 1.3)

    PG_ROLES = ("data_readiness", "legacy_integration", "integration", "configuration", "release", "audit", "audit_app")

    @staticmethod
    def pg_variable(role: str) -> str:
        """Name of the platform/.env variable that holds the role's credential (PG_<ROLE>_PASSWORD)."""
        return f"PG_{role.upper()}_PASSWORD"

    def pg_secret(self, role: str) -> str:
        return self.env[self.pg_variable(role)]

    def psql_as(self, role: str, sql: str) -> subprocess.CompletedProcess:
        # `-e PGPASSWORD` without a value copies it from this process's environment: never on a command line.
        return compose("exec", "-T", "-e", "PGPASSWORD", "postgres", "psql",
                       "-h", "127.0.0.1", "-U", role, "-d", "autoreliance", "-At", "-v", "ON_ERROR_STOP=1",
                       "-c", sql, check=False, env={"PGPASSWORD": self.pg_secret(role)})

    def test_16_bootstrap_created_each_context_schema_and_login_role(self):
        for role in self.PG_ROLES:
            with self.subTest(role=role):
                own = "audit" if role == "audit_app" else role
                proc = self.psql_as(role, f"SELECT has_schema_privilege('{own}', 'USAGE')")
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.strip(), "t")
        proc = self.psql_as("legacy_integration", "SELECT has_schema_privilege('data_readiness', 'USAGE')")
        self.assertEqual(proc.stdout.strip(), "f", "contexts in data-platform must not see each other's schema")
        proc = self.psql_as("data_readiness", "SELECT extname FROM pg_extension WHERE extname = 'vector'")
        self.assertEqual(proc.stdout.strip(), "vector")

    def test_17_vault_holds_each_postgres_role_credential(self):
        for role in self.PG_ROLES:
            with self.subTest(role=role):
                status, body = vault_get(f"kv/data/platform/postgres/{role}", self.env["VAULT_DEV_ROOT_TOKEN"])
                self.assertEqual(status, 200)
                data = body["data"]["data"]
                self.assertEqual((data["username"], data["password"], data["host"], data["database"]),
                                 (role, self.pg_secret(role), "postgres", "autoreliance"))

    # --------------------------------------------------------------------------------------- secrets

    def secret_values(self) -> dict[str, str]:
        return {k: v for k, v in self.env.items() if len(v) >= 16}

    def test_13_no_secret_in_committed_files(self):
        files = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout.split(b"\0")
        values = self.secret_values()
        for rel in filter(None, files):
            path = REPO / rel.decode()
            if not path.is_file() or path.stat().st_size > 5_000_000:
                continue
            text = path.read_bytes().decode("utf-8", errors="replace")
            for name, value in values.items():
                self.assertNotIn(value, text, f"{name} value appears in committed file {rel.decode()}")
            for label, pattern in SECRET_PATTERNS.items():
                self.assertIsNone(pattern.search(text), f"{label} pattern in committed file {rel.decode()}")

    def test_14_no_secret_in_container_logs(self):
        # Access key IDs are identifiers, not secrets (Garage logs them per request, as AWS logs key IDs); the
        # secret keys, passwords, and tokens must never appear. Key IDs are still checked in files and images.
        logs = compose("logs", "--no-color").stdout
        values = {k: v for k, v in self.secret_values().items() if not k.endswith("_ACCESS_KEY_ID")}
        self.assertTrue(any(k.endswith("_SECRET_ACCESS_KEY") for k in values))
        for name, value in values.items():
            with self.subTest(variable=name):
                self.assertNotIn(value, logs)

    def test_15_no_secret_in_image_layers_or_image_config(self):
        refs = set(re.findall(r"(?m)^\s+image:\s*(\S+)\s*$", (PLATFORM / "docker-compose.yml").read_text(encoding="utf-8")))
        values = self.secret_values()
        for ref in refs:
            with self.subTest(image=ref):
                meta = subprocess.run(["docker", "image", "inspect", ref], capture_output=True, text=True, check=True).stdout
                hist = subprocess.run(["docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", ref],
                                      capture_output=True, text=True, check=True).stdout
                for name, value in values.items():
                    self.assertNotIn(value, meta + hist, f"{name} in image {ref}")


if __name__ == "__main__":
    unittest.main()
