#!/usr/bin/env python3
"""Focused host-only tests for the transactional Gate 5 acceptance driver."""

from __future__ import annotations

import copy
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_foundation_gate5  # noqa: E402
import gate5_corpus  # noqa: E402
import run_memory_case  # noqa: E402
from core0_common import Core0Error  # noqa: E402


class Gate5DriverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = gate5_corpus.build_corpus()

    def test_closed_corpus_and_oracle_digest(self) -> None:
        expected = check_foundation_gate5._expected_cases(self.corpus)
        self.assertEqual(len(expected), 52)
        self.assertEqual(set(expected), set(range(1, 53)))
        digest = check_foundation_gate5._result_digest(
            {case_id: (case.status, case.value) for case_id, case in expected.items()}
        )
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(
            digest,
            check_foundation_gate5._result_digest(
                dict(
                    reversed(
                        [
                            (case_id, (case.status, case.value))
                            for case_id, case in expected.items()
                        ]
                    )
                )
            ),
        )

    def test_generated_descriptors_bind_to_closed_root_catalog(self) -> None:
        expected = check_foundation_gate5._expected_cases(self.corpus)
        roots = [
            {
                "root_id": root_id,
                "source": spec.name,
                "signature": {"args": list(spec.args)},
            }
            for root_id, spec in enumerate(gate5_corpus.ROOT_SPECS, 1)
        ]
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            gate5_corpus.generate(output)
            descriptors = check_foundation_gate5._load_descriptors(
                corpus_dir=output,
                manifest={"roots": roots},
                expected_cases=expected,
                suite_id=int(str(self.corpus["suite_id"]), 16),
                source_seed=int(str(self.corpus["source_seed"]), 16),
                runtime_seed=int(str(self.corpus["runtime_seed"]), 16),
            )
        self.assertEqual(len(descriptors), 52)
        self.assertEqual([item.case_id for item in descriptors], list(range(1, 53)))

    def test_descriptor_revalidation_includes_event_digest(self) -> None:
        changed = copy.deepcopy(self.corpus)
        changed["cases"][0]["expected"]["event_sha256"] = "0" * 64
        expected = check_foundation_gate5._expected_cases(changed)
        roots = [
            {
                "root_id": root_id,
                "source": spec.name,
                "signature": {"args": list(spec.args)},
            }
            for root_id, spec in enumerate(gate5_corpus.ROOT_SPECS, 1)
        ]
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw)
            gate5_corpus.generate(output)
            with self.assertRaisesRegex(Core0Error, "oracle differs"):
                check_foundation_gate5._load_descriptors(
                    corpus_dir=output,
                    manifest={"roots": roots},
                    expected_cases=expected,
                    suite_id=int(str(self.corpus["suite_id"]), 16),
                    source_seed=int(str(self.corpus["source_seed"]), 16),
                    runtime_seed=int(str(self.corpus["runtime_seed"]), 16),
                )

    def _case_for_root(
        self, leaf: str, vector: int = 0
    ) -> tuple[
        run_memory_case.MemoryCaseDescriptor,
        gate5_corpus.RootSpec,
        check_foundation_gate5.ExpectedCase,
    ]:
        root_id = next(
            index
            for index, spec in enumerate(gate5_corpus.ROOT_SPECS, 1)
            if spec.leaf == leaf
        )
        spec = gate5_corpus.ROOT_SPECS[root_id - 1]
        matching = [
            item for item in self.corpus["cases"] if item["root_id"] == root_id
        ]
        item = matching[vector]
        descriptor = run_memory_case.MemoryCaseDescriptor(
            suite_id=int(str(self.corpus["suite_id"]), 16),
            case_id=int(str(item["case_id"]), 16),
            root=spec.name,
            root_id=root_id,
            signature=run_memory_case.MemorySignature(spec.args),
            source_seed=int(str(self.corpus["source_seed"]), 16),
            runtime_seed=int(str(self.corpus["runtime_seed"]), 16),
            args=tuple(int(str(arg["value"]), 16) for arg in item["args"]),
        )
        expected = check_foundation_gate5._expected_cases(self.corpus)[descriptor.case_id]
        return descriptor, spec, expected

    @staticmethod
    def _target_record(
        descriptor: run_memory_case.MemoryCaseDescriptor,
        expected: check_foundation_gate5.ExpectedCase,
        memory: gate5_corpus.FiniteMemory,
    ) -> dict[str, object]:
        lines = [
            "LEMMA_MEMORY/1",
            f"CASE:{descriptor.suite_id:016x}:{descriptor.case_id:016x}:"
            f"{descriptor.root_id:016x}",
            f"OUTCOME:{descriptor.case_id:016x}:{expected.status:016x}:"
            f"{expected.value:016x}",
        ]
        for spec in run_memory_case.REGION_SPECS:
            region_id = int(spec["id"])
            data = bytes(memory.memory[region_id])
            words = "".join(
                f"{int.from_bytes(data[start : start + 8], 'little'):016x}"
                for start in range(0, len(data), 8)
            )
            lines.append(f"REGION:{region_id:02x}:{len(data):016x}:{words}")
        lines.extend(
            f"CANARY:{canary_id:02x}:{low:016x}:{high:016x}"
            for canary_id, low, high in run_memory_case.expected_canary_words(descriptor)
        )
        lines.append(f"END:{descriptor.case_id:016x}")
        uart = ("\n".join(lines) + "\n").encode("ascii")
        _outcome, regions, _canaries = run_memory_case.validate_transcript(
            uart, descriptor
        )
        return {
            "uart": uart.decode("ascii"),
            "post_state_bytes": sum(len(region.data) for region in regions),
            "final_memory_sha256": run_memory_case.final_memory_sha256(regions),
            "regions": [
                {
                    "id": region.region_id,
                    "name": str(
                        run_memory_case.REGIONS_BY_ID[region.region_id]["name"]
                    ),
                    "bytes": len(region.data),
                    "sha256": hashlib.sha256(region.data).hexdigest(),
                }
                for region in regions
            ],
        }

    def test_complete_target_post_state_catches_store_offset_and_route_mutations(self) -> None:
        mutations: list[
            tuple[
                str,
                run_memory_case.MemoryCaseDescriptor,
                check_foundation_gate5.ExpectedCase,
                gate5_corpus.FiniteMemory,
            ]
        ] = []

        descriptor, spec, expected = self._case_for_root("store8Status")
        _outcome, correct = gate5_corpus.evaluate(spec, descriptor)
        correct_record = self._target_record(descriptor, expected, correct)
        self.assertEqual(
            check_foundation_gate5._validate_target_post_state(
                profile="O0",
                descriptor=descriptor,
                record=correct_record,
                expected=expected,
            ),
            expected.final_memory_sha256,
        )

        wrong_value = gate5_corpus.FiniteMemory(descriptor)
        wrong_value.store(descriptor.args[0], descriptor.args[1], 1, descriptor.args[2] ^ 1)
        mutations.append(("wrong-store-value", descriptor, expected, wrong_value))

        descriptor, _spec, expected = self._case_for_root("store8Status")
        wrong_offset = gate5_corpus.FiniteMemory(descriptor)
        wrong_offset.store(
            descriptor.args[0], descriptor.args[1] + 1, 1, descriptor.args[2]
        )
        mutations.append(("wrong-checked-offset", descriptor, expected, wrong_offset))

        descriptor, _spec, expected = self._case_for_root("branchWrite")
        wrong_route = gate5_corpus.FiniteMemory(descriptor)
        wrong_route.store(3, descriptor.args[1], 1, descriptor.args[2])
        mutations.append(("wrong-branch-destination", descriptor, expected, wrong_route))

        for name, descriptor, expected, memory in mutations:
            with self.subTest(name=name):
                record = self._target_record(descriptor, expected, memory)
                with self.assertRaises(check_foundation_gate5.Gate5Failure) as raised:
                    check_foundation_gate5._validate_target_post_state(
                        profile="O0",
                        descriptor=descriptor,
                        record=record,
                        expected=expected,
                    )
                self.assertEqual(raised.exception.category, "lowering-or-codegen-mismatch")

    def test_rejection_manifest_pins_all_fourteen_fixtures(self) -> None:
        records = check_foundation_gate5._load_rejections(
            ROOT / "examples/foundation/gate5-reject/rejections.json", ROOT
        )
        self.assertEqual(len(records), 14)
        self.assertEqual(
            tuple(record.path.name for record in records),
            check_foundation_gate5.REJECTION_FILES,
        )

    def test_stage_wraps_failures_with_category_and_context(self) -> None:
        def fail() -> None:
            raise Core0Error("broken model")

        with self.assertRaises(check_foundation_gate5.Gate5Failure) as raised:
            check_foundation_gate5._stage("model-failure", "case", fail)
        self.assertEqual(raised.exception.category, "model-failure")
        self.assertEqual(raised.exception.context, "case")
        self.assertEqual(raised.exception.detail, "broken model")

    def test_early_rerun_failure_invalidates_stale_pass_record(self) -> None:
        build_root = ROOT / "build"
        build_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as raw:
            work = Path(raw)
            result = work / "gate5-results.json"
            result.write_text('{"status":"pass"}\n', encoding="utf-8")
            (work / "retained.txt").write_text("force non-clean failure\n", encoding="utf-8")
            with self.assertRaises(check_foundation_gate5.Gate5Failure) as raised:
                check_foundation_gate5.check_gate5(
                    root=ROOT,
                    work=work,
                    clean=False,
                    timeout_seconds=1.0,
                    qemu_timeout=1.0,
                )
            self.assertEqual(raised.exception.category, "work-directory-failure")
            self.assertFalse(result.exists())

    def test_target_stage_distinguishes_protocol_process_and_timeout(self) -> None:
        cases = (
            ("memory transcript is truncated", "target-protocol-failure"),
            ("memory QEMU process failure", "target-process-failure"),
            ("command timed out", "target-timeout"),
        )
        for detail, category in cases:
            with self.subTest(detail=detail):
                def fail(detail: str = detail) -> None:
                    raise Core0Error(detail)

                with self.assertRaises(check_foundation_gate5.Gate5Failure) as raised:
                    check_foundation_gate5._target_stage("O0", 1, fail)
                self.assertEqual(raised.exception.category, category)


if __name__ == "__main__":
    unittest.main()
