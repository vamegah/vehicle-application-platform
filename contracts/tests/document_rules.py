"""Cross-field rules of document.text.extracted that a JSON Schema cannot express (task 2.8).

This is the reference implementation of the producer-side and consumer-side checks the contract describes:
the legacy-integration producer (task 7.5) must refuse to publish, and the data-readiness consumer (task 6.12)
must route to dlt.data-readiness-document, any event for which semantic_errors() is not empty.

Rules:
  content-hash      envelope contentHash equals payload.contentSha256.
  natural-key       the first segment of naturalKey equals sourceSystem (percent-encoded with | and %).
  raw-uri-tenant    the tenant in the objectStoreUri key prefix equals the envelope tenantId; under the dedicated
                    layout (bucket autoreliance-raw-<env>-<tenantId>) the bucket tenant equals it too.
  raw-uri-key       the objectStoreUri key names payload.canonicalDocumentId and payload.contentSha256.
  text-uri-tenant   the same tenant rules for textUri.
  text-uri-key      the textUri key names payload.canonicalDocumentId and payload.textSha256.
  layout            objectStoreUri and textUri use the same layout (both shared or both dedicated) and the same env.
  inline-text       when extractedText is present, textSizeBytes equals its UTF-8 size and textSha256 its SHA-256.
  event-id          eventId is the UUIDv5 named by x-event-id in the contract.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from functools import lru_cache

import contract_lib as cl

CONTRACT = cl.ASYNCAPI_DIR / "document.text.extracted.yaml"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
URI_RE = re.compile(
    rf"^s3://autoreliance-(?P<role>raw|text)-(?P<env>[a-z0-9]{{2,8}})(?:-(?P<bucketTenant>{UUID}))?"
    rf"/(?P<keyTenant>{UUID})/(?P<keyRole>raw|text)/documents/(?P<documentId>{UUID})/(?P<sha>[0-9a-f]{{64}})\.(?P<ext>pdf|txt)$"
)


@lru_cache(maxsize=None)
def _identifier_rule(name: str) -> tuple[uuid.UUID, str]:
    rule = cl.load_yaml(CONTRACT)["info"][name]
    return uuid.UUID(rule["namespace"]), rule["name"]


def event_id(tenant_id: str, canonical_document_id: str, content_sha256: str) -> str:
    namespace, template = _identifier_rule("x-event-id")
    name = template.format(tenantId=tenant_id.lower(), canonicalDocumentId=canonical_document_id.lower(),
                           contentSha256=content_sha256.lower())
    return str(uuid.uuid5(namespace, name))


def canonical_document_id(tenant_id: str, source_system: str, source_doc_key: str) -> str:
    namespace, template = _identifier_rule("x-canonical-document-id")
    return str(uuid.uuid5(namespace, template.format(tenantId=tenant_id.lower(), sourceSystem=source_system,
                                                       sourceDocKey=source_doc_key)))


def encode_segment(value: str) -> str:
    """naturalKey segment encoding: trimmed, case preserved, % and | percent-encoded."""
    return value.strip().replace("%", "%25").replace("|", "%7C")


def _uri_errors(label: str, uri: str, tenant: str, document_id: str, sha: str) -> tuple[list[str], dict | None]:
    match = URI_RE.match(uri or "")
    if not match:
        return [f"{label}-uri-key: {uri!r} does not have the documented form"], None
    parts = match.groupdict()
    errors = []
    if parts["keyTenant"] != tenant:
        errors.append(f"{label}-uri-tenant: key tenant {parts['keyTenant']} differs from envelope tenantId {tenant}")
    if parts["bucketTenant"] is not None and parts["bucketTenant"] != tenant:
        errors.append(f"{label}-uri-tenant: dedicated bucket tenant {parts['bucketTenant']} differs from envelope tenantId {tenant}")
    if parts["role"] != label or parts["keyRole"] != label:
        errors.append(f"{label}-uri-key: {uri!r} is not a {label} location")
    if parts["documentId"] != document_id:
        errors.append(f"{label}-uri-key: key document {parts['documentId']} differs from canonicalDocumentId {document_id}")
    if parts["sha"] != sha:
        errors.append(f"{label}-uri-key: key hash differs from the payload hash")
    return errors, parts


def semantic_errors(event: dict) -> list[str]:
    """Return the cross-field rule violations of a schema-valid document.text.extracted event."""
    errors: list[str] = []
    payload = event["payload"]
    tenant = event["tenantId"]
    if event["contentHash"] != payload["contentSha256"]:
        errors.append("content-hash: envelope contentHash differs from payload.contentSha256")
    first = event["naturalKey"].split("|", 1)[0]
    if first != encode_segment(event["sourceSystem"]):
        errors.append("natural-key: the first naturalKey segment differs from sourceSystem")
    raw_errors, raw = _uri_errors("raw", payload["objectStoreUri"], tenant, payload["canonicalDocumentId"], payload["contentSha256"])
    errors += raw_errors
    if "textUri" in payload:
        text_errors, text = _uri_errors("text", payload["textUri"], tenant, payload["canonicalDocumentId"], payload["textSha256"])
        errors += text_errors
        if raw and text:
            if (raw["bucketTenant"] is None) != (text["bucketTenant"] is None):
                errors.append("layout: objectStoreUri and textUri use different layouts")
            if raw["env"] != text["env"]:
                errors.append("layout: objectStoreUri and textUri name different environments")
    if "extractedText" in payload:
        data = payload["extractedText"].encode("utf-8")
        if payload["textSizeBytes"] != len(data):
            errors.append("inline-text: textSizeBytes differs from the UTF-8 size of extractedText")
        if payload["textSha256"] != hashlib.sha256(data).hexdigest():
            errors.append("inline-text: textSha256 differs from the SHA-256 of extractedText")
    expected = event_id(tenant, payload["canonicalDocumentId"], payload["contentSha256"])
    if event["eventId"] != expected:
        errors.append(f"event-id: eventId {event['eventId']} is not the UUIDv5 of the idempotency key ({expected})")
    return errors
