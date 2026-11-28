"""Task 1.1 repository checks: monorepo layout, toolchain versions in the build files, the Jackson 2 rule on the
real Java modules, and that the root task runner covers every module. Python 3.12 standard library only.

Run: python -m unittest discover -s scripts/tests -p "test_repository_*.py"
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import re
import sys
import tomllib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))

from depcheck.checker import check  # noqa: E402

SEVEN_CONTEXTS = {
    "data-readiness", "legacy-integration", "integration-intelligence", "configuration-assurance",
    "release-assurance", "api-gateway", "audit-sink",
}
JAVA_PACKAGES = {
    "legacy-integration": "legacyintegration",
    "integration-intelligence": "integrationintelligence",
    "configuration-assurance": "configurationassurance",
    "release-assurance": "releaseassurance",
    "api-gateway": "apigateway",
    "audit-sink": "auditsink",
}
PYTHON_ENTRYPOINTS = {
    "services/data-readiness": "app/data_readiness/main.py",
    "services/release-assurance/inference-sidecar": "app/release_assurance/main.py",
}
# Phase 2 to 4 contexts of the platform brief (product.md): no folder may exist for them in Phase 1.
LATER_PHASE_NAMES = re.compile(r"(?i)quality|diagnostic|security|ota|copilot|knowledge|warranty|dealer|supplier")
REQUIRED_DIRS = (
    "apps/web", "libs", "contracts/asyncapi", "contracts/openapi", "contracts/proto", "platform/deployables",
    "platform/k8s/base", "platform/k8s/overlays/dev", "platform/k8s/overlays/staging", "platform/terraform",
    ".github/workflows",
)


def load_build_runner():
    loader = importlib.machinery.SourceFileLoader("ar_build", str(SCRIPTS / "build"))
    spec = importlib.util.spec_from_loader("ar_build", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def pom(path: Path) -> ET.Element:
    root = ET.parse(path).getroot()
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def ledger_text() -> str:
    return (REPO / "DEPENDENCIES.lock.md").read_text(encoding="utf-8")


class Layout(unittest.TestCase):
    def test_exactly_the_seven_context_directories_sit_under_services(self):
        dirs = {p.name for p in (REPO / "services").iterdir() if p.is_dir()}
        self.assertEqual(dirs, SEVEN_CONTEXTS)

    def test_no_folder_exists_for_a_phase_2_to_4_context(self):
        for top in ("services", "apps", "libs", "platform/deployables", "contracts/proto"):
            base = REPO / top
            for p in base.iterdir():
                if p.is_dir():
                    with self.subTest(path=p.relative_to(REPO).as_posix()):
                        self.assertIsNone(LATER_PHASE_NAMES.search(p.name), f"{p} looks like a Phase 2 to 4 context")

    def test_web_is_the_only_frontend_app(self):
        self.assertEqual({p.name for p in (REPO / "apps").iterdir() if p.is_dir()}, {"web"})

    def test_required_directories_exist(self):
        for rel in REQUIRED_DIRS:
            with self.subTest(dir=rel):
                self.assertTrue((REPO / rel).is_dir(), rel)

    def test_java_contexts_use_their_package_root(self):
        for ctx, pkg in JAVA_PACKAGES.items():
            with self.subTest(context=ctx):
                base = REPO / "services" / ctx / "src/main/java/com/autoreliance" / pkg
                self.assertTrue(base.is_dir(), base)
                self.assertTrue(list(base.glob("*Application.java")), f"no Spring Boot application class in {base}")

    def test_python_components_use_their_entrypoint(self):
        for rel, entry in PYTHON_ENTRYPOINTS.items():
            with self.subTest(module=rel):
                self.assertTrue((REPO / rel / entry).is_file(), f"{rel}/{entry}")

    def test_every_context_has_its_contract(self):
        # Contract-first rule (structure.md): every services/<context>/ has contracts/openapi/<context>.yaml.
        for ctx in SEVEN_CONTEXTS:
            with self.subTest(context=ctx):
                self.assertTrue((REPO / "contracts/openapi" / f"{ctx}.yaml").is_file())


class Toolchain(unittest.TestCase):
    def setUp(self):
        self.tool = load_build_runner().ledger_toolchain(ledger_text())

    def java_poms(self) -> list[Path]:
        return sorted((REPO / "services").glob("*/pom.xml"))

    def test_toolchain_rows_are_the_locked_versions(self):
        self.assertEqual(self.tool["java"], "21")
        self.assertRegex(self.tool["python"], r"^3\.12\.\d+$")
        self.assertRegex(self.tool["node"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(self.tool["maven"], r"^\d+\.\d+\.\d+$")

    def test_every_java_module_is_java_21_on_spring_boot_4_1(self):
        poms = self.java_poms()
        self.assertEqual({p.parent.name for p in poms}, set(JAVA_PACKAGES))
        for path in poms:
            with self.subTest(pom=path.relative_to(REPO).as_posix()):
                root = pom(path)
                parent = root.find("parent")
                self.assertEqual(parent.findtext("artifactId"), "spring-boot-starter-parent")
                self.assertRegex(parent.findtext("version"), r"^4\.1\.\d+$")
                self.assertEqual(root.findtext("properties/java.version"), self.tool["java"])

    def test_gateway_imports_the_spring_cloud_2025_1_bom(self):
        root = pom(REPO / "services/api-gateway/pom.xml")
        boms = {d.findtext("artifactId"): d.findtext("version") for d in root.findall("dependencyManagement/dependencies/dependency")}
        self.assertRegex(boms.get("spring-cloud-dependencies", ""), r"^2025\.1\.\d+$")

    def test_every_python_module_requires_python_3_12(self):
        for rel in PYTHON_ENTRYPOINTS:
            with self.subTest(module=rel):
                data = tomllib.loads((REPO / rel / "pyproject.toml").read_text(encoding="utf-8"))
                self.assertEqual(data["project"]["requires-python"], "==3.12.*")
                self.assertEqual(data["build-system"]["build-backend"], "setuptools.build_meta")

    def test_web_engine_is_the_pinned_node(self):
        data = json.loads((REPO / "apps/web/package.json").read_text(encoding="utf-8"))
        self.assertEqual(data["engines"]["node"], self.tool["node"])

    def test_ci_uses_the_ledger_toolchain(self):
        text = (REPO / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertIn(f'python-version: "{self.tool["python"]}"', text)
        self.assertIn(f'node-version: "{self.tool["node"]}"', text)
        self.assertIn(f'java-version: "{self.tool["java"]}"', text)
        self.assertIn(f"apache-maven-{self.tool['maven']}-bin.tar.gz", text)
        self.assertIn("python scripts/build", text)


class Jackson3Only(unittest.TestCase):
    """ADR-006 on the real modules: no import of com.fasterxml.jackson.databind and no direct jackson-databind."""

    def test_pin_check_scans_every_java_module_and_finds_no_jackson_2(self):
        violations, _ = check(REPO)
        jackson = [str(v) for v in violations if v.rule == "jackson2-import" or "jackson-databind" in v.message]
        self.assertEqual(jackson, [])
        java_files = list((REPO / "services").rglob("*.java"))
        self.assertGreaterEqual(len(java_files), 18)  # application, health controller, smoke test per Java context
        for f in java_files:
            with self.subTest(file=f.relative_to(REPO).as_posix()):
                self.assertNotRegex(f.read_text(encoding="utf-8"), r"(?m)^\s*import\s+(static\s+)?com\.fasterxml\.jackson\.databind\b")

    def test_no_java_module_declares_jackson_databind(self):
        for path in (REPO / "services").glob("*/pom.xml"):
            with self.subTest(pom=path.parent.name):
                arts = {d.findtext("artifactId") for d in pom(path).iter("dependency")}
                self.assertNotIn("jackson-databind", arts)


JAVA_SUFFIXES = {".java", ".kt", ".xml", ".yml", ".yaml", ".properties", ".sql"}
PYTHON_SUFFIXES = {".py", ".toml", ".ini", ".cfg", ".txt", ".mako", ".yml", ".yaml"}
SKIP_PARTS = {"target", ".venv", "node_modules", "__pycache__", ".pytest_cache", "build", "dist"}


def _module_files(module: Path, suffixes: set[str]):
    for path in module.rglob("*"):
        rel = path.relative_to(module).parts
        if path.is_file() and path.suffix.lower() in suffixes and not (set(rel) & SKIP_PARTS) \
                and not any(p.endswith(".egg-info") for p in rel):
            yield path


def migration_tool_violations(root: Path) -> list[str]:
    """Task 1.5 (ADR-003): Flyway is the Java migration tool and Alembic the Python one; neither crosses over.

    A Java module is a directory with a pom.xml under services/, libs/, or platform/; a Python module is a directory
    with a pyproject.toml there. A Java module that mentions Alembic, or a Python module that mentions Flyway, fails.
    """
    out = []
    for top in ("services", "libs", "platform"):
        base = root / top
        if not base.is_dir():
            continue
        for pom in base.rglob("pom.xml"):
            if SKIP_PARTS & set(pom.relative_to(root).parts):
                continue
            for f in _module_files(pom.parent, JAVA_SUFFIXES):
                if re.search(r"(?i)alembic", f.read_text(encoding="utf-8", errors="replace")):
                    out.append(f"Java module {pom.parent.relative_to(root).as_posix()} references Alembic in {f.relative_to(root).as_posix()}")
        for pyproject in base.rglob("pyproject.toml"):
            if SKIP_PARTS & set(pyproject.relative_to(root).parts):
                continue
            for f in _module_files(pyproject.parent, PYTHON_SUFFIXES):
                if re.search(r"(?i)flyway", f.read_text(encoding="utf-8", errors="replace")):
                    out.append(f"Python module {pyproject.parent.relative_to(root).as_posix()} references Flyway in {f.relative_to(root).as_posix()}")
    return out


class MigrationToolPerRuntime(unittest.TestCase):
    """Task 1.5: one migration tool per runtime (Flyway for Java, Alembic for Python)."""

    def test_repository_has_no_cross_runtime_migration_tool(self):
        self.assertEqual(migration_tool_violations(REPO), [])

    def test_every_java_context_with_a_schema_uses_flyway(self):
        for ctx in ("legacy-integration", "integration-intelligence", "configuration-assurance", "release-assurance", "audit-sink"):
            with self.subTest(context=ctx):
                module = REPO / "services" / ctx
                arts = {d.findtext("artifactId") for d in pom(module / "pom.xml").iter("dependency")}
                self.assertTrue({"flyway-core", "flyway-database-postgresql", "spring-boot-starter-flyway"} <= arts)
                self.assertTrue((module / "src/main/resources/db/migration/V1__baseline.sql").is_file())

    def test_data_readiness_uses_alembic_and_the_sidecar_has_no_migrations(self):
        dr = REPO / "services/data-readiness"
        self.assertTrue((dr / "alembic.ini").is_file())
        self.assertTrue((dr / "migrations/env.py").is_file())
        deps = tomllib.loads((dr / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
        self.assertTrue(any(d.startswith("alembic==") for d in deps))
        sidecar = REPO / "services/release-assurance/inference-sidecar"
        self.assertFalse((sidecar / "alembic.ini").exists(), "the inference sidecar owns no tables")

    def test_a_java_module_referencing_alembic_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "services/x/src/main/resources").mkdir(parents=True)
            (root / "services/x/pom.xml").write_text("<project/>", encoding="utf-8")
            (root / "services/x/src/main/resources/application.yml").write_text("migrate: alembic upgrade head\n", encoding="utf-8")
            self.assertEqual(len(migration_tool_violations(root)), 1)

    def test_a_python_module_referencing_flyway_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "services/y/app").mkdir(parents=True)
            (root / "services/y/pyproject.toml").write_text("[project]\nname = 'y'\n", encoding="utf-8")
            (root / "services/y/app/migrate.py").write_text("import subprocess\nsubprocess.run(['flyway', 'migrate'])\n", encoding="utf-8")
            self.assertEqual(len(migration_tool_violations(root)), 1)

    def test_build_outputs_are_ignored(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "services/y/.venv/lib").mkdir(parents=True)
            (root / "services/y/pyproject.toml").write_text("[project]\nname = 'y'\n", encoding="utf-8")
            (root / "services/y/.venv/lib/flyway_mention.py").write_text("flyway\n", encoding="utf-8")
            self.assertEqual(migration_tool_violations(root), [])


class BuildRunnerCoverage(unittest.TestCase):
    def setUp(self):
        self.runner = load_build_runner()

    def test_root_pom_lists_every_java_module(self):
        modules = {m.text for m in pom(REPO / "pom.xml").findall("modules/module")}
        # Java modules: the bounded contexts under services/, the platform test modules (task 1.3), and libs (task 1.5).
        found = {p.parent.relative_to(REPO).as_posix() for top in ("services", "platform", "libs")
                 for p in (REPO / top).rglob("pom.xml") if "target" not in p.parts}
        self.assertEqual(modules, found)
        self.assertEqual(set(self.runner.JAVA_MODULES), found)

    def test_runner_lists_every_python_and_web_module(self):
        py = {p.parent.relative_to(REPO).as_posix() for p in (REPO / "services").rglob("pyproject.toml") if ".venv" not in p.parts}
        self.assertEqual(set(self.runner.PYTHON_MODULES), py)
        web = {p.parent.relative_to(REPO).as_posix() for p in (REPO / "apps").glob("*/package.json")}
        self.assertEqual(set(self.runner.WEB_MODULES), web)

    def test_ledger_toolchain_rejects_a_ledger_without_rows(self):
        with self.assertRaises(self.runner.BuildError):
            self.runner.ledger_toolchain("# empty ledger\n")


if __name__ == "__main__":
    unittest.main()
