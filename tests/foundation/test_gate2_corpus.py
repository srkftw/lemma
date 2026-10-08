"""Unit tests for the deterministic Gate 2 typed corpus and oracle sources."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gate2_corpus  # noqa: E402


class Gate2CorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = gate2_corpus.build_corpus()

    def test_exact_count_distribution_types_and_uniqueness(self) -> None:
        gate2_corpus.validate_corpus(self.corpus)
        self.assertEqual(self.corpus["case_count"], 1024)
        self.assertEqual(len(self.corpus["roots"]), 37)
        cases = self.corpus["cases"]
        self.assertEqual(len(cases), 1024)
        self.assertEqual(len({case["case_id"] for case in cases}), 1024)
        vectors = {
            (case["root"], tuple((arg["type"], arg["value"]) for arg in case["args"]))
            for case in cases
        }
        self.assertEqual(len(vectors), 1024)
        self.assertEqual({case["root"] for case in cases}, {root["name"] for root in self.corpus["roots"]})

    def test_generation_is_deterministic_and_both_seeds_are_material(self) -> None:
        self.assertEqual(self.corpus, gate2_corpus.build_corpus())
        changed_source = gate2_corpus.build_corpus(
            source_seed=gate2_corpus.DEFAULT_SOURCE_SEED ^ 1
        )
        changed_runtime = gate2_corpus.build_corpus(
            runtime_seed=gate2_corpus.DEFAULT_RUNTIME_SEED ^ 1
        )
        self.assertNotEqual(self.corpus["suite_id"], changed_source["suite_id"])
        self.assertNotEqual(self.corpus["cases"], changed_source["cases"])
        self.assertNotEqual(self.corpus["suite_id"], changed_runtime["suite_id"])
        self.assertNotEqual(self.corpus["cases"], changed_runtime["cases"])

    def test_metamorphic_pairs_have_identical_ordered_vectors(self) -> None:
        by_root: dict[str, list[tuple[tuple[str, str], ...]]] = {}
        for case in self.corpus["cases"]:
            by_root.setdefault(case["root"], []).append(
                tuple((arg["type"], arg["value"]) for arg in case["args"])
            )
        self.assertEqual(len(self.corpus["metamorphic_pairs"]), 5)
        for pair in self.corpus["metamorphic_pairs"]:
            with self.subTest(pair=pair["name"]):
                self.assertEqual(by_root[pair["left"]], by_root[pair["right"]])

    def test_direct_driver_calls_source_without_core0(self) -> None:
        source = gate2_corpus.render_direct_driver(self.corpus)
        imports = [line for line in source.splitlines() if line.startswith("import ")]
        self.assertEqual(imports, ["import examples.foundation.Conformance"])
        self.assertNotIn("Lemma.Core0", source)
        self.assertNotIn("#core0_eval", source)
        case_lines = tuple(f"  gate2Emit{suffix} " for suffix in ("Bool", "U8", "U32", "U64"))
        self.assertEqual(sum(line.startswith(case_lines) for line in source.splitlines()), 1024)
        self.assertEqual(source.count("private def gate2DirectChunk"), 16)
        for root in self.corpus["roots"]:
            self.assertIn(root["name"], source)

    def test_model_driver_uses_only_typed_model_command(self) -> None:
        source = gate2_corpus.render_model_driver(self.corpus)
        self.assertEqual(source.count("#core0_eval_typed "), 1024)
        self.assertNotIn("#core0_eval ", source)
        self.assertIn("import Lemma.Compiler.Test.ScalarEval", source)

    def test_generate_writes_round_trippable_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "caller-supplied"
            generated = gate2_corpus.generate(output)
            loaded = json.loads((output / "gate2-cases.json").read_text(encoding="utf-8"))
            self.assertEqual(generated, loaded)
            gate2_corpus.validate_corpus(loaded)
            self.assertEqual(
                (output / "DirectEval.lean").read_text(encoding="utf-8"),
                gate2_corpus.render_direct_driver(generated),
            )
            self.assertEqual(
                (output / "ModelEval.lean").read_text(encoding="utf-8"),
                gate2_corpus.render_model_driver(generated),
            )

    def test_malformed_range_and_bool_encoding_are_rejected(self) -> None:
        for wanted_type, invalid in (("bool", 2), ("u8", 0x100), ("u32", 0x100000000)):
            with self.subTest(type=wanted_type):
                corpus = copy.deepcopy(self.corpus)
                case = next(
                    case
                    for case in corpus["cases"]
                    if any(arg["type"] == wanted_type for arg in case["args"])
                )
                argument = next(arg for arg in case["args"] if arg["type"] == wanted_type)
                argument["value"] = f"0x{invalid:016x}"
                with self.assertRaisesRegex(gate2_corpus.CorpusError, "outside"):
                    gate2_corpus.validate_corpus(corpus)

    def test_wrong_types_signatures_and_result_types_are_rejected(self) -> None:
        corpus = copy.deepcopy(self.corpus)
        case = next(case for case in corpus["cases"] if case["args"])
        case["args"][0]["type"] = "u64" if case["args"][0]["type"] != "u64" else "u8"
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "wrong type"):
            gate2_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        corpus["cases"][0]["signature"]["result"] = "bool"
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "signature differs"):
            gate2_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        case = corpus["cases"][0]
        case["expected_result_type"] = "bool" if case["expected_result_type"] != "bool" else "u64"
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "wrong expected result type"):
            gate2_corpus.validate_corpus(corpus)

    def test_duplicate_ids_vectors_and_wrong_count_are_rejected(self) -> None:
        corpus = copy.deepcopy(self.corpus)
        corpus["cases"][1]["case_id"] = corpus["cases"][0]["case_id"]
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "duplicate case ID"):
            gate2_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        grouped: dict[str, list[dict[str, object]]] = {}
        for case in corpus["cases"]:
            grouped.setdefault(case["root"], []).append(case)
        same_root = next(cases for cases in grouped.values() if len(cases) > 1)
        same_root[1]["args"] = copy.deepcopy(same_root[0]["args"])
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "duplicates a \\(root,args\\) vector"):
            gate2_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        corpus["cases"].pop()
        corpus["case_count"] = 1023
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "exactly 1024"):
            gate2_corpus.validate_corpus(corpus)

    def test_missing_root_coverage_is_rejected_without_changing_total_count(self) -> None:
        corpus = copy.deepcopy(self.corpus)
        constant = next(case for case in corpus["cases"] if case["root"].endswith(".constantU64"))
        replacement = next(case for case in corpus["cases"] if case["root"].endswith(".boolSelect"))
        seen = {
            tuple(int(arg["value"], 16) for arg in case["args"])
            for case in corpus["cases"]
            if case["root"] == replacement["root"]
        }
        replacement_vector = next(
            (0, value, value + 1)
            for value in range(3, 100)
            if (0, value, value + 1) not in seen
        )
        constant["root"] = replacement["root"]
        constant["signature"] = copy.deepcopy(replacement["signature"])
        constant["args"] = [
            {"type": "bool", "value": f"0x{replacement_vector[0]:016x}"},
            {"type": "u64", "value": f"0x{replacement_vector[1]:016x}"},
            {"type": "u64", "value": f"0x{replacement_vector[2]:016x}"},
        ]
        constant["expected_result_type"] = "u64"
        constant["covers"] = ["boundary", "bool-input", "conditional"]
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "root coverage/case distribution"):
            gate2_corpus.validate_corpus(corpus)

    def test_metamorphic_vector_divergence_is_rejected(self) -> None:
        corpus = copy.deepcopy(self.corpus)
        pair = corpus["metamorphic_pairs"][0]
        right_case = next(case for case in corpus["cases"] if case["root"] == pair["right"])
        value = int(right_case["args"][0]["value"], 16)
        right_case["args"][0]["value"] = f"0x{(value + 1) & ((1 << 64) - 1):016x}"
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "does not use identical input vectors"):
            gate2_corpus.validate_corpus(corpus)

    def test_stale_suite_id_unknown_fields_and_noncanonical_values_are_rejected(self) -> None:
        corpus = copy.deepcopy(self.corpus)
        corpus["suite_id"] = "gate2-forged"
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "suite_id is stale"):
            gate2_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        corpus["unexpected"] = True
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "fields differ from schema"):
            gate2_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        corpus["cases"][0]["case_id"] = "1"
        with self.assertRaisesRegex(gate2_corpus.CorpusError, "canonical string-encoded UInt64"):
            gate2_corpus.validate_corpus(corpus)


if __name__ == "__main__":
    unittest.main()
