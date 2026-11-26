"""Maven test for ADR-010 (task 1.4 item h).

Runs `mvn dependency:tree` on a fixture module and fails unless spring-vault-core resolves to 4.1.2 with no
managed-version conflict and no Spring Cloud Vault starter. The `good` fixture must pass; the three bad
fixtures (4.0.x pinned, version left to the Cloud BOM, Cloud Vault starter present) must each fail.

Needs Maven and network access to Maven Central. If `mvn` is not on PATH the tests are skipped and the CI
workflow (which installs Maven) treats a skip as a failure.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "maven"
EXPECTED = "4.1.2"
MVN = shutil.which("mvn") or shutil.which("mvn.cmd")


def vault_tree_problems(fixture: str) -> list[str]:
    """Return the problems found in the dependency tree of the fixture module (empty means it passes)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / fixture
        shutil.copytree(FIXTURES / fixture, work)
        out = work / "tree.txt"
        proc = subprocess.run(
            [MVN, "-B", "-ntp", "-q", "dependency:tree", "-Dverbose", f"-DoutputFile={out}"],
            cwd=work, capture_output=True, text=True,
        )
        if proc.returncode != 0 or not out.exists():
            return [f"mvn dependency:tree failed: {(proc.stdout + proc.stderr)[-600:]}"]
        tree = out.read_text(encoding="utf-8")
    problems: list[str] = []
    versions = re.findall(r"org\.springframework\.vault:spring-vault-core:jar:([^:\s]+)", tree)
    if not versions:
        problems.append("spring-vault-core is not in the tree")
    for v in versions:
        if v != EXPECTED:
            problems.append(f"spring-vault-core resolves to {v}, expected {EXPECTED}")
    for line in tree.splitlines():
        if "spring-vault-core" in line and ("omitted for conflict" in line or "omitted for duplicate" in line):
            problems.append(f"spring-vault-core conflict or duplicate: {line.strip()}")
    if "spring-cloud-starter-vault-config" in tree:
        problems.append("spring-cloud-starter-vault-config is present")
    return problems


@unittest.skipUnless(MVN, "mvn is not on PATH")
class VaultDependencyTree(unittest.TestCase):
    def test_good_fixture_resolves_4_1_2_with_no_conflict(self):
        self.assertEqual(vault_tree_problems("good"), [])

    def test_fixture_with_4_0_x_fails(self):
        problems = vault_tree_problems("vault-4-0-x")
        self.assertTrue(any("4.0.5" in p for p in problems), problems)

    def test_fixture_leaving_version_to_cloud_bom_fails(self):
        problems = vault_tree_problems("vault-managed-by-cloud")
        self.assertTrue(any("expected 4.1.2" in p for p in problems), problems)

    def test_fixture_with_cloud_vault_starter_fails(self):
        problems = vault_tree_problems("vault-starter")
        self.assertTrue(any("spring-cloud-starter-vault-config" in p for p in problems), problems)

    def test_smoke_module_resolves_vault_4_1_2(self):
        smoke = Path(__file__).resolve().parents[1] / "verification" / "dependency-smoke"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tree.txt"
            proc = subprocess.run([MVN, "-B", "-ntp", "-q", "dependency:tree", f"-DoutputFile={out}"], cwd=smoke, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout[-600:] + proc.stderr[-600:])
            tree = out.read_text(encoding="utf-8")
        self.assertIn("org.springframework.vault:spring-vault-core:jar:4.1.2", tree)
        self.assertNotIn("spring-cloud-starter-vault-config", tree)
        self.assertIn("software.amazon.awssdk:s3:jar:2.59.10", tree)
        self.assertNotIn("com.fasterxml.jackson.core:jackson-databind", tree)


if __name__ == "__main__":
    unittest.main()
