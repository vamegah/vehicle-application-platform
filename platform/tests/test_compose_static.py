"""Task 1.2 static checks of platform/docker-compose.yml and its scripts. Standard library only; no Docker.

Run: python -m unittest discover -s platform/tests -p "test_compose_static.py"
"""
from __future__ import annotations

import importlib.util
import re
import tomllib
import unittest
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
REPO = PLATFORM.parent
COMPOSE = PLATFORM / "docker-compose.yml"
LEDGER = REPO / "DEPENDENCIES.lock.md"
BOOTSTRAP = PLATFORM / "garage" / "bootstrap.sh"
VAULT_INIT = PLATFORM / "vault" / "init.sh"
GARAGE_TOML = PLATFORM / "garage" / "garage.toml"
ENV_TEMPLATE = PLATFORM / "env.template"
INIT_ENV = PLATFORM / "scripts" / "init-env.py"

PINNED_IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*@sha256:[0-9a-f]{64}$")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SECRET_NAMES = re.compile(r"(?i)(password|secret|token)")
ONE_SHOT = {"vault-init", "garage-bootstrap"}
CORE = {"postgres", "kafka", "vault", "vault-init"}
SUPPORTING = {"neo4j", "redis", "garage", "garage-bootstrap", "otel-collector", "prometheus", "grafana"}
# Deployable services (task 1.6) -> profile; images are built locally from platform/deployables/.
DEPLOYABLES = {
    "data-readiness-api": "data-platform", "legacy-integration": "data-platform", "integration-config": "integration-config",
    "release-assurance": "release-assurance", "release-assurance-sidecar": "release-assurance", "api-gateway": "api-gateway",
    "audit-sink": "audit-sink", "web": "web",
}
LOCAL_IMAGE = re.compile(r"^autoreliance/[a-z0-9-]+:dev$")
DOCKERFILES = sorted((PLATFORM / "deployables").rglob("Dockerfile*"))


def compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def services(text: str) -> dict[str, str]:
    """Top-level service name -> its block of text (indentation-based; the compose file uses 2-space indent)."""
    out: dict[str, str] = {}
    body = text.split("\nservices:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    current = None
    for line in body.splitlines():
        m = re.match(r"^  ([a-z0-9-]+):\s*$", line)
        if m:
            current = m.group(1)
            out[current] = ""
        elif current:
            out[current] += line + "\n"
    return out


def images(text: str) -> list[str]:
    """Pulled images; locally built deployable images (autoreliance/<name>:dev) are checked through their Dockerfile."""
    return [r for r in (m.group(1).strip() for m in re.finditer(r"(?m)^\s+image:\s*(\S+)\s*$", text)) if not LOCAL_IMAGE.match(r)]


def ledger_image_rows() -> set[str]:
    rows = set()
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|[^|]+\|\s*`([^`]+@sha256:[0-9a-f]{64})`\s*\|", line)
        if m:
            rows.add(m.group(1))
    return rows


class ImagePins(unittest.TestCase):
    def test_every_image_has_a_tag_and_a_digest_and_no_latest(self):
        imgs = images(compose_text())
        self.assertGreaterEqual(len(imgs), 10)
        for ref in imgs:
            with self.subTest(image=ref):
                self.assertRegex(ref, PINNED_IMAGE)
                self.assertNotIn(":latest", ref)

    def test_every_image_equals_its_ledger_row(self):
        rows = ledger_image_rows()
        for ref in set(images(compose_text())):
            with self.subTest(image=ref):
                self.assertIn(ref, rows, "change an image only with a new dated decision and a ledger update")

    def test_garage_image_is_the_ledger_digest(self):
        garage = [r for r in images(compose_text()) if "/garage:" in r]
        self.assertEqual(garage, ["dxflrs/garage:v2.6.0@sha256:4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013"])
        self.assertIn(garage[0], ledger_image_rows())

    def test_no_minio_anywhere_in_the_platform_files(self):
        for path in [COMPOSE, BOOTSTRAP, VAULT_INIT, GARAGE_TOML, ENV_TEMPLATE, INIT_ENV]:
            with self.subTest(file=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"(?i)minio")

    def test_no_seaweedfs_or_ceph_in_compose(self):
        self.assertNotRegex(compose_text(), r"(?i)seaweed|ceph")


class Services(unittest.TestCase):
    def setUp(self):
        self.svc = services(compose_text())

    def test_the_infrastructure_and_deployable_services_exist(self):
        self.assertEqual(set(self.svc), CORE | SUPPORTING | set(DEPLOYABLES))

    def test_profiles_let_each_deployable_start_with_only_postgres_kafka_and_vault(self):
        for name in CORE:
            with self.subTest(service=name):
                self.assertNotIn("profiles:", self.svc[name])
        for name in SUPPORTING:
            with self.subTest(service=name):
                self.assertIn("    profiles: [infra, all]\n", self.svc[name])
        for name, profile in DEPLOYABLES.items():
            with self.subTest(service=name):
                self.assertIn(f"    profiles: [{profile}, all]\n", self.svc[name])
                deps = set(re.findall(r"(?m)^      ([a-z0-9-]+):\n        condition:", self.svc[name]))
                self.assertTrue(deps <= CORE, f"{name} depends on {deps - CORE}")

    def test_deployables_are_built_from_platform_deployables_with_a_local_tag(self):
        for name in DEPLOYABLES:
            with self.subTest(service=name):
                block = self.svc[name]
                self.assertIn(f"    image: autoreliance/{name}:dev\n", block)
                self.assertIn("      context: ..\n", block)
                dockerfile = re.search(r"dockerfile: (\S+)", block).group(1)
                self.assertTrue(dockerfile.startswith("platform/deployables/"), dockerfile)
                self.assertTrue((REPO / dockerfile).is_file(), dockerfile)
                self.assertIn("healthcheck:", block)

    def test_every_dockerfile_base_image_is_pinned_and_in_the_ledger(self):
        self.assertGreaterEqual(len(DOCKERFILES), 8)
        rows = ledger_image_rows()
        for path in DOCKERFILES:
            for ref in re.findall(r"(?m)^FROM\s+(\S+)", path.read_text(encoding="utf-8")):
                with self.subTest(dockerfile=path.relative_to(REPO).as_posix(), image=ref):
                    self.assertRegex(ref, PINNED_IMAGE)
                    self.assertIn(ref, rows)

    def test_every_image_runs_as_a_non_root_user(self):
        for path in DOCKERFILES:
            with self.subTest(dockerfile=path.relative_to(REPO).as_posix()):
                users = re.findall(r"(?m)^USER\s+(\S+)", path.read_text(encoding="utf-8"))
                self.assertTrue(users and users[-1] not in {"root", "0"})

    def test_every_service_has_a_memory_limit(self):
        for name, block in self.svc.items():
            with self.subTest(service=name):
                self.assertRegex(block, r"(?m)^    mem_limit: \d+[mg]$")

    def test_host_ports_bind_to_loopback_only(self):
        for m in re.finditer(r'(?m)^\s+- "([^"]+)"$', compose_text()):
            if re.fullmatch(r"[\d.]*:?\d+:\d+", m.group(1)):
                with self.subTest(port=m.group(1)):
                    self.assertTrue(m.group(1).startswith("127.0.0.1:"))

    def test_garage_admin_and_rpc_ports_are_not_published(self):
        self.assertNotRegex(self.svc["garage"], r":390[13]\"")

    def test_every_secret_comes_from_the_environment(self):
        for name, block in self.svc.items():
            for m in re.finditer(r"(?m)^\s+([A-Z][A-Z0-9_]*):\s*(.+)$", block):
                key, value = m.group(1), m.group(2).strip()
                if SECRET_NAMES.search(key) and key not in {"GF_SECURITY_ADMIN_USER"}:
                    with self.subTest(service=name, variable=key):
                        self.assertRegex(value, r"^\$\{[A-Z0-9_]+:\?\}$|^neo4j/\$\{[A-Z0-9_]+:\?\}$")

    def test_one_shot_jobs_run_after_their_dependencies_and_do_not_restart(self):
        for name in ONE_SHOT:
            with self.subTest(service=name):
                self.assertIn('restart: "no"', self.svc[name])
        self.assertIn("condition: service_healthy", self.svc["vault-init"])
        self.assertIn("vault-init:\n        condition: service_completed_successfully", self.svc["garage-bootstrap"])
        self.assertIn("garage:\n        condition: service_healthy", self.svc["garage-bootstrap"])

    def test_bootstrap_adds_no_image(self):
        vault_image = re.search(r"image:\s*(\S+)", self.svc["vault"]).group(1)
        self.assertEqual(re.search(r"image:\s*(\S+)", self.svc["garage-bootstrap"]).group(1), vault_image)
        self.assertEqual(re.search(r"image:\s*(\S+)", self.svc["vault-init"]).group(1), vault_image)

    def test_redis_is_noeviction_single_instance(self):
        self.assertIn("--maxmemory-policy noeviction", self.svc["redis"])
        self.assertIn("--maxmemory ", self.svc["redis"])

    def test_vault_redacts_dev_credentials_from_its_log(self):
        self.assertIn("Root Token:", self.svc["vault"])
        self.assertIn("[redacted]", self.svc["vault"])


class GarageConfig(unittest.TestCase):
    def test_garage_toml_matches_the_design(self):
        cfg = tomllib.loads(GARAGE_TOML.read_text(encoding="utf-8"))
        self.assertEqual(cfg["replication_factor"], 1)
        self.assertEqual(cfg["s3_api"]["s3_region"], "garage")
        self.assertEqual(cfg["s3_api"]["api_bind_addr"], "[::]:3900")
        self.assertEqual(cfg["admin"]["api_bind_addr"], "[::]:3903")
        self.assertNotIn("s3_web", cfg)
        for key in ("rpc_secret", "admin_token", "metrics_token"):
            self.assertNotIn(key, cfg)
            self.assertNotIn(key, cfg.get("admin", {}))

    def test_garage_runs_single_node_with_status_healthcheck(self):
        block = services(compose_text())["garage"]
        self.assertIn('command: ["/garage", "server", "--single-node"]', block)
        self.assertIn('test: ["CMD", "/garage", "status"]', block)
        self.assertNotIn("--default-bucket", block)


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.text = BOOTSTRAP.read_text(encoding="utf-8")

    def test_bootstrap_creates_exactly_the_two_shared_buckets(self):
        names = set(re.findall(r'^(?:RAW|TEXT)_BUCKET="([^"]+)"$', self.text, re.MULTILINE))
        self.assertEqual(names, {"autoreliance-raw-dev", "autoreliance-text-dev"})
        self.assertEqual(len(re.findall(r"ensure_bucket \"\$", self.text)), 2)

    def test_no_bucket_name_contains_a_tenant_id(self):
        for name in re.findall(r'_BUCKET="([^"]+)"', self.text):
            self.assertNotRegex(name, UUID)
        code = "\n".join(l for l in self.text.splitlines() if not l.lstrip().startswith("#"))
        self.assertNotRegex(code, r"(?i)SEED_TENANT|tenant")

    def test_data_readiness_never_gets_write_or_raw_access(self):
        self.assertIn('perm Allow "$text" "$dr" true false false', self.text)
        self.assertIn('perm Deny "$raw" "$dr" true true true', self.text)
        self.assertNotRegex(self.text, r'perm Allow "\$raw" "\$dr"')

    def test_scripts_never_trace_or_print_secrets(self):
        for path in (BOOTSTRAP, VAULT_INIT):
            text = path.read_text(encoding="utf-8")
            with self.subTest(script=path.name):
                self.assertNotRegex(text, r"(?m)^\s*set\s+-[a-z]*x")
                self.assertNotRegex(text, r'(?i)echo[^\n]*\$\{?[A-Z_]*(SECRET|TOKEN|PASSWORD)')
                self.assertIn("set -eu", text)

    def test_scripts_are_lf_only(self):
        for path in (BOOTSTRAP, VAULT_INIT):
            with self.subTest(script=path.name):
                self.assertNotIn(b"\r\n", path.read_bytes())


class LocalSecrets(unittest.TestCase):
    def test_env_template_lists_names_only(self):
        for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                with self.subTest(line=line):
                    self.assertRegex(line, r"^[A-Z][A-Z0-9_]*=$")

    def test_generator_and_template_agree(self):
        spec = importlib.util.spec_from_file_location("init_env", INIT_ENV)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(sorted(module.generate()), sorted(module.template_names()))
        values = module.generate()
        self.assertRegex(values["LEGACY_INTEGRATION_ACCESS_KEY_ID"], r"^GK[0-9a-f]{24}$")
        self.assertRegex(values["DATA_READINESS_SECRET_ACCESS_KEY"], r"^[0-9a-f]{64}$")
        self.assertFalse(values["VAULT_DEV_ROOT_TOKEN"].startswith("hvs."))
        for name, value in values.items():
            with self.subTest(variable=name):
                self.assertFalse(value.startswith("-"))

    def test_every_compose_variable_is_in_the_template(self):
        used = set(re.findall(r"\$\{([A-Z0-9_]+):\?", compose_text()))
        names = {l.split("=", 1)[0] for l in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines() if l and not l.startswith("#")}
        # COMPOSE_PROFILES is read by compose itself, not interpolated (task 1.6).
        self.assertEqual(used, names - {"COMPOSE_PROFILES"})

    def test_generated_env_file_is_ignored_by_git(self):
        self.assertIn("platform/.env", (REPO / ".gitignore").read_text(encoding="utf-8").splitlines())


if __name__ == "__main__":
    unittest.main()
