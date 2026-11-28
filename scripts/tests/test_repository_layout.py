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


class BuildRunnerCoverage(unittest.TestCase):
    def setUp(self):
        self.runner = load_build_runner()

    def test_root_pom_lists_every_java_module(self):
        modules = {m.text for m in pom(REPO / "pom.xml").findall("modules/module")}
        # Java modules: the bounded contexts under services/ and the platform test modules (task 1.3).
        found = {p.parent.relative_to(REPO).as_posix() for top in ("services", "platform")
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
