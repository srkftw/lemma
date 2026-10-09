#!/usr/bin/env python3
"""Fail-closed tests for the Gate 5 one-case QEMU host boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import core0_common  # noqa: E402
import run_memory_case  # noqa: E402


def h(value: int) -> str:
    return f"0x{value:016x}"


def descriptor_document(
    *, arg_types: list[str] | None = None, args: list[int] | None = None
) -> dict[str, object]:
    types = ["u8", "u64"] if arg_types is None else arg_types
    values = [1, 0x20] if args is None else args
    return {
        "schema_version": 1,
        "test_abi": "lemma-memory-test-v1",
        "suite_id": h(0x5355495445303035),
        "case_id": h(0x31),
        "root": "Lemma.Examples.Foundation.Memory.load8Value",
        "root_id": h(1),
        "signature": {"args": types, "result": "checked-result-v1"},
        "source_seed": h(0x4C454D4D41353035),
        "runtime_seed": h(0x52554E54494D4535),
        "args": [h(value) for value in values],
    }


def transcript(
    descriptor: run_memory_case.MemoryCaseDescriptor,
    *, status: int = 0,
    value: int = 0xFEDCBA9876543210,
    regions: dict[int, bytes] | None = None,
) -> bytes:
    if regions is None:
        regions = {
            int(spec["id"]): run_memory_case.initial_region_bytes(
                descriptor, int(spec["id"])
            )
            for spec in run_memory_case.REGION_SPECS
        }
    lines = [
        "LEMMA_MEMORY/1",
        f"CASE:{descriptor.suite_id:016x}:{descriptor.case_id:016x}:{descriptor.root_id:016x}",
        f"OUTCOME:{descriptor.case_id:016x}:{status:016x}:{value:016x}",
    ]
    for spec in run_memory_case.REGION_SPECS:
        region_id = int(spec["id"])
        data = regions[region_id]
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
    return ("\n".join(lines) + "\n").encode("ascii")


def replace_u64(data: bytes, word: int, value: int) -> bytes:
    changed = bytearray(data)
    struct.pack_into("<Q", changed, word * 8, value)
    return bytes(changed)


class DescriptorAndControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.descriptor = run_memory_case.parse_descriptor(descriptor_document())

    def test_descriptor_schema_identity_signature_and_ranges_are_exact(self) -> None:
        self.assertEqual(self.descriptor.signature.args, ("u8", "u64"))
        self.assertEqual(self.descriptor.args, (1, 0x20))
        for mutation, diagnostic in (
            (lambda value: value.update(extra=True), "fields differ from schema"),
            (lambda value: value.update(schema_version=2), "unsupported schema"),
            (lambda value: value.update(schema_version=True), "unsupported schema"),
            (lambda value: value.update(root="not/a/Lean/name"), "Lean identity"),
            (lambda value: value["signature"].update(result="u64"), "result tag"),
            (lambda value: value.update(case_id=h(0)), "must be nonzero"),
        ):
            with self.subTest(diagnostic=diagnostic):
                document = descriptor_document()
                mutation(document)
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    run_memory_case.parse_descriptor(document)

        invalid = descriptor_document(arg_types=["bool"], args=[2])
        with self.assertRaisesRegex(core0_common.Core0Error, "invalid Bool encoding"):
            run_memory_case.parse_descriptor(invalid)
        invalid = descriptor_document(arg_types=["u8"], args=[256])
        with self.assertRaisesRegex(core0_common.Core0Error, "outside u8"):
            run_memory_case.parse_descriptor(invalid)

    def test_control_has_exact_magic_header_tags_slots_and_round_trip(self) -> None:
        control = run_memory_case.pack_control(self.descriptor)
        self.assertEqual(len(control), 256)
        self.assertEqual(control[:8], b"LEMMA005")
        words = struct.unpack("<16Q", control[:128])
        self.assertEqual(
            words,
            (
                run_memory_case.MAGIC_WORD,
                1,
                128,
                256,
                self.descriptor.suite_id,
                self.descriptor.case_id,
                self.descriptor.root_id,
                2,
                0x0402,
                0,
                self.descriptor.source_seed,
                self.descriptor.runtime_seed,
                0,
                0,
                0,
                0,
            ),
        )
        self.assertEqual(struct.unpack("<16Q", control[128:])[:2], self.descriptor.args)
        self.assertEqual(run_memory_case.parse_control(control).args, self.descriptor.args)

    def test_control_rejects_header_tag_slot_and_scalar_mutations(self) -> None:
        control = run_memory_case.pack_control(self.descriptor)
        for word, value, diagnostic in (
            (0, 0, "wrong magic"),
            (1, 2, "unsupported version"),
            (2, 120, "wrong size"),
            (3, 248, "wrong size"),
            (7, 17, "exceeds 16"),
            (8, 0x0400, "unknown type tag"),
            (12, 1, "reserved words"),
        ):
            with self.subTest(word=word):
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    run_memory_case.parse_control(replace_u64(control, word, value))
        with self.assertRaisesRegex(core0_common.Core0Error, "unused argument slots"):
            run_memory_case.parse_control(replace_u64(control, 16 + 2, 1))
        with self.assertRaisesRegex(core0_common.Core0Error, "exactly 256 bytes"):
            run_memory_case.parse_control(control[:-1])


class FixtureAndTranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.descriptor = run_memory_case.parse_descriptor(descriptor_document())

    def test_two_loader_blobs_cover_regions_control_and_all_ten_canaries(self) -> None:
        machine = run_memory_case.pack_machine_fixture(self.descriptor)
        input_blob = run_memory_case.pack_input_fixture(self.descriptor)
        self.assertEqual(len(machine), 0x16020)
        self.assertEqual(len(input_blob), 0x1020)
        for region in run_memory_case.REGION_SPECS:
            payload = run_memory_case.initial_region_bytes(self.descriptor, int(region["id"]))
            blob, fixture_start = (
                (input_blob, run_memory_case.INPUT_FIXTURE_START)
                if region["id"] == 2
                else (machine, run_memory_case.MACHINE_FIXTURE_START)
            )
            start = int(region["base"]) - fixture_start
            self.assertEqual(blob[start : start + len(payload)], payload)
        input_start = 0x81000000 - run_memory_case.INPUT_FIXTURE_START
        self.assertEqual(
            input_blob[input_start : input_start + run_memory_case.CONTROL_BYTES],
            run_memory_case.pack_control(self.descriptor),
        )
        expected = run_memory_case.canary_bytes(self.descriptor)
        for canary in run_memory_case.CANARY_SPECS:
            address = int(canary["address"])
            blob, fixture_start = (
                (machine, run_memory_case.MACHINE_FIXTURE_START)
                if address < run_memory_case.MACHINE_FIXTURE_STOP
                else (input_blob, run_memory_case.INPUT_FIXTURE_START)
            )
            start = address - fixture_start
            self.assertEqual(
                blob[start : start + run_memory_case.CANARY_SIZE],
                expected[str(canary["name"])],
            )

    def test_fixture_generation_is_deterministic_and_seed_bound(self) -> None:
        self.assertEqual(
            run_memory_case.pack_machine_fixture(self.descriptor),
            run_memory_case.pack_machine_fixture(self.descriptor),
        )
        document = descriptor_document()
        document["runtime_seed"] = h(self.descriptor.runtime_seed ^ 1)
        changed = run_memory_case.parse_descriptor(document)
        self.assertNotEqual(
            run_memory_case.pack_machine_fixture(self.descriptor),
            run_memory_case.pack_machine_fixture(changed),
        )
        self.assertNotEqual(
            run_memory_case.pack_input_fixture(self.descriptor),
            run_memory_case.pack_input_fixture(changed),
        )

    def test_exact_uart_schema_outcome_and_canaries_are_accepted(self) -> None:
        valid = transcript(self.descriptor, status=8, value=0xFFFFFFFFFFFFFFFF)
        outcome, regions, canaries = run_memory_case.validate_transcript(
            valid, self.descriptor
        )
        self.assertEqual(outcome, run_memory_case.MemoryOutcome(8, 0xFFFFFFFFFFFFFFFF))
        self.assertEqual(tuple(item.region_id for item in regions), (1, 2, 3, 4))
        self.assertEqual(sum(len(item.data) for item in regions), 4 * 4096)
        expected_digest = hashlib.sha256()
        for region in regions:
            expected_digest.update(bytes([region.region_id]))
            expected_digest.update(region.data)
        self.assertEqual(
            run_memory_case.final_memory_sha256(regions), expected_digest.hexdigest()
        )
        self.assertEqual(canaries, run_memory_case.expected_canary_words(self.descriptor))

    def test_noisy_truncated_uppercase_misordered_and_changed_canary_fail_closed(self) -> None:
        valid = transcript(self.descriptor)
        lines = valid.splitlines(keepends=True)
        canary_line = 3 + len(run_memory_case.REGION_SPECS)
        changed_canary = bytearray(lines[canary_line])
        changed_canary[11] = ord("1") if changed_canary[11] == ord("0") else ord("0")
        invalid = (
            b"",
            valid[:-1],
            b"noise\n" + valid,
            valid + b"extra\n",
            valid.upper(),
            valid.replace(b"\n", b"\r\n"),
            b"".join([*lines[:3], lines[4], lines[3], *lines[5:]]),
            valid.replace(lines[canary_line], bytes(changed_canary), 1),
        )
        for changed in invalid:
            with self.subTest(changed=changed[:48]):
                with self.assertRaises(core0_common.Core0Error):
                    run_memory_case.validate_transcript(changed, self.descriptor)

    def test_status_high_bits_and_identity_mismatches_fail_closed(self) -> None:
        high_status = transcript(self.descriptor, status=0x100)
        with self.assertRaisesRegex(core0_common.Core0Error, "nonzero high bits"):
            run_memory_case.validate_transcript(high_status, self.descriptor)
        with self.assertRaisesRegex(core0_common.Core0Error, "unknown status code"):
            run_memory_case.validate_transcript(
                transcript(self.descriptor, status=10), self.descriptor
            )
        valid = transcript(self.descriptor)
        changed = valid.replace(
            f"CASE:{self.descriptor.suite_id:016x}".encode(),
            b"CASE:0000000000000000",
            1,
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "identity"):
            run_memory_case.validate_transcript(changed, self.descriptor)


class RunMemoryCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()
        self.image = self.artifacts / "image.elf"
        self.image.write_bytes(b"not-an-elf")
        self.output = self.root / "runs"
        self.descriptor = run_memory_case.parse_descriptor(descriptor_document())
        identity = {
            "suite_id": f"{self.descriptor.suite_id:016x}",
            "source_seed": f"{self.descriptor.source_seed:016x}",
            "runtime_seed": f"{self.descriptor.runtime_seed:016x}",
        }
        manifest = {
            "artifact_category": "test-memory-suite",
            "contract_version": "core0-v0.4",
            "test_abi": "lemma-memory-test-v1",
            **identity,
            "memory_contract": run_memory_case.expected_memory_contract(),
            "roots": [
                {
                    "root_id": self.descriptor.root_id,
                    "source": self.descriptor.root,
                    "signature": {"args": list(self.descriptor.signature.args)},
                }
            ],
        }
        abi = run_memory_case.expected_test_abi(self.descriptor)
        (self.artifacts / "memory-suite-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (self.artifacts / "memory-test-abi.json").write_text(
            json.dumps(abi), encoding="utf-8"
        )
        (self.artifacts / "layout.json").write_text(
            json.dumps(run_memory_case.expected_machine_layout()), encoding="utf-8"
        )
        (self.artifacts / "memory-fixtures.json").write_text(
            json.dumps(run_memory_case.expected_fixture_contract()), encoding="utf-8"
        )
        (self.artifacts / "provenance.json").write_text(
            json.dumps({"artifact_category": "test-memory-suite"}), encoding="utf-8"
        )
        (self.artifacts / "build.json").write_text(
            json.dumps(
                {
                    "artifact_category": "test-memory-suite",
                    "artifacts": {
                        name: core0_common.sha256(self.artifacts / name)
                        for name in (
                            "image.elf",
                            "memory-suite-manifest.json",
                            "memory-test-abi.json",
                        )
                    },
                }
            ),
            encoding="utf-8",
        )
        self.valid = transcript(self.descriptor)
        self.stem = f"{self.descriptor.suite_id:016x}-{self.descriptor.case_id:016x}"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_with(self, result: core0_common.CommandResult) -> dict[str, object]:
        with mock.patch.object(run_memory_case, "require_tools", return_value={}), mock.patch.object(
            run_memory_case, "run_bounded", return_value=result
        ):
            return run_memory_case.run_case(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                descriptor=self.descriptor,
                timeout_seconds=1.0,
            )

    def test_success_writes_both_fixtures_uart_and_bound_run_record(self) -> None:
        record = self.run_with(
            core0_common.CommandResult(("qemu-system-riscv64",), 0, self.valid, b"", 0.125)
        )
        machine = self.output / f"machine-{self.stem}.bin"
        input_blob = self.output / f"input-{self.stem}.bin"
        run_record = self.output / f"run-{self.stem}.json"
        self.assertEqual(machine.stat().st_size, run_memory_case.MACHINE_FIXTURE_SIZE)
        self.assertEqual(input_blob.stat().st_size, run_memory_case.INPUT_FIXTURE_SIZE)
        self.assertTrue(run_record.is_file())
        argv = record["qemu_argv"]
        loaders = [item for item in argv if isinstance(item, str) and item.startswith("loader,file=")]
        self.assertEqual(len(loaders), 2)
        self.assertIn("addr=0x807efff0", loaders[0])
        self.assertIn("addr=0x80fffff0", loaders[1])
        self.assertEqual(record["status"], "pass")
        self.assertEqual(record["outcome"]["value"], "0xfedcba9876543210")
        self.assertEqual(record["post_state_bytes"], 4 * 4096)
        self.assertEqual(len(record["regions"]), 4)
        self.assertRegex(record["final_memory_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(record["canaries"]), 10)

    def test_process_protocol_and_stderr_failures_leave_no_success_record(self) -> None:
        failures = (
            (
                core0_common.CommandResult(
                    ("qemu-system-riscv64",), 7, self.valid, b"injected failure", 0.01
                ),
                "QEMU process failure",
            ),
            (
                core0_common.CommandResult(
                    ("qemu-system-riscv64",), 0, self.valid, b"unexpected warning", 0.01
                ),
                "unexpected stderr",
            ),
            (
                core0_common.CommandResult(
                    ("qemu-system-riscv64",), 0, self.valid[:-1], b"", 0.01
                ),
                "noisy, truncated",
            ),
        )
        for result, diagnostic in failures:
            with self.subTest(diagnostic=diagnostic):
                self.output.mkdir(exist_ok=True)
                stale = self.output / f"run-{self.stem}.json"
                stale.write_text('{"status":"pass"}\n', encoding="utf-8")
                with self.assertRaisesRegex(core0_common.Core0Error, diagnostic):
                    self.run_with(result)
                self.assertFalse(stale.exists())

    def test_image_identity_contract_signature_and_hashes_are_bound(self) -> None:
        run_memory_case.validate_image_binding(self.image, self.descriptor)
        manifest_path = self.artifacts / "memory-suite-manifest.json"
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        mutations = (
            lambda value: value.update(contract_version="core0-v0.3"),
            lambda value: value["memory_contract"].update(successful_access_volatile=False),
            lambda value: value["roots"][0].update(source="Lemma.Examples.Foundation.Memory.forged"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(original)
                mutation(changed)
                manifest_path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(core0_common.Core0Error):
                    run_memory_case.validate_image_binding(self.image, self.descriptor)
        manifest_path.write_text(json.dumps(original), encoding="utf-8")
        build = json.loads((self.artifacts / "build.json").read_text(encoding="utf-8"))
        build["artifacts"]["image.elf"] = "0" * 64
        (self.artifacts / "build.json").write_text(json.dumps(build), encoding="utf-8")
        with self.assertRaisesRegex(core0_common.Core0Error, "build hash"):
            run_memory_case.validate_image_binding(self.image, self.descriptor)

    def test_alternate_unbound_image_filename_is_rejected(self) -> None:
        alternate = self.artifacts / "alternate.elf"
        alternate.write_bytes(self.image.read_bytes())
        with self.assertRaisesRegex(core0_common.Core0Error, "bound image.elf"):
            run_memory_case.validate_image_binding(alternate, self.descriptor)

    def test_abi_machine_layout_and_fixture_layout_are_exactly_bound(self) -> None:
        abi_path = self.artifacts / "memory-test-abi.json"
        abi = json.loads(abi_path.read_text(encoding="utf-8"))
        abi["magic_bytes"] = "0000000000000000"
        abi_path.write_text(json.dumps(abi), encoding="utf-8")
        with self.assertRaisesRegex(core0_common.Core0Error, "test ABI differs"):
            run_memory_case.validate_image_binding(self.image, self.descriptor)
        abi_path.write_text(
            json.dumps(run_memory_case.expected_test_abi(self.descriptor)), encoding="utf-8"
        )

        layout_path = self.artifacts / "layout.json"
        layout = run_memory_case.expected_machine_layout()
        layout["input"]["start"] = "0x0000000081000008"
        layout_path.write_text(json.dumps(layout), encoding="utf-8")
        with self.assertRaisesRegex(core0_common.Core0Error, "Lem.*VM map"):
            run_memory_case.validate_image_binding(self.image, self.descriptor)
        layout_path.write_text(
            json.dumps(run_memory_case.expected_machine_layout()), encoding="utf-8"
        )

        fixture_path = self.artifacts / "memory-fixtures.json"
        fixtures = run_memory_case.expected_fixture_contract()
        fixtures["canaries"][0]["size"] = 8
        fixture_path.write_text(json.dumps(fixtures), encoding="utf-8")
        with self.assertRaisesRegex(core0_common.Core0Error, "fixture/canary"):
            run_memory_case.validate_image_binding(self.image, self.descriptor)

    def test_invalid_descriptor_rerun_removes_stale_success(self) -> None:
        self.output.mkdir()
        stale = self.output / f"run-{self.stem}.json"
        stale.write_text('{"status":"pass"}\n', encoding="utf-8")
        invalid = run_memory_case.MemoryCaseDescriptor(
            self.descriptor.suite_id,
            self.descriptor.case_id,
            self.descriptor.root,
            self.descriptor.root_id,
            self.descriptor.signature,
            self.descriptor.source_seed,
            self.descriptor.runtime_seed,
            (256, self.descriptor.args[1]),
        )
        with self.assertRaisesRegex(core0_common.Core0Error, "outside u8"):
            run_memory_case.run_case(
                root=self.root,
                image=self.image,
                output_dir=self.output,
                descriptor=invalid,
                timeout_seconds=1.0,
            )
        self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
