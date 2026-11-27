"""Contract tests for document.text.extracted (task 2.8, ADR-008, ADR-012, ADR-018).

Schema-level golden examples run in test_asyncapi_contracts.py (GoldenExamples). This module covers the
cross-field rules (document_rules.py), the identifier derivations, the envelope, the operations, and the
retired-topic checks.

    python -m unittest discover -s contracts/tests -p "test_asyncapi*.py" -v
"""
from __future__ import annotations

import copy
import unittest

import contract_lib as cl
import document_rules as dr

CONTRACT = cl.ASYNCAPI_DIR / "document.text.extracted.yaml"
GOLDEN = cl.load_yaml(next(p for p in cl.golden_files() if p.stem == "document.text.extracted"))
OTHER_TENANT = "9f8e7d6c-5b4a-4c3d-8e2f-1a0b9c8d7e6f"


def _sample(name: str) -> dict:
    return copy.deepcopy(GOLDEN["valid"][name])


def _schema_errors(event: dict) -> list[str]:
    return cl.errors_for("document.text.extracted.yaml", "DocumentTextExtracted", event)


class CrossFieldRules(unittest.TestCase):
    def test_every_golden_valid_sample_passes_the_cross_field_rules(self):
        for name in GOLDEN["valid"]:
            with self.subTest(sample=name):
                self.assertEqual(dr.semantic_errors(_sample(name)), [])

    def assertRule(self, event: dict, rule: str):
        self.assertEqual(_schema_errors(event), [], "fixture must stay schema-valid so only the cross-field rule fails")
        errors = dr.semantic_errors(event)
        self.assertTrue(any(e.startswith(rule + ":") for e in errors), f"expected {rule}; got {errors}")

    def test_content_hash_that_differs_from_content_sha256_fails(self):
        event = _sample("inlineShared")
        event["contentHash"] = "0" * 64
        self.assertRule(event, "content-hash")

    def test_raw_key_tenant_must_equal_the_envelope_tenant(self):
        for layout in ("inlineShared", "textUriDedicated"):
            with self.subTest(layout=layout):
                event = _sample(layout)
                event["tenantId"] = OTHER_TENANT
                self.assertRule(event, "raw-uri-tenant")

    def test_dedicated_bucket_tenant_must_equal_the_envelope_tenant(self):
        event = _sample("textUriDedicated")
        tenant = event["tenantId"]
        event["payload"]["objectStoreUri"] = event["payload"]["objectStoreUri"].replace(f"raw-dev-{tenant}", f"raw-dev-{OTHER_TENANT}")
        self.assertRule(event, "raw-uri-tenant")

    def test_text_key_tenant_must_equal_the_envelope_tenant(self):
        for layout in ("textUriShared", "textUriDedicated"):
            with self.subTest(layout=layout):
                event = _sample(layout)
                tenant = event["tenantId"]
                event["payload"]["textUri"] = event["payload"]["textUri"].replace(f"/{tenant}/text/", f"/{OTHER_TENANT}/text/")
                self.assertRule(event, "text-uri-tenant")

    def test_uri_keys_must_name_the_document_and_its_hashes(self):
        event = _sample("textUriShared")
        event["payload"]["textUri"] = event["payload"]["textUri"].replace(event["payload"]["textSha256"], "f" * 64)
        self.assertRule(event, "text-uri-key")
        event = _sample("inlineShared")
        other_doc = "11111111-2222-4333-8444-555555555555"
        event["payload"]["objectStoreUri"] = event["payload"]["objectStoreUri"].replace(event["payload"]["canonicalDocumentId"], other_doc)
        self.assertRule(event, "raw-uri-key")

    def test_raw_and_text_locations_use_one_layout(self):
        event = _sample("textUriDedicated")
        shared = _sample("textUriShared")
        event["payload"]["objectStoreUri"] = shared["payload"]["objectStoreUri"]
        self.assertRule(event, "layout")

    def test_inline_text_size_and_hash_must_match_the_text(self):
        event = _sample("inlineShared")
        event["payload"]["textSizeBytes"] = 97
        self.assertRule(event, "inline-text")
        event = _sample("inlineShared")
        event["payload"]["extractedText"] += " changed"
        self.assertRule(event, "inline-text")

    def test_inline_byte_limit_counts_utf8_bytes_not_characters(self):
        # 40,000 two-byte characters fit the 65,536-character maxLength but are 80,000 bytes: the producer must use
        # textUri. The schema rejects the declared textSizeBytes, and a lying textSizeBytes fails the cross-field rule.
        event = _sample("inlineShared")
        event["payload"]["extractedText"] = "\u00e9" * 40000
        event["payload"]["textSizeBytes"] = 80000
        self.assertNotEqual(_schema_errors(event), [])
        event["payload"]["textSizeBytes"] = 40000
        self.assertTrue(any(e.startswith("inline-text:") for e in dr.semantic_errors(event)))

    def test_natural_key_first_segment_must_be_the_source_system(self):
        event = _sample("inlineShared")
        event["naturalKey"] = "FIC-OTHER|specs/FIC-BRAKE-ECU-spec-v4.pdf"
        self.assertRule(event, "natural-key")

    def test_event_id_must_be_the_uuidv5_of_the_idempotency_key(self):
        event = _sample("inlineShared")
        event["eventId"] = "8ef910c1-eee1-4984-a121-593a231b73db"
        self.assertRule(event, "event-id")


class Identifiers(unittest.TestCase):
    TENANT = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
    DOC = "607cdc4a-fadb-5321-8722-39301687815b"
    SHA = "efa06ec78455c1c966fd055aa5bdc448e87da81cbe55c980e2e51a7c1edade81"

    def test_event_id_is_deterministic_for_the_same_key(self):
        self.assertEqual(dr.event_id(self.TENANT, self.DOC, self.SHA), dr.event_id(self.TENANT, self.DOC, self.SHA))
        self.assertEqual(dr.event_id(self.TENANT.upper(), self.DOC, self.SHA.upper()), dr.event_id(self.TENANT, self.DOC, self.SHA))

    def test_a_revised_document_gets_a_new_event_id(self):
        self.assertNotEqual(dr.event_id(self.TENANT, self.DOC, self.SHA), dr.event_id(self.TENANT, self.DOC, "0" * 64))
        self.assertNotEqual(dr.event_id(self.TENANT, self.DOC, self.SHA), dr.event_id(Identifiers.OTHER, self.DOC, self.SHA))

    OTHER = OTHER_TENANT

    def test_event_id_and_canonical_document_id_are_version_5_uuids(self):
        self.assertEqual(dr.event_id(self.TENANT, self.DOC, self.SHA)[14], "5")
        self.assertEqual(dr.canonical_document_id(self.TENANT, "FIC-DMS", "specs/a.pdf")[14], "5")

    def test_golden_canonical_document_id_follows_the_contract_rule(self):
        event = _sample("inlineShared")
        source_doc_key = event["naturalKey"].split("|", 1)[1]
        self.assertEqual(dr.canonical_document_id(event["tenantId"], event["sourceSystem"], source_doc_key),
                         event["payload"]["canonicalDocumentId"])

    def test_the_two_identifier_rules_use_different_namespaces(self):
        info = cl.load_yaml(CONTRACT)["info"]
        self.assertNotEqual(info["x-event-id"]["namespace"], info["x-canonical-document-id"]["namespace"])
        self.assertEqual(info["x-event-id"]["name"], "{tenantId}|{canonicalDocumentId}|{contentSha256}")


class DocumentTopicContract(unittest.TestCase):
    def setUp(self):
        self.doc = cl.load_yaml(CONTRACT)
        self.envelope = self.doc["components"]["schemas"]["DocumentTextExtractedEnvelope"]

    def test_envelope_is_the_base_envelope_plus_the_source_ingestion_extension_without_record_version(self):
        common = cl.load_yaml(cl.COMMON_DIR / "envelope.yaml")["components"]["schemas"]
        base, source = common["BaseEnvelope"], common["SourceIngestionFields"]
        expected = set(base["properties"]) | set(source["properties"]) - {"sourceRecordVersion"}
        self.assertEqual(set(self.envelope["properties"]), expected)
        self.assertEqual(set(self.envelope["required"]), set(base["required"]) | set(source["required"]))
        self.assertIs(self.envelope["additionalProperties"], False)
        for field in ("sourceSystem", "contentHash", "extractedAt"):
            for key in ("type", "format", "pattern", "minLength"):
                self.assertEqual(self.envelope["properties"][field].get(key), source["properties"][field].get(key), f"{field}.{key}")

    def test_exactly_one_send_and_one_receive(self):
        ops = [op for _, _, op, _ in cl.operations(CONTRACT)]
        self.assertEqual(sorted(op["action"] for op in ops), ["receive", "send"])
        send = next(op for op in ops if op["action"] == "send")
        receive = next(op for op in ops if op["action"] == "receive")
        self.assertEqual(send["x-owner-context"], "legacy-integration")
        self.assertEqual(send["x-dead-letter-topic"], "dlt.legacy-integration-extraction")
        self.assertEqual(receive["x-owner-context"], "data-readiness")
        self.assertEqual(cl.operation_group(receive), "data-readiness-document")
        self.assertEqual(receive["x-dead-letter-topic"], "dlt.data-readiness-document")

    def test_partition_key_and_message_size(self):
        channel = self.doc["channels"]["documentTextExtracted"]
        self.assertIn("{tenantId}:{canonicalDocumentId}", channel["description"])
        key = self.doc["components"]["messages"]["DocumentTextExtracted"]["bindings"]["kafka"]["key"]["description"]
        self.assertEqual(key, '"{tenantId}:{canonicalDocumentId}"')
        self.assertEqual(channel["bindings"]["kafka"]["topicConfiguration"]["max.message.bytes"], 262144)
        self.assertEqual(self.doc["info"]["x-text-inline-max-bytes"], 65536)

    def test_no_document_extraction_requested_topic_exists(self):
        retired = "document.extraction." + "requested"
        for path in (cl.CONTRACTS_DIR).rglob("*"):
            if path.is_file() and "node_modules" not in path.parts and path.suffix in (".yaml", ".yml", ".json", ".proto"):
                with self.subTest(file=str(path.relative_to(cl.CONTRACTS_DIR))):
                    self.assertNotIn(retired, path.read_text(encoding="utf-8"))
                    self.assertNotIn(retired, path.name)


if __name__ == "__main__":
    unittest.main()
