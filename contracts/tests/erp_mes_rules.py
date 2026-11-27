"""Cross-field rules of the four ERP and MES topics that a JSON Schema cannot express (task 2.9, ADR-016).

Reference implementation of the producer-side checks of the legacy-integration connectors (task 7.2) and the
consumer-side checks of data-readiness (task 6.13):

  content-hash   contentHash is the SHA-256 (lowercase hex) of the RFC 8785 canonical JSON of payload.
  natural-key    the first naturalKey segment is sourceSystem, and the topic-specific segments equal the
                 ACL-mapped payload fields named in each contract's naturalKey description. Segments are trimmed,
                 case preserved, and percent-encoded for | and %.
  event-id       eventId is the UUIDv5 named by x-event-id in the contract.

RFC 8785 (JSON Canonicalization Scheme) here: object members sorted by the UTF-16 code units of their names, no
insignificant whitespace, strings escaped as in RFC 8785 section 3.2.2.2, and integers in shortest decimal form.
The Phase 1 payloads contain no fractional numbers; canonical_json() rejects a float rather than guess the
ECMAScript number serialization, so a payload change that introduces one fails these tests until the
implementation is extended.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from functools import lru_cache

import contract_lib as cl

TOPICS = ("erp.masterdata.changed", "erp.purchaseorder.updated", "mes.workorder.reported", "mes.quality.inspection.recorded")


def _escape(text: str) -> str:
    # json.dumps with ensure_ascii=False escapes exactly ", \, and control characters, using \b \f \n \r \t and
    # \u00XX (lowercase hex) for the rest, which is the RFC 8785 string form.
    return json.dumps(text, ensure_ascii=False)


def canonical_json(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ValueError("canonical_json: fractional numbers are not supported (no Phase 1 payload has one)")
    if isinstance(value, str):
        return _escape(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(_escape(k) + ":" + canonical_json(value[k]) for k in keys) + "}"
    raise TypeError(f"canonical_json: unsupported type {type(value).__name__}")


def content_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@lru_cache(maxsize=None)
def _event_id_rule(topic: str) -> tuple[uuid.UUID, str]:
    rule = cl.load_yaml(cl.ASYNCAPI_DIR / f"{topic}.yaml")["info"]["x-event-id"]
    return uuid.UUID(rule["namespace"]), rule["name"]


def event_id(event: dict) -> str:
    namespace, template = _event_id_rule(event["eventType"])
    return str(uuid.uuid5(namespace, template.format(**{k: event[k] for k in
                                                         ("tenantId", "eventType", "naturalKey", "contentHash", "extractedAt")})))


def encode_segment(value: str) -> str:
    return value.strip().replace("%", "%25").replace("|", "%7C")


def natural_key(topic: str, source_system: str, payload: dict, source_columns: dict | None = None) -> list[str]:
    """Expected naturalKey segments; None for a segment that comes from a source column the payload does not carry."""
    cols = source_columns or {}
    if topic == "erp.masterdata.changed":
        kind = payload["masterDataType"]
        value = payload.get("partNumber") if kind == "part" else payload.get("supplierCode")
        third = cols.get("PLANT_CD") if kind == "part" else cols.get("COMPANY_CD")
        return [source_system, kind, value, third]
    if topic == "erp.purchaseorder.updated":
        return [source_system, payload["purchaseOrderNumber"]]
    if topic == "mes.workorder.reported":
        return [source_system, payload["plant"], payload["workOrderNumber"]]
    if topic == "mes.quality.inspection.recorded":
        return [source_system, cols.get("PLANT_CD"), payload["inspectionId"]]
    raise KeyError(topic)


def semantic_errors(event: dict) -> list[str]:
    """Return the cross-field rule violations of a schema-valid ERP or MES event."""
    topic = event["eventType"]
    errors: list[str] = []
    expected_hash = content_hash(event["payload"])
    if event["contentHash"] != expected_hash:
        errors.append(f"content-hash: contentHash is not the SHA-256 of the RFC 8785 canonical payload ({expected_hash})")
    segments = event["naturalKey"].split("|")
    expected = natural_key(topic, event["sourceSystem"], event["payload"])
    if len(segments) != len(expected):
        errors.append(f"natural-key: {len(segments)} segments, expected {len(expected)}")
    else:
        for i, (actual, value) in enumerate(zip(segments, expected)):
            if value is not None and actual != encode_segment(value):
                errors.append(f"natural-key: segment {i + 1} is {actual!r}, expected {encode_segment(value)!r}")
    expected_id = event_id(event)
    if event["eventId"] != expected_id:
        errors.append(f"event-id: eventId is not the UUIDv5 of (tenantId, eventType, naturalKey, contentHash, extractedAt) ({expected_id})")
    return errors


def finalize(event: dict) -> dict:
    """Return a copy of event with contentHash and eventId recomputed (for building fixtures)."""
    event = json.loads(json.dumps(event))
    event["contentHash"] = content_hash(event["payload"])
    event["eventId"] = event_id(event)
    return event
