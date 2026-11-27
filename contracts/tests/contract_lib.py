"""Helpers for the AsyncAPI contract tests (task 2.1).

Loads the AsyncAPI documents under contracts/asyncapi/, resolves `$ref` pointers across files, and
builds JSON Schema validators for message payloads. Message payloads use the AsyncAPI default schema
format, a superset of JSON Schema draft-07, so payloads are validated with Draft7Validator.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from jsonschema import Draft7Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

CONTRACTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CONTRACTS_DIR.parent
ASYNCAPI_DIR = CONTRACTS_DIR / "asyncapi"
COMMON_DIR = ASYNCAPI_DIR / "common"

# The seven Phase 1 contexts. Each has contracts/asyncapi/<context>.yaml.
CONTEXTS = (
    "data-readiness",
    "legacy-integration",
    "integration-intelligence",
    "configuration-assurance",
    "release-assurance",
    "api-gateway",
    "audit-sink",
)

# Topics with a file of their own (contracts/asyncapi/<topic>.yaml).
PER_TOPIC_FILES = (
    "integration.risk.scored",
    "configuration.risk.scored",
    "release.risk.scored",
    "document.text.extracted",
    "erp.masterdata.changed",
    "erp.purchaseorder.updated",
    "mes.workorder.reported",
    "mes.quality.inspection.recorded",
)

# The five legacy-integration source topics that use the source-ingestion envelope (ADR-017).
SOURCE_INGESTION_TOPICS = (
    "document.text.extracted",
    "erp.masterdata.changed",
    "erp.purchaseorder.updated",
    "mes.workorder.reported",
    "mes.quality.inspection.recorded",
)

# Topic naming (api-standards.md): <domain>.<entity>.<action>, lowercase, with exactly the documented
# exceptions: dlt.<consumer-group-id> dead-letter topics and the four-segment names approved as written
# (the Phase 2+ ones are reserved and have no channel in Phase 1).
TOPIC_NAME_RULE = re.compile(r"^[a-z][a-z0-9]*\.[a-z][a-z0-9]*\.[a-z][a-z0-9]*$")
DLT_NAME_RULE = re.compile(r"^dlt\.[a-z][a-z0-9]*(-[a-z0-9]+)*$")
NAMED_TOPIC_EXCEPTIONS = frozenset({
    "mes.quality.inspection.recorded",
    "release.evidence.gap.detected",
    "quality.failure.cluster.detected",
    "dealer.service.event.recorded",
    "ota.release.risk.scored",
})


def topic_name_ok(name: str) -> bool:
    """True when the topic name follows api-standards.md or is a documented exception."""
    return bool(TOPIC_NAME_RULE.match(name) or DLT_NAME_RULE.match(name) or name in NAMED_TOPIC_EXCEPTIONS)


@lru_cache(maxsize=None)
def load_yaml(path: Path) -> dict:
    with Path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def asyncapi_documents() -> list[Path]:
    """Every AsyncAPI document (top-level YAML files in contracts/asyncapi/, not common/)."""
    return sorted(p for p in ASYNCAPI_DIR.glob("*.yaml") if "asyncapi" in (load_yaml(p) or {}))


def common_files() -> list[Path]:
    return sorted(COMMON_DIR.glob("*.yaml"))


def is_ref(node) -> bool:
    return isinstance(node, dict) and set(node) == {"$ref"}


def iter_refs(node, pointer: str = ""):
    """Yield (json pointer of the $ref, ref string) for every $ref in a document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield pointer, value
            else:
                yield from iter_refs(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from iter_refs(value, f"{pointer}/{i}")


def iter_schema_keys(node, pointer: str = ""):
    """Yield (pointer, property name) for every key of every `properties` map in a document."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for prop in value:
                    yield f"{pointer}/properties", prop
            yield from iter_schema_keys(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from iter_schema_keys(value, f"{pointer}/{i}")


def resolve_ref(base_file: Path, ref: str, _depth: int = 0) -> tuple[Path, str, object]:
    """Resolve a $ref relative to base_file. Returns (file, pointer, target). Raises KeyError/FileNotFoundError.

    A pointer may pass through a node that is itself a whole-object $ref (for example a channel that
    references another file); the walk follows it, as an AsyncAPI parser does.
    """
    if _depth > 20:
        raise RecursionError(f"$ref chain too deep at {ref!r} in {base_file}")
    file_part, _, pointer = ref.partition("#")
    file = (base_file.parent / file_part).resolve() if file_part else base_file
    if not file.is_file():
        raise FileNotFoundError(f"{base_file.name}: $ref {ref!r} points to a missing file {file}")
    node = load_yaml(file)
    for part in [p for p in pointer.split("/") if p]:
        if is_ref(node):
            file, _, node = resolve_ref(file, node["$ref"], _depth + 1)
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return file, pointer, node


def deref(base_file: Path, node, max_depth: int = 20) -> tuple[Path, object]:
    """Follow a chain of whole-object $refs. Returns (file the final object lives in, object)."""
    file = base_file
    for _ in range(max_depth):
        if not is_ref(node):
            return file, node
        file, _, node = resolve_ref(file, node["$ref"])
    raise RecursionError(f"$ref chain too deep in {base_file}")


def channels(doc_path: Path):
    """Yield (channel key, defining file, channel object, is_local) for the channels of a document."""
    doc = load_yaml(doc_path)
    for key, value in (doc.get("channels") or {}).items():
        file, channel = deref(doc_path, value)
        yield key, file, channel, not is_ref(value)


def operations(doc_path: Path):
    """Yield (operation key, defining file, operation object, is_local) for the operations of a document."""
    doc = load_yaml(doc_path)
    for key, value in (doc.get("operations") or {}).items():
        file, op = deref(doc_path, value)
        yield key, file, op, not is_ref(value)


def operation_address(op_file: Path, op: dict) -> str:
    _, channel = deref(op_file, op["channel"])
    return channel["address"]


def operation_group(op: dict) -> str | None:
    try:
        return op["bindings"]["kafka"]["groupId"]["enum"][0]
    except (KeyError, IndexError, TypeError):
        return None


# ---------------------------------------------------------------------------------- payload validation

_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _is_date_time(value) -> bool:
    # jsonschema checks date-time only with an extra package; this stdlib check keeps the pinned set small.
    if not isinstance(value, str):
        return True
    if not _RFC3339.match(value):
        return False
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return True


def _retrieve(uri: str) -> Resource:
    path = unquote(urlparse(uri).path)
    if re.match(r"^/[A-Za-z]:", path):  # file:///C:/... on Windows
        path = path[1:]
    return Resource.from_contents(load_yaml(Path(path)), default_specification=DRAFT7)


@lru_cache(maxsize=None)
def payload_validator(doc_file: str, message_key: str) -> Draft7Validator:
    """Validator for the payload of components.messages.<message_key> in doc_file (a contracts/asyncapi name)."""
    path = ASYNCAPI_DIR / doc_file
    message = load_yaml(path)["components"]["messages"][message_key]
    payload_ref = message["payload"]["$ref"]
    file_part, _, pointer = payload_ref.partition("#")
    target = (path.parent / file_part).resolve() if file_part else path.resolve()
    schema = {"$ref": f"{target.as_uri()}#{pointer}"}
    registry = Registry(retrieve=_retrieve)
    return Draft7Validator(schema, registry=registry, format_checker=FORMAT_CHECKER)


def errors_for(doc_file: str, message_key: str, instance) -> list[str]:
    validator = payload_validator(doc_file, message_key)
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in validator.iter_errors(instance)]


# ---------------------------------------------------------------------------------- golden examples

def _split_path(path: str) -> list:
    return [int(p) if p.isdigit() else p for p in path.split(".")]


def apply_mutation(base, mutation: dict):
    """Return a deep copy of base with the mutation applied: `remove` (list of paths) and `set` (path: value)."""
    value = copy.deepcopy(base)
    for path in mutation.get("remove", []):
        *parents, last = _split_path(path)
        node = value
        for p in parents:
            node = node[p]
        del node[last]
    for path, new in (mutation.get("set") or {}).items():
        *parents, last = _split_path(path)
        node = value
        for p in parents:
            node = node[p]
        node[last] = copy.deepcopy(new)
    return value


def golden_files() -> list[Path]:
    return sorted((Path(__file__).parent / "golden").glob("*.yaml"))
