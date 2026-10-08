#!/usr/bin/env python3
"""Cumulative Gate 2 source/model/RV64 conformance acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from pathlib import Path
from typing import Callable, TypeVar

import audit_core0
import gate2_corpus
from build_core0 import invalidate_output_file, prepare_output_directory
from build_scalar_suite import build_scalar_suite
from core0_common import Core0Error, checked, load_json, run_bounded, sha256, write_json
from run_scalar_batch import (
    HEADER_BYTES,
    ScalarBatchDescriptor,
    load_descriptor,
    pack_fixture,
    run_batch,
    run_malformed_fixture_for_test,
    validate_fixture,
)


SOURCE_RESULT = re.compile(r"LEAN_TYPED_SOURCE:(\d+):(bool|u8|u32|u64):(\d+)")
MODEL_RESULT = re.compile(
    r"CORE0_TYPED_REFERENCE:([0-9a-f]{16}):(bool|u8|u32|u64):([0-9a-f]{16})"
)
T = TypeVar("T")


class Gate2Failure(Core0Error):
    def __init__(self, category: str, context: str, detail: str):
        self.category = category
        self.context = context
        self.detail = detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate2Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        raise Gate2Failure(category, context, str(error)) from error


def _hex(value: int) -> str:
    return f"0x{value:016x}"


def _run_host_driver(
    *, root: Path, source: Path, output_prefix: Path, execute: bool, timeout_seconds: float
) -> tuple[str, dict[str, object]]:
    relative = source.relative_to(root)
    argv = ["lake", "env", "lean"]
    if execute:
        argv.append("--run")
    argv.append(str(relative))
    result = checked(argv, cwd=root, timeout_seconds=timeout_seconds)
    stdout_path = output_prefix.with_suffix(".stdout")
    stderr_path = output_prefix.with_suffix(".stderr")
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    text = (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="strict")
    return text, {
        "argv": argv,
        "returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
        "source": str(relative),
        "source_sha256": sha256(source),
        "stdout": str(stdout_path.relative_to(root)),
        "stdout_sha256": sha256(stdout_path),
        "stderr": str(stderr_path.relative_to(root)),
        "stderr_sha256": sha256(stderr_path),
    }


def _parse_reference_results(
    text: str, *, source: bool, expected_ids: set[int]
) -> dict[int, tuple[str, int]]:
    matches = SOURCE_RESULT.findall(text) if source else MODEL_RESULT.findall(text)
    if len(matches) != len(expected_ids):
        label = "direct source" if source else "checked model"
        raise Core0Error(
            f"{label} emitted {len(matches)} typed records; expected {len(expected_ids)}"
        )
    results: dict[int, tuple[str, int]] = {}
    limits = {"bool": 1, "u8": 0xFF, "u32": 0xFFFFFFFF, "u64": 0xFFFFFFFFFFFFFFFF}
    for raw_id, tag, raw_value in matches:
        case_id = int(raw_id, 10 if source else 16)
        value = int(raw_value, 10 if source else 16)
        if case_id in results:
            raise Core0Error(f"duplicate reference result for case {_hex(case_id)}")
        if value > limits[tag]:
            raise Core0Error(f"reference result for case {_hex(case_id)} is outside {tag}")
        results[case_id] = (tag, value)
    if set(results) != expected_ids:
        raise Core0Error("reference output case IDs differ from the exact corpus")
    return results


def _corpus_cases(corpus: dict[str, object]) -> dict[int, tuple[str, tuple[int, ...], str]]:
    cases = corpus.get("cases")
    assert isinstance(cases, list)
    result: dict[int, tuple[str, tuple[int, ...], str]] = {}
    for item in cases:
        assert isinstance(item, dict)
        arguments = item["args"]
        assert isinstance(arguments, list)
        values = tuple(int(str(argument["value"]), 16) for argument in arguments)
        case_id = int(str(item["case_id"]), 16)
        result[case_id] = (
            str(item["root"]),
            values,
            str(item["expected_result_type"]),
        )
    return result


def _manifest_root_map(manifest: object) -> dict[str, tuple[int, tuple[str, ...], str]]:
    if not isinstance(manifest, dict):
        raise Core0Error("scalar suite manifest is not an object")
    roots = manifest.get("roots")
    if not isinstance(roots, list):
        raise Core0Error("scalar suite manifest has no root array")
    result: dict[str, tuple[int, tuple[str, ...], str]] = {}
    for item in roots:
        if not isinstance(item, dict) or not isinstance(item.get("signature"), dict):
            raise Core0Error("scalar suite manifest has a malformed root row")
        source = item.get("source")
        root_id = item.get("root_id")
        signature = item["signature"]
        args, return_type = signature.get("args"), signature.get("result")
        if (
            not isinstance(source, str)
            or isinstance(root_id, bool)
            or not isinstance(root_id, int)
            or not isinstance(args, list)
            or any(not isinstance(arg, str) for arg in args)
            or not isinstance(return_type, str)
            or source in result
        ):
            raise Core0Error("scalar suite manifest root identity/signature is malformed")
        result[source] = (root_id, tuple(args), return_type)
    return result


def _verify_profile_source_identity(
    *, root: Path, outputs: dict[str, Path], manifests: dict[str, object]
) -> dict[str, object]:
    """Require O0/O2 to originate from one exact checked source snapshot."""
    if set(outputs) != {"O0", "O2"} or set(manifests) != {"O0", "O2"}:
        raise Core0Error("profile source-identity check requires exact O0/O2 inputs")
    if manifests["O0"] != manifests["O2"]:
        raise Core0Error("O0/O2 scalar suite manifests are not identical")

    file_names = (
        "scalar-suite-manifest.json",
        "scalar-suite-normalized.txt",
        "scalar-test-abi.json",
        "symbols.txt",
    )
    file_hashes: dict[str, str] = {}
    for name in file_names:
        left = sha256(outputs["O0"] / name)
        right = sha256(outputs["O2"] / name)
        if left != right:
            raise Core0Error(f"O0/O2 checked source artifact differs: {name}")
        file_hashes[name] = left

    provenances = {
        profile: load_json(output / "provenance.json")
        for profile, output in outputs.items()
    }
    if any(not isinstance(value, dict) for value in provenances.values()):
        raise Core0Error("O0/O2 provenance is not an object")
    identity_fields = (
        "artifact_category",
        "source_commit",
        "dirty_tree",
        "dirty_paths",
        "compiler_route",
        "target",
        "source_inputs",
        "elaborated_inputs",
        "export_configuration",
    )
    differing = [
        field
        for field in identity_fields
        if provenances["O0"].get(field) != provenances["O2"].get(field)
    ]
    if differing:
        raise Core0Error(
            "O0/O2 provenance does not identify one source snapshot: "
            + ", ".join(differing)
        )
    return {
        "profiles": ["O0", "O2"],
        "identical_checked_source_artifacts": file_hashes,
        "identical_provenance_fields": list(identity_fields),
        "source_commit": provenances["O0"]["source_commit"],
        "dirty_tree": provenances["O0"]["dirty_tree"],
    }


def _load_batches(
    *, corpus_dir: Path, manifest: object, expected_cases: dict[int, tuple[str, tuple[int, ...], str]]
) -> tuple[ScalarBatchDescriptor, ...]:
    root_map = _manifest_root_map(manifest)
    paths = sorted((corpus_dir / "batches").glob("batch-*.json"))
    if not paths:
        raise Core0Error("Gate 2 generated no scalar batch descriptors")
    descriptors: list[ScalarBatchDescriptor] = []
    observed_cases: set[int] = set()
    observed_batches: set[int] = set()
    for path in paths:
        descriptor = load_descriptor(path)
        if descriptor.batch_id in observed_batches:
            raise Core0Error(f"duplicate scalar batch ID {_hex(descriptor.batch_id)}")
        observed_batches.add(descriptor.batch_id)
        expected_root = root_map.get(descriptor.root)
        if expected_root is None:
            raise Core0Error(f"batch selects root absent from manifest: {descriptor.root}")
        manifest_id, manifest_args, manifest_result = expected_root
        if (
            descriptor.root_id != manifest_id
            or descriptor.signature.args != manifest_args
            or descriptor.signature.result != manifest_result
        ):
            raise Core0Error(f"batch signature/root ID differs from manifest: {descriptor.root}")
        for case in descriptor.cases:
            if case.case_id in observed_cases:
                raise Core0Error(f"case {_hex(case.case_id)} occurs in more than one batch")
            observed_cases.add(case.case_id)
            expected = expected_cases.get(case.case_id)
            if expected != (descriptor.root, case.args, case.expected_result_type):
                raise Core0Error(
                    f"batch record for case {_hex(case.case_id)} differs from the source corpus"
                )
        descriptors.append(descriptor)
    if observed_cases != set(expected_cases):
        raise Core0Error("scalar batches do not cover the complete 1,024-case corpus")
    if observed_batches != set(range(1, len(descriptors) + 1)):
        raise Core0Error("scalar batch IDs are not the canonical contiguous sequence")
    return tuple(descriptors)


def _result_digest(results: dict[int, tuple[str, int]]) -> str:
    digest = hashlib.sha256()
    for case_id in sorted(results):
        tag, value = results[case_id]
        digest.update(f"{case_id:016x}:{tag}:{value:016x}\n".encode("ascii"))
    return digest.hexdigest()


def _replace_u64(data: bytes, offset: int, value: int) -> bytes:
    if offset < 0 or offset + 8 > len(data) or offset % 8 != 0:
        raise Core0Error(f"invalid malformed-fixture UInt64 offset {offset}")
    if value < 0 or value >= 1 << 64:
        raise Core0Error(f"malformed-fixture replacement is outside UInt64: {value}")
    result = bytearray(data)
    struct.pack_into("<Q", result, offset, value)
    return bytes(result)


def _malformed_fixture_matrix(
    descriptors: tuple[ScalarBatchDescriptor, ...],
) -> tuple[tuple[str, ScalarBatchDescriptor, bytes, bool, str], ...]:
    by_root: dict[str, ScalarBatchDescriptor] = {}
    for descriptor in descriptors:
        by_root.setdefault(descriptor.root, descriptor)

    base = "Lemma.Examples.Foundation.Conformance"
    required = {
        "constant": f"{base}.constantU64",
        "bool": f"{base}.boolEq",
        "u8": f"{base}.u8Add",
        "u32": f"{base}.u32Arithmetic",
    }
    missing = [name for name, root_name in required.items() if root_name not in by_root]
    if missing:
        raise Core0Error(
            "malformed-fixture matrix lacks required binding roots: " + ", ".join(missing)
        )

    constant = by_root[required["constant"]]
    boolean = by_root[required["bool"]]
    u8 = by_root[required["u8"]]
    u32 = by_root[required["u32"]]
    constant_fixture = pack_fixture(constant)
    bool_fixture = pack_fixture(boolean)
    u8_fixture = pack_fixture(u8)
    u32_fixture = pack_fixture(u32)
    bool_tags = struct.unpack_from("<Q", bool_fixture, 10 * 8)[0]

    candidates: tuple[tuple[str, ScalarBatchDescriptor, bytes, bool], ...] = (
        (
            "inconsistent-suite-id",
            boolean,
            _replace_u64(bool_fixture, 4 * 8, boolean.suite_id ^ 1),
            False,
        ),
        (
            "excess-argument-count",
            boolean,
            _replace_u64(bool_fixture, 8 * 8, 17),
            False,
        ),
        (
            "argument-tag-mismatch",
            boolean,
            _replace_u64(bool_fixture, 10 * 8, (bool_tags & ~0xFF) | 2),
            False,
        ),
        (
            "invalid-bool-encoding",
            boolean,
            _replace_u64(bool_fixture, HEADER_BYTES + 8, 2),
            True,
        ),
        (
            "u8-out-of-range-before-truncation",
            u8,
            _replace_u64(u8_fixture, HEADER_BYTES + 8, 1 << 8),
            True,
        ),
        (
            "u32-out-of-range-before-truncation",
            u32,
            _replace_u64(u32_fixture, HEADER_BYTES + 8, 1 << 32),
            True,
        ),
        (
            "nonzero-unused-slot",
            constant,
            _replace_u64(constant_fixture, HEADER_BYTES + 8, 1),
            True,
        ),
    )
    checked_cases: list[tuple[str, ScalarBatchDescriptor, bytes, bool, str]] = []
    for name, descriptor, raw_fixture, announced in candidates:
        try:
            validate_fixture(raw_fixture, descriptor)
        except Core0Error as error:
            checked_cases.append(
                (name, descriptor, raw_fixture, announced, str(error))
            )
        else:
            raise Core0Error(
                f"malformed-fixture case {name} was accepted by the strict host decoder"
            )
    return tuple(checked_cases)


def _check_metamorphic(
    corpus: dict[str, object], cases: dict[int, tuple[str, tuple[int, ...], str]],
    results: dict[int, tuple[str, int]]
) -> list[dict[str, object]]:
    by_root: dict[str, dict[tuple[int, ...], tuple[str, int]]] = {}
    for case_id, (root_name, arguments, _result_type) in cases.items():
        by_root.setdefault(root_name, {})[arguments] = results[case_id]
    pairs = corpus.get("metamorphic_pairs")
    assert isinstance(pairs, list)
    records: list[dict[str, object]] = []
    for pair in pairs:
        assert isinstance(pair, dict)
        name, left, right = str(pair["name"]), str(pair["left"]), str(pair["right"])
        if by_root.get(left) != by_root.get(right):
            raise Core0Error(f"metamorphic pair {name} changed observable results")
        records.append({"name": name, "left": left, "right": right, "cases": len(by_root[left])})
    return records


def _check_excess_argument_rejection(
    *, root: Path, work: Path, suite_id: int, source_seed: int,
    runtime_seed: int, timeout_seconds: float
) -> dict[str, object]:
    fixture = root / "examples/foundation/gate2-reject/TooManySuiteArgs.lean"
    output = work / "rejections" / "too-many-suite-args"
    environment = os.environ.copy()
    environment.update(
        {
            "LEMMA_CORE0_OUT": str(output),
            "LEMMA_SCALAR_SUITE_ID": str(suite_id),
            "LEMMA_SCALAR_SOURCE_SEED": str(source_seed),
            "LEMMA_SCALAR_RUNTIME_SEED": str(runtime_seed),
        }
    )
    argv = ["lake", "env", "lean", str(fixture.relative_to(root))]
    result = run_bounded(argv, cwd=root, timeout_seconds=timeout_seconds, env=environment)
    log_dir = work / "rejections"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "too-many-suite-args.stdout"
    stderr_path = log_dir / "too-many-suite-args.stderr"
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    diagnostic = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    required = (
        "typed scalar suite root `tooManySuiteArgs` has 17 arguments",
        "lemma-scalar-test-v1 maximum is 16",
    )
    if result.returncode == 0 or any(fragment not in diagnostic for fragment in required):
        raise Core0Error(
            "excess-argument suite fixture did not fail for the exact ABI-limit diagnostic"
        )
    if (output / "program.ll").exists():
        raise Core0Error("excess-argument suite rejection emitted target LLVM")
    return {
        "fixture": str(fixture.relative_to(root)),
        "fixture_sha256": sha256(fixture),
        "argv": argv,
        "returncode": result.returncode,
        "required_diagnostic": list(required),
        "stdout": str(stdout_path.relative_to(root)),
        "stdout_sha256": sha256(stdout_path),
        "stderr": str(stderr_path.relative_to(root)),
        "stderr_sha256": sha256(stderr_path),
    }


def check_gate2(
    *, root: Path, work: Path, clean: bool, timeout_seconds: float,
    qemu_timeout: float
) -> dict[str, object]:
    # A failed rerun must never leave an earlier PASS record at the canonical
    # result path, including failures that happen before directory preparation.
    invalidate_output_file(work / "gate2-results.json", root)
    prepare_output_directory(work, root, clean=clean)
    corpus_dir = work / "corpus"
    corpus = _stage("corpus-generation-failure", "typed-corpus", lambda: gate2_corpus.generate(corpus_dir))
    assert isinstance(corpus, dict)
    gate2_corpus.validate_corpus(corpus)
    source_seed = int(str(corpus["source_seed"]), 16)
    runtime_seed = int(str(corpus["runtime_seed"]), 16)
    suite_id = int(str(corpus["suite_id"]), 16)
    expected_cases = _corpus_cases(corpus)
    expected_ids = set(expected_cases)

    profile_records: dict[str, dict[str, object]] = {}
    manifests: dict[str, object] = {}
    outputs: dict[str, Path] = {}
    for index, profile in enumerate(("O0", "O2")):
        output = work / profile
        outputs[profile] = output
        build_record = _stage(
            "compile-or-link-failure",
            profile,
            lambda profile=profile, output=output, index=index: build_scalar_suite(
                root=root,
                output_dir=output,
                opt_level=profile,
                suite_id=suite_id,
                source_seed=source_seed,
                runtime_seed=runtime_seed,
                clean=False,
                build_lean=index == 0,
                timeout_seconds=timeout_seconds,
            ),
        )
        manifest = load_json(output / "scalar-suite-manifest.json")
        manifests[profile] = manifest
        if not isinstance(manifest, dict):
            raise Gate2Failure("manifest-rejection", profile, "manifest is not an object")
        expected_hex = f"{suite_id:016x}"
        if (
            manifest.get("suite_id") != expected_hex
            or manifest.get("source_seed") != f"{source_seed:016x}"
            or manifest.get("runtime_seed") != f"{runtime_seed:016x}"
        ):
            raise Gate2Failure("manifest-rejection", profile, "manifest seeds/suite differ from corpus")
        audit_record = _stage(
            "provenance-or-closure-rejection",
            profile,
            lambda output=output: audit_core0.audit(
                output, root, policy="test-frontend-suite"
            ),
        )
        profile_records[profile] = {
            "build": build_record,
            "audit": audit_record,
        }

    profile_source_identity = _stage(
        "profile-source-identity-rejection",
        "O0/O2",
        lambda: _verify_profile_source_identity(
            root=root, outputs=outputs, manifests=manifests
        ),
    )

    direct_text, direct_command = _stage(
        "direct-source-evaluation-failure",
        "direct-source",
        lambda: _run_host_driver(
            root=root,
            source=corpus_dir / "DirectEval.lean",
            output_prefix=work / "direct-source",
            execute=True,
            timeout_seconds=timeout_seconds,
        ),
    )
    model_text, model_command = _stage(
        "checked-model-evaluation-failure",
        "checked-model",
        lambda: _run_host_driver(
            root=root,
            source=corpus_dir / "ModelEval.lean",
            output_prefix=work / "checked-model",
            execute=False,
            timeout_seconds=timeout_seconds,
        ),
    )
    direct_results = _parse_reference_results(direct_text, source=True, expected_ids=expected_ids)
    model_results = _parse_reference_results(model_text, source=False, expected_ids=expected_ids)
    if direct_results != model_results:
        mismatch = next(
            case_id for case_id in sorted(expected_ids)
            if direct_results[case_id] != model_results[case_id]
        )
        root_name, arguments, _ = expected_cases[mismatch]
        raise Gate2Failure(
            "frontend-or-model-mismatch",
            _hex(mismatch),
            f"root={root_name}, args={arguments!r}, "
            f"direct={direct_results[mismatch]!r}, model={model_results[mismatch]!r}",
        )

    rejection = _stage(
        "intended-source-rejection-failure",
        "excess-arguments",
        lambda: _check_excess_argument_rejection(
            root=root,
            work=work,
            suite_id=suite_id,
            source_seed=source_seed,
            runtime_seed=runtime_seed,
            timeout_seconds=timeout_seconds,
        ),
    )

    descriptors = _load_batches(
        corpus_dir=corpus_dir,
        manifest=manifests["O0"],
        expected_cases=expected_cases,
    )
    if _manifest_root_map(manifests["O0"]) != _manifest_root_map(manifests["O2"]):
        raise Gate2Failure("manifest-rejection", "O0/O2", "root manifests differ")
    malformed_cases = _stage(
        "typed-input-negative-generation-failure",
        "closed-matrix",
        lambda: _malformed_fixture_matrix(descriptors),
    )

    for profile in ("O0", "O2"):
        target_results: dict[int, tuple[str, int]] = {}
        run_records: list[dict[str, object]] = []
        for descriptor in descriptors:
            record = _stage(
                "target-execution-failure",
                f"{profile}/batch-{descriptor.batch_id}",
                lambda descriptor=descriptor, profile=profile: run_batch(
                    root=root,
                    image=work / profile / "image.elf",
                    output_dir=work / profile / "runs",
                    descriptor=descriptor,
                    timeout_seconds=qemu_timeout,
                ),
            )
            run_records.append(record)
            values = record.get("results")
            assert isinstance(values, list)
            for value in values:
                assert isinstance(value, dict)
                case_id = int(str(value["case_id"]), 16)
                if case_id in target_results:
                    raise Gate2Failure("protocol-failure", profile, f"duplicate case {_hex(case_id)}")
                target_results[case_id] = (
                    str(value["result_type"]), int(str(value["value"]), 16)
                )
        if set(target_results) != expected_ids:
            raise Gate2Failure("protocol-failure", profile, "target result IDs differ from corpus")
        if target_results != direct_results:
            mismatch = next(
                case_id for case_id in sorted(expected_ids)
                if target_results[case_id] != direct_results[case_id]
            )
            root_name, arguments, _ = expected_cases[mismatch]
            raise Gate2Failure(
                "lowering-or-codegen-mismatch",
                f"{profile}/{_hex(mismatch)}",
                f"root={root_name}, args={arguments!r}, source={direct_results[mismatch]!r}, target={target_results[mismatch]!r}",
            )
        profile_records[profile]["target"] = {
            "qemu_boots": len(descriptors),
            "case_count": len(target_results),
            "result_sha256": _result_digest(target_results),
            "run_records": [
                {
                    "batch_id": record["descriptor"]["batch_id"],
                    "root": record["descriptor"]["root"],
                    "cases": len(record["results"]),
                    "uart_sha256": record["uart_sha256"],
                }
                for record in run_records
            ],
        }
        negative_run_dir = work / profile / "malformed-runs"
        negative_records: list[dict[str, object]] = []
        for name, descriptor, raw_fixture, announced, host_rejection in malformed_cases:
            record = _stage(
                "typed-input-guest-rejection-failure",
                f"{profile}/{name}",
                lambda descriptor=descriptor, raw_fixture=raw_fixture,
                name=name, announced=announced, profile=profile: (
                    run_malformed_fixture_for_test(
                        root=root,
                        image=work / profile / "image.elf",
                        output_dir=negative_run_dir,
                        binding_descriptor=descriptor,
                        raw_fixture=raw_fixture,
                        case_name=name,
                        announced=announced,
                        timeout_seconds=qemu_timeout,
                    )
                ),
            )
            record_path = negative_run_dir / (
                "malformed-run-"
                f"{descriptor.suite_id:016x}-{descriptor.batch_id:016x}-{name}.json"
            )
            negative_records.append(
                {
                    "case": name,
                    "binding_root": descriptor.root,
                    "announced_before_rejection": announced,
                    "host_rejection": host_rejection,
                    "guest_status": record["status"],
                    "qemu_returncode": record["qemu_returncode"],
                    "fixture_sha256": record["fixture_sha256"],
                    "uart_sha256": record["uart_sha256"],
                    "run_record": str(record_path.relative_to(root)),
                    "run_record_sha256": sha256(record_path),
                }
            )
        profile_records[profile]["typed_input_rejections"] = {
            "qemu_boots": len(negative_records),
            "exact_guest_rejections": len(negative_records),
            "cases": negative_records,
        }

    metamorphic = _check_metamorphic(corpus, expected_cases, direct_results)
    from check_gate2_exhaustive import run_exhaustive

    exhaustive = _stage(
        "exhaustive-source-model-failure",
        "UInt8-pairs",
        lambda: run_exhaustive(root=root, output_dir=work / "exhaustive", timeout_seconds=timeout_seconds),
    )
    source_commit = str(load_json(work / "O0" / "provenance.json")["source_commit"])
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "gate": 2,
        "source_commit": source_commit,
        "contract_version": "core0-v0.1",
        "test_abi": gate2_corpus.TEST_ABI,
        "suite_id": corpus["suite_id"],
        "seeds": {
            "source_generation": corpus["source_seed"],
            "runtime_inputs": corpus["runtime_seed"],
            "algorithm": "SplitMix64-v1 with fixed typed boundary pools",
        },
        "corpus": {
            "path": str((corpus_dir / "gate2-cases.json").relative_to(root)),
            "sha256": sha256(corpus_dir / "gate2-cases.json"),
            "roots": len(corpus["roots"]),
            "distinct_cases_per_profile": len(expected_cases),
            "batches_per_profile": len(descriptors),
        },
        "comparisons": {
            "direct_source": {
                "cases": len(direct_results),
                "result_sha256": _result_digest(direct_results),
                "command": direct_command,
            },
            "checked_core0_model": {
                "cases": len(model_results),
                "result_sha256": _result_digest(model_results),
                "command": model_command,
            },
            "shared_assumption": (
                "direct and model paths share the pinned Lean elaborator/type checker; "
                "the direct path does not import or call the Core0 checker/evaluator"
            ),
        },
        "profiles": profile_records,
        "profile_source_identity": profile_source_identity,
        "metamorphic": metamorphic,
        "exhaustive_u8": exhaustive,
        "negative_cases": {
            "source_rejections": [rejection],
            "typed_input_guest_matrix": {
                "cases_per_profile": len(malformed_cases),
                "profiles": ["O0", "O2"],
                "required_uart_terminal": "ERROR:TYPED-INPUT\\n",
                "required_qemu_returncode": 1,
            },
        },
        "counts": {
            "roots": len(corpus["roots"]),
            "cases_per_profile": len(expected_cases),
            "valid_qemu_boots_per_profile": len(descriptors),
            "typed_input_rejection_boots_per_profile": len(malformed_cases),
            "qemu_boots_per_profile": len(descriptors) + len(malformed_cases),
            "qemu_boots_total": (len(descriptors) + len(malformed_cases)) * 2,
            "direct_source_model_matches": len(expected_cases),
            "source_model_target_matches": len(expected_cases) * 2,
            "metamorphic_pairs": len(metamorphic),
        },
        "limitations": [
            "Finite and exhaustive subdomain tests are evidence, not a compiler-correctness proof.",
            "The typed suite remains Core0 v0.1 and introduces no managed Lean runtime.",
            "This gate does not complete G1 or G2.",
        ],
    }
    write_json(work / "gate2-results.json", report)
    return report
