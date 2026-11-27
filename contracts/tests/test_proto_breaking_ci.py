"""Tests for the buf breaking-change CI check (task 2.6).

The CI-runner tests build a throwaway git repository with the real buf.yaml and contracts/proto on a main
branch, create one fixture branch per change, and run contracts/tools/check_proto.py exactly as the
proto-breaking workflow does (`--against .git#branch=main`). Needs git and the pinned buf (BUF or PATH).

    python -m unittest discover -s contracts/tests -p "test_proto*.py" -v
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "contracts" / "tools" / "check_proto.py"
WORKFLOW = REPO / ".github" / "workflows" / "proto-breaking.yml"
LEDGER = REPO / "DEPENDENCIES.lock.md"
CONFIG_PROTO = "contracts/proto/configuration-assurance/config_validation.proto"
GRAPH_PROTO = "contracts/proto/integration-intelligence/graph_facts.proto"
GIT_ID = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false"]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_ID, *args], cwd=cwd, check=True, capture_output=True, text=True)


class FixtureBranches(unittest.TestCase):
    def setUp(self):
        if not (os.environ.get("BUF") or shutil.which("buf")):
            self.fail("buf not found: install the pinned buf and put it on PATH or set BUF")
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        shutil.copy2(REPO / "buf.yaml", self.repo / "buf.yaml")
        shutil.copytree(REPO / "contracts" / "proto", self.repo / "contracts" / "proto")
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "baseline")

    def tearDown(self):
        self._tmp.cleanup()

    def _branch(self, name: str, edits: dict[str, tuple[str, str]] | None = None, new_files: dict[str, str] | None = None):
        _git(self.repo, "switch", "-q", "-c", name)
        for rel, (pattern, replacement) in (edits or {}).items():
            path = self.repo / rel
            text = path.read_text(encoding="utf-8")
            changed = re.sub(pattern, replacement, text, count=1)
            self.assertNotEqual(changed, text, f"fixture edit did not match in {rel}")
            path.write_text(changed, encoding="utf-8")
        for rel, text in (new_files or {}).items():
            (self.repo / rel).write_text(text, encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", name)

    def _check(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--against", ".git#branch=main"], cwd=self.repo,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_unchanged_branch_passes(self):
        self._branch("unchanged", new_files={"README.md": "fixture\n"})
        proc = self._check()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[PASS] buf breaking", proc.stdout)

    def test_removing_a_v1_field_fails_and_names_the_file_and_rule(self):
        self._branch("remove-field", {CONFIG_PROTO: (r"\s*string rule_set_version = 3;(\r?\n)\}", r"\1}")})
        proc = self._check()
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("config_validation.proto", proc.stdout)
        self.assertIn("FIELD_NO_DELETE", proc.stdout)

    def test_renaming_a_v1_package_fails(self):
        self._branch("rename-package", {GRAPH_PROTO: (r"package autoreliance\.integration\.v1;",
                                                      "package autoreliance.integration.v1beta;")})
        proc = self._check()
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("graph_facts.proto", proc.stdout)
        self.assertRegex(proc.stdout, r"error [A-Z_]+ :")

    def test_adding_a_new_v2_package_passes(self):
        """A v2 package lives in contracts/proto/<context>/v2/ (buf DIRECTORY_SAME_PACKAGE); lint and breaking pass."""
        v1 = (self.repo / CONFIG_PROTO).read_text(encoding="utf-8")
        v2 = (v1.replace("autoreliance.configuration.v1", "autoreliance.configuration.v2")
                .replace("com.autoreliance.contracts.configuration.v1", "com.autoreliance.contracts.configuration.v2"))
        (self.repo / "contracts/proto/configuration-assurance/v2").mkdir()
        self._branch("add-v2", new_files={"contracts/proto/configuration-assurance/v2/config_validation.proto": v2})
        proc = self._check()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("[PASS] buf lint", proc.stdout)

    def test_a_lint_violation_fails_even_without_a_breaking_change(self):
        self._branch("lint", {GRAPH_PROTO: (r"NODE_TYPE_UNSPECIFIED = 0;", "NODE_TYPE_NONE = 0;")})
        proc = self._check()
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("[FAIL] buf lint", proc.stdout)


class WorkflowDefinition(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        # PyYAML reads the bare key `on` as the boolean True.
        self.triggers = self.workflow.get("on", self.workflow.get(True))
        self.steps = self.workflow["jobs"]["buf-breaking"]["steps"]

    def test_path_filter_covers_every_proto_change(self):
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertIn("contracts/proto/**", self.triggers[event]["paths"])
                self.assertIn("buf.yaml", self.triggers[event]["paths"])

    def test_checkout_has_full_history(self):
        checkout = next(s for s in self.steps if str(s.get("uses", "")).startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["fetch-depth"], 0)

    def test_breaking_check_runs_against_main(self):
        runs = " ".join(str(s.get("run", "")) for s in self.steps)
        self.assertIn("check_proto.py --against '.git#branch=main'", runs)
        self.assertIn("git branch --force main origin/main", runs)

    def test_buf_version_and_checksum_match_the_ledger(self):
        row = next(line for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.startswith("| buf |"))
        version = row.split("|")[2].strip()
        linux_sha = re.search(r"`buf-Linux-x86_64` `([0-9a-f]{64})`", row).group(1)
        install = next(str(s["run"]) for s in self.steps if "buf-Linux-x86_64" in str(s.get("run", "")))
        self.assertIn(f"/releases/download/v{version}/buf-Linux-x86_64", install)
        self.assertIn(linux_sha, install)

    def test_actions_are_the_pinned_versions(self):
        ledger = LEDGER.read_text(encoding="utf-8")
        for step in self.steps:
            uses = step.get("uses")
            if uses:
                name, version = uses.split("@")
                with self.subTest(action=name):
                    self.assertIn(f"| {name} | {version} |", ledger)


if __name__ == "__main__":
    unittest.main()
