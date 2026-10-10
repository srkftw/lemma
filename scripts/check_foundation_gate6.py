#!/usr/bin/env python3
"""Cumulative Gate 6 compiled-device source/model/RV64 acceptance.

The driver builds the closed ``core0-v0.5`` device suite at O0 and O2,
performs the generic object/ELF closure audit and the independent ordered-MMIO
audit, then executes every closed UART scenario against a live QEMU process.
It also checks the exact frontend rejections, executable Lean device models,
and the local device theorem dependencies.  A PASS report is installed only
after every required check succeeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import audit_core0
import audit_device
import gate6_corpus
import run_device_session
from build_core0 import invalidate_output_file, prepare_output_directory
from build_device_suite import build_device_suite
from check_foundation_gate2 import _run_host_driver
from core0_common import Core0Error, load_json, repo_root, run_bounded, sha256, write_json


T = TypeVar("T")

RESULT_FILE = "gate6-results.json"
CORPUS_FILE = "gate6-scenarios.json"

ARTIFACT_FILES = (
    "image.elf",
    "image.map",
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "layout.json",
    "device-contract.json",
    "device-suite-manifest.json",
    "device-suite-normalized.txt",
    "device-test-abi.json",
    "symbols.txt",
    "platform.dtb",
    "platform.dts",
    "provenance.json",
    "build.json",
    "audit.json",
    "sha256sums.txt",
    "program.o.stack-sizes.txt",
    "disassembly.txt",
)

BUILD_HASHED_ARTIFACTS = (
    "device-contract.json",
    "device-suite-manifest.json",
    "device-suite-normalized.txt",
    "device-test-abi.json",
    "image.elf",
    "image.map",
    "layout.json",
    "link.ld",
    "platform.dtb",
    "platform.dts",
    "program.ll",
    "program.o",
    "program.opt.ll",
    "provenance.json",
    "startup.S",
    "startup.o",
    "symbols.txt",
)

# These artifacts are emitted directly from the same elaborated and checked
# source envelope.  Optimization-specific IR/object/ELF outputs are audited
# separately and deliberately excluded from this byte-identity set.
CHECKED_SOURCE_ARTIFACTS = (
    "program.ll",
    "startup.S",
    "link.ld",
    "layout.json",
    "device-contract.json",
    "device-suite-manifest.json",
    "device-suite-normalized.txt",
    "device-test-abi.json",
    "symbols.txt",
)

REJECTION_FILES = (
    "V04Device.lean",
    "OverDeviceBudget.lean",
    "StoredDeviceContinuation.lean",
    "HiddenExternDevice.lean",
    "PureDeviceResult.lean",
)

DEVICE_LEMMAS = (
    "empty_write_has_ordered_events",
    "fifo_reset_discards_pending_rx",
    "fifo_reset_is_ordered",
    "response_size",
)
DEVICE_LEMMA_NAMESPACE = "Lemma.Core0.Device.Model"

PINNED_DEVICE_PROBES = (
    "catalog",
    "fifo-reset-status",
    "fifo-reset-discards-rx",
    "fifo-reset-ordered",
    "rx-consumes",
    "rx-scripted-delay",
    "rx-timeout",
    "line-error-cleared-by-lsr",
    "lsr-clears-only-break-overrun",
    "tx-scripted-ready",
    "tx-timeout",
    "drain-requires-temt",
)

DEVICE_MODEL_PROBES = (
    "add64-wrap",
    "unsupported-recovers",
    "false-branch-only-ram",
    "true-branch-only-uart",
    "invalid-bool-terminal",
    "bounded-stress",
    "empty-timeout",
    "truncated-header",
    "invalid-length",
    "malformed-magic",
    "compiled-ready-bytes",
    "source-model-response-encoding",
    "response-size",
)

BRANCH_INITIAL_MARKER = 0x3C
BRANCH_FALSE_MARKER = 0x5A
BRANCH_FALSE_RESPONSE = 0x5A00
BRANCH_TRUE_RESPONSE = 0x3C01
BRANCH_REQUEST_IDS = (0x2001, 0x2002)

REQUIRED_DEVICE_MUTATIONS = frozenset(
    {
        "duplicate-device-op",
        "stale-transitive-effects",
        "wrong-manifest-device-address",
        "misplaced-branch-effects",
        "wrong-device-address",
        "wrong-device-width",
        "nonvolatile-device-access",
        "missing-before-fence",
        "reordered-before-fence",
        "duplicate-site-id",
        "duplicate-physical-device-operation",
        "misplaced-pre-branch-effects",
        "optimized-wrong-device-address",
        "optimized-nonvolatile-device-access",
        "optimized-missing-before-fence",
        "optimized-invalid-device-alignment",
        "optimized-duplicate-physical-device-operation",
        "misplaced-post-branch-effects",
    }
)


class Gate6Failure(Core0Error):
    """One classified Gate 6 acceptance failure."""

    def __init__(self, category: str, context: str, detail: str):
        self.category = category
        self.context = context
        self.detail = detail
        super().__init__(f"{category}[{context}]: {detail}")


def _stage(category: str, context: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except Gate6Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError, UnicodeError) as error:
        raise Gate6Failure(category, context, str(error)) from error


def _target_stage(
    profile: str, scenario: str, action: Callable[[], T]
) -> T:
    context = f"{profile}/{scenario}"
    try:
        return action()
    except Gate6Failure:
        raise
    except (Core0Error, OSError, ValueError, json.JSONDecodeError, UnicodeError) as error:
        detail = str(error)
        lowered = detail.lower()
        if "timed out" in lowered:
            category = "target-timeout"
        elif any(
            marker in lowered
            for marker in (
                "ready frame",
                "response differs",
                "prefix differs",
                "transcript",
                "uart bytes",
                "public response",
                "truncated",
            )
        ):
            category = "target-protocol-failure"
        elif any(
            marker in lowered
            for marker in (
                "image binding",
                "bound image",
                "image hash",
                "artifact",
                "manifest",
                "provenance",
            )
        ):
            category = "target-artifact-binding-failure"
        elif any(
            marker in lowered
            for marker in (
                "qemu exit",
                "qemu process",
                "process failure",
                "unexpected stderr",
                "stdin closed",
            )
        ):
            category = "target-process-failure"
        else:
            category = "target-execution-failure"
        raise Gate6Failure(category, context, detail) from error


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        raise Core0Error(
            f"{context} fields differ from schema: "
            f"missing={sorted(expected - actual)!r}, "
            f"unexpected={sorted(actual - expected)!r}"
        )


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _artifact_inventory(root: Path, output: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for name in ARTIFACT_FILES:
        path = output / name
        if not path.is_file() or path.stat().st_size == 0:
            raise Core0Error(f"Gate 6 required artifact is missing or empty: {path}")
        inventory[name] = {
            "path": _relative(path, root),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    return inventory


def _validate_corpus(manifest: object) -> dict[str, object]:
    if not isinstance(manifest, dict):
        raise Core0Error("Gate 6 scenario manifest is not an object")
    expected = gate6_corpus.scenario_manifest()
    if manifest != expected:
        raise Core0Error("Gate 6 scenario manifest differs from the closed corpus")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 14:
        raise Core0Error("Gate 6 requires exactly 14 scenarios")
    for scenario in gate6_corpus.SCENARIOS:
        run_device_session.validate_scenario(scenario)
    normal = [scenario for scenario in gate6_corpus.SCENARIOS if scenario.exchanges]
    terminal = [scenario for scenario in gate6_corpus.SCENARIOS if not scenario.exchanges]
    if len(normal) != 4 or len(terminal) != 10:
        raise Core0Error("Gate 6 requires exactly four interactive and ten terminal scenarios")
    return manifest


def _validate_manifest_identity(manifest: object, normalized: str) -> dict[str, object]:
    if not isinstance(manifest, dict):
        raise Core0Error("Gate 6 device manifest is not an object")
    report = audit_device.validate_device_suite_manifest(manifest, normalized=normalized)
    expected = {
        "suite_id": f"{gate6_corpus.DEFAULT_SUITE_ID:016x}",
        "source_seed": f"{gate6_corpus.DEFAULT_SOURCE_SEED:016x}",
        "runtime_seed": f"{gate6_corpus.DEFAULT_RUNTIME_SEED:016x}",
    }
    for field, value in expected.items():
        if manifest.get(field) != value or report.get(field) != value:
            raise Core0Error(f"Gate 6 manifest {field} differs from the closed corpus")
    return report


def _validate_build_record(
    record: object, *, root: Path, output: Path, profile: str
) -> dict[str, object]:
    if not isinstance(record, dict):
        raise Core0Error("Gate 6 build record is not an object")
    if (
        record.get("schema_version") != 1
        or record.get("status") != "pass"
        or record.get("artifact_category") != audit_core0.TEST_DEVICE_SUITE_POLICY
        or record.get("optimization") != profile
        or record.get("output_directory") != _relative(output, root)
    ):
        raise Core0Error("Gate 6 build record has the wrong identity/status")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(BUILD_HASHED_ARTIFACTS):
        raise Core0Error("Gate 6 build hash closure differs from the exact artifact set")
    for name in BUILD_HASHED_ARTIFACTS:
        path = output / name
        if not path.is_file() or artifacts.get(name) != sha256(path):
            raise Core0Error(f"Gate 6 build hash differs for {name}")
    return record


def _verify_profile_source_identity(
    *, root: Path, outputs: Mapping[str, Path], manifests: Mapping[str, object]
) -> dict[str, object]:
    if set(outputs) != {"O0", "O2"} or set(manifests) != {"O0", "O2"}:
        raise Core0Error("Gate 6 profile identity requires exact O0/O2 inputs")
    if manifests["O0"] != manifests["O2"]:
        raise Core0Error("Gate 6 O0/O2 device manifests are not identical")

    hashes: dict[str, str] = {}
    for name in CHECKED_SOURCE_ARTIFACTS:
        left = sha256(outputs["O0"] / name)
        right = sha256(outputs["O2"] / name)
        if left != right:
            raise Core0Error(f"Gate 6 O0/O2 checked source artifact differs: {name}")
        hashes[name] = left

    provenances = {
        profile: load_json(output / "provenance.json")
        for profile, output in outputs.items()
    }
    if any(not isinstance(value, dict) for value in provenances.values()):
        raise Core0Error("Gate 6 O0/O2 provenance is malformed")
    fields = (
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
        for field in fields
        if provenances["O0"].get(field) != provenances["O2"].get(field)
    ]
    if differing:
        raise Core0Error(
            "Gate 6 O0/O2 provenance does not identify one source snapshot: "
            + ", ".join(differing)
        )
    return {
        "profiles": ["O0", "O2"],
        "identical_checked_source_artifacts": hashes,
        "identical_provenance_fields": list(fields),
        "source_commit": provenances["O0"].get("source_commit"),
        "dirty_tree": provenances["O0"].get("dirty_tree"),
        "dirty_paths": provenances["O0"].get("dirty_paths"),
    }


def _run_mutation_matrix(
    manifest: Mapping[str, object], pre_ir: str, post_ir: str
) -> dict[str, object]:
    records = audit_device.audit_mutation_matrix(manifest, pre_ir, post_ir)
    names = [str(record.get("name")) for record in records]
    if len(names) != len(set(names)):
        raise Core0Error("Gate 6 device mutation matrix repeats a mutation")
    missing = REQUIRED_DEVICE_MUTATIONS - set(names)
    if missing:
        raise Core0Error(
            f"Gate 6 device mutation matrix omits required mutations: {sorted(missing)!r}"
        )
    return {
        "total_mutants_detected": len(records),
        "required_mutants_detected": len(REQUIRED_DEVICE_MUTATIONS),
        "records": [{"status": "detected", **record} for record in records],
    }


def _validate_branch_structural_audit(
    value: object, *, profile: str
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise Core0Error("device audit lacks branch-effect structural evidence")
    _exact_keys(
        value,
        {
            "source_function",
            "llvm_symbol",
            "selector_0",
            "selector_1",
            "readback",
            "source",
            "pre_ir",
            "post_ir",
        },
        "branch-effect audit",
    )
    source_function = "Lemma.Examples.Foundation.Device.dispatchBranch"
    llvm_symbol = audit_device.BRANCH_SYMBOL
    selector_0 = {
        "scratch_offset": 64,
        "stored_byte": 90,
        "send_byte_0xa5": False,
    }
    selector_1 = {"scratch_marker_store": False, "sent_byte": 165}
    readback = {
        "scratch_offset": 64,
        "width_bits": 8,
        "sentinel_byte": BRANCH_INITIAL_MARKER,
        "false_marker_byte": BRANCH_FALSE_MARKER,
        "response_shift": 8,
        "includes_selector": True,
        "selector_0_expected": BRANCH_FALSE_RESPONSE,
        "selector_1_expected": BRANCH_TRUE_RESPONSE,
    }
    if (
        value.get("source_function") != source_function
        or value.get("llvm_symbol") != llvm_symbol
        or value.get("selector_0") != selector_0
        or value.get("selector_1") != selector_1
        or value.get("readback") != readback
        or value.get("source")
        != {
            "source_function": source_function,
            "llvm_symbol": llvm_symbol,
            "selector_0": selector_0,
            "selector_1": selector_1,
            "readback": readback,
            "separate_subtrees": True,
            "common_sentinel_before_selection": True,
            "branch_local_readbacks": True,
            "readbacks_encoded": True,
        }
    ):
        raise Core0Error("branch-effect source/selector evidence differs from the closed contract")

    expected_dispatch = {"pre_ir": "conditional-branches", "post_ir": "switch" if profile == "O2" else "conditional-branches"}
    for layer in ("pre_ir", "post_ir"):
        record = value.get(layer)
        if not isinstance(record, dict):
            raise Core0Error(f"branch-effect {layer} evidence is malformed")
        _exact_keys(
            record,
            {
                "source_function",
                "llvm_symbol",
                "dispatch",
                "separate_successors",
                "selector_0_successor",
                "selector_1_successor",
                "marker_store_block",
                "send_byte_block",
                "exclusive_reachability",
                "sentinel_store_block",
                "sentinel_dominates_selection",
                "sentinel_dominance_kind",
                "selector_0_readback_block",
                "selector_1_readback_block",
                "branch_local_readbacks",
                "readbacks_encoded",
            },
            f"branch-effect {layer} audit",
        )
        if (
            record.get("source_function") != source_function
            or record.get("llvm_symbol") != llvm_symbol
            or record.get("dispatch") != expected_dispatch[layer]
            or record.get("separate_successors") is not True
            or record.get("exclusive_reachability") is not True
            or record.get("sentinel_dominates_selection") is not True
            or record.get("sentinel_dominance_kind") not in {"direct", "checked-success"}
            or record.get("branch_local_readbacks") is not True
            or record.get("readbacks_encoded") is not True
            or not isinstance(record.get("selector_0_successor"), str)
            or not isinstance(record.get("selector_1_successor"), str)
            or record.get("selector_0_successor") == record.get("selector_1_successor")
            or not isinstance(record.get("marker_store_block"), str)
            or not isinstance(record.get("send_byte_block"), str)
            or record.get("marker_store_block") == record.get("send_byte_block")
            or not isinstance(record.get("sentinel_store_block"), str)
            or record.get("sentinel_store_block")
            in {record.get("marker_store_block"), record.get("send_byte_block")}
            or not isinstance(record.get("selector_0_readback_block"), str)
            or not isinstance(record.get("selector_1_readback_block"), str)
            or record.get("selector_0_readback_block")
            == record.get("selector_1_readback_block")
        ):
            raise Core0Error(f"branch-effect {layer} CFG placement evidence differs")
    return value


@dataclass(frozen=True)
class Gate6Rejection:
    name: str
    path: Path
    diagnostic_code: str
    required_fragments: tuple[str, ...]


def _load_rejections(path: Path, root: Path) -> tuple[Gate6Rejection, ...]:
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise Core0Error("Gate 6 rejection manifest is not an object")
    _exact_keys(
        raw,
        {"schema_version", "profile", "legacy_profile", "cases"},
        "Gate 6 rejection manifest",
    )
    if (
        raw.get("schema_version") != 1
        or raw.get("profile") != gate6_corpus.PROFILE
        or raw.get("legacy_profile") != "core0-v0.4"
    ):
        raise Core0Error("Gate 6 rejection manifest has the wrong profile identity")
    values = raw.get("cases")
    if not isinstance(values, list) or len(values) != len(REJECTION_FILES):
        raise Core0Error("Gate 6 rejection manifest lacks its exact five cases")

    quarantine = (root / "examples/foundation/gate6-reject").resolve()
    records: list[Gate6Rejection] = []
    names: set[str] = set()
    paths: set[Path] = set()
    for index, (item, expected_file) in enumerate(zip(values, REJECTION_FILES, strict=True)):
        if not isinstance(item, dict):
            raise Core0Error(f"Gate 6 rejection #{index} is not an object")
        _exact_keys(
            item,
            {"name", "path", "diagnostic_code", "required_fragments"},
            f"Gate 6 rejection #{index}",
        )
        name, relative = item.get("name"), item.get("path")
        code, fragments = item.get("diagnostic_code"), item.get("required_fragments")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"Gate 6 rejection #{index} has an invalid/duplicate name")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            raise Core0Error(f"Gate 6 rejection {name} has an invalid path")
        fixture = (root / relative).resolve()
        try:
            fixture.relative_to(quarantine)
        except ValueError as error:
            raise Core0Error(f"Gate 6 rejection escapes quarantine: {relative}") from error
        if fixture.name != expected_file or not fixture.is_file() or fixture in paths:
            raise Core0Error(f"Gate 6 rejection {name} has a missing/out-of-order fixture")
        if not isinstance(code, str) or not code:
            raise Core0Error(f"Gate 6 rejection {name} has an invalid diagnostic code")
        if (
            not isinstance(fragments, list)
            or not fragments
            or any(not isinstance(fragment, str) or not fragment for fragment in fragments)
            or len(set(fragments)) != len(fragments)
        ):
            raise Core0Error(f"Gate 6 rejection {name} has invalid fragments")
        names.add(name)
        paths.add(fixture)
        records.append(Gate6Rejection(name, fixture, code, tuple(fragments)))
    discovered = set(quarantine.glob("*.lean"))
    if paths != discovered:
        raise Core0Error(
            "Gate 6 rejection manifest/file set differs: "
            f"untested={sorted(item.name for item in discovered - paths)!r}, "
            f"stale={sorted(item.name for item in paths - discovered)!r}"
        )
    return tuple(records)


def _run_rejections(
    cases: tuple[Gate6Rejection, ...],
    *,
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for case in cases:
        environment = os.environ.copy()
        environment["LEMMA_CORE0_OUT"] = str((output_dir / case.name).resolve())
        argv = ("lake", "env", "lean", str(case.path.relative_to(root)))
        result = run_bounded(
            argv, cwd=root, timeout_seconds=timeout_seconds, env=environment
        )
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        log = output_dir / f"{case.name}.txt"
        log.write_text(output, encoding="utf-8")
        marker = f"Core0[{case.diagnostic_code}]"
        if result.returncode == 0:
            raise Core0Error(f"Gate 6 negative fixture unexpectedly passed: {case.name}")
        error_lines = [
            line
            for line in output.splitlines()
            if re.search(r"(?:^|:\s)error:", line) is not None
        ]
        if (
            len(error_lines) != 1
            or "error: Core0[" not in error_lines[0]
            or marker not in error_lines[0]
        ):
            raise Core0Error(
                f"Gate 6 rejection {case.name} did not emit exactly one total {marker} "
                f"diagnostic: {error_lines!r}"
            )
        missing = [fragment for fragment in case.required_fragments if fragment not in output]
        if missing:
            raise Core0Error(
                f"Gate 6 rejection {case.name} lacked intended diagnostics: {missing!r}"
            )
        unrelated = [
            fragment
            for fragment in (
                "lean.unknownIdentifier",
                "declaration uses 'sorry'",
                "Aborting evaluation",
                "unknown declaration",
            )
            if fragment in output
        ]
        if unrelated:
            raise Core0Error(
                f"Gate 6 rejection {case.name} also had unrelated failures: {unrelated!r}"
            )
        records.append(
            {
                "name": case.name,
                "path": str(case.path.relative_to(root)),
                "source_sha256": sha256(case.path),
                "argv": list(argv),
                "returncode": result.returncode,
                "diagnostic_code": case.diagnostic_code,
                "required_fragments": list(case.required_fragments),
                "diagnostic_log": _relative(log, root),
                "diagnostic_sha256": sha256(log),
            }
        )
    return records


def _parse_probe_output(
    text: str, *, prefix: str, expected_labels: Sequence[str]
) -> list[str]:
    matches = re.findall(
        rf"(?m)^{re.escape(prefix)}:([a-z0-9-]+):(ok|failed)\s*$", text
    )
    failed = [label for label, status in matches if status != "ok"]
    observed = [label for label, _status in matches]
    if failed:
        raise Core0Error(f"{prefix} probes reported failure: {failed!r}")
    if observed != list(expected_labels) or len(observed) != len(set(observed)):
        raise Core0Error(
            f"{prefix} probe catalog differs: observed={observed!r}, "
            f"expected={list(expected_labels)!r}"
        )
    return observed


def _run_probe(
    *,
    root: Path,
    work: Path,
    source_relative: str,
    output_stem: str,
    prefix: str,
    expected_labels: Sequence[str],
    timeout_seconds: float,
) -> dict[str, object]:
    source = root / source_relative
    text, command = _run_host_driver(
        root=root,
        source=source,
        output_prefix=work / output_stem,
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    observed = _parse_probe_output(
        text, prefix=prefix, expected_labels=expected_labels
    )
    return {
        "source": source_relative,
        "source_sha256": sha256(source),
        "command": command,
        "probe_count": len(observed),
        "probes": observed,
    }


def _check_device_probes(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    pinned = _run_probe(
        root=root,
        work=work,
        source_relative="examples/foundation/DevicePinnedSemantics.lean",
        output_stem="device-pinned-semantics",
        prefix="PINNED_DEVICE",
        expected_labels=PINNED_DEVICE_PROBES,
        timeout_seconds=timeout_seconds,
    )
    model = _run_probe(
        root=root,
        work=work,
        source_relative="examples/foundation/DeviceModelProbes.lean",
        output_stem="device-model-probes",
        prefix="DEVICE_MODEL",
        expected_labels=DEVICE_MODEL_PROBES,
        timeout_seconds=timeout_seconds,
    )
    return {
        "pinned_uart_semantics": pinned,
        "packet_and_source_model": model,
        "device_model_source": "Lemma/Core0/DeviceModel.lean",
        "device_model_source_sha256": sha256(root / "Lemma/Core0/DeviceModel.lean"),
        "source_routines": "examples/foundation/DeviceConformance.lean",
        "source_routines_sha256": sha256(
            root / "examples/foundation/DeviceConformance.lean"
        ),
        "interpretation": (
            "the finite UART model and packet model execute separately from QEMU; "
            "the packet probes also compare the original elaborated source encoders"
        ),
    }


def _check_device_lemmas(
    *, root: Path, work: Path, timeout_seconds: float
) -> dict[str, object]:
    work.mkdir(parents=True, exist_ok=True)
    probe = root / "examples/foundation/DeviceLemmas.lean"
    text, command = _run_host_driver(
        root=root,
        source=probe,
        output_prefix=work / "device-lemmas-axioms",
        execute=False,
        timeout_seconds=timeout_seconds,
    )
    lemma_source = root / "Lemma/Core0/DeviceLemmas.lean"
    source_text = lemma_source.read_text(encoding="utf-8")
    if "sorryAx" in text:
        raise Core0Error("Gate 6 device lemmas depend on sorryAx")
    forbidden = [
        token
        for token in ("sorry", "admit", "native_decide")
        if re.search(rf"\b{re.escape(token)}\b", source_text)
    ]
    if forbidden:
        raise Core0Error(
            f"Gate 6 device lemma source contains forbidden proof devices: {forbidden!r}"
        )

    theorem_records: list[dict[str, object]] = []
    for name in DEVICE_LEMMAS:
        full_name = f"{DEVICE_LEMMA_NAMESPACE}.{name}"
        dependency = re.search(
            rf"'{re.escape(full_name)}' depends on axioms:\s*\[([^\]]*)\]", text
        )
        no_dependencies = f"'{full_name}' does not depend on any axioms" in text
        if dependency is None and not no_dependencies:
            raise Core0Error(f"cannot parse axiom dependencies for {full_name}")
        axioms = (
            []
            if dependency is None
            else [item.strip() for item in dependency.group(1).split(",") if item.strip()]
        )
        if set(axioms) - {"propext", "Classical.choice", "Quot.sound"}:
            raise Core0Error(f"Gate 6 lemma {full_name} has unexpected axioms: {axioms!r}")
        statement = re.search(rf"(?ms)^theorem {re.escape(name)}\b(.*?) := by", source_text)
        if statement is None:
            raise Core0Error(f"cannot extract theorem statement for {full_name}")
        theorem_records.append(
            {
                "theorem": full_name,
                "statement": " ".join(f"theorem {name}{statement.group(1)}".split()),
                "axioms": axioms,
            }
        )
    return {
        "source": str(lemma_source.relative_to(root)),
        "source_sha256": sha256(lemma_source),
        "model_source": "Lemma/Core0/DeviceModel.lean",
        "model_source_sha256": sha256(root / "Lemma/Core0/DeviceModel.lean"),
        "dependency_probe": command,
        "theorems": theorem_records,
        "scope": (
            "local finite-UART ordering, reset, and response-size facts; "
            "not a compiler-correctness or hardware-correctness proof"
        ),
    }


def _expected_sent(scenario: gate6_corpus.Scenario) -> bytes:
    if scenario.exchanges:
        return b"".join(exchange.request.encode() for exchange in scenario.exchanges)
    return scenario.raw_input


def _expected_received(scenario: gate6_corpus.Scenario) -> bytes | None:
    if scenario.exchanges:
        return gate6_corpus.READY + b"".join(
            exchange.expected_prefix
            + gate6_corpus.encode_response(exchange.expected_response)
            for exchange in scenario.exchanges
        )
    if scenario.suppress_output_after_ready:
        return None
    return gate6_corpus.READY


def _load_bound_raw(
    *, root: Path, expected: Path, record: Mapping[str, object], field: str
) -> bytes:
    if record.get(field) != _relative(expected, root):
        raise Core0Error(f"device run record {field} path differs from its session directory")
    if not expected.is_file():
        raise Core0Error(f"device run record {field} artifact is missing")
    if record.get(f"{field}_sha256") != sha256(expected):
        raise Core0Error(f"device run record {field} hash differs")
    return expected.read_bytes()


def _validate_iso_interval(record: Mapping[str, object]) -> None:
    started_raw, finished_raw = record.get("started_at"), record.get("finished_at")
    if not isinstance(started_raw, str) or not isinstance(finished_raw, str):
        raise Core0Error("device run record lacks UTC timestamps")
    started = datetime.fromisoformat(started_raw)
    finished = datetime.fromisoformat(finished_raw)
    if (
        started.tzinfo is None
        or finished.tzinfo is None
        or started.utcoffset() != timezone.utc.utcoffset(started)
        or finished.utcoffset() != timezone.utc.utcoffset(finished)
        or finished < started
    ):
        raise Core0Error("device run timestamps are not an ordered UTC interval")
    elapsed = record.get("elapsed_seconds")
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
        raise Core0Error("device run record elapsed time is malformed")


def _validate_session_record(
    *,
    root: Path,
    profile: str,
    image: Path,
    output_dir: Path,
    scenario: gate6_corpus.Scenario,
    record: object,
) -> dict[str, object]:
    if not isinstance(record, dict):
        raise Core0Error("device session record is not an object")
    _exact_keys(
        record,
        {
            "schema_version",
            "status",
            "profile",
            "test_abi",
            "scenario",
            "purpose",
            "image",
            "image_sha256",
            "qemu_pid",
            "single_pid",
            "single_elf",
            "qemu_argv",
            "qemu_returncode",
            "expected_exit_status",
            "started_at",
            "finished_at",
            "elapsed_seconds",
            "ready_hex",
            "withhold_after_ready",
            "suppress_output_after_ready",
            "exchanges",
            "sent",
            "sent_sha256",
            "received",
            "received_sha256",
            "stderr",
            "stderr_sha256",
        },
        "Gate 6 session record",
    )
    image_digest = sha256(image)
    pid = record.get("qemu_pid")
    if (
        record.get("schema_version") != 1
        or record.get("status") != "pass"
        or record.get("profile") != gate6_corpus.PROFILE
        or record.get("test_abi") != gate6_corpus.TEST_ABI
        or record.get("scenario") != scenario.name
        or record.get("purpose") != scenario.purpose
        or record.get("image") != _relative(image, root)
        or record.get("image_sha256") != image_digest
        or isinstance(pid, bool)
        or not isinstance(pid, int)
        or pid <= 0
        or record.get("single_pid") is not True
        or record.get("single_elf") is not True
        or record.get("qemu_argv") != list(run_device_session._qemu_argv(image))
        or record.get("qemu_returncode") != scenario.expected_exit_status
        or record.get("expected_exit_status") != scenario.expected_exit_status
        or record.get("ready_hex") != gate6_corpus.READY.hex()
        or record.get("withhold_after_ready") is not scenario.withhold_after_ready
        or record.get("suppress_output_after_ready") is not scenario.suppress_output_after_ready
    ):
        raise Core0Error("device session record identity/process binding differs")
    _validate_iso_interval(record)

    paths = run_device_session._paths(output_dir, scenario)
    persisted = load_json(paths["record"])
    if persisted != record:
        raise Core0Error("returned device session record differs from persisted evidence")
    sent = _load_bound_raw(root=root, expected=paths["sent"], record=record, field="sent")
    received = _load_bound_raw(
        root=root, expected=paths["received"], record=record, field="received"
    )
    stderr = _load_bound_raw(
        root=root, expected=paths["stderr"], record=record, field="stderr"
    )
    if sent != _expected_sent(scenario):
        raise Core0Error("device sent-byte evidence differs from the closed scenario")
    if stderr:
        raise Core0Error("successful device session retained nonempty QEMU stderr")
    exact_received = _expected_received(scenario)
    if exact_received is not None and received != exact_received:
        raise Core0Error("device received-byte evidence differs from the closed scenario")
    if scenario.suppress_output_after_ready:
        post_ready = received[len(gate6_corpus.READY) :]
        stress = b"\x55" * 65535
        response = gate6_corpus.encode_response(
            gate6_corpus.Response(gate6_corpus.STATUS_OK, 0x8001, 65535)
        )
        response_prefix = post_ready[len(stress) :]
        if (
            not received.startswith(gate6_corpus.READY)
            or not post_ready.startswith(stress)
            or len(response_prefix) >= len(response)
            or not response.startswith(response_prefix)
        ):
            raise Core0Error("device backpressure evidence is not the exact bounded prefix")

    raw_exchanges = record.get("exchanges")
    if not isinstance(raw_exchanges, list) or len(raw_exchanges) != len(scenario.exchanges):
        raise Core0Error("device run exchange count differs from the scenario")
    for index, (raw, exchange) in enumerate(zip(raw_exchanges, scenario.exchanges, strict=True)):
        expected = {
            "index": index,
            "pid": pid,
            "image_sha256": image_digest,
            "prefix_hex": exchange.expected_prefix.hex(),
            "response": asdict(exchange.expected_response),
        }
        if raw != expected:
            raise Core0Error(f"device exchange {index} is not bound to one PID/ELF/oracle")
    return record


def _session_digest(records: Sequence[Mapping[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(
            (
                f"{record['scenario']}:{record['image_sha256']}:"
                f"{record['qemu_returncode']}:{record['sent_sha256']}:"
                f"{record['received_sha256']}:{record['stderr_sha256']}:"
                f"{json.dumps(record['exchanges'], sort_keys=True, separators=(',', ':'))}\n"
            ).encode("ascii")
        )
    return digest.hexdigest()


def _branch_runtime_evidence(record: Mapping[str, object]) -> dict[str, object]:
    """Strictly decode the target's selected-branch RAM-marker readbacks."""
    if record.get("scenario") != gate6_corpus.BRANCH_EFFECTS.name:
        raise Core0Error("branch-effect evidence was derived from the wrong scenario")
    exchanges = record.get("exchanges")
    if not isinstance(exchanges, list) or len(exchanges) != 2:
        raise Core0Error("branch-effect session lacks its exact two exchanges")
    expected = gate6_corpus.BRANCH_EFFECTS.exchanges
    observations: list[dict[str, object]] = []
    expected_values = (BRANCH_FALSE_RESPONSE, BRANCH_TRUE_RESPONSE)
    expected_markers = (BRANCH_FALSE_MARKER, BRANCH_INITIAL_MARKER)
    expected_prefixes = ("", "a5")
    for branch, (raw, exchange) in enumerate(zip(exchanges, expected, strict=True)):
        if not isinstance(raw, dict):
            raise Core0Error("branch-effect exchange is malformed")
        response = raw.get("response")
        if (
            raw.get("index") != branch
            or raw.get("prefix_hex") != expected_prefixes[branch]
            or exchange.expected_prefix.hex() != expected_prefixes[branch]
            or response != asdict(exchange.expected_response)
            or exchange.request.request_id != BRANCH_REQUEST_IDS[branch]
            or not isinstance(response, dict)
            or response.get("status") != gate6_corpus.STATUS_OK
            or response.get("request_id") != BRANCH_REQUEST_IDS[branch]
            or response.get("value") != expected_values[branch]
        ):
            raise Core0Error("branch-effect exchange differs from its independent oracle")
        value = response["value"]
        assert isinstance(value, int)
        marker, decoded_branch, high = (value >> 8) & 0xFF, value & 0xFF, value >> 16
        if (
            high != 0
            or marker != expected_markers[branch]
            or decoded_branch != branch
        ):
            raise Core0Error("branch-effect response does not encode marker<<8|branch")
        observations.append(
            {
                "branch_value": branch,
                "uart_prefix_hex": raw["prefix_hex"],
                "response": response,
                "response_value_hex": f"0x{value:04x}",
                "decoded_scratch_marker": marker,
                "decoded_branch": decoded_branch,
                "selected_effect": (
                    "scratch+64 overwritten with 0x5a"
                    if branch == 0
                    else "raw UART 0xa5 emitted; scratch+64 preserved at sentinel 0x3c"
                ),
            }
        )
    return {
        "scenario": gate6_corpus.BRANCH_EFFECTS.name,
        "single_qemu_pid": record.get("qemu_pid"),
        "single_elf_sha256": record.get("image_sha256"),
        "observations": observations,
        "response_encoding": "(scratch+64 readback << 8) | branch",
        "initial_scratch_marker": BRANCH_INITIAL_MARKER,
        "direct_target_observation": (
            "the false request emits no raw UART marker and returns 0x5a00 after its "
            "scratch write/readback; the true request emits raw byte 0xa5 and returns "
            "0x3c01 after reading back the preserved sentinel"
        ),
        "ram_marker_directly_read_back": True,
    }


def _run_target_profile(
    *,
    root: Path,
    profile: str,
    output: Path,
    qemu_timeout: float,
) -> dict[str, object]:
    image = output / "image.elf"
    image_digest = sha256(image)
    records: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for scenario in gate6_corpus.SCENARIOS:
        run_dir = output / "runs" / scenario.name
        record = _target_stage(
            profile,
            scenario.name,
            lambda scenario=scenario, run_dir=run_dir: run_device_session.run_session(
                root=root,
                image=image,
                output_dir=run_dir,
                scenario=scenario,
                timeout_seconds=qemu_timeout,
            ),
        )
        checked_record = _target_stage(
            profile,
            scenario.name,
            lambda scenario=scenario, run_dir=run_dir, record=record: _validate_session_record(
                root=root,
                profile=profile,
                image=image,
                output_dir=run_dir,
                scenario=scenario,
                record=record,
            ),
        )
        records.append(checked_record)
        summaries.append(
            {
                "scenario": scenario.name,
                "purpose": scenario.purpose,
                "record": _relative(
                    run_device_session._paths(run_dir, scenario)["record"], root
                ),
                "qemu_pid": checked_record["qemu_pid"],
                "qemu_returncode": checked_record["qemu_returncode"],
                "exchange_count": len(scenario.exchanges),
                "sent_sha256": checked_record["sent_sha256"],
                "received_sha256": checked_record["received_sha256"],
                "elapsed_seconds": checked_record["elapsed_seconds"],
                "started_at": checked_record["started_at"],
                "finished_at": checked_record["finished_at"],
            }
        )
    if len(records) != 14 or {str(record["scenario"]) for record in records} != set(
        gate6_corpus.SCENARIO_BY_NAME
    ):
        raise Gate6Failure(
            "target-protocol-failure", profile, "target records do not cover the exact corpus"
        )
    positive = [record for record in records if record["exchanges"]]
    terminal = [record for record in records if not record["exchanges"]]
    branch_records = [
        record
        for record in records
        if record.get("scenario") == gate6_corpus.BRANCH_EFFECTS.name
    ]
    if len(branch_records) != 1:
        raise Gate6Failure(
            "target-protocol-failure", profile, "branch-effect target record is absent/duplicated"
        )
    return {
        "image_sha256": image_digest,
        "fresh_qemu_boots": len(records),
        "interactive_sessions": len(positive),
        "terminal_sessions": len(terminal),
        "runtime_requests": sum(len(record["exchanges"]) for record in positive),
        "single_pid_two_request_sessions": sum(
            len(record["exchanges"]) == gate6_corpus.REQUESTS_PER_SESSION
            and record["single_pid"] is True
            and record["single_elf"] is True
            for record in positive
        ),
        "exit_status_histogram": {
            str(status): sum(record["qemu_returncode"] == status for record in records)
            for status in sorted({int(record["qemu_returncode"]) for record in records})
        },
        "branch_effect_observation": _branch_runtime_evidence(branch_records[0]),
        "session_result_sha256": _session_digest(records),
        "sessions": summaries,
    }


def _install_report(path: Path, report: Mapping[str, object]) -> None:
    """Install the only PASS marker without exposing a partial JSON record."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        write_json(temporary, report)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def check_gate6(
    *,
    root: Path,
    work: Path,
    clean: bool,
    timeout_seconds: float,
    qemu_timeout: float,
) -> dict[str, object]:
    """Execute the complete Gate 6 acceptance and return its PASS record."""
    _stage(
        "work-directory-failure",
        _relative(work, root),
        lambda: (
            invalidate_output_file(work / RESULT_FILE, root),
            invalidate_output_file(work / (RESULT_FILE + ".tmp"), root),
            prepare_output_directory(work, root, clean=clean),
        ),
    )

    corpus_path = work / "corpus" / CORPUS_FILE
    corpus = _stage(
        "corpus-generation-failure",
        gate6_corpus.PROFILE,
        gate6_corpus.scenario_manifest,
    )
    _stage(
        "corpus-generation-failure",
        _relative(corpus_path, root),
        lambda: write_json(corpus_path, corpus),
    )
    _stage(
        "corpus-validation-failure",
        gate6_corpus.PROFILE,
        lambda: _validate_corpus(load_json(corpus_path)),
    )

    outputs: dict[str, Path] = {}
    manifests: dict[str, dict[str, object]] = {}
    profiles: dict[str, dict[str, object]] = {}
    for index, profile in enumerate(("O0", "O2")):
        output = work / profile
        outputs[profile] = output
        build_record = _stage(
            "compile-or-link-failure",
            profile,
            lambda profile=profile, output=output, index=index: build_device_suite(
                root=root,
                output_dir=output,
                opt_level=profile,
                suite_id=gate6_corpus.DEFAULT_SUITE_ID,
                source_seed=gate6_corpus.DEFAULT_SOURCE_SEED,
                runtime_seed=gate6_corpus.DEFAULT_RUNTIME_SEED,
                clean=False,
                build_lean=index == 0,
                timeout_seconds=timeout_seconds,
            ),
        )
        persisted_build = _stage(
            "build-record-rejection",
            profile,
            lambda output=output: _validate_build_record(
                load_json(output / "build.json"),
                root=root,
                output=output,
                profile=profile,
            ),
        )
        if build_record != persisted_build:
            raise Gate6Failure(
                "build-record-rejection",
                profile,
                "returned and persisted build records differ",
            )
        manifest = _stage(
            "manifest-rejection",
            profile,
            lambda output=output: load_json(output / "device-suite-manifest.json"),
        )
        if not isinstance(manifest, dict):
            raise Gate6Failure("manifest-rejection", profile, "device manifest is malformed")
        manifests[profile] = manifest
        manifest_report = _stage(
            "device-manifest-rejection",
            profile,
            lambda output=output, manifest=manifest: _validate_manifest_identity(
                manifest,
                (output / "device-suite-normalized.txt").read_text(encoding="utf-8"),
            ),
        )
        closure_audit = _stage(
            "provenance-or-closure-rejection",
            profile,
            lambda output=output: audit_core0.audit(
                output, root, policy=audit_core0.TEST_DEVICE_SUITE_POLICY
            ),
        )
        device_audit = _stage(
            "device-ordering-or-platform-rejection",
            profile,
            lambda output=output: audit_device.audit_device_directory(output, root),
        )
        branch_effects = _stage(
            "branch-effect-structural-rejection",
            profile,
            lambda device_audit=device_audit, profile=profile: _validate_branch_structural_audit(
                device_audit.get("branch_effects"), profile=profile
            ),
        )
        if (
            closure_audit.get("status") != "pass"
            or closure_audit.get("artifact_category")
            != audit_core0.TEST_DEVICE_SUITE_POLICY
            or closure_audit.get("manifest") != manifest
            or device_audit.get("manifest") != manifest_report
        ):
            raise Gate6Failure(
                "audit-composition-failure",
                profile,
                "generic and independent device audits are not bound to one manifest",
            )
        inventory = _stage(
            "artifact-inventory-failure",
            profile,
            lambda output=output: _artifact_inventory(root, output),
        )
        profiles[profile] = {
            "build": persisted_build,
            "closure_audit": closure_audit,
            "device_audit": device_audit,
            "branch_effects": branch_effects,
            "artifacts": inventory,
        }

    profile_identity = _stage(
        "profile-source-identity-rejection",
        "O0/O2",
        lambda: _verify_profile_source_identity(
            root=root, outputs=outputs, manifests=manifests
        ),
    )
    mutation_profiles = {
        profile: _stage(
            "device-mutation-detection-failure",
            f"{profile}/manifest+LLVM",
            lambda profile=profile: _run_mutation_matrix(
                manifests[profile],
                (outputs[profile] / "program.ll").read_text(encoding="utf-8"),
                (outputs[profile] / "program.opt.ll").read_text(encoding="utf-8"),
            ),
        )
        for profile in ("O0", "O2")
    }
    mutation_matrix = {
        "profiles": mutation_profiles,
        "distinct_mutants_per_profile": len(REQUIRED_DEVICE_MUTATIONS),
        "total_mutants_detected": sum(
            record["total_mutants_detected"] for record in mutation_profiles.values()
        ),
    }

    rejection_cases = _stage(
        "rejection-manifest-failure",
        gate6_corpus.PROFILE,
        lambda: _load_rejections(
            root / "examples/foundation/gate6-reject/rejections.json", root
        ),
    )
    rejection_records = _stage(
        "frontend-rejection-failure",
        gate6_corpus.PROFILE,
        lambda: _run_rejections(
            rejection_cases,
            root=root,
            output_dir=work / "rejections",
            timeout_seconds=timeout_seconds,
        ),
    )
    probes = _stage(
        "device-model-probe-failure",
        gate6_corpus.PROFILE,
        lambda: _check_device_probes(
            root=root, work=work / "probes", timeout_seconds=timeout_seconds
        ),
    )
    lemmas = _stage(
        "device-lemma-check-failure",
        DEVICE_LEMMA_NAMESPACE,
        lambda: _check_device_lemmas(
            root=root, work=work / "proofs", timeout_seconds=timeout_seconds
        ),
    )

    for profile in ("O0", "O2"):
        profiles[profile]["target"] = _run_target_profile(
            root=root,
            profile=profile,
            output=outputs[profile],
            qemu_timeout=qemu_timeout,
        )

    provenance = _stage(
        "provenance-rejection", "O0", lambda: load_json(outputs["O0"] / "provenance.json")
    )
    if not isinstance(provenance, dict):
        raise Gate6Failure("provenance-rejection", "O0", "provenance is malformed")
    action_functions = manifests["O0"].get("action_functions")
    scalar_functions = manifests["O0"].get("scalar_functions")
    used_ops = manifests["O0"].get("used_device_ops")
    if not all(isinstance(value, list) for value in (action_functions, scalar_functions, used_ops)):
        raise Gate6Failure("manifest-rejection", "O0", "closure arrays are malformed")

    interactive_per_profile = sum(bool(scenario.exchanges) for scenario in gate6_corpus.SCENARIOS)
    terminal_per_profile = len(gate6_corpus.SCENARIOS) - interactive_per_profile
    requests_per_profile = sum(len(scenario.exchanges) for scenario in gate6_corpus.SCENARIOS)
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "gate": 6,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": provenance.get("source_commit"),
        "contract_version": gate6_corpus.PROFILE,
        "test_abi": gate6_corpus.TEST_ABI,
        "artifact_category": audit_core0.TEST_DEVICE_SUITE_POLICY,
        "suite_id": f"{gate6_corpus.DEFAULT_SUITE_ID:016x}",
        "seeds": {
            "source_generation": f"{gate6_corpus.DEFAULT_SOURCE_SEED:016x}",
            "runtime_inputs": f"{gate6_corpus.DEFAULT_RUNTIME_SEED:016x}",
            "algorithm": "closed deterministic Gate 6 UART scenario catalog",
        },
        "corpus": {
            "path": _relative(corpus_path, root),
            "sha256": sha256(corpus_path),
            "scenarios_per_profile": len(gate6_corpus.SCENARIOS),
            "interactive_sessions_per_profile": interactive_per_profile,
            "terminal_sessions_per_profile": terminal_per_profile,
            "runtime_requests_per_profile": requests_per_profile,
            "ready_hex": gate6_corpus.READY.hex(),
            "request_header_bytes": gate6_corpus.REQUEST_HEADER_BYTES,
            "maximum_payload_bytes": gate6_corpus.MAXIMUM_PAYLOAD_BYTES,
            "response_bytes": gate6_corpus.RESPONSE_BYTES,
        },
        "profiles": profiles,
        "profile_source_identity": profile_identity,
        "mutation_matrix": mutation_matrix,
        "negative_cases": {
            gate6_corpus.PROFILE: rejection_records,
            "legacy_profile_rejections": [
                record for record in rejection_records if record["name"] == "v04-device"
            ],
        },
        "device_probes": probes,
        "device_lemmas": lemmas,
        "branch_effect_evidence": {
            "source_model": {
                "probe_source": probes["packet_and_source_model"]["source"],
                "false_branch_probe": "false-branch-only-ram",
                "true_branch_probe": "true-branch-only-uart",
            },
            "compiled_structure": {
                profile: profiles[profile]["branch_effects"]
                for profile in ("O0", "O2")
            },
            "target_runtime": {
                profile: profiles[profile]["target"]["branch_effect_observation"]
                for profile in ("O0", "O2")
            },
            "evidence_boundary": (
                "QEMU directly observes both selected UART behavior and the scratch+64 "
                "byte read back by compiled Lean: false returns 0x5a00 after writing "
                "0x5a, while true emits 0xa5 and returns 0x3c01 with the initialized "
                "0x3c sentinel preserved; source/model and exclusive pre/post-LLVM CFG "
                "audits bind those observations to the selected branches"
            ),
        },
        "counts": {
            "roots": 1,
            "scalar_functions": len(scalar_functions),
            "action_functions": len(action_functions),
            "device_operations": len(used_ops),
            "scenarios_per_profile": len(gate6_corpus.SCENARIOS),
            "interactive_sessions_per_profile": interactive_per_profile,
            "terminal_sessions_per_profile": terminal_per_profile,
            "runtime_requests_per_profile": requests_per_profile,
            "single_pid_two_request_sessions": interactive_per_profile * 2,
            "branch_marker_target_readbacks": 4,
            "qemu_boots_total": len(gate6_corpus.SCENARIOS) * 2,
            "frontend_rejections": len(rejection_records),
            "legacy_profile_rejections": 1,
            "pinned_device_probes": len(PINNED_DEVICE_PROBES),
            "packet_model_probes": len(DEVICE_MODEL_PROBES),
            "device_lemmas_checked": len(DEVICE_LEMMAS),
            "audit_mutants_detected": mutation_matrix["total_mutants_detected"],
            "ordered_uart_sites_per_profile": profiles["O0"]["device_audit"]["ir"][
                "pre"
            ]["sites"],
            "optimized_uart_accesses_per_profile": profiles["O0"]["device_audit"][
                "ir"
            ]["post"]["accesses"],
        },
        "security_interpretation": (
            "compiled checked Core0 code performs declared ordered MMIO and checked ordinary-RAM "
            "access inside one trusted M-mode image; this is not isolation against arbitrary "
            "privileged machine code"
        ),
        "limitations": [
            "Finite model/source probes and local device lemmas are not a compiler-correctness or hardware-correctness proof.",
            "The machine result is specific to the pinned QEMU virt ns16550a model; it is not a physical-board claim.",
            "Transmit backpressure is exercised through QEMU's stdio serial backend and is not a UART latency measurement.",
            "Gate 6 remains polling-only and adds no trap substrate, interrupts, scheduler, or managed runtime.",
            "This result does not complete G1 or G2.",
        ],
    }
    _stage(
        "evidence-write-failure",
        _relative(work / RESULT_FILE, root),
        lambda: _install_report(work / RESULT_FILE, report),
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--work-dir", type=Path, default=Path("build/foundation/check/gate6")
    )
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--qemu-timeout", type=float, default=20.0)
    ns = parser.parse_args()
    root = repo_root()
    work = (
        (root / ns.work_dir).resolve()
        if not ns.work_dir.is_absolute()
        else ns.work_dir.resolve()
    )
    try:
        report = check_gate6(
            root=root,
            work=work,
            clean=ns.clean,
            timeout_seconds=ns.timeout,
            qemu_timeout=ns.qemu_timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FOUNDATION GATE 6 CHECK FAIL: {error}", file=sys.stderr)
        return 1
    counts = report.get("counts")
    if not isinstance(counts, dict):
        print("FOUNDATION GATE 6 CHECK FAIL: PASS report lacks counts", file=sys.stderr)
        return 1
    print(
        "FOUNDATION GATE 6 PASS: "
        f"{counts['scenarios_per_profile']} scenarios/profile; "
        f"{counts['qemu_boots_total']} fresh QEMU boots; "
        f"{counts['runtime_requests_per_profile'] * 2} runtime requests"
    )
    print(f"evidence: {work / RESULT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
