"""Fixture-based unit tests for scripts/check-dependency-pins (task 1.4).

Every test copies the clean fixture tree to a temp directory, applies one change, runs the checker, and
asserts the expected rule fires (or that nothing fires for the clean tree and the passing variants).
Run: python -m unittest discover -s scripts/tests -v
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from depcheck.checker import check  # noqa: E402

CLEAN = Path(__file__).resolve().parent / "fixtures" / "clean"
POM = "services/legacy-integration/pom.xml"
LEDGER = "DEPENDENCIES.lock.md"
DR = "services/data-readiness/pyproject.toml"
SIDECAR = "services/release-assurance/inference-sidecar/pyproject.toml"
WEB = "apps/web/package.json"
COMPOSE = "platform/docker-compose.yml"
JAVA = "services/legacy-integration/src/main/java/com/autoreliance/legacyintegration/Json.java"
GARAGE = "dxflrs/garage:v2.6.0@sha256:4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013"


class Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        shutil.copytree(CLEAN, self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def edit(self, rel: str, old: str, new: str) -> None:
        p = self.root / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture {rel} no longer contains {old!r}")
        p.write_text(text.replace(old, new), encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def run_check(self):
        violations, _ = check(self.root)
        return violations

    def rules(self) -> set[str]:
        return {v.rule for v in self.run_check()}

    def assertFails(self, rule: str, path_fragment: str | None = None):
        vs = self.run_check()
        hits = [v for v in vs if v.rule == rule and (path_fragment is None or path_fragment in v.path or path_fragment in v.message)]
        self.assertTrue(hits, f"expected rule {rule!r}; got {[str(v) for v in vs]}")


class CleanTree(Case):
    def test_clean_fixture_has_no_violations(self):
        self.assertEqual([str(v) for v in self.run_check()], [])

    def test_real_repository_passes(self):
        violations, _ = check(REPO)
        self.assertEqual([str(v) for v in violations], [])

    def test_script_runs_from_the_command_line_and_exits_zero(self):
        proc = subprocess.run([sys.executable, str(SCRIPTS / "check-dependency-pins"), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OK", proc.stdout)

    def test_script_exits_nonzero_on_violation(self):
        self.edit(WEB, '"16.4.6"', '"^16.4.6"')
        proc = subprocess.run([sys.executable, str(SCRIPTS / "check-dependency-pins"), "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("FAIL [unpinned-version]", proc.stdout)

    def test_no_manifests_passes_and_skips_unused_rule(self):
        for rel in (POM, DR, SIDECAR, WEB, COMPOSE, JAVA):
            (self.root / rel).unlink()
        violations, notes = check(self.root)
        self.assertEqual([str(v) for v in violations], [])
        self.assertTrue(any("skipped" in n for n in notes))


class RangeOperators(Case):
    def test_caret_range_in_package_json(self):
        self.edit(WEB, '"16.4.6"', '"^16.4.6"')
        self.assertFails("unpinned-version", "next")

    def test_tilde_and_star_and_latest_in_package_json(self):
        for bad in ("~16.4.6", "*", "latest", ">=16", "16.x"):
            with self.subTest(bad=bad):
                self.write(WEB, '{"dependencies": {"next": "%s"}}' % bad)
                self.assertFails("unpinned-version", "next")

    def test_ge_operator_in_pyproject(self):
        self.edit(DR, "fastapi==0.165.0", "fastapi>=0.165.0")
        self.assertFails("unpinned-version", "fastapi")

    def test_latest_or_bare_name_in_python(self):
        for bad in ("fastapi", "fastapi~=0.165", "fastapi==0.165.*", "fastapi==0.165.0,<1"):
            with self.subTest(bad=bad):
                self.edit(DR, '"fastapi==0.165.0"', f'"{bad}"')
                self.assertFails("unpinned-version", "fastapi")
                self.edit(DR, f'"{bad}"', '"fastapi==0.165.0"')

    def test_requirements_txt_range(self):
        self.write("services/data-readiness/requirements.txt", "fastapi>=0.165.0\n")
        self.assertFails("unpinned-version", "fastapi")

    def test_requirements_txt_exact_passes(self):
        self.write("services/data-readiness/requirements.txt", "fastapi==0.165.0  # pinned\n-r other.txt\n")
        self.assertEqual(self.rules(), set())

    def test_maven_latest_release_range_and_snapshot(self):
        for bad in ("LATEST", "RELEASE", "[4.1,)", "4.1.2-SNAPSHOT", "(,4.2)"):
            with self.subTest(bad=bad):
                self.edit(POM, "<version>4.1.2</version>", f"<version>{bad}</version>")
                self.assertFails("unpinned-version", "spring-vault-core")
                self.edit(POM, f"<version>{bad}</version>", "<version>4.1.2</version>")

    def test_maven_property_version_resolves_and_must_match(self):
        self.edit(POM, "<version>4.1.2</version>", "<version>${vault.version}</version>")
        self.assertFails("unresolved-property", "spring-vault-core")
        self.edit(POM, "<modelVersion>4.0.0</modelVersion>", "<modelVersion>4.0.0</modelVersion><properties><vault.version>4.1.2</vault.version></properties>")
        self.assertEqual(self.rules(), set())


class LedgerCoverage(Case):
    def test_missing_ledger_row_python(self):
        self.edit(DR, '"boto3==1.44.12",', '"boto3==1.44.12",\n  "requests==2.0.0",')
        self.assertFails("ledger-missing", "requests")

    def test_missing_ledger_row_node(self):
        self.write(WEB, '{"dependencies": {"next": "16.4.6", "left-pad": "1.3.0"}}')
        self.assertFails("ledger-missing", "left-pad")

    def test_missing_ledger_row_maven(self):
        self.edit(POM, "</dependencies>\n</project>", "<dependency><groupId>org.example</groupId><artifactId>lib</artifactId><version>1.0.0</version></dependency>\n  </dependencies>\n</project>")
        self.assertFails("ledger-missing", "org.example:lib")

    def test_version_differs_from_ledger(self):
        self.edit(DR, "fastapi==0.165.0", "fastapi==0.114.2")
        self.assertFails("version-mismatch", "fastapi")

    def test_unverified_row_in_use(self):
        self.edit(LEDGER, "| fastapi | 0.165.0 | |", "| fastapi | UNVERIFIED - resolve at task 1.4 | |")
        self.assertFails("unverified-in-use", "fastapi")
        self.assertFails("ledger-unverified")

    def test_unverified_row_unused_still_fails_the_ledger(self):
        self.edit(LEDGER, "| next | 16.4.6 | |", "| next | UNVERIFIED - resolve at task 1.4 | |\n| celery | UNVERIFIED - resolve at task 1.4 | |")
        self.assertFails("ledger-unverified", "celery")

    def test_ledger_row_with_no_manifest_entry(self):
        self.edit(LEDGER, "| next | 16.4.6 | |", "| next | 16.4.6 | |\n| unused-lib | 1.0.0 | |")
        self.assertFails("ledger-unused", "unused-lib")

    def test_planned_or_not_used_rows_are_exempt(self):
        self.edit(LEDGER, "| next | 16.4.6 | |", "| next | 16.4.6 | |\n| later-lib | 1.0.0 | Planned (task 5.1) |")
        self.assertEqual(self.rules(), set())


class ForbiddenLibraries(Case):
    def test_langgraph_in_python_manifest(self):
        self.edit(DR, '"boto3==1.44.12",', '"boto3==1.44.12",\n  "langgraph==0.2.28",')
        self.assertFails("forbidden-artifact", "langgraph")

    def test_langgraph_in_package_json(self):
        self.write(WEB, '{"dependencies": {"next": "16.4.6", "@langchain/langgraph": "0.2.28"}}')
        self.assertFails("forbidden-artifact", "langgraph")

    def test_xgboost_outside_sidecar(self):
        self.edit(DR, '"boto3==1.44.12",', '"boto3==1.44.12",\n  "xgboost==3.4.1",')
        self.assertFails("sidecar-only", "xgboost")

    def test_scikit_learn_outside_sidecar(self):
        self.edit(DR, '"boto3==1.44.12",', '"boto3==1.44.12",\n  "scikit_learn==1.9.1",')
        self.assertFails("sidecar-only", "scikit_learn")

    def test_xgboost_and_scikit_learn_inside_sidecar_pass(self):
        self.assertEqual(self.rules(), set())

    def test_spring_cloud_vault_starter_is_forbidden(self):
        self.edit(POM, "</dependencies>\n</project>", "<dependency><groupId>org.springframework.cloud</groupId><artifactId>spring-cloud-starter-vault-config</artifactId></dependency>\n  </dependencies>\n</project>")
        self.assertFails("forbidden-artifact", "spring-cloud-starter-vault-config")

    def test_old_gateway_starter_is_forbidden(self):
        self.edit(POM, "spring-cloud-starter-gateway-server-webflux", "spring-cloud-starter-gateway")
        self.assertFails("forbidden-artifact", "spring-cloud-starter-gateway")

    def test_direct_jackson_databind_dependency_is_forbidden(self):
        self.edit(POM, "</dependencies>\n</project>", "<dependency><groupId>com.fasterxml.jackson.core</groupId><artifactId>jackson-databind</artifactId><version>2.21.8</version></dependency>\n  </dependencies>\n</project>")
        self.assertFails("forbidden-artifact", "jackson-databind")


class BomRules(Case):
    def test_bom_managed_artifact_without_bom_row(self):
        self.edit(LEDGER, "| software.amazon.awssdk:bom | 2.59.10 | Approved by user, Decision 3. |\n", "")
        self.edit(LEDGER, "| software.amazon.awssdk:s3 | 2.59.10 | Approved by user, Decision 3. |\n", "")
        self.assertFails("bom-ledger-missing", "software.amazon.awssdk:s3")

    def test_bom_managed_artifact_without_bom_import(self):
        self.edit(POM, """      <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>bom</artifactId>
        <version>2.59.10</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
""", "")
        self.assertFails("bom-not-imported", "software.amazon.awssdk:s3")

    def test_unpinned_aws_sdk_s3_with_range(self):
        self.edit(POM, "<artifactId>s3</artifactId>", "<artifactId>s3</artifactId><version>[2.0,)</version>")
        self.assertFails("unpinned-version", "software.amazon.awssdk:s3")

    def test_unpinned_aws_sdk_s3_without_version_or_bom(self):
        self.edit(POM, """      <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>bom</artifactId>
        <version>2.59.10</version>
        <type>pom</type>
        <scope>import</scope>
      </dependency>
""", "")
        self.assertIn("bom-not-imported", self.rules())

    def test_aws_bom_version_must_match_ledger(self):
        self.edit(POM, "<version>2.59.10</version>", "<version>2.30.0</version>")
        self.assertFails("version-mismatch", "software.amazon.awssdk:bom")

    def test_versionless_dependency_without_any_managing_bom(self):
        self.edit(POM, """  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.3</version>
    <relativePath/>
  </parent>
""", "")
        self.assertFails("no-managing-bom", "kafka-clients")

    def test_spring_boot_3_parent(self):
        self.edit(POM, "<version>4.1.3</version>", "<version>3.5.16</version>")
        self.assertFails("boot-version", "3.5.16")

    def test_spring_boot_4_0_parent(self):
        self.edit(POM, "<version>4.1.3</version>", "<version>4.0.10</version>")
        self.assertFails("boot-version", "4.0.10")

    def test_pre_2025_1_spring_cloud_bom(self):
        for old in ("2024.0.1", "2023.0.5", "2025.0.0", "2022.0.4"):
            with self.subTest(old=old):
                self.edit(POM, "<version>2025.1.5</version>", f"<version>{old}</version>")
                self.assertFails("cloud-train", old)
                self.edit(POM, f"<version>{old}</version>", "<version>2025.1.5</version>")

    def test_named_legacy_spring_cloud_train(self):
        self.edit(POM, "<version>2025.1.5</version>", "<version>Hoxton.SR12</version>")
        self.assertFails("cloud-train", "Hoxton.SR12")


class ImageRules(Case):
    def test_garage_image_with_latest_tag(self):
        self.edit(COMPOSE, GARAGE, "dxflrs/garage:latest")
        self.assertFails("image-no-digest", COMPOSE)

    def test_garage_image_without_digest(self):
        self.edit(COMPOSE, GARAGE, "dxflrs/garage:v2.6.0")
        self.assertFails("image-no-digest", COMPOSE)

    def test_garage_image_bare_name(self):
        self.edit(COMPOSE, GARAGE, "dxflrs/garage")
        self.assertFails("image-no-digest", COMPOSE)

    def test_compose_garage_digest_differs_from_ledger(self):
        self.edit(COMPOSE, "4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013", "0" * 64)
        self.assertFails("image-ledger-mismatch", COMPOSE)

    def test_compose_garage_tag_differs_from_ledger(self):
        self.edit(COMPOSE, "v2.6.0", "v2.5.0")
        self.assertFails("image-ledger-mismatch", COMPOSE)

    def test_testcontainers_fixture_garage_digest_differs(self):
        self.write("services/legacy-integration/src/test/java/GarageIT.java", 'class GarageIT { String img = "dxflrs/garage:v2.6.0@sha256:%s"; }' % ("a" * 64))
        self.assertFails("image-ledger-mismatch", "GarageIT.java")

    def test_testcontainers_fixture_garage_without_digest(self):
        self.write("services/legacy-integration/src/test/java/GarageIT.java", 'class GarageIT { String img = "dxflrs/garage:v2.6.0"; }')
        self.assertFails("image-no-digest", "GarageIT.java")

    def test_seaweedfs_without_digest(self):
        self.write("platform/ci/seaweed.yml", "image: chrislusf/seaweedfs:4.55\n")
        self.assertFails("image-no-digest", "seaweed.yml")

    def test_seaweedfs_with_ledger_digest_passes(self):
        self.write("platform/ci/seaweed.yml", "image: chrislusf/seaweedfs:4.55@sha256:7ca46aeae2f223b37e5d91593c17ab37738eec6df6ab69b48a0487f7643342b9\n")
        self.assertEqual(self.rules(), set())

    def test_ledger_garage_row_without_digest(self):
        self.edit(LEDGER, "dxflrs/garage:v2.6.0@sha256:4b5a318fc9fe2fbec5d3af590eeafe05d83492e6411266fa0b9e215c20264013", "dxflrs/garage:v2.6.0")
        self.assertIn("image-no-digest", self.rules())

    def test_minio_image(self):
        self.edit(COMPOSE, "services:", "services:\n  store:\n    image: minio/minio:RELEASE.2025-01-01T00-00-00Z")
        self.assertFails("minio", COMPOSE)

    def test_minio_service_name_in_compose(self):
        self.edit(COMPOSE, "services:", "services:\n  minio:\n    image: example/other:1.0.0")
        self.assertFails("minio", COMPOSE)

    def test_testcontainers_minio_maven_dependency(self):
        self.edit(POM, "</dependencies>\n</project>", "<dependency><groupId>org.testcontainers</groupId><artifactId>testcontainers-minio</artifactId></dependency>\n  </dependencies>\n</project>")
        self.assertFails("minio", "legacy-integration/pom.xml")

    def test_testcontainers_minio_python_extra(self):
        self.edit(DR, '"boto3==1.44.12",', '"boto3==1.44.12",\n  "testcontainers-minio==1.0.0",')
        self.assertFails("minio", "data-readiness")

    def test_minio_in_java_test_code(self):
        self.write("services/legacy-integration/src/test/java/X.java", "import org.testcontainers.containers.MinIOContainer;\nclass X {}\n")
        self.assertFails("minio", "X.java")


class LedgerRules(Case):
    def test_aws_sdk_row_missing_approval_note(self):
        self.edit(LEDGER, "| software.amazon.awssdk:s3 | 2.59.10 | Approved by user, Decision 3. |", "| software.amazon.awssdk:s3 | 2.59.10 | Chosen for S3. |")
        self.assertFails("approval-note-missing", "software.amazon.awssdk:s3")

    def test_aws_sdk_bom_row_missing_approval_note(self):
        self.edit(LEDGER, "| software.amazon.awssdk:bom | 2.59.10 | Approved by user, Decision 3. |", "| software.amazon.awssdk:bom | 2.59.10 | BOM. |")
        self.assertFails("approval-note-missing", "software.amazon.awssdk:bom")

    def test_boto3_row_missing_approval_note(self):
        self.edit(LEDGER, "| boto3 | 1.44.12 | Approved by user, Decision 3. |", "| boto3 | 1.44.12 | S3 client. |")
        self.assertFails("approval-note-missing", "boto3")

    def test_xgboost_row_must_remain(self):
        self.edit(LEDGER, "| xgboost | 3.4.1 | Sidecar only. |\n", "")
        self.edit(SIDECAR, '  "xgboost==3.4.1",\n', "")
        self.assertFails("ledger-rule", "xgboost")

    def test_langgraph_row_outside_not_used_section(self):
        self.edit(LEDGER, "| next | 16.4.6 | |", "| next | 16.4.6 | |\n| langgraph | 0.2.28 | Phase 2. |")
        self.assertFails("ledger-rule", "langgraph")

    def test_minio_row_outside_not_used_section(self):
        self.edit(LEDGER, "| next | 16.4.6 | |", "| next | 16.4.6 | |\n| minio | 8.5.0 | client |")
        self.assertFails("ledger-rule", "minio")

    def test_vault_row_must_be_4_1_2_and_name_the_override(self):
        self.edit(LEDGER, "| 4.1.2 | Overrides the Spring Cloud BOM's managed 4.0.x. |", "| 4.0.5 | Managed by the Cloud BOM. |")
        self.assertFails("ledger-rule", "spring-vault-core")

    def test_vault_manifest_version_4_0_x_mismatches_ledger(self):
        self.edit(POM, "<version>4.1.2</version>", "<version>4.0.5</version>")
        self.assertFails("version-mismatch", "spring-vault-core")

    def test_missing_ledger_file(self):
        (self.root / LEDGER).unlink()
        self.assertFails("ledger-file")


class JacksonImports(Case):
    def test_object_mapper_import_fails(self):
        self.write(JAVA, "package x;\nimport com.fasterxml.jackson.databind.ObjectMapper;\nclass A { ObjectMapper m; }\n")
        self.assertFails("jackson2-import", "Json.java")

    def test_static_and_wildcard_import_fail(self):
        self.write(JAVA, "package x;\nimport static com.fasterxml.jackson.databind.SerializationFeature.INDENT_OUTPUT;\nclass A {}\n")
        self.assertFails("jackson2-import")
        self.write(JAVA, "package x;\nimport com.fasterxml.jackson.databind.*;\nclass A {}\n")
        self.assertFails("jackson2-import")

    def test_json_mapper_import_passes(self):
        self.write(JAVA, "package x;\nimport tools.jackson.databind.json.JsonMapper;\nclass A { JsonMapper m; }\n")
        self.assertEqual(self.rules(), set())

    def test_jackson_annotations_import_passes(self):
        self.write(JAVA, "package x;\nimport com.fasterxml.jackson.annotation.JsonProperty;\nclass A {}\n")
        self.assertEqual(self.rules(), set())

    def test_class_name_string_is_not_an_import(self):
        self.write(JAVA, 'package x;\nclass A { String n = "com.fasterxml.jackson.databind.ObjectMapper"; }\n')
        self.assertEqual(self.rules(), set())


if __name__ == "__main__":
    unittest.main()
