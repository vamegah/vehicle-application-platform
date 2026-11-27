"""Protobuf contract tests for task 2.3.

Needs the pinned buf (DEPENDENCIES.lock.md) on PATH or in the BUF environment variable. The buf tests fail,
and never skip, when buf is missing. The Java compile test is the Maven module contracts/proto-java
(`mvn -B -ntp verify`), run by the same CI workflow.

    python -m unittest discover -s contracts/tests -p "test_proto*.py" -v
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import proto_lint

REPO = Path(__file__).resolve().parents[2]
PROTO = REPO / "contracts" / "proto"
CONFIG = PROTO / "configuration-assurance" / "config_validation.proto"
GRAPH = PROTO / "integration-intelligence" / "graph_facts.proto"
PINNED_BUF = "1.75.0"


def _buf() -> str | None:
    return os.environ.get("BUF") or shutil.which("buf")


def _run_buf(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    buf = _buf()
    if buf is None:
        raise AssertionError("buf not found: install the pinned buf and put it on PATH or set BUF")
    return subprocess.run([buf, *args], cwd=cwd, capture_output=True, text=True)


class RepositoryProtoLint(unittest.TestCase):
    def test_contract_files_exist(self):
        self.assertTrue(CONFIG.is_file())
        self.assertTrue(GRAPH.is_file())

    def test_repository_passes_the_package_and_tenant_rules(self):
        self.assertEqual(proto_lint.lint_tree(PROTO), [])

    def test_missing_tenant_id_fails(self):
        text = CONFIG.read_text(encoding="utf-8").replace("string tenant_id = 1;", "string tenant = 1;")
        problems = proto_lint.lint_text("configuration-assurance", text)
        self.assertTrue(any("tenant_id" in p for p in problems), problems)

    def test_tenant_id_with_another_type_or_number_fails(self):
        for bad in ("int64 tenant_id = 1;", "string tenant_id = 4;"):
            with self.subTest(field=bad):
                text = GRAPH.read_text(encoding="utf-8").replace("string tenant_id = 1;", bad)
                self.assertTrue(proto_lint.lint_text("integration-intelligence", text))

    def test_tenant_id_only_in_a_comment_fails(self):
        text = CONFIG.read_text(encoding="utf-8").replace("  string tenant_id = 1;", "  // string tenant_id = 1;")
        self.assertTrue(proto_lint.lint_text("configuration-assurance", text))

    def test_package_that_does_not_match_the_context_fails(self):
        for bad in ("autoreliance.integration.v1", "autoreliance.configuration", "autoreliance.configuration.v0",
                    "com.autoreliance.configuration.v1"):
            with self.subTest(package=bad):
                text = CONFIG.read_text(encoding="utf-8").replace("package autoreliance.configuration.v1;", f"package {bad};")
                self.assertTrue(proto_lint.lint_text("configuration-assurance", text))

    def test_v2_package_in_the_right_directory_passes(self):
        text = CONFIG.read_text(encoding="utf-8").replace("autoreliance.configuration.v1", "autoreliance.configuration.v2")
        self.assertEqual(proto_lint.lint_text("configuration-assurance", text), [])

    def test_unknown_context_directory_fails(self):
        self.assertTrue(proto_lint.lint_text("quality-intelligence", CONFIG.read_text(encoding="utf-8")))


class BufLintAndBuild(unittest.TestCase):
    def test_pinned_buf_version(self):
        proc = _run_buf("--version", cwd=REPO)
        self.assertEqual(proc.stdout.strip(), PINNED_BUF, proc.stderr)

    def test_buf_build_and_lint_pass(self):
        for args in (("build",), ("lint",)):
            with self.subTest(command=" ".join(args)):
                proc = _run_buf(*args, cwd=REPO)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_buf_lint_rejects_a_bad_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._copy_module(Path(tmp) / "repo")
            target = root / "contracts" / "proto" / "integration-intelligence" / "graph_facts.proto"
            target.write_text(target.read_text(encoding="utf-8").replace("NODE_TYPE_UNSPECIFIED = 0;", "NODE_TYPE_NONE = 0;"),
                              encoding="utf-8")
            proc = _run_buf("lint", cwd=root)
            self.assertNotEqual(proc.returncode, 0, "buf lint accepted an enum zero value without the _UNSPECIFIED suffix")

    @staticmethod
    def _copy_module(root: Path) -> Path:
        shutil.copytree(PROTO, root / "contracts" / "proto")
        shutil.copy2(REPO / "buf.yaml", root / "buf.yaml")
        return root


class BufBreaking(unittest.TestCase):
    """buf breaking between a baseline copy and a changed copy of the module (task 2.3 and 2.6)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.baseline = BufLintAndBuild._copy_module(base / "baseline")
        self.changed = BufLintAndBuild._copy_module(base / "changed")

    def tearDown(self):
        self._tmp.cleanup()

    def _edit(self, rel: str, old: str, new: str):
        path = self.changed / "contracts" / "proto" / rel
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def _breaking(self) -> subprocess.CompletedProcess:
        return _run_buf("breaking", str(self.changed), "--against", str(self.baseline), cwd=REPO)

    def test_unchanged_contracts_pass(self):
        proc = self._breaking()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_removing_a_v1_field_fails(self):
        self._edit("configuration-assurance/config_validation.proto", "  string rule_set_version = 3;\n}", "}")
        proc = self._breaking()
        self.assertNotEqual(proc.returncode, 0, "removing a v1 field was not reported as breaking")
        self.assertIn("config_validation.proto", proc.stdout + proc.stderr)

    def test_renaming_a_v1_package_fails(self):
        self._edit("integration-intelligence/graph_facts.proto", "package autoreliance.integration.v1;",
                   "package autoreliance.integration.v1beta;")
        self.assertNotEqual(self._breaking().returncode, 0)

    def test_renumbering_a_v1_field_fails(self):
        self._edit("integration-intelligence/graph_facts.proto", "uint32 max_depth = 3;", "uint32 max_depth = 9;")
        self.assertNotEqual(self._breaking().returncode, 0)

    def test_adding_a_v1_field_passes(self):
        self._edit("integration-intelligence/graph_facts.proto", "  uint32 max_depth = 3;",
                   "  uint32 max_depth = 3;\n  // Added field, wire compatible.\n  bool include_sensors = 4;")
        proc = self._breaking()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_adding_a_new_v2_package_passes(self):
        v2 = self.changed / "contracts" / "proto" / "configuration-assurance" / "config_validation_v2.proto"
        text = CONFIG.read_text(encoding="utf-8").replace("autoreliance.configuration.v1", "autoreliance.configuration.v2")
        text = text.replace("com.autoreliance.contracts.configuration.v1", "com.autoreliance.contracts.configuration.v2")
        text = text.replace("ConfigValidationProto", "ConfigValidationV2Proto")
        v2.write_text(text, encoding="utf-8")
        proc = self._breaking()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proto_lint.lint_tree(self.changed / "contracts" / "proto"), [])


if __name__ == "__main__":
    unittest.main()
