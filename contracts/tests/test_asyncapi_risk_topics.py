"""Contract tests for the three domain-prefixed risk topics (task 2.2, ADR-001).

integration.risk.scored, configuration.risk.scored, and release.risk.scored each have their own AsyncAPI file
with file-local schemas. AsyncAPI CLI validation of the three files runs in test_asyncapi_contracts.py
(AsyncApiCliValidation, every document), and their golden examples run in its GoldenExamples test.

    python -m unittest discover -s contracts/tests -p "test_asyncapi*.py" -v
"""
from __future__ import annotations

import unittest

import contract_lib as cl

RISK_TOPICS = ("integration.risk.scored", "configuration.risk.scored", "release.risk.scored")
RISK_FILES = {t: cl.ASYNCAPI_DIR / f"{t}.yaml" for t in RISK_TOPICS}
SHARED_HEADER_SCHEMA = "KafkaHeaders"  # a copy of common/envelope.yaml KafkaHeaders, checked below


def _strip_descriptions(node):
    if isinstance(node, dict):
        return {k: _strip_descriptions(v) for k, v in node.items() if k != "description"}
    if isinstance(node, list):
        return [_strip_descriptions(v) for v in node]
    return node


def _payload(topic: str) -> dict:
    path = RISK_FILES[topic]
    doc = cl.load_yaml(path)
    envelope = next(s for n, s in doc["components"]["schemas"].items() if n.endswith("Envelope"))
    _, payload = cl.deref(path, envelope["properties"]["payload"])
    return payload


class RiskTopicFiles(unittest.TestCase):
    def test_the_three_files_are_asyncapi_documents_with_golden_examples(self):
        documents = {p.name for p in cl.asyncapi_documents()}
        goldens = {p.stem for p in cl.golden_files()}
        for topic in RISK_TOPICS:
            with self.subTest(topic=topic):
                self.assertIn(f"{topic}.yaml", documents)
                self.assertIn(topic, goldens)
                self.assertEqual(cl.load_yaml(RISK_FILES[topic])["asyncapi"], "3.0.0")

    def test_each_file_defines_its_own_payload_schema(self):
        for topic, path in RISK_FILES.items():
            doc = cl.load_yaml(path)
            with self.subTest(topic=topic):
                envelope = next(s for n, s in doc["components"]["schemas"].items() if n.endswith("Envelope"))
                ref = envelope["properties"]["payload"]["$ref"]
                self.assertTrue(ref.startswith("#/components/schemas/"), f"payload must be file-local, got {ref}")

    def test_no_ref_crosses_between_the_three_files(self):
        names = {p.name for p in RISK_FILES.values()}
        for topic, path in RISK_FILES.items():
            for pointer, ref in cl.iter_refs(cl.load_yaml(path)):
                file_part = ref.partition("#")[0]
                with self.subTest(topic=topic, at=pointer):
                    self.assertEqual(file_part, "", f"{path.name} references another file: {ref}")
                    self.assertNotIn(file_part.split("/")[-1], names)

    def test_no_schema_name_is_defined_in_more_than_one_file(self):
        seen: dict[str, str] = {}
        for topic, path in RISK_FILES.items():
            for name in cl.load_yaml(path)["components"]["schemas"]:
                if name == SHARED_HEADER_SCHEMA:
                    continue
                with self.subTest(schema=name):
                    self.assertNotIn(name, seen, f"{name} is defined in {seen.get(name)} and {topic}")
                    seen[name] = topic

    def test_the_header_copies_equal_the_shared_header_schema(self):
        shared = cl.load_yaml(cl.COMMON_DIR / "envelope.yaml")["components"]["schemas"][SHARED_HEADER_SCHEMA]
        for topic, path in RISK_FILES.items():
            with self.subTest(topic=topic):
                local = cl.load_yaml(path)["components"]["schemas"][SHARED_HEADER_SCHEMA]
                self.assertEqual(_strip_descriptions(local), _strip_descriptions(shared))

    def test_the_inline_envelopes_equal_the_shared_base_envelope(self):
        base = cl.load_yaml(cl.COMMON_DIR / "envelope.yaml")["components"]["schemas"]["BaseEnvelope"]
        expected = _strip_descriptions({k: v for k, v in base["properties"].items() if k not in ("eventType", "version", "payload")})
        for topic, path in RISK_FILES.items():
            doc = cl.load_yaml(path)
            envelope = next(s for n, s in doc["components"]["schemas"].items() if n.endswith("Envelope"))
            with self.subTest(topic=topic):
                self.assertEqual(envelope["required"], base["required"])
                self.assertIs(envelope["additionalProperties"], False)
                self.assertEqual(set(envelope["properties"]), set(base["properties"]))
                actual = _strip_descriptions({k: v for k, v in envelope["properties"].items() if k in expected})
                self.assertEqual(actual, expected)
                self.assertEqual(envelope["properties"]["eventType"], {"type": "string", "const": topic})
                self.assertEqual(envelope["properties"]["version"], {"type": "integer", "const": 1})


class RiskPayloadRules(unittest.TestCase):
    def test_every_risk_payload_bounds_the_score_and_requires_citations(self):
        for topic in RISK_TOPICS:
            payload = _payload(topic)
            with self.subTest(topic=topic):
                self.assertIs(payload["additionalProperties"], False)
                self.assertIn("score", payload["required"])
                self.assertEqual((payload["properties"]["score"]["minimum"], payload["properties"]["score"]["maximum"]), (0, 100))
                self.assertIn("citations", payload["required"])
                self.assertGreaterEqual(payload["properties"]["citations"]["minItems"], 1)

    def test_integration_and_configuration_scores_are_estimates_requiring_review(self):
        for topic in ("integration.risk.scored", "configuration.risk.scored"):
            payload = _payload(topic)
            with self.subTest(topic=topic):
                for label in ("estimate", "requiresHumanReview"):
                    self.assertIn(label, payload["required"])
                    self.assertEqual(payload["properties"][label]["const"], True)

    def test_configuration_score_has_per_rule_factors_rule_set_version_and_rule_result_citations(self):
        payload = _payload("configuration.risk.scored")
        self.assertIn("ruleSetVersion", payload["required"])
        _, factor = cl.deref(RISK_FILES["configuration.risk.scored"], payload["properties"]["ruleFactors"]["items"])
        self.assertLessEqual({"ruleResultId", "status", "weight", "contribution"}, set(factor["required"]))
        self.assertEqual(payload["properties"]["citations"]["contains"]["properties"]["type"]["const"], "rule-result")

    def test_release_score_is_decision_support_only(self):
        payload = _payload("release.risk.scored")
        self.assertIn("decisionSupportOnly", payload["required"])
        self.assertEqual(payload["properties"]["decisionSupportOnly"]["const"], True)
        self.assertIn("unavailableInputs", payload["required"])


class RiskTopicOperations(unittest.TestCase):
    def _operations(self):
        for doc in cl.asyncapi_documents():
            for _, file, op, _ in cl.operations(doc):
                address = cl.operation_address(file, op)
                if address in RISK_TOPICS:
                    yield doc, file, op, address

    def test_each_topic_has_exactly_its_producer(self):
        producers = {"integration.risk.scored": "integration-intelligence",
                     "configuration.risk.scored": "configuration-assurance",
                     "release.risk.scored": "release-assurance"}
        for topic, path in RISK_FILES.items():
            sends = [op for _, file, op, _ in cl.operations(path) if op["action"] == "send"]
            with self.subTest(topic=topic):
                self.assertEqual(len(sends), 1)
                self.assertEqual(sends[0]["x-owner-context"], producers[topic])

    def test_the_only_receivers_are_release_assurance_on_integration_and_configuration(self):
        for doc, file, op, address in self._operations():
            if op["action"] != "receive":
                continue
            with self.subTest(document=doc.name, topic=address):
                self.assertIn(address, ("integration.risk.scored", "configuration.risk.scored"))
                self.assertEqual(op["x-owner-context"], "release-assurance")
                self.assertEqual(cl.operation_group(op), "release-assurance-evidence")

    def test_release_risk_scored_has_no_receive_anywhere(self):
        self.assertFalse(any(op["action"] == "receive" for _, _, op, _ in cl.operations(RISK_FILES["release.risk.scored"])))
        for doc, file, op, address in self._operations():
            if address == "release.risk.scored":
                with self.subTest(document=doc.name):
                    self.assertEqual(op["action"], "send")

    def test_integration_and_configuration_each_have_one_release_assurance_receiver(self):
        for topic in ("integration.risk.scored", "configuration.risk.scored"):
            receives = [op for _, _, op, _ in cl.operations(RISK_FILES[topic]) if op["action"] == "receive"]
            with self.subTest(topic=topic):
                self.assertEqual(len(receives), 1)
                self.assertEqual(receives[0]["x-dead-letter-topic"], "dlt.release-assurance-evidence")


if __name__ == "__main__":
    unittest.main()
