"""AsyncAPI contract tests for task 2.1.

Run from the repository root (after `npm ci` in contracts/ and installing contracts/tests/requirements.txt):

    python -m unittest discover -s contracts/tests -v

The AsyncAPI CLI validation test fails, and never skips, when the pinned CLI is not installed.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import contract_lib as cl

RETIRED_TOPICS = ("risk.score." + "computed", "source.record." + "extracted")
TRACE_BODY_FIELDS = {"traceparent", "tracestate", "traceContext", "trace_context"}
BASE_FIELDS = ("eventId", "eventType", "version", "tenantId", "occurredAt", "payload")
SOURCE_FIELDS = ("sourceSystem", "naturalKey", "contentHash", "extractedAt", "sourceRecordVersion")


def _cli() -> list[str] | None:
    exe = cl.CONTRACTS_DIR / "node_modules" / ".bin" / ("asyncapi.cmd" if os.name == "nt" else "asyncapi")
    return [str(exe)] if exe.exists() else None


def _local_topics() -> dict[str, tuple[Path, str, dict]]:
    """address -> (defining file, channel key, channel) for every channel defined (not referenced)."""
    found: dict[str, list] = {}
    for doc in cl.asyncapi_documents():
        for key, file, channel, local in cl.channels(doc):
            if local:
                found.setdefault(channel["address"], []).append((file, key, channel))
    return found


class AsyncApiCliValidation(unittest.TestCase):
    def test_every_document_passes_asyncapi_validation(self):
        cli = _cli()
        self.assertIsNotNone(cli, "AsyncAPI CLI not installed: run `npm ci` in contracts/ (pinned @asyncapi/cli)")
        env = dict(os.environ, ASYNCAPI_TELEMETRY="false")
        for doc in cl.asyncapi_documents():
            with self.subTest(document=doc.name):
                proc = subprocess.run(
                    cli + ["validate", str(doc), "--fail-severity", "warn"],
                    cwd=cl.CONTRACTS_DIR, capture_output=True, text=True, env=env,
                )
                self.assertEqual(proc.returncode, 0, f"{doc.name}:\n{proc.stdout}\n{proc.stderr}")


class GoldenExamples(unittest.TestCase):
    def test_golden_files_exist_for_each_new_topic(self):
        names = {p.stem for p in cl.golden_files()}
        for topic in ("vehicle.identity.resolved", "firmware.change.committed", "dependency.impact.computed",
                      "config.validation.completed", "test.result.recorded", "release.evidence.gap.detected",
                      "audit.event.recorded", "dlt.legacy-integration-extraction",
                      "integration.risk.scored", "configuration.risk.scored", "release.risk.scored",
                      "document.text.extracted"):
            self.assertIn(topic, names)

    def test_valid_samples_pass_and_mutations_fail(self):
        for golden in cl.golden_files():
            spec = cl.load_yaml(golden)
            doc, message = spec["doc"], spec["message"]
            for name, sample in spec["valid"].items():
                with self.subTest(golden=golden.stem, valid=name):
                    self.assertEqual(cl.errors_for(doc, message, sample), [])
            self.assertTrue(spec.get("invalid"), f"{golden.name} has no mutated samples")
            for mutation in spec["invalid"]:
                with self.subTest(golden=golden.stem, invalid=mutation["name"]):
                    sample = cl.apply_mutation(spec["valid"][mutation["base"]], mutation)
                    self.assertNotEqual(cl.errors_for(doc, message, sample), [],
                                        f"mutation {mutation['name']!r} was accepted")

    def test_date_time_format_is_checked(self):
        self.assertTrue(cl.FORMAT_CHECKER.conforms("2026-11-26T08:15:00Z", "date-time"))
        self.assertFalse(cl.FORMAT_CHECKER.conforms("2026-11-26 08:15", "date-time"))
        self.assertFalse(cl.FORMAT_CHECKER.conforms("2026-13-40T08:15:00Z", "date-time"))


class EnvelopeRules(unittest.TestCase):
    def setUp(self):
        self.common = cl.load_yaml(cl.COMMON_DIR / "envelope.yaml")["components"]["schemas"]

    def _envelopes(self):
        """(file, channel address, envelope schema) for every domain-event message defined locally."""
        for address, entries in _local_topics().items():
            if address.startswith("dlt."):
                continue
            for file, _, channel in entries:
                for msg_ref in channel["messages"].values():
                    msg_file, msg = cl.deref(file, msg_ref)
                    env_file, env = cl.deref(msg_file, msg["payload"])
                    yield env_file, address, env

    def test_common_file_has_base_envelope_and_source_ingestion_variant(self):
        self.assertEqual(tuple(self.common["BaseEnvelope"]["required"]), BASE_FIELDS)
        self.assertEqual(set(self.common["SourceIngestionFields"]["properties"]), set(SOURCE_FIELDS))
        self.assertEqual(set(self.common["SourceIngestionFields"]["required"]), set(SOURCE_FIELDS) - {"sourceRecordVersion"})

    def test_every_envelope_matches_the_shared_envelope(self):
        base = self.common["BaseEnvelope"]["properties"]
        source = self.common["SourceIngestionFields"]["properties"]
        for file, address, env in self._envelopes():
            with self.subTest(topic=address):
                props = env["properties"]
                self.assertIs(env.get("additionalProperties"), False)
                for field in BASE_FIELDS:
                    self.assertIn(field, env["required"])
                    if field != "payload":
                        self.assertEqual(props[field]["type"], base[field]["type"], field)
                        self.assertEqual(props[field].get("format"), base[field].get("format"), field)
                self.assertEqual(props["eventType"].get("const"), address)
                self.assertIsInstance(props["version"].get("const"), int)
                extra = set(props) - set(BASE_FIELDS)
                if address in cl.SOURCE_INGESTION_TOPICS:
                    self.assertLessEqual(extra, set(SOURCE_FIELDS))
                    for field in ("sourceSystem", "naturalKey", "contentHash", "extractedAt"):
                        self.assertIn(field, env["required"])
                        self.assertEqual(props[field]["type"], source[field]["type"], field)
                    self.assertEqual(props["contentHash"]["pattern"], source["contentHash"]["pattern"])
                    self.assertNotIn("sourceRecordVersion", env["required"])
                else:
                    self.assertEqual(extra, set(), f"{address} adds envelope fields {sorted(extra)}")

    def test_no_schema_version_or_trace_body_field_anywhere(self):
        for path in cl.asyncapi_documents() + cl.common_files():
            for pointer, prop in cl.iter_schema_keys(cl.load_yaml(path)):
                with self.subTest(file=path.name, at=pointer):
                    self.assertNotEqual(prop, "schemaVersion")
                    if "/headers" not in pointer and not pointer.startswith("/components/schemas/KafkaHeaders"):
                        self.assertNotIn(prop, TRACE_BODY_FIELDS)


class TopicNames(unittest.TestCase):
    def test_lint_rule(self):
        self.assertTrue(cl.topic_name_ok("firmware.change.committed"))
        self.assertTrue(cl.topic_name_ok("dlt.release-assurance-evidence"))
        self.assertTrue(cl.topic_name_ok("mes.quality.inspection.recorded"))
        self.assertTrue(cl.topic_name_ok("release.evidence.gap.detected"))
        self.assertFalse(cl.topic_name_ok("erp.quality.inspection.recorded"), "a four-segment fixture must fail")
        self.assertFalse(cl.topic_name_ok("firmware.changeCommitted"))
        self.assertFalse(cl.topic_name_ok("Firmware.Change.Committed"))
        self.assertFalse(cl.topic_name_ok("firmware.change"))

    def test_exception_list_matches_api_standards(self):
        text = (cl.REPO_ROOT / ".kiro" / "steering" / "api-standards.md").read_text(encoding="utf-8")
        for name in cl.NAMED_TOPIC_EXCEPTIONS:
            with self.subTest(exception=name):
                self.assertIn(f"`{name}`", text, f"{name} is excepted by the lint but not documented in api-standards.md")

    def test_every_topic_follows_the_naming_rule(self):
        for address in _local_topics():
            with self.subTest(topic=address):
                self.assertTrue(cl.topic_name_ok(address), f"{address} breaks <domain>.<entity>.<action>")


class ReservedAndRetiredNames(unittest.TestCase):
    def test_reserved_names_have_no_channel_or_operation(self):
        reserved = cl.load_yaml(cl.COMMON_DIR / "reserved-topics.yaml")
        self.assertNotIn("operations", reserved)
        self.assertNotIn("channels", reserved)
        names = {r["name"] for r in reserved["reservedTopics"]}
        self.assertEqual(len(names), 11)
        for doc in cl.asyncapi_documents():
            for _, _, channel, _ in cl.channels(doc):
                with self.subTest(document=doc.name, topic=channel["address"]):
                    self.assertNotIn(channel["address"], names)

    def test_retired_topic_names_appear_nowhere(self):
        roots = [cl.REPO_ROOT / d for d in ("contracts", "services", "libs") if (cl.REPO_ROOT / d).exists()]
        skip = {"node_modules", "tests", "__pycache__", "target", ".venv"}
        for root in roots:
            for path in root.rglob("*"):
                if not path.is_file() or skip & set(path.relative_to(cl.REPO_ROOT).parts):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for retired in RETIRED_TOPICS:
                    with self.subTest(file=str(path.relative_to(cl.REPO_ROOT)), name=retired):
                        self.assertNotIn(retired, text)


class References(unittest.TestCase):
    def test_every_ref_resolves(self):
        for path in cl.asyncapi_documents() + cl.common_files():
            for pointer, ref in cl.iter_refs(cl.load_yaml(path)):
                with self.subTest(file=path.name, at=pointer, ref=ref):
                    cl.resolve_ref(path, ref)

    def test_per_context_files_reference_and_never_redefine_per_topic_files(self):
        topic_schema_names = set()
        topic_addresses = set(cl.PER_TOPIC_FILES)
        for topic in cl.PER_TOPIC_FILES:
            topic_schema_names |= set(cl.load_yaml(cl.ASYNCAPI_DIR / f"{topic}.yaml")["components"]["schemas"])
        topic_schema_names.discard("KafkaHeaders")
        for context in cl.CONTEXTS:
            path = cl.ASYNCAPI_DIR / f"{context}.yaml"
            doc = cl.load_yaml(path)
            with self.subTest(context=context):
                redefined = topic_schema_names & set((doc.get("components") or {}).get("schemas") or {})
                self.assertEqual(redefined, set(), f"{context}.yaml redefines {sorted(redefined)}")
                for key, file, channel, local in cl.channels(path):
                    if channel["address"] in topic_addresses:
                        self.assertFalse(local, f"{context}.yaml defines {channel['address']} instead of referencing it")
                        self.assertEqual(file.name, f"{channel['address']}.yaml")

    def test_legacy_integration_and_data_readiness_reference_the_five_source_topics(self):
        expected = {"legacy-integration": "send", "data-readiness": "receive"}
        for context, action in expected.items():
            path = cl.ASYNCAPI_DIR / f"{context}.yaml"
            seen = set()
            for _, file, op, local in cl.operations(path):
                address = cl.operation_address(file, op)
                if address in cl.SOURCE_INGESTION_TOPICS and op["action"] == action:
                    self.assertFalse(local, f"{context}.yaml redefines the {address} operation")
                    seen.add(address)
            self.assertEqual(seen, set(cl.SOURCE_INGESTION_TOPICS), context)
        own = {ch["address"] for _, _, ch, local in cl.channels(cl.ASYNCAPI_DIR / "legacy-integration.yaml") if local}
        self.assertEqual(own, {"test.result.recorded", "dlt.legacy-integration-extraction"})
        own = {ch["address"] for _, _, ch, local in cl.channels(cl.ASYNCAPI_DIR / "data-readiness.yaml") if local}
        self.assertEqual({a for a in own if not a.startswith("dlt.")}, {"vehicle.identity.resolved"})


class CatalogStructure(unittest.TestCase):
    def test_every_context_has_its_file(self):
        for context in cl.CONTEXTS:
            with self.subTest(context=context):
                self.assertTrue((cl.ASYNCAPI_DIR / f"{context}.yaml").is_file())

    def test_every_context_that_produces_or_consumes_has_its_file_and_lists_its_operations(self):
        owners: dict[str, set[tuple[str, str]]] = {}
        for doc in cl.asyncapi_documents():
            for _, file, op, local in cl.operations(doc):
                if local:
                    owners.setdefault(op["x-owner-context"], set()).add((op["action"], cl.operation_address(file, op)))
        for context, ops in owners.items():
            with self.subTest(context=context):
                path = cl.ASYNCAPI_DIR / f"{context}.yaml"
                self.assertTrue(path.is_file(), f"{context} owns operations but has no {path.name}")
                listed = {(op["action"], cl.operation_address(f, op)) for _, f, op, _ in cl.operations(path)}
                self.assertLessEqual(ops, listed, f"{context}.yaml does not list {sorted(ops - listed)}")

    def test_each_topic_is_defined_once(self):
        for address, entries in _local_topics().items():
            with self.subTest(topic=address):
                self.assertEqual(len(entries), 1, f"{address} is defined in {[e[0].name for e in entries]}")

    def test_the_phase_1_catalog_is_complete(self):
        topics = set(_local_topics())
        for topic in ("vehicle.identity.resolved", "firmware.change.committed", "dependency.impact.computed",
                      "config.validation.completed", "test.result.recorded", "release.evidence.gap.detected",
                      "audit.event.recorded", *cl.PER_TOPIC_FILES):
            self.assertIn(topic, topics)

    def test_every_topic_has_payload_key_and_every_consumer_group_a_dead_letter_topic(self):
        topics = _local_topics()
        for address, [(file, _, channel)] in topics.items():
            with self.subTest(topic=address):
                self.assertTrue(channel.get("messages"))
                for msg_ref in channel["messages"].values():
                    msg_file, msg = cl.deref(file, msg_ref)
                    self.assertIn("payload", msg)
                    self.assertIn("key", msg.get("bindings", {}).get("kafka", {}), f"{address} has no Kafka key")
        groups = set()
        for doc in cl.asyncapi_documents():
            for _, file, op, local in cl.operations(doc):
                if op["action"] != "receive":
                    continue
                group = cl.operation_group(op)
                with self.subTest(operation=op.get("summary"), group=group):
                    self.assertIsNotNone(group, "receive operation without a consumer group")
                    self.assertEqual(op.get("x-dead-letter-topic"), f"dlt.{group}")
                    self.assertIn(f"dlt.{group}", topics, f"dlt.{group} is not defined")
                    groups.add(group)
        self.assertEqual(groups, {
            "integration-intelligence-identity", "integration-intelligence-change", "integration-intelligence-impact",
            "configuration-assurance-identity", "configuration-assurance-impact", "release-assurance-evidence",
            "audit-sink", "data-readiness-document", "data-readiness-erp-masterdata",
            "data-readiness-erp-purchaseorder", "data-readiness-mes-workorder", "data-readiness-mes-quality",
        })
        dlts = {a for a in topics if a.startswith("dlt.")}
        self.assertEqual(dlts, {f"dlt.{g}" for g in groups} | {"dlt.legacy-integration-extraction"})

    def test_release_assurance_never_receives_release_risk_scored(self):
        for doc in cl.asyncapi_documents():
            for _, file, op, _ in cl.operations(doc):
                if cl.operation_address(file, op) == "release.risk.scored":
                    with self.subTest(document=doc.name):
                        self.assertEqual(op["action"], "send")

    def test_no_consumer_for_release_evidence_gap_detected_in_phase_1(self):
        for doc in cl.asyncapi_documents():
            for _, file, op, _ in cl.operations(doc):
                if cl.operation_address(file, op) == "release.evidence.gap.detected":
                    self.assertEqual(op["action"], "send")


if __name__ == "__main__":
    unittest.main()
