"""Unit tests for the deterministic `core0-v0.2` scalar/CFG corpus."""

from __future__ import annotations

import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gate3_corpus  # noqa: E402
import run_scalar_batch  # noqa: E402


class Gate3CorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = gate3_corpus.build_corpus()

    def test_exact_profile_catalog_distribution_and_uniqueness(self) -> None:
        gate3_corpus.validate_corpus(self.corpus)
        self.assertEqual(self.corpus["profile"], "core0-v0.2")
        self.assertEqual(self.corpus["test_abi"], "lemma-scalar-test-v1")
        self.assertEqual(self.corpus["suite_id"], "0xb15c8d071a8dc520")
        self.assertEqual(self.corpus["source_seed"], "0x4c454d4d41333033")
        self.assertEqual(self.corpus["runtime_seed"], "0x52554e54494d4533")
        self.assertEqual(self.corpus["case_count"], 708)
        self.assertEqual(len(self.corpus["roots"]), 44)
        cases = self.corpus["cases"]
        self.assertEqual(len(cases), 708)
        self.assertEqual(len({case["case_id"] for case in cases}), 708)
        vectors = {
            (case["root"], tuple((arg["type"], arg["value"]) for arg in case["args"]))
            for case in cases
        }
        self.assertEqual(len(vectors), 708)
        self.assertEqual(
            {case["root"] for case in cases},
            {root["name"] for root in self.corpus["roots"]},
        )

    def test_all_fifteen_new_primitives_have_notation_and_direct_roots(self) -> None:
        coverage = self.corpus["primitive_coverage"]
        self.assertEqual(len(coverage), 15)
        self.assertEqual(
            {entry["stable_id"] for entry in coverage},
            {
                f"{ty}.{operation}"
                for ty in ("u8", "u32", "u64")
                for operation in ("complement", "shl", "lshr", "udiv", "urem")
            },
        )
        roots = {root["name"] for root in self.corpus["roots"]}
        for entry in coverage:
            self.assertIn(entry["notation_root"], roots)
            self.assertIn(entry["direct_root"], roots)

    def test_retained_v01_primitive_catalog_is_closed_and_root_witnessed(self) -> None:
        coverage = self.corpus["retained_primitive_coverage"]
        self.assertEqual(
            [spec.name.rsplit(".", 1)[1] for spec in gate3_corpus.ROOT_SPECS[-9:]],
            [
                "u8LegacyArithmetic",
                "u32LegacyArithmetic",
                "u64LegacyArithmetic",
                "u8LegacyCompare",
                "u32LegacyCompare",
                "u64LegacyCompare",
                "u8LegacyCasts",
                "u32LegacyCasts",
                "u64LegacyCasts",
            ],
        )
        expected = {
            *(f"{ty}.{operation}" for ty in ("u8", "u32", "u64")
              for operation in ("add", "sub", "mul", "and", "or", "xor", "ult", "ule", "eq")),
            "bool.eq",
            "u8.to-u32.zext",
            "u8.to-u64.zext",
            "u32.to-u8.trunc",
            "u32.to-u64.zext",
            "u64.to-u8.trunc",
            "u64.to-u32.trunc",
        }
        self.assertEqual(len(coverage), 34)
        self.assertEqual({entry["stable_id"] for entry in coverage}, expected)
        retained_roots = {spec.name for spec in gate3_corpus.ROOT_SPECS[-9:]}
        self.assertTrue(all(entry["witness_root"] in retained_roots for entry in coverage))
        cases_by_root: dict[str, int] = {}
        for case in self.corpus["cases"]:
            cases_by_root[case["root"]] = cases_by_root.get(case["root"], 0) + 1
        self.assertEqual({name: cases_by_root[name] for name in retained_roots},
                         {name: 12 for name in retained_roots})
        tampered = copy.deepcopy(self.corpus)
        tampered["retained_primitive_coverage"][0]["stable_id"] = "u8.forged"
        with self.assertRaisesRegex(gate3_corpus.CorpusError, "retained-v0.1 primitive catalog"):
            gate3_corpus.validate_corpus(tampered)

    def test_retained_source_witnesses_are_operations_not_only_labels(self) -> None:
        source = (ROOT / "examples/foundation/ScalarV2Conformance.lean").read_text(
            encoding="utf-8"
        )

        def body(name: str) -> str:
            match = re.search(rf"^def {name}\b.*?(?=^def |^end )", source, re.MULTILINE | re.DOTALL)
            self.assertIsNotNone(match, name)
            assert match is not None
            return match.group(0)

        for ty in ("u8", "u32", "u64"):
            arithmetic = body(f"{ty}LegacyArithmetic")
            for token in (" + ", " - ", " * ", "&&&", "|||", "^^^"):
                self.assertIn(token, arithmetic)
            compare = body(f"{ty}LegacyCompare")
            for token in ("flag = expected", "x = y", "x < y", "x ≤ z"):
                self.assertIn(token, compare)
        self.assertIn("x.toUInt32.toUInt64", body("u8LegacyCasts"))
        self.assertIn("x.toUInt64", body("u8LegacyCasts"))
        self.assertIn("x.toUInt8.toUInt64", body("u32LegacyCasts"))
        self.assertIn("x.toUInt64", body("u32LegacyCasts"))
        self.assertIn("x.toUInt8.toUInt64", body("u64LegacyCasts"))
        self.assertIn("x.toUInt32.toUInt64", body("u64LegacyCasts"))

    def test_required_division_shift_and_cfg_edges_are_present(self) -> None:
        by_root: dict[str, list[tuple[int, ...]]] = {}
        for case in self.corpus["cases"]:
            by_root.setdefault(case["root"], []).append(
                tuple(int(arg["value"], 16) for arg in case["args"])
            )
        for spec in gate3_corpus.ROOT_SPECS:
            vectors = by_root[spec.name]
            if spec.operation in ("shl", "lshr"):
                counts = {vector[1] for vector in vectors}
                self.assertTrue(
                    {
                        spec.width - 1,
                        spec.width,
                        spec.width + 1,
                        gate3_corpus.TYPE_MAX[spec.args[1]],
                    }.issubset(counts),
                    spec.name,
                )
            if spec.operation in ("udiv", "urem"):
                self.assertIn((0, 0), vectors, spec.name)
                self.assertTrue(any(vector[0] == 0 for vector in vectors), spec.name)
                self.assertTrue(any(vector[1] == 0 for vector in vectors), spec.name)
                self.assertTrue(
                    any(vector[0] == gate3_corpus.TYPE_MAX[spec.args[0]] for vector in vectors),
                    spec.name,
                )
            if spec.operation in ("cfg", "nested-cfg"):
                divisor_index = len(spec.args) - 2
                count_index = len(spec.args) - 1
                self.assertTrue(any(vector[divisor_index] == 0 for vector in vectors), spec.name)
                counts = {vector[count_index] for vector in vectors}
                self.assertTrue(
                    {
                        spec.width - 1,
                        spec.width,
                        spec.width + 1,
                        gate3_corpus.TYPE_MAX[spec.args[count_index]],
                    }.issubset(counts),
                    spec.name,
                )

    def test_cfg_roots_return_every_scalar_type_and_use_helper_boundaries(self) -> None:
        cfg_roots = [
            root
            for root in self.corpus["roots"]
            if "structured-cfg" in root["covers"]
        ]
        self.assertEqual({root["signature"]["result"] for root in cfg_roots}, set(gate3_corpus.TYPES))
        self.assertEqual(len(cfg_roots), 5)
        self.assertTrue(all("branch-dependent-dangerous-operation" in root["covers"] for root in cfg_roots))

    def test_generation_is_deterministic_and_both_seeds_are_material(self) -> None:
        self.assertEqual(self.corpus, gate3_corpus.build_corpus())
        changed_source = gate3_corpus.build_corpus(
            source_seed=gate3_corpus.DEFAULT_SOURCE_SEED ^ 1
        )
        changed_runtime = gate3_corpus.build_corpus(
            runtime_seed=gate3_corpus.DEFAULT_RUNTIME_SEED ^ 1
        )
        self.assertNotEqual(self.corpus["suite_id"], changed_source["suite_id"])
        self.assertNotEqual(self.corpus["cases"], changed_source["cases"])
        self.assertNotEqual(self.corpus["suite_id"], changed_runtime["suite_id"])
        self.assertNotEqual(self.corpus["cases"], changed_runtime["cases"])

    def test_all_notation_direct_pairs_have_identical_ordered_vectors(self) -> None:
        by_root: dict[str, list[tuple[tuple[str, str], ...]]] = {}
        for case in self.corpus["cases"]:
            by_root.setdefault(case["root"], []).append(
                tuple((arg["type"], arg["value"]) for arg in case["args"])
            )
        self.assertEqual(len(self.corpus["metamorphic_pairs"]), 15)
        for pair in self.corpus["metamorphic_pairs"]:
            with self.subTest(pair=pair["name"]):
                self.assertEqual(by_root[pair["left"]], by_root[pair["right"]])

    def test_source_catalog_declares_every_root(self) -> None:
        source = (ROOT / "examples/foundation/ScalarV2Conformance.lean").read_text(
            encoding="utf-8"
        )
        for spec in gate3_corpus.ROOT_SPECS:
            short_name = spec.name.rsplit(".", 1)[1]
            self.assertIn(f"def {short_name} ", source)
        support = (ROOT / "examples/foundation/ScalarV2ConformanceSupport.lean").read_text(
            encoding="utf-8"
        )
        for width in ("U8", "U32", "U64"):
            self.assertIn(f"def choose{width} ", support)

    def test_export_source_uses_the_canonical_root_order(self) -> None:
        source = (ROOT / "examples/foundation/ScalarV2Build.lean").read_text(
            encoding="utf-8"
        )
        self.assertIn("#core0_export_scalar_v2_suite [", source)
        offsets = [source.index(spec.name) for spec in gate3_corpus.ROOT_SPECS]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(source.count("Lemma.Examples.Foundation.ScalarV2."), 44)

    def test_direct_driver_calls_only_the_original_source(self) -> None:
        source = gate3_corpus.render_direct_driver(self.corpus)
        imports = [line for line in source.splitlines() if line.startswith("import ")]
        self.assertEqual(imports, ["import examples.foundation.ScalarV2Conformance"])
        self.assertNotIn("Lemma.Core0", source)
        self.assertNotIn("#core0_eval", source)
        case_prefixes = tuple(
            f"  gate3Emit{suffix} " for suffix in ("Bool", "U8", "U32", "U64")
        )
        self.assertEqual(sum(line.startswith(case_prefixes) for line in source.splitlines()), 708)
        self.assertEqual(source.count("private def gate3DirectChunk"), 12)
        for root in self.corpus["roots"]:
            self.assertIn(root["name"], source)

    def test_model_driver_uses_only_the_v02_typed_command(self) -> None:
        source = gate3_corpus.render_model_driver(self.corpus)
        self.assertEqual(source.count("#core0_eval_typed_v02 "), 708)
        self.assertNotIn("#core0_eval_typed ", source)
        self.assertIn("import Lemma.Compiler.Test.ScalarV2Eval", source)
        self.assertIn("-- profile: core0-v0.2", source)

    def test_generate_writes_round_trippable_abi_v1_batches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "caller-supplied"
            generated = gate3_corpus.generate(output)
            loaded = json.loads((output / "gate3-cases.json").read_text(encoding="utf-8"))
            self.assertEqual(generated, loaded)
            gate3_corpus.validate_corpus(loaded)
            self.assertEqual(
                (output / "DirectEval.lean").read_text(encoding="utf-8"),
                gate3_corpus.render_direct_driver(generated),
            )
            self.assertEqual(
                (output / "ModelEval.lean").read_text(encoding="utf-8"),
                gate3_corpus.render_model_driver(generated),
            )
            batches = sorted((output / "batches").glob("batch-*.json"))
            self.assertEqual(len(batches), 44)
            seen_cases: set[int] = set()
            for batch in batches:
                descriptor = run_scalar_batch.load_descriptor(batch)
                self.assertEqual(descriptor.suite_id, int(generated["suite_id"], 16))
                self.assertLessEqual(len(descriptor.cases), run_scalar_batch.MAX_CASES)
                seen_cases.update(case.case_id for case in descriptor.cases)
            self.assertEqual(seen_cases, set(range(1, 709)))

    def test_wrong_profile_ranges_and_stale_suite_id_are_rejected(self) -> None:
        corpus = copy.deepcopy(self.corpus)
        corpus["profile"] = "core0-v0.1"
        with self.assertRaisesRegex(gate3_corpus.CorpusError, "profile/test ABI"):
            gate3_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        case = next(
            item for item in corpus["cases"] if any(arg["type"] == "u8" for arg in item["args"])
        )
        argument = next(arg for arg in case["args"] if arg["type"] == "u8")
        argument["value"] = "0x0000000000000100"
        with self.assertRaisesRegex(gate3_corpus.CorpusError, "outside u8"):
            gate3_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        corpus["suite_id"] = "0x0000000000000001"
        with self.assertRaisesRegex(gate3_corpus.CorpusError, "suite_id is stale"):
            gate3_corpus.validate_corpus(corpus)

    def test_duplicate_vectors_and_missing_required_edges_are_rejected(self) -> None:
        corpus = copy.deepcopy(self.corpus)
        grouped: dict[str, list[dict[str, object]]] = {}
        for case in corpus["cases"]:
            grouped.setdefault(case["root"], []).append(case)
        same_root = next(cases for cases in grouped.values() if len(cases) > 1)
        same_root[1]["args"] = copy.deepcopy(same_root[0]["args"])
        with self.assertRaisesRegex(gate3_corpus.CorpusError, "duplicates a \\(root,args\\) vector"):
            gate3_corpus.validate_corpus(corpus)

        corpus = copy.deepcopy(self.corpus)
        shift_spec = next(spec for spec in gate3_corpus.ROOT_SPECS if spec.operation == "shl")
        pair = next(
            pair
            for pair in gate3_corpus.METAMORPHIC_PAIRS
            if pair[1] == shift_spec.name
        )
        for root_name in pair[1:]:
            replacement_count = 2
            for case in (item for item in corpus["cases"] if item["root"] == root_name):
                if int(case["args"][1]["value"], 16) == shift_spec.width:
                    case["args"][1]["value"] = f"0x{replacement_count:016x}"
                    replacement_count += 1
        with self.assertRaisesRegex(gate3_corpus.CorpusError, "lacks required count edges"):
            gate3_corpus.validate_corpus(corpus)


if __name__ == "__main__":
    unittest.main()
