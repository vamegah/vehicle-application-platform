"""Contract tests for the four ERP and MES topics (task 2.9, ADR-011, ADR-016, ADR-017).

Schema-level golden examples run in test_asyncapi_contracts.py (GoldenExamples); the golden files are generated
by build_erp_mes_golden.py. This module covers the cross-field rules (erp_mes_rules.py), RFC 8785 canonical JSON,
the eventId derivation, the envelope, the operations, schema independence, and the retired names.

    python -m unittest discover -s contracts/tests -p "test_asyncapi*.py" -v
"""
from __future__ import annotations

import copy
import subprocess
import sys
import unittest
from pathlib import Path

import contract_lib as cl
import erp_mes_rules as rules

FILES = {t: cl.ASYNCAPI_DIR / f"{t}.yaml" for t in rules.TOPICS}
GROUPS = {
    "erp.masterdata.changed": "data-readiness-erp-masterdata",
    "erp.purchaseorder.updated": "data-readiness-erp-purchaseorder",
    "mes.workorder.reported": "data-readiness-mes-workorder",
    "mes.quality.inspection.recorded": "data-readiness-mes-quality",
}
RETIRED_KEY_FIELD = "sourceNatural" + "KeyHash"


def _golden(topic: str) -> dict:
    return cl.load_yaml(next(p for p in cl.golden_files() if p.stem == topic))


def _first_valid(topic: str) -> dict:
    return copy.deepcopy(next(iter(_golden(topic)["valid"].values())))


def _envelope(topic: str) -> dict:
    schemas = cl.load_yaml(FILES[topic])["components"]["schemas"]
    return next(s for n, s in schemas.items() if n.endswith("Envelope"))


class CanonicalJson(unittest.TestCase):
    def test_members_are_sorted_by_utf16_code_units_without_whitespace(self):
        # RFC 8785 sorts by UTF-16 code units: "\u20ac" (U+20AC) sorts before "\ud83d\ude00" (U+1F600, surrogate
        # D83D), although by code point it would sort after.
        value = {"b": 1, "a": [True, None, "x"], "\U0001F600": 2, "\u20ac": 3, "A": {"z": 0, "y": -1}}
        self.assertEqual(rules.canonical_json(value),
                         '{"A":{"y":-1,"z":0},"a":[true,null,"x"],"b":1,"\u20ac":3,"\U0001F600":2}')

    def test_strings_escape_only_what_rfc_8785_escapes(self):
        self.assertEqual(rules.canonical_json('q"b\\\n\t\u0001\u00e9/'), '"q\\"b\\\\\\n\\t\\u0001\u00e9/"')

    def test_fractional_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            rules.canonical_json({"quantity": 1.5})

    def test_content_hash_ignores_member_order(self):
        self.assertEqual(rules.content_hash({"a": 1, "b": 2}), rules.content_hash({"b": 2, "a": 1}))
        self.assertNotEqual(rules.content_hash({"a": 1}), rules.content_hash({"a": 2}))


class CrossFieldRules(unittest.TestCase):
    def assertRule(self, event: dict, rule: str):
        topic = event["eventType"]
        self.assertEqual(cl.errors_for(FILES[topic].name, _golden(topic)["message"], event), [],
                         "fixture must stay schema-valid so only the cross-field rule fails")
        errors = rules.semantic_errors(event)
        self.assertTrue(any(e.startswith(rule + ":") for e in errors), f"expected {rule}; got {errors}")

    def test_every_golden_valid_sample_passes(self):
        for topic in rules.TOPICS:
            for name, event in _golden(topic)["valid"].items():
                with self.subTest(topic=topic, sample=name):
                    self.assertEqual(rules.semantic_errors(event), [])

    def test_a_changed_payload_without_a_new_content_hash_fails(self):
        event = _first_valid("erp.purchaseorder.updated")
        event["payload"]["lines"][0]["quantityDelivered"] = 300
        self.assertRule(event, "content-hash")

    def test_natural_key_segments_must_equal_the_payload_fields(self):
        cases = {
            "erp.masterdata.changed": "FIC-ERP|part|FIC-PN-999999|FIC-PLANT-01",
            "erp.purchaseorder.updated": "FIC-ERP|FIC-PO-00000",
            "mes.workorder.reported": "FIC-MES|FIC-PLANT-02|FIC-WO-30001",
            "mes.quality.inspection.recorded": "FIC-MES|FIC-PLANT-01|FIC-INSP-0000",
        }
        for topic, key in cases.items():
            with self.subTest(topic=topic):
                event = _first_valid(topic)
                event["naturalKey"] = key
                event = rules.finalize(event)
                self.assertRule(event, "natural-key")

    def test_natural_key_first_segment_must_be_the_source_system(self):
        event = _first_valid("mes.workorder.reported")
        event["naturalKey"] = "FIC-OTHER|FIC-PLANT-01|FIC-WO-30001"
        self.assertRule(rules.finalize(event), "natural-key")

    def test_natural_key_segments_are_percent_encoded(self):
        payload = {"purchaseOrderNumber": " PO|50%  "}
        self.assertEqual(rules.natural_key("erp.purchaseorder.updated", "FIC-ERP", payload)[1], " PO|50%  ")
        self.assertEqual(rules.encode_segment(" PO|50%  "), "PO%7C50%25")

    def test_event_id_must_follow_the_contract_rule(self):
        event = _first_valid("mes.quality.inspection.recorded")
        event["eventId"] = "11111111-2222-4333-8444-555555555555"
        self.assertRule(event, "event-id")


class EventIds(unittest.TestCase):
    def test_same_key_gives_the_same_event_id(self):
        event = _first_valid("erp.masterdata.changed")
        self.assertEqual(rules.event_id(event), rules.event_id(copy.deepcopy(event)))
        self.assertEqual(rules.event_id(event), event["eventId"])

    def test_changing_natural_key_content_hash_or_extracted_at_changes_the_event_id(self):
        base = _first_valid("erp.masterdata.changed")
        for field, value in (("naturalKey", "FIC-ERP|part|FIC-PN-000124|FIC-PLANT-01"), ("contentHash", "0" * 64),
                             ("extractedAt", "2026-11-26T07:30:00Z")):
            with self.subTest(field=field):
                changed = dict(base, **{field: value})
                self.assertNotEqual(rules.event_id(changed), rules.event_id(base))

    def test_an_a_b_a_revert_gets_a_new_event_id(self):
        """Without extractedAt in the name, a record changed A to B and back to A would be dropped as a duplicate."""
        a = _first_valid("erp.purchaseorder.updated")
        later = dict(a, extractedAt="2026-11-27T07:04:58Z")
        self.assertNotEqual(rules.event_id(a), rules.event_id(later))

    def test_the_four_topics_never_share_an_event_id_for_the_same_fields(self):
        base = _first_valid("erp.purchaseorder.updated")
        ids = {rules.event_id(dict(base, eventType=t)) for t in rules.TOPICS}
        self.assertEqual(len(ids), 4)

    def test_all_four_contracts_use_the_same_rule(self):
        rules_seen = {repr(cl.load_yaml(p)["info"]["x-event-id"]) for p in FILES.values()}
        self.assertEqual(len(rules_seen), 1)
        rule = cl.load_yaml(FILES["erp.masterdata.changed"])["info"]["x-event-id"]
        self.assertEqual(rule["name"], "{tenantId}|{eventType}|{naturalKey}|{contentHash}|{extractedAt}")


class ErpMesContracts(unittest.TestCase):
    def test_golden_files_are_generated_and_up_to_date(self):
        proc = subprocess.run([sys.executable, str(Path(__file__).with_name("build_erp_mes_golden.py")), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for topic in rules.TOPICS:
            golden = _golden(topic)
            with self.subTest(topic=topic):
                self.assertTrue(any("sourceRecordVersion" not in e for e in golden["valid"].values()),
                                "a valid sample without sourceRecordVersion is required")

    def test_envelope_is_base_plus_source_ingestion_with_optional_record_version(self):
        common = cl.load_yaml(cl.COMMON_DIR / "envelope.yaml")["components"]["schemas"]
        base, source = common["BaseEnvelope"], common["SourceIngestionFields"]
        for topic in rules.TOPICS:
            envelope = _envelope(topic)
            with self.subTest(topic=topic):
                self.assertEqual(set(envelope["properties"]), set(base["properties"]) | set(source["properties"]))
                self.assertEqual(set(envelope["required"]), set(base["required"]) | set(source["required"]))
                self.assertNotIn("sourceRecordVersion", envelope["required"])
                self.assertEqual(envelope["properties"]["sourceRecordVersion"]["minimum"], 1)
                self.assertIs(envelope["additionalProperties"], False)

    def test_natural_key_composition_is_documented(self):
        for topic in rules.TOPICS:
            description = " ".join(_envelope(topic)["properties"]["naturalKey"]["description"].split())
            with self.subTest(topic=topic):
                self.assertIn("Composition: <sourceSystem>|", description)
                self.assertIn("segment equals payload.", description)

    def test_ordering_rule_is_stated_in_each_contract(self):
        for topic in rules.TOPICS:
            text = " ".join(cl.load_yaml(FILES[topic])["info"]["description"].split())
            with self.subTest(topic=topic):
                self.assertIn("use sourceRecordVersion when", text)
                self.assertIn("otherwise compare extractedAt", text)
                self.assertIn("is a no-op", text)

    def test_one_send_by_legacy_integration_and_one_receive_by_data_readiness(self):
        for topic, path in FILES.items():
            ops = [op for _, _, op, _ in cl.operations(path)]
            with self.subTest(topic=topic):
                self.assertEqual(sorted(op["action"] for op in ops), ["receive", "send"])
                send = next(op for op in ops if op["action"] == "send")
                receive = next(op for op in ops if op["action"] == "receive")
                self.assertEqual(send["x-owner-context"], "legacy-integration")
                self.assertEqual(receive["x-owner-context"], "data-readiness")
                self.assertEqual(cl.operation_group(receive), GROUPS[topic])
                self.assertEqual(receive["x-dead-letter-topic"], f"dlt.{GROUPS[topic]}")

    def test_partition_key_is_tenant_and_natural_key(self):
        for topic, path in FILES.items():
            doc = cl.load_yaml(path)
            message = next(iter(doc["components"]["messages"].values()))
            with self.subTest(topic=topic):
                self.assertEqual(message["bindings"]["kafka"]["key"]["description"], '"{tenantId}:{naturalKey}"')

    def test_no_schema_or_ref_is_shared_with_another_source_topic(self):
        files = dict(FILES, **{"document.text.extracted": cl.ASYNCAPI_DIR / "document.text.extracted.yaml"})
        seen: dict[str, str] = {}
        for topic, path in files.items():
            doc = cl.load_yaml(path)
            for pointer, ref in cl.iter_refs(doc):
                with self.subTest(topic=topic, at=pointer):
                    self.assertTrue(ref.startswith("#/"), f"{path.name} references another file: {ref}")
            for name in doc["components"]["schemas"]:
                if name == "KafkaHeaders":
                    continue  # identical copy of common/envelope.yaml KafkaHeaders, checked by EnvelopeRules
                with self.subTest(schema=name):
                    self.assertNotIn(name, seen, f"{name} is defined for {seen.get(name)} and {topic}")
                    seen[name] = topic

    def test_no_contract_carries_the_retired_hash_based_key_field(self):
        for path in cl.ASYNCAPI_DIR.rglob("*.yaml"):
            with self.subTest(file=path.name):
                self.assertNotIn(RETIRED_KEY_FIELD, path.read_text(encoding="utf-8"))

    def test_no_source_record_extracted_anywhere_in_contracts(self):
        retired = "source.record." + "extracted"
        for path in cl.CONTRACTS_DIR.rglob("*"):
            if path.is_file() and "node_modules" not in path.parts and path.suffix in (".yaml", ".yml", ".json", ".proto"):
                with self.subTest(file=str(path.relative_to(cl.CONTRACTS_DIR))):
                    self.assertNotIn(retired, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
