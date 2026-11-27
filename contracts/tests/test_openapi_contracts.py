"""OpenAPI contract tests for task 2.4.

Needs the pinned Redocly CLI (`npm ci` in contracts/) and contracts/tests/requirements.txt. The Redocly tests
fail, and never skip, when the CLI is missing.

    python -m unittest discover -s contracts/tests -p "test_openapi*.py" -v
"""
from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

import openapi_lint as ol

CONTRACTS = Path(__file__).resolve().parents[1]
REPO = CONTRACTS.parent
OPENAPI = CONTRACTS / "openapi"
COMPOSER = CONTRACTS / "tools" / "compose_gateway.py"
CONTEXTS = ("data-readiness", "legacy-integration", "integration-intelligence", "configuration-assurance",
            "release-assurance", "api-gateway", "audit-sink")
C = "./common/components.yaml#/components"


def _redocly() -> list[str] | None:
    exe = CONTRACTS / "node_modules" / ".bin" / ("redocly.cmd" if os.name == "nt" else "redocly")
    return [str(exe)] if exe.exists() else None


def _run_redocly(*args: str, cwd: Path = CONTRACTS) -> subprocess.CompletedProcess:
    cli = _redocly()
    if cli is None:
        raise AssertionError("Redocly CLI not installed: run `npm ci` in contracts/ (pinned @redocly/cli)")
    env = dict(os.environ, REDOCLY_TELEMETRY="off", REDOCLY_SUPPRESS_UPDATE_NOTICE="true")
    # Redocly prints emoji; decode as UTF-8 so the Windows console code page cannot break the test.
    return subprocess.run(cli + list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, shell=os.name == "nt")


# ------------------------------------------------------------------------------------------- fixtures

def errors(*extra: str) -> dict:
    codes = {"400": f"{C}/responses/Problem400", "401": f"{C}/responses/Problem401",
             "403": f"{C}/responses/Problem403", "504": f"{C}/responses/Problem504"}
    for code in extra:
        codes[code] = f"{C}/responses/Problem{code}"
    return {code: {"$ref": ref} for code, ref in codes.items()}


def get_item(roles=("auditor",), path_param: str | None = None) -> dict:
    """A valid single-item GET operation."""
    op = {
        "operationId": "fixtureGetItem",
        "summary": "fixture",
        "tags": ["fixture"],
        "security": [{"tenantPrincipal": list(roles)}],
        "responses": {
            "200": {"description": "ok", "content": {"application/json": {"schema": {
                "type": "object", "required": ["data", "meta"],
                "properties": {"data": {"type": "object"}, "meta": {"$ref": f"{C}/schemas/Meta"}}}}}},
            **errors(),
        },
    }
    if path_param:
        op["parameters"] = [{"name": path_param, "in": "path", "required": True,
                             "schema": {"$ref": f"{C}/schemas/CanonicalId"}}]
        op["responses"].update(errors("404"))
    return op


def list_items() -> dict:
    op = get_item()
    op["operationId"] = "fixtureListItems"
    op["parameters"] = [{"$ref": f"{C}/parameters/Cursor"}, {"$ref": f"{C}/parameters/Limit"}]
    op["responses"]["200"]["content"]["application/json"]["schema"]["properties"] = {
        "data": {"type": "array", "items": {"type": "object"}}, "meta": {"$ref": f"{C}/schemas/ListMeta"}}
    return op


def admin_get() -> dict:
    op = get_item(path_param="tenantId")
    op["operationId"] = "fixtureAdminGet"
    op["security"] = [{"platformOperator": []}]
    op["x-audit-event-required"] = True
    op["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["meta"] = {
        "type": "object", "required": ["traceId", "tenantId", "targetTenantId"],
        "properties": {"traceId": {"type": "string"}, "tenantId": {"type": "null"}, "targetTenantId": {"type": "string"}}}
    return op


def document(paths: dict) -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "fixture", "version": "1.0.0",
                 "license": {"name": "Proprietary", "identifier": "LicenseRef-AutoReliance-Proprietary"}},
        "servers": [{"url": "https://gateway.autoreliance.example"}],
        "tags": [{"name": "fixture", "description": "fixture"}],
        "security": [{"tenantPrincipal": ["auditor"]}],
        "paths": paths,
        "components": {"securitySchemes": {
            "tenantPrincipal": {"$ref": f"{C}/securitySchemes/tenantPrincipal"},
            "platformOperator": {"$ref": f"{C}/securitySchemes/platformOperator"}}},
    }


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "openapi"
        (self.dir / "common").mkdir(parents=True)
        shutil.copy2(OPENAPI / "common" / "components.yaml", self.dir / "common" / "components.yaml")

    def tearDown(self):
        self._tmp.cleanup()

    def lint(self, paths: dict, name: str = "data-readiness.yaml") -> list[str]:
        path = self.dir / name
        path.write_text(yaml.safe_dump(document(paths), sort_keys=False), encoding="utf-8")
        return ol.lint_document(path) + ol.lint_ai_labels(ol.Resolver(), path)

    def assertRule(self, problems: list[str], rule: str):
        self.assertTrue(any(p.startswith(rule + ":") for p in problems), f"expected {rule}; got {problems}")


# ------------------------------------------------------------------------------------------- tests

class RepositoryContracts(unittest.TestCase):
    def test_every_context_has_its_openapi_file(self):
        for context in CONTEXTS:
            with self.subTest(context=context):
                self.assertTrue((OPENAPI / f"{context}.yaml").is_file())
        for extra in ("release-assurance-sidecar.yaml", "admin.yaml", "gateway.yaml"):
            self.assertTrue((OPENAPI / extra).is_file(), extra)

    def test_repository_passes_the_repository_lint(self):
        self.assertEqual(ol.lint_all(), [])

    def test_admin_yaml_passes_the_lint(self):
        self.assertEqual(ol.lint_document(OPENAPI / "admin.yaml"), [])

    def test_admin_yaml_holds_exactly_the_phase_1_admin_operations(self):
        doc = yaml.safe_load((OPENAPI / "admin.yaml").read_text(encoding="utf-8"))
        ops = {(m, p) for p, item in doc["paths"].items() for m in item if m in ol.HTTP_METHODS}
        self.assertEqual(ops, {("get", "/admin/v1/layout/{tenantId}"), ("get", "/admin/v1/layout-cache/{tenantId}")})
        self.assertTrue(doc["paths"]["/admin/v1/layout-cache/{tenantId}"]["get"]["x-internal-only"])

    def test_no_operation_between_data_readiness_and_legacy_integration(self):
        """ADR-008, ADR-024: neither file declares a server or an operation for the other context."""
        for name, other in (("legacy-integration.yaml", "data-readiness"), ("data-readiness.yaml", "legacy-integration")):
            doc = yaml.safe_load((OPENAPI / name).read_text(encoding="utf-8"))
            with self.subTest(file=name):
                for server in doc.get("servers", []):
                    self.assertNotIn(other, server["url"])
                for path in doc["paths"]:
                    self.assertFalse(path.startswith(f"/api/v1/{other}/"), path)
                text = (OPENAPI / name).read_text(encoding="utf-8")
                self.assertNotRegex(text.lower(), r"operationid:\s*\S*(extract|ingest)\S*text")
        li = yaml.safe_load((OPENAPI / "legacy-integration.yaml").read_text(encoding="utf-8"))
        for path, item in li["paths"].items():
            for method in ("post", "put", "patch", "delete"):
                self.assertNotIn(method, item, f"legacy-integration exposes {method.upper()} {path}")

    def test_no_tenant_property_in_any_request(self):
        problems = [p for p in ol.lint_all() if p.startswith("tenant-in-request")]
        self.assertEqual(problems, [])

    def test_every_operation_declares_a_role_except_health_probes(self):
        resolver = ol.Resolver()
        for file in ol.contract_files():
            doc = resolver.load(file)
            for path, method, owner, op, _ in ol.iter_operations(resolver, file):
                with self.subTest(file=file.name, op=f"{method.upper()} {path}"):
                    security = op.get("security", resolver.load(owner).get("security"))
                    if op.get("x-health-check"):
                        self.assertEqual(security, [])
                        self.assertTrue(op.get("x-internal-only"), "a health probe must be internal")
                    else:
                        self.assertTrue(security and any(roles or s == "platformOperator"
                                                         for req in security for s, roles in req.items()))

    def test_ai_outputs_cite_evidence(self):
        resolver = ol.Resolver()
        found = 0
        for file in ol.contract_files():
            doc = resolver.load(file)
            for name, schema in ((doc.get("components") or {}).get("schemas") or {}).items():
                props, required, _ = resolver.flatten(file, schema)
                if "aiGenerated" in props:
                    found += 1
                    self.assertIn("citations", required, f"{file.name} {name}")
        self.assertGreaterEqual(found, 4, "expected the AI outputs of integration, configuration, recommendations, and sidecar")


class RedoclyValidation(unittest.TestCase):
    def test_every_contract_passes_openapi_3_1_validation_with_no_warning(self):
        files = [f"openapi/{p.name}" for p in ol.contract_files()]
        proc = _run_redocly("lint", *files, "--format", "stylish")
        out = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, out)
        self.assertNotIn("You have", out, f"Redocly reported warnings:\n{out}")

    def test_gateway_bundles_without_renamed_or_unresolved_components(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run_redocly("bundle", "openapi/gateway.yaml", "-o", str(Path(tmp) / "bundle.yaml"))
            out = proc.stdout + proc.stderr
            self.assertEqual(proc.returncode, 0, out)
            self.assertNotIn("Renamed", out, out)
            self.assertNotIn("Can't resolve", out, out)

    def test_redocly_rejects_an_invalid_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.yaml"
            bad.write_text("openapi: 3.1.0\ninfo: {title: x}\npaths:\n  /x:\n    get:\n      responses: {}\n", encoding="utf-8")
            proc = _run_redocly("lint", str(bad), "--config", str(CONTRACTS / "redocly.yaml"))
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class GatewayAggregate(unittest.TestCase):
    def test_gateway_yaml_is_up_to_date(self):
        proc = subprocess.run([sys.executable, str(COMPOSER), "--check"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_gateway_routes_every_public_operation_and_no_internal_one(self):
        resolver = ol.Resolver()
        gateway = OPENAPI / "gateway.yaml"
        routed = {(p, m) for p, m, _, op, _ in ol.iter_operations(resolver, gateway)}
        for p, m, _, op, _ in ol.iter_operations(resolver, gateway):
            self.assertNotEqual(op.get("x-internal-only"), True, f"{m} {p} is internal")
        expected = set()
        for name in ("data-readiness.yaml", "legacy-integration.yaml", "integration-intelligence.yaml",
                     "configuration-assurance.yaml", "release-assurance.yaml", "api-gateway.yaml", "admin.yaml"):
            for p, m, _, op, _ in ol.iter_operations(resolver, OPENAPI / name):
                if op.get("x-internal-only") is not True:
                    expected.add((p, m))
        self.assertEqual(routed, expected)
        self.assertIn(("/admin/v1/layout/{tenantId}", "get"), routed)
        self.assertNotIn(("/admin/v1/layout-cache/{tenantId}", "get"), routed)
        self.assertFalse(any(p.endswith("/health") or "/internal/" in p for p, _ in routed))


class OperatorRouteLint(FixtureCase):
    """The api-standards.md rule: tenantId in a path parameter is forbidden unless the route path starts with
    /admin/; any /admin/ route MUST declare platformOperator and x-audit-event-required."""

    def test_admin_layout_route_with_scheme_and_extension_passes(self):
        self.assertEqual(self.lint({"/admin/v1/layout/{tenantId}": {"get": admin_get()}}, "admin.yaml"), [])

    def test_rule_matches_the_admin_prefix_not_a_hardcoded_layout_path(self):
        self.assertEqual(self.lint({"/admin/v1/other/{tenantId}": {"get": admin_get()}}, "admin.yaml"), [])

    def test_admin_route_without_the_platform_operator_scheme_fails(self):
        op = admin_get()
        op["security"] = [{"tenantPrincipal": ["auditor"]}]
        self.assertRule(self.lint({"/admin/v1/layout/{tenantId}": {"get": op}}, "admin.yaml"), "admin-route")

    def test_admin_route_with_no_security_fails(self):
        op = admin_get()
        del op["security"]
        doc_problems = self.lint({"/admin/v1/layout/{tenantId}": {"get": op}}, "admin.yaml")
        self.assertRule(doc_problems, "admin-route")

    def test_admin_route_without_the_audit_extension_fails(self):
        op = admin_get()
        del op["x-audit-event-required"]
        self.assertRule(self.lint({"/admin/v1/layout/{tenantId}": {"get": op}}, "admin.yaml"), "admin-route")

    def test_unversioned_admin_route_fails(self):
        self.assertRule(self.lint({"/admin/layout/{tenantId}": {"get": admin_get()}}, "admin.yaml"), "base-path")

    def test_tenant_path_parameter_outside_admin_fails(self):
        op = get_item(path_param="tenantId")
        self.assertRule(self.lint({"/api/v1/data-readiness/x/{tenantId}": {"get": op}}), "tenant-path")

    def test_api_v1_route_with_tenant_id_fails(self):
        op = get_item(path_param="tenantId")
        self.assertRule(self.lint({"/api/v1/x/{tenantId}": {"get": op}}), "tenant-path")

    def test_platform_operator_on_a_tenant_route_fails(self):
        op = get_item()
        op["security"] = [{"platformOperator": []}]
        self.assertRule(self.lint({"/api/v1/data-readiness/x": {"get": op}}), "role")


class TenantInRequestLint(FixtureCase):
    def test_tenant_query_parameter_fails(self):
        for name in ("tenantId", "tenant_id", "tenant", "X-Tenant-Id"):
            with self.subTest(name=name):
                op = get_item()
                op["parameters"] = [{"name": name, "in": "header" if name.startswith("X-") else "query",
                                     "schema": {"type": "string"}}]
                self.assertRule(self.lint({"/api/v1/data-readiness/x": {"get": op}}), "tenant-in-request")

    def test_tenant_field_in_a_nested_request_body_fails(self):
        op = get_item()
        op["requestBody"] = {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "properties": {"filter": {"allOf": [{"type": "object",
                                                                   "properties": {"tenantId": {"type": "string"}}}]}}}}}}
        op["responses"].update(errors("413"))
        self.assertRule(self.lint({"/api/v1/data-readiness/x": {"post": op}}), "tenant-in-request")

    def test_tenant_id_in_a_response_is_allowed(self):
        self.assertEqual(self.lint({"/api/v1/data-readiness/x": {"get": get_item()}}), [])


class StandardsLint(FixtureCase):
    def test_valid_fixtures_pass(self):
        self.assertEqual(self.lint({"/api/v1/data-readiness/items": {"get": list_items()},
                                    "/api/v1/data-readiness/items/{itemId}": {"get": get_item(path_param="itemId")}}), [])

    def test_path_outside_the_context_base_path_fails(self):
        for path in ("/items", "/api/v2/data-readiness/items", "/api/v1/release-assurance/items"):
            with self.subTest(path=path):
                self.assertRule(self.lint({path: {"get": get_item()}}), "base-path")

    def test_offset_or_page_parameter_fails(self):
        for name in ("offset", "page", "pageSize"):
            with self.subTest(name=name):
                op = list_items()
                op["parameters"].append({"name": name, "in": "query", "schema": {"type": "integer"}})
                self.assertRule(self.lint({"/api/v1/data-readiness/items": {"get": op}}), "pagination")

    def test_list_without_cursor_and_limit_fails(self):
        op = list_items()
        op["parameters"] = []
        self.assertRule(self.lint({"/api/v1/data-readiness/items": {"get": op}}), "pagination")

    def test_list_without_next_cursor_fails(self):
        op = list_items()
        op["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["meta"] = {"$ref": f"{C}/schemas/Meta"}
        self.assertRule(self.lint({"/api/v1/data-readiness/items": {"get": op}}), "pagination")

    def test_success_without_the_envelope_fails(self):
        op = get_item()
        op["responses"]["200"]["content"]["application/json"]["schema"] = {"type": "object", "properties": {"id": {"type": "string"}}}
        self.assertRule(self.lint({"/api/v1/data-readiness/x": {"get": op}}), "envelope")

    def test_error_that_is_not_problem_json_fails(self):
        op = get_item()
        op["responses"]["403"] = {"description": "no", "content": {"application/json": {"schema": {"type": "object"}}}}
        self.assertRule(self.lint({"/api/v1/data-readiness/x": {"get": op}}), "problem")

    def test_problem_without_correlation_id_fails(self):
        op = get_item()
        op["responses"]["400"] = {"description": "bad", "content": {"application/problem+json": {"schema": {
            "type": "object", "required": ["type", "title", "status"]}}}}
        self.assertRule(self.lint({"/api/v1/data-readiness/x": {"get": op}}), "problem")

    def test_missing_error_responses_fail(self):
        for code in ("400", "401", "403", "504"):
            with self.subTest(code=code):
                op = get_item()
                del op["responses"][code]
                self.assertRule(self.lint({"/api/v1/data-readiness/x": {"get": op}}), "error-set")
        op = get_item(path_param="itemId")
        del op["responses"]["404"]
        self.assertRule(self.lint({"/api/v1/data-readiness/x/{itemId}": {"get": op}}), "error-set")

    def test_operation_without_a_role_fails(self):
        for security in ([], [{"tenantPrincipal": []}], [{"tenantPrincipal": ["superuser"]}]):
            with self.subTest(security=security):
                op = get_item()
                op["security"] = security
                self.assertRule(self.lint({"/api/v1/data-readiness/x": {"get": op}}), "role")

    def test_ai_output_without_citations_fails(self):
        self.lint({"/api/v1/data-readiness/x": {"get": get_item()}})
        path = self.dir / "data-readiness.yaml"
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc["components"]["schemas"] = {"Recommendation": {"type": "object", "required": ["aiGenerated"],
                                                            "properties": {"aiGenerated": {"const": True}}}}
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")
        self.assertRule(ol.lint_ai_labels(ol.Resolver(), path), "ai-labels")

    def test_duplicate_operation_id_fails(self):
        a = self.dir / "data-readiness.yaml"
        b = self.dir / "legacy-integration.yaml"
        a.write_text(yaml.safe_dump(document({"/api/v1/data-readiness/x": {"get": get_item()}})), encoding="utf-8")
        b.write_text(yaml.safe_dump(document({"/api/v1/legacy-integration/x": {"get": get_item()}})), encoding="utf-8")
        problems = ol.lint_operation_ids(ol.Resolver(), [a, b])
        self.assertTrue(any(p.startswith("operation-id:") for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
