#!/usr/bin/env python3
"""Focused tests for the closed Gate 5 checked-memory corpus and oracle."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_memory  # noqa: E402
import gate5_corpus  # noqa: E402
import run_memory_case  # noqa: E402


class Gate5CorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = gate5_corpus.build_corpus()

    def cases_for(self, root_id: int) -> list[dict[str, object]]:
        return [case for case in self.corpus["cases"] if case["root_id"] == root_id]

    def descriptor_for(self, case: dict[str, object]) -> run_memory_case.MemoryCaseDescriptor:
        root_id = int(case["root_id"])
        spec = gate5_corpus.ROOT_SPECS[root_id - 1]
        return run_memory_case.MemoryCaseDescriptor(
            suite_id=int(self.corpus["suite_id"], 16),
            case_id=int(case["case_id"], 16),
            root=spec.name,
            root_id=root_id,
            signature=run_memory_case.MemorySignature(spec.args),
            source_seed=int(self.corpus["source_seed"], 16),
            runtime_seed=int(self.corpus["runtime_seed"], 16),
            args=tuple(int(item["value"], 16) for item in case["args"]),
        )

    def custom_descriptor(
        self, root_id: int, args: tuple[int, ...]
    ) -> run_memory_case.MemoryCaseDescriptor:
        spec = gate5_corpus.ROOT_SPECS[root_id - 1]
        return run_memory_case.MemoryCaseDescriptor(
            suite_id=int(self.corpus["suite_id"], 16),
            case_id=0x1000 + root_id,
            root=spec.name,
            root_id=root_id,
            signature=run_memory_case.MemorySignature(spec.args),
            source_seed=int(self.corpus["source_seed"], 16),
            runtime_seed=int(self.corpus["runtime_seed"], 16),
            args=args,
        )

    def test_exact_26_root_52_fresh_boot_catalog(self) -> None:
        gate5_corpus.validate_corpus(self.corpus)
        self.assertEqual(self.corpus["profile"], "core0-v0.4")
        self.assertEqual(self.corpus["suite_id"], "0xa20c6fd4108dbf27")
        self.assertEqual(self.corpus["root_count"], 26)
        self.assertEqual(self.corpus["case_count"], 52)
        self.assertEqual(self.corpus["fresh_boots_per_profile"], 52)
        counts = [root["case_count"] for root in self.corpus["roots"]]
        self.assertEqual(counts[12], 1)
        self.assertEqual(counts[22], 3)
        self.assertEqual(sum(counts), 52)
        self.assertTrue(all(count == 2 for index, count in enumerate(counts) if index not in {12, 22}))
        self.assertEqual(
            [root["name"].rsplit(".", 1)[-1] for root in self.corpus["roots"]],
            [spec.leaf for spec in gate5_corpus.ROOT_SPECS],
        )
        self.assertEqual(
            {case["expected"]["status"] for case in self.corpus["cases"]},
            {0, 1, 2, 3, 5, 6, 7, 8, 9},
        )
        # Status 4 remains defined, but cannot occur without a write-only ordinary region.
        self.assertIn({"code": 4, "name": "read-denied"}, self.corpus["status_codes"])

    def test_memory_contract_is_identical_to_independent_audit_catalog(self) -> None:
        self.assertEqual(run_memory_case.expected_memory_contract(), audit_memory.MEMORY_CONTRACT)
        self.assertEqual(self.corpus["memory_contract"], audit_memory.MEMORY_CONTRACT)
        regions = self.corpus["memory_contract"]["regions"]
        self.assertEqual([item["id"] for item in regions], [1, 2, 3, 4, 0x70, 0x71, 0x80, 0x81])
        self.assertTrue(all(item["alignment"] == 8 for item in regions))
        self.assertTrue(self.corpus["memory_contract"]["successful_access_volatile"])

    def test_little_endian_loads_and_overlap_results_are_from_fixture_bytes(self) -> None:
        for root_id, width in ((1, 1), (2, 4), (3, 8)):
            for case in self.cases_for(root_id):
                descriptor = self.descriptor_for(case)
                region, offset = descriptor.args
                expected = int.from_bytes(
                    run_memory_case.initial_region_bytes(descriptor, region)[offset : offset + width],
                    "little",
                )
                self.assertEqual(int(case["expected"]["value"], 16), expected)
        self.assertEqual(
            [int(case["expected"]["value"], 16) for case in self.cases_for(11)],
            [0x55667788, 0x76543210],
        )
        self.assertEqual(
            [int(case["expected"]["value"], 16) for case in self.cases_for(12)],
            [0x11223344, 0xFEDCBA98],
        )
        self.assertEqual(int(self.cases_for(13)[0]["expected"]["value"], 16), 0xA1D4)

    def test_guard_precedence_boundaries_and_rejections_have_no_access(self) -> None:
        # store64 at 0xff9 is both OOB and misaligned; bounds must win.
        self.assertEqual(self.cases_for(6)[1]["expected"]["status"], 7)
        self.assertEqual(self.cases_for(17)[1]["expected"]["status"], 8)
        self.assertEqual(self.cases_for(18)[0]["expected"]["status"], 2)
        self.assertEqual(self.cases_for(19)[0]["expected"]["status"], 3)
        self.assertEqual(self.cases_for(20)[1]["expected"]["status"], 1)
        for root_id in (6, 10, 14, 15, 16, 17, 18, 19, 20, 23, 24):
            for case in self.cases_for(root_id):
                if case["expected"]["status"] != 0:
                    self.assertEqual(case["events"], [], case)

    def test_denied_writes_preserve_every_region_and_success_changes_only_target(self) -> None:
        denied = self.cases_for(4)[1]  # write to immutable input records
        descriptor = self.descriptor_for(denied)
        before = gate5_corpus.FiniteMemory(descriptor).digest()
        _outcome, after = gate5_corpus.evaluate(gate5_corpus.ROOT_SPECS[3], descriptor)
        self.assertEqual(before, after.digest())

        success = self.cases_for(4)[0]
        descriptor = self.descriptor_for(success)
        before_model = gate5_corpus.FiniteMemory(descriptor)
        initial = {region: bytes(data) for region, data in before_model.memory.items()}
        _outcome, after_model = gate5_corpus.evaluate(gate5_corpus.ROOT_SPECS[3], descriptor)
        self.assertNotEqual(bytes(after_model.memory[1]), initial[1])
        self.assertEqual(bytes(after_model.memory[2]), initial[2])
        self.assertEqual(bytes(after_model.memory[3]), initial[3])
        self.assertEqual(bytes(after_model.memory[4]), initial[4])

    def test_effectful_fold_zero_exact_budget_and_exhaustion(self) -> None:
        zero, exact, exhausted = self.cases_for(23)
        self.assertEqual([case["expected"]["status"] for case in (zero, exact, exhausted)], [0, 0, 9])
        self.assertEqual(int(zero["expected"]["value"], 16), 0)
        self.assertEqual(int(exact["expected"]["value"], 16), sum((0xF8 + i) & 0xFF for i in range(16)))
        self.assertEqual(int(exhausted["expected"]["value"], 16), 0)
        self.assertEqual(zero["events"], [])
        self.assertEqual(len(exact["events"]), 16)
        self.assertTrue(all(event["kind"] == "write" for event in exact["events"]))
        self.assertEqual(exhausted["events"], [])

    def test_source_ordered_preflight_budget_and_partial_fold_semantics(self) -> None:
        # bufferFill performs its range preflight before testing the fold budget.
        descriptor = self.custom_descriptor(24, (1, 0xFF0, 257, 0xAA))
        outcome, model = gate5_corpus.evaluate(gate5_corpus.ROOT_SPECS[23], descriptor)
        self.assertEqual(outcome, gate5_corpus.ModelOutcome(7, 0))
        self.assertEqual(model.events, [])
        descriptor = self.custom_descriptor(24, (1, 0, 257, 0xAA))
        outcome, model = gate5_corpus.evaluate(gate5_corpus.ROOT_SPECS[23], descriptor)
        self.assertEqual(outcome, gate5_corpus.ModelOutcome(9, 0))
        self.assertEqual(model.events, [])

        # foldWrite has no aggregate preflight: an accepted in-range write is
        # observable before the following element is rejected.
        descriptor = self.custom_descriptor(23, (2, 0xFFF, 0x11))
        outcome, model = gate5_corpus.evaluate(gate5_corpus.ROOT_SPECS[22], descriptor)
        self.assertEqual(outcome, gate5_corpus.ModelOutcome(7, 0x11))
        self.assertEqual(len(model.events), 1)
        self.assertEqual(model.events[0], gate5_corpus.MemoryEvent("write", 1, 0xFFF, 1, 0x11))

    def test_overlap_copy_uses_memmove_direction_and_exact_access_order(self) -> None:
        backwards, forwards = self.cases_for(26)
        backward_accesses = backwards["events"]
        forward_accesses = forwards["events"]
        self.assertEqual(
            [(event["kind"], event["offset"]) for event in backward_accesses[:4]],
            [("read", 0x40F), ("write", 0x417), ("read", 0x40E), ("write", 0x416)],
        )
        self.assertEqual(
            [(event["kind"], event["offset"]) for event in forward_accesses[:4]],
            [("read", 0x408), ("write", 0x400), ("read", 0x409), ("write", 0x401)],
        )

    def test_generation_is_deterministic_and_both_seeds_are_material(self) -> None:
        self.assertEqual(self.corpus, gate5_corpus.build_corpus())
        changed_source = gate5_corpus.build_corpus(
            source_seed=gate5_corpus.DEFAULT_SOURCE_SEED ^ 1
        )
        changed_runtime = gate5_corpus.build_corpus(
            runtime_seed=gate5_corpus.DEFAULT_RUNTIME_SEED ^ 1
        )
        self.assertNotEqual(self.corpus["suite_id"], changed_source["suite_id"])
        self.assertNotEqual(self.corpus["suite_id"], changed_runtime["suite_id"])
        self.assertNotEqual(self.corpus["cases"], changed_source["cases"])
        self.assertNotEqual(self.corpus["cases"], changed_runtime["cases"])

    def test_expected_results_and_event_traces_fail_closed_under_mutation(self) -> None:
        tampered = copy.deepcopy(self.corpus)
        tampered["cases"][0]["expected"]["value"] = "0x0000000000000000"
        with self.assertRaisesRegex(gate5_corpus.CorpusError, "independent model"):
            gate5_corpus.validate_corpus(tampered)

        tampered = copy.deepcopy(self.corpus)
        tampered["cases"][3]["events"][0]["value"] ^= 1
        with self.assertRaisesRegex(gate5_corpus.CorpusError, "event trace"):
            gate5_corpus.validate_corpus(tampered)

    def test_generation_writes_52_closed_one_boot_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "corpus"
            generated = gate5_corpus.generate(output)
            loaded = json.loads((output / "gate5-cases.json").read_text(encoding="utf-8"))
            self.assertEqual(generated, loaded)
            descriptors = sorted((output / "descriptors").glob("case-*.json"))
            self.assertEqual(len(descriptors), 52)
            observed_ids = {
                run_memory_case.load_descriptor(path).case_id for path in descriptors
            }
            self.assertEqual(observed_ids, set(range(1, 53)))


if __name__ == "__main__":
    unittest.main()
