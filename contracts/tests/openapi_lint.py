"""Repository lint for the OpenAPI contracts in contracts/openapi/ (task 2.4).

Redocly CLI validates OpenAPI 3.1 structure. This module enforces the API standards of api-standards.md and
security.md, which need path context and cross-file $ref resolution:

  tenant-path         tenantId in a path parameter is forbidden unless the route path starts with /admin/.
  admin-route         Any route whose path starts with /admin/ MUST declare the platform-operator security
                      scheme (platformOperator) and the audit-event-required extension (x-audit-event-required).
  base-path           Every path starts with /api/v1/<context>/ for the file's context, or /admin/v1/.
  tenant-in-request   No tenant ID in a query, header, or cookie parameter or in any request body field.
  role                Every operation except a health probe declares a role; tenant roles are the six roles of
                      Req 12.8; platformOperator appears only on /admin/ routes.
  problem             Every 4xx and 5xx response is application/problem+json with a correlationId member.
  error-set           Every operation except a health probe answers 400, 401 and 403; 504 when the gateway routes
                      it (not x-internal-only); 404 when a path parameter names a resource (any path parameter
                      without an enum); 413 when it has a request body.
  envelope            Every 2xx JSON response of a non-health operation is { data, meta } with meta.traceId and
                      meta.tenantId (admin routes: meta.tenantId null and meta.targetTenantId).
  pagination          A response whose data is an array is a list: the operation takes cursor and limit and
                      meta has nextCursor. No offset or page parameter exists anywhere.
  ai-labels           Every schema with aiGenerated requires aiGenerated, requiresHumanReview, a non-empty
                      citations list, and decisionSupportStatement (Req 18.4, 18.6).
  operation-id        operationIds are unique across all contracts.

lint_document() returns a list of "rule: location: message" strings; an empty list means the file passes.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

OPENAPI_DIR = Path(__file__).resolve().parents[1] / "openapi"
HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
TENANT_ROLES = frozenset({
    "release-manager", "firmware-engineer", "configuration-engineer", "data-engineer", "auditor", "tenant-administrator",
})
TENANT_PARAM_NAMES = re.compile(r"^(x-)?tenant([-_]?id)?$", re.I)
TENANT_IN_PATH = re.compile(r"\{tenant", re.I)
PAGING_PARAM_NAMES = re.compile(r"^(offset|page|pagenumber|page_number|pagesize|page_size|skip)$", re.I)
# Contexts of each contract file: its routes live under /api/v1/<context>/ for one of them.
# api-gateway.yaml serves the audit query under /api/v1/audit/ and its own internal health probe under
# /api/v1/api-gateway/ (task 1.1).
FILE_CONTEXTS = {
    "data-readiness.yaml": ("data-readiness",),
    "legacy-integration.yaml": ("legacy-integration",),
    "integration-intelligence.yaml": ("integration-intelligence",),
    "configuration-assurance.yaml": ("configuration-assurance",),
    "release-assurance.yaml": ("release-assurance",),
    "release-assurance-sidecar.yaml": ("release-assurance",),
    "api-gateway.yaml": ("audit", "api-gateway"),
    "audit-sink.yaml": ("audit",),
}
ALL_CONTEXTS = frozenset(c for cs in FILE_CONTEXTS.values() for c in cs)


class Resolver:
    """Loads YAML files and resolves $ref pointers relative to the file that contains them."""

    def __init__(self):
        self._cache: dict[Path, dict] = {}

    def load(self, path: Path) -> dict:
        path = path.resolve()
        if path not in self._cache:
            with path.open(encoding="utf-8") as fh:
                self._cache[path] = yaml.safe_load(fh)
        return self._cache[path]

    def resolve(self, file: Path, node, depth: int = 0):
        """Follow whole-object $refs. Returns (file, node)."""
        while isinstance(node, dict) and "$ref" in node and len(node) <= 2 and depth < 25:
            ref = node["$ref"]
            file_part, _, pointer = ref.partition("#")
            target = (file.parent / file_part).resolve() if file_part else file
            if not target.is_file():
                raise KeyError(f"$ref {ref!r} in {file.name} points to a missing file")
            node = self.load(target)
            for part in [p for p in pointer.split("/") if p]:
                node = self.resolve(target, node, depth + 1)[1]
                node = node[part.replace("~1", "/").replace("~0", "~")]
            file = target
            depth += 1
        return file, node

    def flatten(self, file: Path, schema) -> tuple[dict, set[str], list]:
        """Merge an object schema across $ref and allOf: (properties as (file, schema) pairs, required, oneOf/anyOf branches)."""
        file, schema = self.resolve(file, schema)
        props: dict[str, tuple[Path, object]] = {}
        required: set[str] = set()
        branches: list = []
        if not isinstance(schema, dict):
            return props, required, branches
        for name, sub in (schema.get("properties") or {}).items():
            props[name] = (file, sub)
        required |= set(schema.get("required") or [])
        for part in schema.get("allOf") or []:
            p, r, b = self.flatten(file, part)
            props.update(p)
            required |= r
            branches += b
        for key in ("oneOf", "anyOf"):
            branches += [(file, b) for b in schema.get(key) or []]
        return props, required, branches


def _schema_contains_tenant(resolver: Resolver, file: Path, schema, seen: set) -> list[str]:
    """Property paths under schema whose name is a tenant identifier."""
    file, schema = resolver.resolve(file, schema)
    key = (file, id(schema))
    if key in seen or not isinstance(schema, dict):
        return []
    seen.add(key)
    hits = []
    props, _, branches = resolver.flatten(file, schema)
    for name, (pfile, sub) in props.items():
        if TENANT_PARAM_NAMES.match(name):
            hits.append(name)
        hits += [f"{name}.{h}" for h in _schema_contains_tenant(resolver, pfile, sub, seen)]
    for bfile, branch in branches:
        hits += _schema_contains_tenant(resolver, bfile, branch, seen)
    if "items" in schema:
        hits += [f"[].{h}" for h in _schema_contains_tenant(resolver, file, schema["items"], seen)]
    if isinstance(schema.get("additionalProperties"), dict):
        hits += _schema_contains_tenant(resolver, file, schema["additionalProperties"], seen)
    return hits


def _effective_security(doc: dict, op: dict):
    return op["security"] if "security" in op else doc.get("security")


def iter_operations(resolver: Resolver, doc_file: Path):
    """Yield (path, method, owner file, operation, path-item parameters) for every operation of a document."""
    doc = resolver.load(doc_file)
    for path, item in (doc.get("paths") or {}).items():
        item_file, item = resolver.resolve(doc_file, item)
        for method in HTTP_METHODS:
            if method in item:
                yield path, method, item_file, item[method], item.get("parameters", [])


def lint_document(doc_file: Path, resolver: Resolver | None = None) -> list[str]:
    resolver = resolver or Resolver()
    doc_file = doc_file.resolve()
    doc = resolver.load(doc_file)
    problems: list[str] = []
    contexts = FILE_CONTEXTS.get(doc_file.name) or ()
    if doc.get("openapi") != "3.1.0":
        problems.append(f"openapi-version: {doc_file.name}: openapi must be 3.1.0")

    for path in (doc.get("paths") or {}):
        where = f"{doc_file.name} {path}"
        admin = path.startswith("/admin/")
        if TENANT_IN_PATH.search(path) and not admin:
            problems.append(f"tenant-path: {where}: tenantId in a path parameter is forbidden unless the route path starts with /admin/")
        if admin:
            if not path.startswith("/admin/v1/") and not re.match(r"^/admin/v[1-9][0-9]*/", path):
                problems.append(f"base-path: {where}: admin routes are versioned as /admin/v<N>/<resource>")
        elif doc_file.name == "gateway.yaml":
            if not any(path.startswith(f"/api/v1/{c}/") for c in ALL_CONTEXTS):
                problems.append(f"base-path: {where}: must start with /api/v1/<context>/")
        elif not any(path.startswith(f"/api/v1/{c}/") for c in contexts):
            allowed = " or ".join(f"/api/v1/{c}/" for c in contexts) or "/api/v1/<context>/"
            problems.append(f"base-path: {where}: must start with {allowed}")

    for path, method, owner, op, item_params in iter_operations(resolver, doc_file):
        where = f"{doc_file.name} {method.upper()} {path}"
        admin = path.startswith("/admin/")
        health = op.get("x-health-check") is True
        params = []
        for raw in list(item_params) + list(op.get("parameters") or []):
            params.append(resolver.resolve(owner, raw)[1])

        # tenant identifiers in the request
        for p in params:
            if p.get("in") == "path" and TENANT_PARAM_NAMES.match(p.get("name", "")) and not admin:
                problems.append(f"tenant-path: {where}: path parameter {p['name']} outside /admin/")
            if p.get("in") in ("query", "header", "cookie") and TENANT_PARAM_NAMES.match(p.get("name", "")):
                problems.append(f"tenant-in-request: {where}: {p['in']} parameter {p['name']} carries a tenant ID")
            if PAGING_PARAM_NAMES.match(p.get("name", "")):
                problems.append(f"pagination: {where}: parameter {p['name']} is offset or page style; use cursor and limit")
        body = op.get("requestBody")
        if body is not None:
            body_file, body = resolver.resolve(owner, body)
            for media, content in (body.get("content") or {}).items():
                for hit in _schema_contains_tenant(resolver, body_file, content.get("schema", {}), set()):
                    problems.append(f"tenant-in-request: {where}: request body ({media}) field {hit} carries a tenant ID")

        # admin route contract
        security = _effective_security(doc if owner == doc_file else resolver.load(owner), op)
        if admin:
            if op.get("x-audit-event-required") is not True:
                problems.append(f"admin-route: {where}: /admin/ routes MUST declare x-audit-event-required: true")
            if not security or not any("platformOperator" in req for req in security):
                problems.append(f"admin-route: {where}: /admin/ routes MUST declare the platformOperator security scheme")
            if security and any(set(req) - {"platformOperator"} for req in security):
                problems.append(f"admin-route: {where}: /admin/ routes accept only platformOperator")
        # roles
        if not health:
            if not security:
                problems.append(f"role: {where}: operation declares no security requirement")
            for req in security or []:
                for scheme, roles in req.items():
                    if scheme == "tenantPrincipal":
                        if not roles:
                            problems.append(f"role: {where}: tenantPrincipal requirement lists no role")
                        bad = set(roles) - TENANT_ROLES
                        if bad:
                            problems.append(f"role: {where}: unknown roles {sorted(bad)}")
                    elif scheme == "platformOperator":
                        if not admin:
                            problems.append(f"role: {where}: platformOperator is only valid on /admin/ routes")
                    else:
                        problems.append(f"role: {where}: unknown security scheme {scheme}")

        # responses
        responses = op.get("responses") or {}
        codes = set(map(str, responses))
        if not health:
            required_codes = {"400", "401", "403"}
            if op.get("x-internal-only") is not True:
                required_codes.add("504")  # a gateway timeout; internal routes are not behind the gateway
            for p in params:
                if p.get("in") != "path":
                    continue
                schema = resolver.resolve(owner, p.get("schema", {}))[1]
                if not (isinstance(schema, dict) and "enum" in schema):
                    required_codes.add("404")  # the parameter names a resource that may not exist (or be another tenant's)
            if body is not None:
                required_codes.add("413")
            missing = sorted(required_codes - codes)
            if missing:
                problems.append(f"error-set: {where}: missing error responses {missing}")
        for code, response in responses.items():
            rfile, response = resolver.resolve(owner, response)
            content = response.get("content") or {}
            code = str(code)
            if code[0] in "45":
                if set(content) != {"application/problem+json"}:
                    problems.append(f"problem: {where} {code}: error responses must be application/problem+json only")
                    continue
                props, required, _ = resolver.flatten(rfile, content["application/problem+json"].get("schema", {}))
                for field in ("type", "title", "status", "correlationId"):
                    if field not in required:
                        problems.append(f"problem: {where} {code}: Problem Details must require {field}")
            elif code[0] == "2" and content and not health:
                if "application/json" not in content:
                    problems.append(f"envelope: {where} {code}: success responses are application/json")
                    continue
                props, required, _ = resolver.flatten(rfile, content["application/json"].get("schema", {}))
                if not {"data", "meta"} <= required:
                    problems.append(f"envelope: {where} {code}: success body must be {{ data, meta }}")
                    continue
                mfile, meta = props["meta"]
                meta_props, meta_req, _ = resolver.flatten(mfile, meta)
                for field in ("traceId", "tenantId"):
                    if field not in meta_req:
                        problems.append(f"envelope: {where} {code}: meta must require {field}")
                if admin and "targetTenantId" not in meta_req:
                    problems.append(f"envelope: {where} {code}: admin meta must require targetTenantId")
                dfile, data = resolver.resolve(*props["data"])
                if isinstance(data, dict) and data.get("type") == "array":
                    names = {p.get("name") for p in params if p.get("in") == "query"}
                    if not {"cursor", "limit"} <= names:
                        problems.append(f"pagination: {where}: list operation must take cursor and limit")
                    if "nextCursor" not in meta_req:
                        problems.append(f"pagination: {where}: list meta must require nextCursor")
    return problems


def lint_ai_labels(resolver: Resolver, file: Path) -> list[str]:
    """Every component schema that declares aiGenerated carries the full AI label set."""
    problems = []
    doc = resolver.load(file)
    for name, schema in ((doc.get("components") or {}).get("schemas") or {}).items():
        props, required, _ = resolver.flatten(file, schema)
        if "aiGenerated" in props or "aiGenerated" in required:
            for field in ("aiGenerated", "requiresHumanReview", "citations", "decisionSupportStatement"):
                if field not in required:
                    problems.append(f"ai-labels: {file.name} {name}: AI output must require {field}")
            if "citations" in props:
                cfile, citations = resolver.resolve(*props["citations"])
                if not isinstance(citations, dict) or citations.get("minItems", 0) < 1:
                    problems.append(f"ai-labels: {file.name} {name}: citations must have minItems 1")
    return problems


def lint_operation_ids(resolver: Resolver, files: list[Path]) -> list[str]:
    seen: dict[str, str] = {}
    problems = []
    for file in files:
        for path, method, owner, op, _ in iter_operations(resolver, file):
            if owner.resolve() != file.resolve():
                continue  # referenced from another file; counted there
            op_id = op.get("operationId")
            where = f"{file.name} {method.upper()} {path}"
            if not op_id:
                problems.append(f"operation-id: {where}: missing operationId")
            elif op_id in seen:
                problems.append(f"operation-id: {where}: operationId {op_id} is also used by {seen[op_id]}")
            else:
                seen[op_id] = where
    return problems


def contract_files() -> list[Path]:
    return sorted(p for p in OPENAPI_DIR.glob("*.yaml") if (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("openapi"))


def lint_all() -> list[str]:
    resolver = Resolver()
    files = contract_files()
    problems = []
    for file in files:
        problems += lint_document(file, resolver)
        problems += lint_ai_labels(resolver, file)
    problems += lint_operation_ids(resolver, files)
    return problems
