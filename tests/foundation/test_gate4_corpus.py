#!/usr/bin/env python3
"""Focused tests for the deterministic Gate 4 bounded-loop corpus."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gate4_corpus  # noqa: E402
import run_scalar_batch  # noqa: E402


class Gate4CorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = gate4_corpus.build_corpus()

    def test_closed_catalog_and_required_boundaries(self) -> None:
        gate4_corpus.validate_corpus(self.corpus)
        self.assertEqual(self.corpus["profile"], "core0-v0.3")
        self.assertEqual(self.corpus["suite_id"], "0xb1e51d2902bca153")
        self.assertEqual(self.corpus["case_count"], 112)
        self.assertEqual(
            [(root["name"].rsplit(".", 1)[-1], root["static_budget"]) for root in self.corpus["roots"]],
            [
                ("sumFold", 16),
                ("sumFoldChanged", 16),
                ("bitMixFold", 64),
                ("nestedFold", 16),
                ("helperFold", 64),
                ("zeroBudgetFold", 0),
                ("maxBudgetFold", 256),
            ],
        )
        required = {0, 1, 7, 15, 16, 17, 63, 64, 65, 255, 256, 257, 0xFFFFFFFF}
        for root in self.corpus["roots"]:
            counts = {
                int(case["args"][0]["value"], 16)
                for case in self.corpus["cases"]
                if case["root"] == root["name"]
            }
            self.assertTrue(required <= counts, root["name"])

    def test_independent_algorithms_and_tagged_exhaustion(self) -> None:
        by_operation = {spec.operation: spec for spec in gate4_corpus.ROOT_SPECS}
        self.assertEqual(gate4_corpus.model_root(by_operation["sum"], 4, 10), 16)
        self.assertEqual(gate4_corpus.model_root(by_operation["sum-changed"], 4, 10), 20)
        self.assertNotEqual(
            gate4_corpus.model_root(by_operation["bit-mix"], 5, 0x12345678),
            gate4_corpus.model_root(by_operation["helper"], 5, 0x12345678),
        )
        nested = by_operation["nested"]
        self.assertEqual(gate4_corpus.model_root(nested, 0, 0x89ABCDEF), 0x89ABCDEF)
        self.assertEqual(
            gate4_corpus.model_root(nested, 17, 0xFEDCBA98),
            0x80000000FEDCBA98,
        )
        for case in self.corpus["cases"]:
            value = int(case["expected_value"], 16)
            initial = int(case["args"][1]["value"], 16)
            if case["expected_outcome"] == "exhausted":
                self.assertEqual(value, gate4_corpus.EXHAUSTION_TAG | initial)
                self.assertEqual(value & 0x7FFFFFFF00000000, 0)
            else:
                self.assertLessEqual(value, gate4_corpus.U32_MASK)

    def test_changed_body_uses_identical_inputs_and_changes_results(self) -> None:
        left_name = f"{gate4_corpus.BASE}.sumFold"
        right_name = f"{gate4_corpus.BASE}.sumFoldChanged"
        rows: dict[str, list[tuple[tuple[str, ...], str]]] = {left_name: [], right_name: []}
        for case in self.corpus["cases"]:
            if case["root"] in rows:
                rows[case["root"]].append(
                    (tuple(arg["value"] for arg in case["args"]), case["expected_value"])
                )
        self.assertEqual([args for args, _ in rows[left_name]], [args for args, _ in rows[right_name]])
        self.assertTrue(
            any(a != b for (_args, a), (_same, b) in zip(rows[left_name], rows[right_name]))
        )

    def test_generation_is_deterministic_and_both_seeds_are_material(self) -> None:
        self.assertEqual(self.corpus, gate4_corpus.build_corpus())
        changed_source = gate4_corpus.build_corpus(
            source_seed=gate4_corpus.DEFAULT_SOURCE_SEED ^ 1
        )
        changed_runtime = gate4_corpus.build_corpus(
            runtime_seed=gate4_corpus.DEFAULT_RUNTIME_SEED ^ 1
        )
        self.assertNotEqual(self.corpus["suite_id"], changed_source["suite_id"])
        self.assertNotEqual(self.corpus["cases"], changed_source["cases"])
        self.assertNotEqual(self.corpus["suite_id"], changed_runtime["suite_id"])
        self.assertNotEqual(self.corpus["cases"], changed_runtime["cases"])

    def test_mutated_expected_value_and_reserved_bits_fail_closed(self) -> None:
        tampered = copy.deepcopy(self.corpus)
        success = next(case for case in tampered["cases"] if case["expected_outcome"] == "success")
        success["expected_value"] = "0x0000000000000001"
        with self.assertRaisesRegex(gate4_corpus.CorpusError, "independent model"):
            gate4_corpus.validate_corpus(tampered)

        tampered = copy.deepcopy(self.corpus)
        exhausted = next(case for case in tampered["cases"] if case["expected_outcome"] == "exhausted")
        exhausted["expected_value"] = "0xc000000000000000"
        with self.assertRaisesRegex(gate4_corpus.CorpusError, "independent model"):
            gate4_corpus.validate_corpus(tampered)

    def test_drivers_and_batch_descriptors_are_closed(self) -> None:
        direct = gate4_corpus.render_direct_driver(self.corpus)
        self.assertEqual(
            [line for line in direct.splitlines() if line.startswith("import ")],
            ["import examples.foundation.BoundedConformance"],
        )
        self.assertNotIn("Lemma.Core0", direct)
        self.assertEqual(direct.count("  gate4Emit "), 112)
        model = gate4_corpus.render_model_driver(self.corpus)
        self.assertEqual(model.count("#core0_eval_typed_v03 "), 112)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "generated"
            generated = gate4_corpus.generate(output)
            loaded = json.loads((output / "gate4-cases.json").read_text(encoding="utf-8"))
            self.assertEqual(generated, loaded)
            batches = sorted((output / "batches").glob("batch-*.json"))
            self.assertEqual(len(batches), 7)
            seen: set[int] = set()
            for path in batches:
                descriptor = run_scalar_batch.load_descriptor(path)
                self.assertEqual(descriptor.signature.args, ("u32", "u32"))
                self.assertEqual(descriptor.signature.result, "u64")
                seen.update(case.case_id for case in descriptor.cases)
            self.assertEqual(seen, set(range(1, 113)))


if __name__ == "__main__":
    unittest.main()
