"""Fail-closed tests for the Gate 2 typed scalar batch host boundary."""

from __future__ import annotations

import copy
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import core0_common  # noqa: E402
import run_scalar_batch  # noqa: E402


def h(value: int) -> str:
    return f"0x{value:016x}"


ARG_TYPES = ["u64", "u8", "u32", "bool", "u64", "u8", "u32", "bool", "u8", "u32"]
ARG_VALUES = [
    h(0xFEDCBA9876543210),
    h(0xFF),
    h(0xFFFFFFFF),
    h(1),
    h(4),
    h(0x80),
    h(0x80000000),
    h(0),
    h(0x80),
    h(0x87654321),
]


def descriptor_document(
    *,
    arg_types: list[str] | None = None,
    result_type: str = "u64",
    case_count: int = 2,
) -> dict[str, object]:
    types = list(ARG_TYPES if arg_types is None else arg_types)
    boundary = {
        "bool": h(1),
        "u8": h(0xFF),
        "u32": h(0xFFFFFFFF),
        "u64": h(0xFEDCBA9876543210),
    }
    args = list(ARG_VALUES) if arg_types is None else [boundary[ty] for ty in types]
    return {
        "schema_version": 1,
        "suite_id": h(0x5355495445303032),
        "batch_id": h(0x4241544348303031),
        "root": "Lemma.Examples.Foundation.Conformance.abiNoInlineRoot",
        "root_id": h(17),
        "signature": {"args": types, "result": result_type},
        "source_seed": h(0x0123456789ABCDEF),
        "runtime_seed": h(0x0F1E2D3C4B5A6978),
        "cases": [
            {
                "case_id": h(0x100 + index),
                "args": list(args),
                "expected_result_type": result_type,
            }
            for index in range(case_count)
        ],
    }


def transcript(
    descriptor: run_scalar_batch.ScalarBatchDescriptor,
    values: list[int] | None = None,
) -> bytes:
    observed = values or [0xA0 + index for index in range(len(descriptor.cases))]
    lines = [
        "LEMMA_SCALAR/1",
        "BATCH:"
        f"{descriptor.suite_id:016x}:{descriptor.batch_id:016x}:"
        f"{descriptor.root_id:016x}:{len(descriptor.cases):016x}",
    ]
    tag = run_scalar_batch.TYPE_TAGS[descriptor.signature.result]
    lines.extend(
        f"RESULT:{case.case_id:016x}:{tag:016x}:{value:016x}"
        for case, value in zip(descriptor.cases, observed, strict=True)
    )
    lines.append(f"END:{descriptor.batch_id:016x}:{len(descriptor.cases):016x}")
    return ("\n".join(lines) + "\n").encode("ascii")


def replace_u64(data: bytes, byte_offset: int, value: int) -> bytes:
    changed = bytearray(data)
    struct.pack_into("<Q", changed, byte_offset, value)
    return bytes(changed)


class DescriptorTests(unittest.TestCase):
    def test_valid_descriptor_retains_exact_identity_signature_cases_and_seeds(self) -> None:
        descriptor = run_scalar_batch.parse_descriptor(descriptor_document())
        self.assertEqual(
            descriptor.root,
            "Lemma.Examples.Foundation.Conformance.abiNoInlineRoot",
        )
        self.assertEqual(descriptor.root_id, 17)
        self.assertEqual(descriptor.signature.args, tuple(ARG_TYPES))
        self.assertEqual(descriptor.signature.result, "u64")
        self.assertEqual(descriptor.cases[0].args[1:4], (0xFF, 0xFFFFFFFF, 1))
        self.assertEqual(descriptor.cases[0].expected_result_type, "u64")
        self.assertEqual(descriptor.source_seed, 0x0123456789ABCDEF)
        self.assertEqual(descriptor.runtime_seed, 0x0F1E2D3C4B5A6978)

    def test_descriptor_schema_and_root_are_exact(self) -> None:
        for mutation, diagnostic in (
            (lambda value: value.update(extra=True), "fields differ from the schema"),
            (lambda value: value.pop("runtime_seed"), "fields differ from the schema"),
            (lambda value: value.update(schema_version=2), "unsupported schema"),
            (lambda value: value.update(root="not a Lean/root"), "Lean identity"),
        ):
            with self.subTest(diagnostic=diagnostic):
                value = descriptor_document()
                mutation(value)
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    run_scalar_batch.parse_descriptor(value)

    def test_signature_rejects_unknown_types_and_more_than_sixteen_args(self) -> None:
        invalid_types = descriptor_document()
        invalid_types["signature"]["args"][0] = "i64"  # type: ignore[index]
        with self.assertRaisesRegex(core0_common.Core0Error, "supported scalar type"):
            run_scalar_batch.parse_descriptor(invalid_types)

        too_many = descriptor_document(arg_types=["u64"] * 17)
        with self.assertRaisesRegex(core0_common.Core0Error, "maximum is 16"):
            run_scalar_batch.parse_descriptor(too_many)

    def test_case_count_arity_result_type_and_identifiers_are_checked(self) -> None:
        empty = descriptor_document(case_count=0)
        with self.assertRaisesRegex(core0_common.Core0Error, "batch is empty"):
            run_scalar_batch.parse_descriptor(empty)

        too_many = descriptor_document(case_count=30)
        with self.assertRaisesRegex(core0_common.Core0Error, "maximum is 29"):
            run_scalar_batch.parse_descriptor(too_many)

        wrong_arity = descriptor_document()
        wrong_arity["cases"][0]["args"].pop()  # type: ignore[index]
        with self.assertRaisesRegex(core0_common.Core0Error, "root signature requires"):
            run_scalar_batch.parse_descriptor(wrong_arity)

        wrong_result = descriptor_document()
        wrong_result["cases"][0]["expected_result_type"] = "u32"  # type: ignore[index]
        with self.assertRaisesRegex(core0_common.Core0Error, "differs from root result"):
            run_scalar_batch.parse_descriptor(wrong_result)

        duplicate = descriptor_document()
        duplicate["cases"][1]["case_id"] = duplicate["cases"][0]["case_id"]  # type: ignore[index]
        with self.assertRaisesRegex(core0_common.Core0Error, "duplicate scalar batch case id"):
            run_scalar_batch.parse_descriptor(duplicate)

    def test_every_scalar_range_is_enforced_before_transport_truncation(self) -> None:
        cases = (
            ("bool", 2, "invalid Bool encoding"),
            ("u8", 1 << 8, "outside u8"),
            ("u32", 1 << 32, "outside u32"),
            ("u64", 1 << 64, "outside UInt64"),
        )
        for ty, value, diagnostic in cases:
            with self.subTest(ty=ty):
                document = descriptor_document(arg_types=[ty], case_count=1)
                document["cases"][0]["args"][0] = h(value)  # type: ignore[index]
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    run_scalar_batch.parse_descriptor(document)

    def test_numeric_metadata_must_be_string_encoded_u64(self) -> None:
        for field in ("suite_id", "batch_id", "root_id", "source_seed", "runtime_seed"):
            with self.subTest(field=field):
                document = descriptor_document()
                document[field] = 7
                with self.assertRaisesRegex(core0_common.Core0Error, "string-encoded UInt64"):
                    run_scalar_batch.parse_descriptor(document)

    def test_manually_constructed_descriptor_cannot_bypass_range_checks(self) -> None:
        descriptor = run_scalar_batch.parse_descriptor(descriptor_document())
        forged_case = run_scalar_batch.ScalarCase(
            descriptor.cases[0].case_id,
            (descriptor.cases[0].args[0], 256, *descriptor.cases[0].args[2:]),
            "u64",
        )
        forged = run_scalar_batch.ScalarBatchDescriptor(
            descriptor.suite_id,
            descriptor.batch_id,
            descriptor.root,
            descriptor.root_id,
            descriptor.signature,
            descriptor.source_seed,
            descriptor.runtime_seed,
            (forged_case, *descriptor.cases[1:]),
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "outside u8"):
            run_scalar_batch.pack_fixture(forged)


class FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.descriptor = run_scalar_batch.parse_descriptor(descriptor_document())
        self.fixture = run_scalar_batch.pack_fixture(self.descriptor)

    def test_exact_header_record_layout_and_little_endian_magic(self) -> None:
        self.assertEqual(self.fixture[:8], b"LEMMA002")
        self.assertEqual(
            len(self.fixture),
            run_scalar_batch.HEADER_BYTES
            + len(self.descriptor.cases) * run_scalar_batch.RECORD_BYTES,
        )
        words = struct.unpack("<16Q", self.fixture[: run_scalar_batch.HEADER_BYTES])
        self.assertEqual(
            words,
            (
                run_scalar_batch.MAGIC_WORD,
                1,
                128,
                136,
                self.descriptor.suite_id,
                self.descriptor.batch_id,
                self.descriptor.root_id,
                2,
                10,
                4,
                0x0103020401030204,
                0x0000000000000302,
                self.descriptor.source_seed,
                self.descriptor.runtime_seed,
                0,
                0,
            ),
        )
        first_record = struct.unpack(
            "<17Q",
            self.fixture[128 : 128 + run_scalar_batch.RECORD_BYTES],
        )
        self.assertEqual(first_record[0], self.descriptor.cases[0].case_id)
        self.assertEqual(first_record[1:11], self.descriptor.cases[0].args)
        self.assertEqual(first_record[11:], (0,) * 6)
        self.assertEqual(run_scalar_batch.validate_fixture(self.fixture, self.descriptor).cases,
                         self.descriptor.cases)

    def test_header_magic_version_sizes_counts_tags_and_reserved_words_fail_closed(self) -> None:
        mutations = (
            (0, 0, "wrong magic"),
            (1, 2, "unsupported ABI version"),
            (2, 120, "wrong header or record size"),
            (3, 128, "wrong header or record size"),
            (7, 0, "case count"),
            (7, 30, "case count"),
            (8, 17, "argument count"),
            (9, 99, "unknown type tag"),
            (14, 1, "reserved header words"),
            (15, 1, "reserved header words"),
        )
        for word, value, diagnostic in mutations:
            with self.subTest(word=word):
                changed = replace_u64(self.fixture, word * 8, value)
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    run_scalar_batch.parse_fixture(changed)

    def test_unused_tags_and_record_slots_must_be_zero(self) -> None:
        # The tenth argument ends in byte 1 of the high tag word; byte 2 is unused.
        high_tags = struct.unpack_from("<Q", self.fixture, 11 * 8)[0]
        changed_tag = replace_u64(self.fixture, 11 * 8, high_tags | (2 << 16))
        with self.assertRaisesRegex(core0_common.Core0Error, "unused argument tags"):
            run_scalar_batch.parse_fixture(changed_tag)

        unused_slot_offset = run_scalar_batch.HEADER_BYTES + (1 + 10) * 8
        changed_slot = replace_u64(self.fixture, unused_slot_offset, 1)
        with self.assertRaisesRegex(core0_common.Core0Error, "unused argument slots"):
            run_scalar_batch.parse_fixture(changed_slot)

        low_tags = struct.unpack_from("<Q", self.fixture, 10 * 8)[0]
        changed_active_tag = replace_u64(self.fixture, 10 * 8, low_tags & ~0xFF)
        with self.assertRaisesRegex(core0_common.Core0Error, "unknown type tag"):
            run_scalar_batch.parse_fixture(changed_active_tag)

    def test_wire_values_are_checked_against_type_tags(self) -> None:
        # Argument 1 is u8, so slot 1 begins after case_id and argument 0.
        u8_slot_offset = run_scalar_batch.HEADER_BYTES + (1 + 1) * 8
        changed = replace_u64(self.fixture, u8_slot_offset, 256)
        with self.assertRaisesRegex(core0_common.Core0Error, "outside u8"):
            run_scalar_batch.parse_fixture(changed)

    def test_fixture_rejects_truncation_trailing_data_and_descriptor_mismatch(self) -> None:
        for changed in (self.fixture[:-1], self.fixture + b"\0"):
            with self.subTest(length=len(changed)):
                with self.assertRaisesRegex(core0_common.Core0Error, "exact length"):
                    run_scalar_batch.parse_fixture(changed)

        other = run_scalar_batch.parse_descriptor(
            {**descriptor_document(), "root_id": h(self.descriptor.root_id + 1)}
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "differ from its host descriptor"):
            run_scalar_batch.validate_fixture(self.fixture, other)

    def test_maximum_batch_fits_existing_four_kib_fixture_region(self) -> None:
        descriptor = run_scalar_batch.parse_descriptor(descriptor_document(case_count=29))
        fixture = run_scalar_batch.pack_fixture(descriptor)
        self.assertEqual(len(fixture), 4072)
        self.assertLessEqual(len(fixture), 0x1000)


class TranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.descriptor = run_scalar_batch.parse_descriptor(descriptor_document())
        self.valid = transcript(self.descriptor)

    def test_complete_exact_ordered_transcript_is_accepted(self) -> None:
        results = run_scalar_batch.validate_transcript(self.valid, self.descriptor)
        self.assertEqual([result.case_id for result in results], [0x100, 0x101])
        self.assertEqual([result.value for result in results], [0xA0, 0xA1])
        self.assertTrue(all(result.result_type == "u64" for result in results))

    def test_truncated_noisy_uppercase_and_duplicate_frames_are_rejected(self) -> None:
        invalid = (
            b"",
            self.valid[:-1],
            b"boot noise\n" + self.valid,
            self.valid + b"extra\n",
            self.valid.upper(),
            self.valid.replace(b"\n", b"\r\n"),
            self.valid.replace(
                b"END:",
                self.valid.splitlines(keepends=True)[2] + b"END:",
            ),
        )
        for value in invalid:
            with self.subTest(value=value[:40]):
                with self.assertRaises(core0_common.Core0Error):
                    run_scalar_batch.validate_transcript(value, self.descriptor)

    def test_batch_identity_count_and_end_metadata_are_exact(self) -> None:
        replacements = (
            (f"{self.descriptor.suite_id:016x}".encode(), b"0000000000000000", "BATCH metadata"),
            (f"{self.descriptor.root_id:016x}".encode(), b"0000000000000012", "BATCH metadata"),
            (
                f"END:{self.descriptor.batch_id:016x}:0000000000000002".encode(),
                f"END:{self.descriptor.batch_id:016x}:0000000000000001".encode(),
                "END metadata",
            ),
        )
        for old, new, diagnostic in replacements:
            with self.subTest(diagnostic=diagnostic):
                changed = self.valid.replace(old, new, 1)
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    run_scalar_batch.validate_transcript(changed, self.descriptor)

    def test_results_must_have_ordered_case_ids_and_exact_type_tag(self) -> None:
        wrong_order = self.valid.replace(b"RESULT:0000000000000100", b"RESULT:0000000000000101", 1)
        with self.assertRaisesRegex(core0_common.Core0Error, "out of order"):
            run_scalar_batch.validate_transcript(wrong_order, self.descriptor)

        wrong_tag = self.valid.replace(b":0000000000000004:00000000000000a0", b":0000000000000003:00000000000000a0", 1)
        with self.assertRaisesRegex(core0_common.Core0Error, "type tag"):
            run_scalar_batch.validate_transcript(wrong_tag, self.descriptor)

    def test_narrow_result_values_cannot_hide_noncanonical_high_bits(self) -> None:
        for result_type, invalid_value, diagnostic in (
            ("bool", 2, "invalid Bool encoding"),
            ("u8", 256, "outside u8"),
            ("u32", 1 << 32, "outside u32"),
        ):
            with self.subTest(result_type=result_type):
                descriptor = run_scalar_batch.parse_descriptor(
                    descriptor_document(arg_types=[], result_type=result_type, case_count=1)
                )
                value = transcript(descriptor, [invalid_value])
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    run_scalar_batch.validate_transcript(value, descriptor)


class RunBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.image = self.artifacts / "image.elf"
        self.image.write_bytes(b"not-an-elf")
        (self.artifacts / "layout.json").write_text(
            json.dumps({"input": {"start": "0x81000000", "size": "0x1000"}}),
            encoding="utf-8",
        )
        self.output = self.root / "runs"
        self.descriptor = run_scalar_batch.parse_descriptor(descriptor_document())
        identity = {
            "suite_id": f"{self.descriptor.suite_id:016x}",
            "source_seed": f"{self.descriptor.source_seed:016x}",
            "runtime_seed": f"{self.descriptor.runtime_seed:016x}",
        }
        (self.artifacts / "scalar-suite-manifest.json").write_text(
            json.dumps(
                {
                    "artifact_category": "test-frontend-suite",
                    "contract_version": "core0-v0.1",
                    **identity,
                    "roots": [
                        {
                            "root_id": self.descriptor.root_id,
                            "source": self.descriptor.root,
                            "signature": {
                                "args": list(self.descriptor.signature.args),
                                "result": self.descriptor.signature.result,
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.artifacts / "scalar-test-abi.json").write_text(
            json.dumps(
                {
                    "name": "lemma-scalar-test-v1",
                    "contract_version": "core0-v0.1",
                    **identity,
                }
            ),
            encoding="utf-8",
        )
        (self.artifacts / "provenance.json").write_text(
            json.dumps({"artifact_category": "test-frontend-suite"}), encoding="utf-8"
        )
        (self.artifacts / "build.json").write_text(
            json.dumps(
                {
                    "artifact_category": "test-frontend-suite",
                    "artifacts": {
                        name: core0_common.sha256(self.artifacts / name)
                        for name in (
                            "image.elf",
                            "scalar-suite-manifest.json",
                            "scalar-test-abi.json",
                        )
                    },
                }
            ),
            encoding="utf-8",
        )
        self.valid = transcript(self.descriptor)
        self.stem = f"{self.descriptor.suite_id:016x}-{self.descriptor.batch_id:016x}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_with(self, result: core0_common.CommandResult) -> dict[str, object]:
        with mock.patch.object(run_scalar_batch, "require_tools", return_value={}), mock.patch.object(
            run_scalar_batch, "run_bounded", return_value=result
        ):
            return run_scalar_batch.run_batch(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                descriptor=self.descriptor,
                timeout_seconds=1.0,
            )

    def run_malformed_with(
        self,
        result: core0_common.CommandResult,
        *,
        raw_fixture: bytes | None = None,
        case_name: str = "bad-magic",
        announced: bool = False,
    ) -> dict[str, object]:
        fixture = raw_fixture
        if fixture is None:
            fixture = replace_u64(
                run_scalar_batch.pack_fixture(self.descriptor),
                0,
                0,
            )
        with mock.patch.object(run_scalar_batch, "require_tools", return_value={}), mock.patch.object(
            run_scalar_batch, "run_bounded", return_value=result
        ):
            return run_scalar_batch.run_malformed_fixture_for_test(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                binding_descriptor=self.descriptor,
                raw_fixture=fixture,
                case_name=case_name,
                announced=announced,
                timeout_seconds=1.0,
            )

    def test_success_writes_bound_fixture_transcript_and_run_record(self) -> None:
        record = self.run_with(
            core0_common.CommandResult(
                ("qemu-system-riscv64",), 0, self.valid, b"", 0.125
            )
        )
        fixture = self.output / f"input-{self.stem}.bin"
        run_record = self.output / f"run-{self.stem}.json"
        self.assertTrue(fixture.is_file())
        self.assertTrue(run_record.is_file())
        self.assertEqual(record["status"], "pass")
        self.assertEqual(record["descriptor"]["root"], self.descriptor.root)  # type: ignore[index]
        self.assertEqual(len(record["results"]), len(self.descriptor.cases))  # type: ignore[arg-type]
        self.assertIn("loader,file=", " ".join(record["qemu_argv"]))  # type: ignore[arg-type]
        run_scalar_batch.validate_fixture(fixture.read_bytes(), self.descriptor)

    def test_valid_uart_cannot_hide_nonzero_qemu_process_failure(self) -> None:
        failed = core0_common.CommandResult(
            ("qemu-system-riscv64",),
            7,
            self.valid,
            b"injected process failure",
            0.01,
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "QEMU process failure"):
            self.run_with(failed)
        self.assertTrue((self.output / f"uart-{self.stem}.bin").is_file())
        self.assertFalse((self.output / f"run-{self.stem}.json").exists())

    def test_failed_rerun_removes_stale_success_record(self) -> None:
        self.output.mkdir()
        stale = self.output / f"run-{self.stem}.json"
        stale.write_text('{"status":"pass"}\n', encoding="utf-8")
        failed = core0_common.CommandResult(
            ("qemu-system-riscv64",), 9, self.valid, b"later failure", 0.01
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "QEMU process failure"):
            self.run_with(failed)
        self.assertFalse(stale.exists())

    def test_invalid_descriptor_rerun_removes_stale_success_when_identity_is_usable(self) -> None:
        self.output.mkdir()
        stale = self.output / f"run-{self.stem}.json"
        stale.write_text('{"status":"pass"}\n', encoding="utf-8")
        first = self.descriptor.cases[0]
        wrong_result = "u8" if self.descriptor.signature.result != "u8" else "u64"
        invalid = run_scalar_batch.ScalarBatchDescriptor(
            self.descriptor.suite_id,
            self.descriptor.batch_id,
            self.descriptor.root,
            self.descriptor.root_id,
            self.descriptor.signature,
            self.descriptor.source_seed,
            self.descriptor.runtime_seed,
            (
                run_scalar_batch.ScalarCase(
                    first.case_id, first.args, wrong_result
                ),
            ),
        )
        with self.assertRaisesRegex(
            core0_common.Core0Error, "expected result type differs"
        ):
            run_scalar_batch.run_batch(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                descriptor=invalid,
                timeout_seconds=1.0,
            )
        self.assertFalse(stale.exists())

    def test_zero_exit_malformed_protocol_is_not_a_process_failure_or_success(self) -> None:
        malformed = core0_common.CommandResult(
            ("qemu-system-riscv64",), 0, self.valid[:-1], b"", 0.01
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "malformed or truncated"):
            self.run_with(malformed)
        self.assertFalse((self.output / f"run-{self.stem}.json").exists())

    def test_zero_exit_with_stderr_is_a_distinct_process_failure(self) -> None:
        noisy = core0_common.CommandResult(
            ("qemu-system-riscv64",), 0, self.valid, b"unexpected warning", 0.01
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "unexpected stderr"):
            self.run_with(noisy)
        self.assertFalse((self.output / f"run-{self.stem}.json").exists())

    def test_input_region_capacity_is_enforced_before_qemu(self) -> None:
        (self.artifacts / "layout.json").write_text(
            json.dumps({"input": {"start": "0x81000000", "size": "0x80"}}),
            encoding="utf-8",
        )
        with mock.patch.object(run_scalar_batch, "require_tools", return_value={}), mock.patch.object(
            run_scalar_batch, "run_bounded"
        ) as run:
            with self.assertRaisesRegex(core0_common.Core0Error, "exceeding input capacity"):
                run_scalar_batch.run_batch(
                    root=self.root,
                    image=self.image,
                    output_dir=self.output,
                    descriptor=self.descriptor,
                    timeout_seconds=1.0,
                )
            run.assert_not_called()

    def test_descriptor_source_identity_is_bound_to_image_root_id(self) -> None:
        forged = run_scalar_batch.ScalarBatchDescriptor(
            self.descriptor.suite_id,
            self.descriptor.batch_id,
            "Lemma.Examples.Foundation.Conformance.forgedRoot",
            self.descriptor.root_id,
            self.descriptor.signature,
            self.descriptor.source_seed,
            self.descriptor.runtime_seed,
            self.descriptor.cases,
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "identity/signature"):
            run_scalar_batch.validate_image_binding(self.image, forged)

    def test_structured_profile_category_is_bound_without_changing_wire_abi(self) -> None:
        manifest_path = self.artifacts / "scalar-suite-manifest.json"
        abi_path = self.artifacts / "scalar-test-abi.json"
        provenance_path = self.artifacts / "provenance.json"
        build_path = self.artifacts / "build.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        abi = json.loads(abi_path.read_text(encoding="utf-8"))
        manifest.update(
            artifact_category="test-cfg-suite", contract_version="core0-v0.2"
        )
        abi["contract_version"] = "core0-v0.2"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        abi_path.write_text(json.dumps(abi), encoding="utf-8")
        provenance_path.write_text(
            json.dumps({"artifact_category": "test-cfg-suite"}), encoding="utf-8"
        )
        build_path.write_text(
            json.dumps(
                {
                    "artifact_category": "test-cfg-suite",
                    "artifacts": {
                        name: core0_common.sha256(self.artifacts / name)
                        for name in (
                            "image.elf",
                            "scalar-suite-manifest.json",
                            "scalar-test-abi.json",
                        )
                    },
                }
            ),
            encoding="utf-8",
        )
        run_scalar_batch.validate_image_binding(self.image, self.descriptor)

        manifest["contract_version"] = "core0-v0.1"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(core0_common.Core0Error, "profile disagrees"):
            run_scalar_batch.validate_image_binding(self.image, self.descriptor)

    def test_legacy_scalar_abi_requires_its_exact_profile(self) -> None:
        abi_path = self.artifacts / "scalar-test-abi.json"
        abi = json.loads(abi_path.read_text(encoding="utf-8"))
        for profile in ("core0-v0.2", "core0-v9.9", None):
            with self.subTest(profile=profile):
                if profile is None:
                    abi.pop("contract_version", None)
                else:
                    abi["contract_version"] = profile
                abi_path.write_text(json.dumps(abi), encoding="utf-8")
                with self.assertRaisesRegex(core0_common.Core0Error, "profile disagrees"):
                    run_scalar_batch.validate_image_binding(self.image, self.descriptor)

    def test_test_only_raw_fixture_path_records_exact_guest_rejection(self) -> None:
        raw_fixture = replace_u64(run_scalar_batch.pack_fixture(self.descriptor), 0, 0)
        with self.assertRaisesRegex(core0_common.Core0Error, "wrong magic"):
            run_scalar_batch.parse_fixture(raw_fixture)

        record = self.run_malformed_with(
            core0_common.CommandResult(
                ("qemu-system-riscv64",),
                run_scalar_batch.GUEST_FAILURE_RETURNCODE,
                run_scalar_batch.TYPED_INPUT_ERROR,
                b"",
                0.025,
            ),
            raw_fixture=raw_fixture,
        )
        negative_stem = f"{self.stem}-bad-magic"
        fixture_path = self.output / f"malformed-input-{negative_stem}.bin"
        record_path = self.output / f"malformed-run-{negative_stem}.json"
        self.assertEqual(fixture_path.read_bytes(), raw_fixture)
        self.assertTrue(record_path.is_file())
        self.assertEqual(record["status"], "expected-guest-rejection")
        self.assertEqual(record["reason"], "typed-input")
        self.assertIs(record["announced"], False)
        self.assertEqual(record["qemu_returncode"], 1)
        self.assertEqual(record["uart"], "ERROR:TYPED-INPUT\n")
        argv = record["qemu_argv"]
        self.assertEqual(argv[0], "qemu-system-riscv64")  # type: ignore[index]
        self.assertIn("-bios", argv)  # type: ignore[operator]
        self.assertIn("none", argv)  # type: ignore[operator]
        self.assertIn("loader,file=", " ".join(argv))  # type: ignore[arg-type]

    def test_malformed_path_requires_exact_failure_exit_not_merely_nonzero(self) -> None:
        for returncode in (0, 2, 7, -9):
            with self.subTest(returncode=returncode):
                result = core0_common.CommandResult(
                    ("qemu-system-riscv64",),
                    returncode,
                    run_scalar_batch.TYPED_INPUT_ERROR,
                    b"",
                    0.01,
                )
                with self.assertRaisesRegex(
                    core0_common.Core0Error,
                    "exact guest failure termination",
                ):
                    self.run_malformed_with(result, case_name=f"exit-{returncode}")
                negative_stem = f"{self.stem}-exit-{returncode}"
                self.assertFalse(
                    (self.output / f"malformed-run-{negative_stem}.json").exists()
                )

    def test_malformed_path_rejects_misleading_or_noisy_uart_and_stderr(self) -> None:
        misleading = (
            self.valid,
            run_scalar_batch.TYPED_INPUT_ERROR + b"PASS\n",
            b"boot noise\n" + run_scalar_batch.TYPED_INPUT_ERROR,
            run_scalar_batch.TYPED_INPUT_ERROR.rstrip(b"\n"),
        )
        for index, stdout in enumerate(misleading):
            with self.subTest(index=index):
                result = core0_common.CommandResult(
                    ("qemu-system-riscv64",), 1, stdout, b"", 0.01
                )
                with self.assertRaisesRegex(core0_common.Core0Error, "misleading UART"):
                    self.run_malformed_with(result, case_name=f"uart-{index}")

        noisy = core0_common.CommandResult(
            ("qemu-system-riscv64",),
            1,
            run_scalar_batch.TYPED_INPUT_ERROR,
            b"host-side failure",
            0.01,
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "unexpected stderr"):
            self.run_malformed_with(noisy, case_name="stderr")

    def test_record_level_rejection_requires_exact_announcement_then_error(self) -> None:
        raw_fixture = replace_u64(
            run_scalar_batch.pack_fixture(self.descriptor),
            run_scalar_batch.HEADER_BYTES + (1 + 3) * 8,
            2,
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "invalid Bool encoding"):
            run_scalar_batch.parse_fixture(raw_fixture)
        expected = (
            "LEMMA_SCALAR/1\n"
            "BATCH:"
            f"{self.descriptor.suite_id:016x}:"
            f"{self.descriptor.batch_id:016x}:"
            f"{self.descriptor.root_id:016x}:"
            f"{len(self.descriptor.cases):016x}\n"
            "ERROR:TYPED-INPUT\n"
        ).encode("ascii")
        record = self.run_malformed_with(
            core0_common.CommandResult(
                ("qemu-system-riscv64",), 1, expected, b"", 0.01
            ),
            raw_fixture=raw_fixture,
            case_name="bad-bool",
            announced=True,
        )
        self.assertIs(record["announced"], True)
        self.assertEqual(record["uart"], expected.decode("ascii"))

        for suffix in (
            b"RESULT:0000000000000100:0000000000000004:0000000000000000\n",
            f"END:{self.descriptor.batch_id:016x}:0000000000000000\n".encode("ascii"),
        ):
            with self.subTest(suffix=suffix):
                misleading = expected[:-len(run_scalar_batch.TYPED_INPUT_ERROR)] + suffix + run_scalar_batch.TYPED_INPUT_ERROR
                with self.assertRaisesRegex(core0_common.Core0Error, "misleading UART"):
                    self.run_malformed_with(
                        core0_common.CommandResult(
                            ("qemu-system-riscv64",), 1, misleading, b"", 0.01
                        ),
                        raw_fixture=raw_fixture,
                        case_name="bad-bool-extra",
                        announced=True,
                    )

    def test_failed_malformed_rerun_invalidates_stale_expected_rejection(self) -> None:
        self.output.mkdir()
        stale = self.output / f"malformed-run-{self.stem}-stale.json"
        stale.write_text('{"status":"expected-guest-rejection"}\n', encoding="utf-8")
        wrong_exit = core0_common.CommandResult(
            ("qemu-system-riscv64",),
            0,
            run_scalar_batch.TYPED_INPUT_ERROR,
            b"",
            0.01,
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "exact guest failure termination"):
            self.run_malformed_with(wrong_exit, case_name="stale")
        self.assertFalse(stale.exists())

        stale_preflight = self.output / f"malformed-run-{self.stem}-stale-preflight.json"
        stale_preflight.write_text(
            '{"status":"expected-guest-rejection"}\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "valid fixture"):
            run_scalar_batch.run_malformed_fixture_for_test(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                binding_descriptor=self.descriptor,
                raw_fixture=run_scalar_batch.pack_fixture(self.descriptor),
                case_name="stale-preflight",
                announced=False,
                timeout_seconds=1.0,
            )
        self.assertFalse(stale_preflight.exists())

    def test_malformed_path_keeps_image_suite_binding_and_is_not_a_cli_mode(self) -> None:
        manifest_path = self.artifacts / "scalar-suite-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["suite_id"] = "0000000000000000"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.object(run_scalar_batch, "require_tools", return_value={}), mock.patch.object(
            run_scalar_batch, "run_bounded"
        ) as run:
            with self.assertRaisesRegex(core0_common.Core0Error, "image suite_id differs"):
                run_scalar_batch.run_malformed_fixture_for_test(
                    root=self.root,
                    image=self.image,
                    output_dir=self.output,
                    binding_descriptor=self.descriptor,
                    raw_fixture=b"bad",
                    case_name="bound-suite",
                    announced=False,
                    timeout_seconds=1.0,
                )
            run.assert_not_called()

        source = (ROOT / "scripts" / "run_scalar_batch.py").read_text(encoding="utf-8")
        main_source = source[source.index("def main()") :]
        self.assertNotIn("malformed", main_source)

    def test_malformed_path_refuses_valid_fixture_and_unsafe_case_name(self) -> None:
        valid_fixture = run_scalar_batch.pack_fixture(self.descriptor)
        with self.assertRaisesRegex(core0_common.Core0Error, "valid fixture"):
            run_scalar_batch.run_malformed_fixture_for_test(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                binding_descriptor=self.descriptor,
                raw_fixture=valid_fixture,
                case_name="valid",
                announced=False,
                timeout_seconds=1.0,
            )
        with self.assertRaisesRegex(core0_common.Core0Error, "case name"):
            run_scalar_batch.run_malformed_fixture_for_test(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                binding_descriptor=self.descriptor,
                raw_fixture=b"bad",
                case_name="../escape",
                announced=False,
                timeout_seconds=1.0,
            )


if __name__ == "__main__":
    unittest.main()
