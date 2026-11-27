"""Repository lint rules for contracts/proto that buf's built-in rules do not express (task 2.3).

1. Package per directory: contracts/proto/<context>/ must declare package autoreliance.<package>.v<N>,
   where <package> is the api-standards.md short name of the context.
2. Every rpc request message has a field `string tenant_id = 1;` (api-standards.md, Req 7.9).

The parser is intentionally small: it understands top-level `package`, `service`/`rpc`, and `message`
blocks, which is all the Phase 1 contracts use. Unparseable input is reported as a violation, so a
construct the parser does not understand fails closed instead of passing.
"""
from __future__ import annotations

import re
from pathlib import Path

# Bounded context directory -> package short name (design: "API standards" / gRPC).
CONTEXT_PACKAGES = {
    "configuration-assurance": "configuration",
    "integration-intelligence": "integration",
}

PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z0-9_.]+)\s*;", re.M)
RPC_RE = re.compile(r"\brpc\s+(\w+)\s*\(\s*(stream\s+)?([\w.]+)\s*\)\s*returns\s*\(\s*(stream\s+)?([\w.]+)\s*\)")
MESSAGE_START_RE = re.compile(r"\bmessage\s+(\w+)\s*\{")
TENANT_FIELD_RE = re.compile(r"^\s*string\s+tenant_id\s*=\s*1\s*;", re.M)


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _message_bodies(text: str) -> dict[str, str]:
    """Top-level message name -> body (text between its braces)."""
    bodies: dict[str, str] = {}
    for match in MESSAGE_START_RE.finditer(text):
        depth, i = 1, match.end()
        while depth and i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        if depth:
            raise ValueError(f"unbalanced braces in message {match.group(1)}")
        bodies.setdefault(match.group(1), text[match.end():i - 1])
    return bodies


def lint_text(context_dir: str, text: str, filename: str = "<text>") -> list[str]:
    """Return a list of violations for one .proto file in contracts/proto/<context_dir>/."""
    problems: list[str] = []
    code = _strip_comments(text)
    short = CONTEXT_PACKAGES.get(context_dir)
    if short is None:
        problems.append(f"{filename}: directory {context_dir!r} has no package mapping in proto_lint.CONTEXT_PACKAGES")
    packages = PACKAGE_RE.findall(code)
    if len(packages) != 1:
        problems.append(f"{filename}: expected exactly one package statement, found {len(packages)}")
    elif short is not None and not re.fullmatch(rf"autoreliance\.{re.escape(short)}\.v[1-9][0-9]*", packages[0]):
        problems.append(f"{filename}: package {packages[0]!r} does not match autoreliance.{short}.v<N>")
    try:
        bodies = _message_bodies(code)
    except ValueError as exc:
        return problems + [f"{filename}: {exc}"]
    rpcs = RPC_RE.findall(code)
    if "service" in code and not rpcs:
        problems.append(f"{filename}: service without a parseable rpc")
    for name, _, request, _, _ in rpcs:
        request = request.rsplit(".", 1)[-1]
        body = bodies.get(request)
        if body is None:
            problems.append(f"{filename}: rpc {name} request {request} is not defined in this file")
        elif not TENANT_FIELD_RE.search(body):
            problems.append(f"{filename}: request message {request} has no `string tenant_id = 1;`")
    return problems


def lint_tree(proto_root: Path) -> list[str]:
    problems: list[str] = []
    files = sorted(proto_root.rglob("*.proto"))
    if not files:
        problems.append(f"{proto_root}: no .proto files")
    for path in files:
        rel = path.relative_to(proto_root)
        if len(rel.parts) != 2:
            problems.append(f"{rel.as_posix()}: proto files live directly in contracts/proto/<context>/")
            continue
        problems += lint_text(rel.parts[0], path.read_text(encoding="utf-8"), rel.as_posix())
    return problems
