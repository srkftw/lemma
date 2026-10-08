#!/usr/bin/env python3
"""Run the bounded, fail-closed Core0 freestanding acceptance suite."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import audit_core0
from build_core0 import (
    LINK_ARGUMENTS,
    LLC_ARGUMENTS,
    build,
    prepare_output_directory,
)
from core0_common import (
    Core0Error,
    checked,
    load_json,
    repo_root,
    require_tools,
    run_bounded,
    sha256,
    write_json,
)
from run_core0 import run_case


U64_MAX = (1 << 64) - 1
REFERENCE_RESULT = re.compile(r"CORE0_REFERENCE:([0-9a-f]{16})")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")

REPRODUCIBLE_ARTIFACTS = (
    "program.ll",
    "program.opt.ll",
    "program.o",
    "startup.S",
    "startup.o",
    "link.ld",
    "image.elf",
    "image.map",
    "layout.json",
    "core0-manifest.json",
    "core0-normalized.txt",
    "symbols.txt",
    "platform.dtb",
    "platform.dts",
)


@dataclass(frozen=True)
class TargetCase:
    name: str
    case_id: int
    args: tuple[int, int, int]
    covers: tuple[str, ...]


@dataclass(frozen=True)
class CaseCorpus:
    seed: int
    root: str
    cases: tuple[TargetCase, ...]


@dataclass(frozen=True)
class RejectionCase:
    name: str
    path: Path
    required_fragments: tuple[str, ...]


def _u64(value: object, field: str) -> int:
    if not isinstance(value, str):
        raise Core0Error(f"{field} must be a string-encoded UInt64")
    try:
        result = int(value, 0)
    except ValueError as error:
        raise Core0Error(f"{field} is not a UInt64: {value!r}") from error
    if result < 0 or result > U64_MAX:
        raise Core0Error(f"{field} is outside UInt64: {value!r}")
    return result


def load_case_corpus(path: Path) -> CaseCorpus:
    raw = load_json(path)
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise Core0Error("case corpus has an unsupported schema")
    root = raw.get("root")
    if not isinstance(root, str) or IDENTIFIER.fullmatch(root) is None:
        raise Core0Error("case corpus root is not a valid fully qualified Lean identifier")
    seed = _u64(raw.get("seed"), "case corpus seed")
    values = raw.get("cases")
    if not isinstance(values, list):
        raise Core0Error("case corpus cases must be an array")
    if not values:
        raise Core0Error("case corpus is empty")
    cases: list[TargetCase] = []
    names: set[str] = set()
    identifiers: set[int] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise Core0Error(f"case #{index} is not an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise Core0Error(f"case #{index} has an empty or invalid name")
        if name in names:
            raise Core0Error(f"duplicate case name: {name}")
        names.add(name)
        case_id = _u64(item.get("case_id"), f"case {name} id")
        if case_id in identifiers:
            raise Core0Error(f"duplicate case id: 0x{case_id:016x}")
        identifiers.add(case_id)
        arguments = item.get("args")
        if not isinstance(arguments, list) or len(arguments) != 3:
            raise Core0Error(f"case {name} must contain exactly three args")
        args = tuple(_u64(value, f"case {name} arg") for value in arguments)
        coverage = item.get("covers")
        if (
            not isinstance(coverage, list)
            or not coverage
            or any(not isinstance(value, str) or not value for value in coverage)
        ):
            raise Core0Error(f"case {name} has no valid coverage labels")
        cases.append(TargetCase(name, case_id, args, tuple(coverage)))
    return CaseCorpus(seed, root, tuple(cases))


def _safe_repo_file(root: Path, relative: object, *, suffix: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise Core0Error(f"fixture path must be nonempty and repository-relative: {relative!r}")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as error:
        raise Core0Error(f"fixture escapes the repository: {relative}") from error
    if resolved.suffix != suffix or not resolved.is_file():
        raise Core0Error(f"fixture is missing or has the wrong suffix: {relative}")
    return resolved


def load_rejections(path: Path, root: Path) -> tuple[RejectionCase, ...]:
    raw = load_json(path)
    if not isinstance(raw, dict):
        raise Core0Error("rejection manifest is not an object")
    if set(raw) != {"schema_version", "profile", "cases"}:
        raise Core0Error("rejection manifest fields differ from the closed schema")
    if raw.get("schema_version") != 1:
        raise Core0Error("rejection manifest has an unsupported schema")
    if raw.get("profile") != "core0-v0.1":
        raise Core0Error("rejection manifest has an unsupported Core0 profile")
    values = raw.get("cases")
    if not isinstance(values, list) or not values:
        raise Core0Error("rejection corpus is empty")
    cases: list[RejectionCase] = []
    names: set[str] = set()
    paths: set[Path] = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise Core0Error(f"rejection #{index} is not an object")
        if set(item) != {"name", "path", "required_fragments"}:
            raise Core0Error(f"rejection #{index} fields differ from the closed schema")
        name = item.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise Core0Error(f"rejection #{index} has an empty or duplicate name")
        names.add(name)
        fixture = _safe_repo_file(root, item.get("path"), suffix=".lean")
        reject_root = (root / "examples/core0/reject").resolve()
        try:
            fixture.relative_to(reject_root)
        except ValueError as error:
            raise Core0Error(f"rejection fixture is outside examples/core0/reject: {fixture}") from error
        if fixture in paths:
            raise Core0Error(f"duplicate rejection fixture: {fixture}")
        paths.add(fixture)
        fragments = item.get("required_fragments")
        if (
            not isinstance(fragments, list)
            or not fragments
            or any(not isinstance(value, str) or not value for value in fragments)
        ):
            raise Core0Error(f"rejection {name} has no valid diagnostic fragments")
        cases.append(RejectionCase(name, fixture, tuple(fragments)))
    discovered = set(reject_root.glob("*.lean"))
    if paths != discovered:
        missing = sorted(str(path.relative_to(root)) for path in discovered - paths)
        stale = sorted(str(path.relative_to(root)) for path in paths - discovered)
        raise Core0Error(
            f"rejection manifest/file set mismatch (untested={missing!r}, stale={stale!r})"
        )
    return tuple(cases)


def run_rejection_suite(
    cases: Iterable[RejectionCase],
    *,
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for case in cases:
        relative = case.path.relative_to(root)
        result = run_bounded(
            ("lake", "env", "lean", str(relative)),
            cwd=root,
            timeout_seconds=timeout_seconds,
        )
        combined = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode(
            "utf-8", errors="replace"
        )
        log_path = output_dir / f"{case.name}.txt"
        log_path.write_text(combined, encoding="utf-8")
        if result.returncode == 0:
            raise Core0Error(f"negative fixture unexpectedly passed: {relative}")
        absent = [fragment for fragment in case.required_fragments if fragment not in combined]
        if absent:
            raise Core0Error(
                f"negative fixture {relative} lacked diagnostic fragments: {absent!r}"
            )
        records.append(
            {
                "name": case.name,
                "path": str(relative),
                "returncode": result.returncode,
                "required_fragments": list(case.required_fragments),
                "diagnostic_log": str(log_path.relative_to(root)),
                "diagnostic_sha256": sha256(log_path),
            }
        )
    if not records:
        raise Core0Error("negative suite executed zero cases")
    return records


def evaluate_reference(
    corpus: CaseCorpus,
    *,
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> list[int]:
    source = output_dir / "Reference.lean"
    lines = ["import Lemma.Compiler.Export", "import examples.core0.Positive", ""]
    for case in corpus.cases:
        args = " ".join(f'"{value}"' for value in case.args)
        lines.append(f"#core0_eval {corpus.root} {args}")
    lines.append("")
    source.write_text("\n".join(lines), encoding="utf-8")
    result = checked(
        ("lake", "env", "lean", str(source)),
        cwd=root,
        timeout_seconds=timeout_seconds,
    )
    stdout = result.stdout.decode("utf-8", errors="strict")
    stderr = result.stderr.decode("utf-8", errors="strict")
    (output_dir / "reference.stdout").write_text(stdout, encoding="utf-8")
    (output_dir / "reference.stderr").write_text(stderr, encoding="utf-8")
    matches = REFERENCE_RESULT.findall(stdout + stderr)
    if len(matches) != len(corpus.cases):
        raise Core0Error(
            f"Lean reference produced {len(matches)} results for {len(corpus.cases)} cases"
        )
    return [int(value, 16) for value in matches]


def _dts_nodes(text: str) -> list[tuple[str, str]]:
    nodes: list[tuple[str, str]] = []
    header = re.compile(r"(?m)^\s*([A-Za-z0-9,._+@-]+)\s*\{")
    for match in header.finditer(text):
        opening = text.find("{", match.start(), match.end())
        depth = 0
        closing = None
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing is not None:
            nodes.append((match.group(1), text[opening + 1 : closing]))
    return nodes


def _reg(block: str) -> tuple[int, int] | None:
    match = re.search(r"(?m)^\s*reg\s*=\s*<([^;>]+)>\s*;", block)
    if match is None:
        return None
    cells = [int(value, 0) for value in re.findall(r"0x[0-9a-fA-F]+|\b[0-9]+\b", match.group(1))]
    if len(cells) != 4:
        return None
    return ((cells[0] << 32) | cells[1], (cells[2] << 32) | cells[3])


def validate_platform(directory: Path, root: Path) -> dict[str, object]:
    dtb = directory / "platform.dtb"
    dts = directory / "platform.dts"
    if not dtb.is_file() or not dts.is_file() or not dtb.stat().st_size or not dts.stat().st_size:
        raise Core0Error(f"missing QEMU platform DTB/DTS in {directory}")
    text = dts.read_text(encoding="utf-8", errors="strict")
    nodes = _dts_nodes(text)

    def find(
        description: str,
        predicate: Callable[[str, str, tuple[int, int]], bool],
    ) -> tuple[str, str, tuple[int, int]]:
        matches: list[tuple[str, str, tuple[int, int]]] = []
        for name, block in nodes:
            reg = _reg(block)
            if reg is not None and predicate(name, block, reg):
                matches.append((name, block, reg))
        if len(matches) != 1:
            raise Core0Error(
                f"QEMU DTB expected exactly one {description} node, found {len(matches)}"
            )
        return matches[0]

    memory = find(
        "128 MiB RAM",
        lambda name, block, reg: 'device_type = "memory"' in block
        and reg == (0x80000000, 0x08000000),
    )
    uart = find(
        "ns16550a UART",
        lambda name, block, reg: 'compatible = "ns16550a"' in block
        and reg == (0x10000000, 0x100),
    )
    finisher = find(
        "SiFive test finisher",
        lambda name, block, reg: "sifive,test" in block
        and reg == (0x00100000, 0x1000),
    )
    cpu_nodes = [
        (name, block)
        for name, block in nodes
        if name.startswith("cpu@") and 'device_type = "cpu"' in block
    ]
    if len(cpu_nodes) != 1:
        raise Core0Error(f"QEMU DTB expected exactly one CPU node, found {len(cpu_nodes)}")
    cpu_name, cpu_block = cpu_nodes[0]
    if 'status = "okay"' not in cpu_block or 'compatible = "riscv"' not in cpu_block:
        raise Core0Error("QEMU DTB CPU node is not an enabled RISC-V CPU")
    if 'riscv,isa-base = "rv64i"' not in cpu_block:
        raise Core0Error("QEMU DTB CPU does not advertise the rv64i ISA base")
    extension_match = re.search(
        r"riscv,isa-extensions\s*=\s*([^;]+);", cpu_block, re.MULTILINE
    )
    if extension_match is None:
        raise Core0Error("QEMU DTB CPU lacks riscv,isa-extensions")
    extensions = set(re.findall(r'"([A-Za-z0-9]+)"', extension_match.group(1)))
    required_extensions = {"i", "m", "zicsr", "zifencei"}
    missing_extensions = sorted(required_extensions - extensions)
    if missing_extensions:
        raise Core0Error(
            f"QEMU DTB CPU lacks required ISA extensions: {missing_extensions!r}"
        )
    return {
        "dtb": str(dtb.relative_to(root)),
        "dtb_sha256": sha256(dtb),
        "dts": str(dts.relative_to(root)),
        "dts_sha256": sha256(dts),
        "ram": {"node": memory[0], "start": "0x80000000", "size": "0x08000000"},
        "uart": {"node": uart[0], "start": "0x10000000", "size": "0x00000100"},
        "finisher": {
            "node": finisher[0],
            "start": "0x00100000",
            "size": "0x00001000",
        },
        "cpu": {
            "node": cpu_name,
            "count": 1,
            "isa_base": "rv64i",
            "required_extensions": sorted(required_extensions),
            "advertised_extensions": sorted(extensions),
        },
        "source": "pinned QEMU virt dumpdtb with -seed 1, decompiled by pinned dtc",
    }


def compare_rebuilds(
    first: Path, second: Path, *, root: Path, optimization: str
) -> dict[str, object]:
    comparisons: list[dict[str, object]] = []
    mismatches: list[str] = []
    for name in REPRODUCIBLE_ARTIFACTS:
        first_path = first / name
        second_path = second / name
        if not first_path.is_file() or not second_path.is_file():
            raise Core0Error(f"reproducibility input is missing: {name}")
        first_hash = sha256(first_path)
        second_hash = sha256(second_path)
        identical = first_hash == second_hash
        if not identical:
            mismatches.append(name)
        comparisons.append(
            {
                "path": name,
                "first_sha256": first_hash,
                "second_sha256": second_hash,
                "byte_identical": identical,
            }
        )
    if mismatches:
        raise Core0Error(
            f"{optimization} clean artifact-directory rebuild was not byte-identical: {mismatches!r}"
        )
    return {
        "optimization": optimization,
        "first": str(first.relative_to(root)),
        "second": str(second.relative_to(root)),
        "artifact_directory_clean": True,
        "lake_dependency_cache_reused": True,
        "all_expected_artifacts_byte_identical": True,
        "comparisons": comparisons,
    }


def _mutation_source(
    multiplier: int, *, helper_name: str = "mix", root_name: str = "entry"
) -> str:
    return f"""import Lemma.Compiler.Export

namespace Lemma.Core0.MutationProbe

def {helper_name} (value seed : UInt64) : UInt64 :=
  (value ^^^ seed) * {multiplier}

def {root_name} (x y seed : UInt64) : UInt64 :=
  let selected := if x ≤ y then x + y else x - y
  {helper_name} selected seed

#core0_export {root_name}

end Lemma.Core0.MutationProbe
"""


def run_mutation_test(
    *,
    root: Path,
    work: Path,
    timeout_seconds: float,
    qemu_timeout: float,
) -> dict[str, object]:
    source_dir = work / "mutation-sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    baseline_source = source_dir / "Baseline.lean"
    changed_source = source_dir / "Changed.lean"
    renamed_source = source_dir / "Renamed.lean"
    baseline_source.write_text(_mutation_source(3), encoding="utf-8")
    changed_source.write_text(_mutation_source(5), encoding="utf-8")
    renamed_source.write_text(
        _mutation_source(3, helper_name="renamedMix", root_name="renamedEntry"),
        encoding="utf-8",
    )
    baseline_dir = work / "mutation-baseline-O2"
    changed_dir = work / "mutation-changed-O2"
    renamed_dir = work / "mutation-renamed-O2"
    build(
        root=root,
        output_dir=baseline_dir,
        opt_level="O2",
        export_source=baseline_source,
        build_lean=False,
        timeout_seconds=timeout_seconds,
    )
    build(
        root=root,
        output_dir=changed_dir,
        opt_level="O2",
        export_source=changed_source,
        build_lean=False,
        timeout_seconds=timeout_seconds,
    )
    build(
        root=root,
        output_dir=renamed_dir,
        opt_level="O2",
        export_source=renamed_source,
        build_lean=False,
        timeout_seconds=timeout_seconds,
    )
    audit_core0.audit(baseline_dir, root)
    audit_core0.audit(changed_dir, root)
    audit_core0.audit(renamed_dir, root)
    case_id = 0x4D55544154453031
    args = (2, 3, 7)
    baseline = run_case(
        root=root,
        image=baseline_dir / "image.elf",
        output_dir=baseline_dir / "runs",
        case_id=case_id,
        args=args,
        timeout_seconds=qemu_timeout,
    )
    changed = run_case(
        root=root,
        image=changed_dir / "image.elf",
        output_dir=changed_dir / "runs",
        case_id=case_id,
        args=args,
        timeout_seconds=qemu_timeout,
    )
    renamed = run_case(
        root=root,
        image=renamed_dir / "image.elf",
        output_dir=renamed_dir / "runs",
        case_id=case_id,
        args=args,
        timeout_seconds=qemu_timeout,
    )
    if baseline["result"] == changed["result"]:
        raise Core0Error("accepted source mutation did not change guest behavior")
    if sha256(baseline_dir / "program.ll") == sha256(changed_dir / "program.ll"):
        raise Core0Error("accepted source mutation did not change generated LLVM")
    if sha256(baseline_dir / "image.elf") == sha256(changed_dir / "image.elf"):
        raise Core0Error("accepted source mutation did not change the linked image")
    if renamed["result"] != baseline["result"]:
        raise Core0Error("renaming accepted declarations changed guest behavior")
    return {
        "status": "pass",
        "fresh_qemu_boots": 3,
        "mutation": "the accepted mix multiplier changes from 3 to 5",
        "args": [f"0x{value:016x}" for value in args],
        "baseline_source_sha256": sha256(baseline_source),
        "changed_source_sha256": sha256(changed_source),
        "baseline_program_ll_sha256": sha256(baseline_dir / "program.ll"),
        "changed_program_ll_sha256": sha256(changed_dir / "program.ll"),
        "baseline_image_sha256": sha256(baseline_dir / "image.elf"),
        "changed_image_sha256": sha256(changed_dir / "image.elf"),
        "baseline_result": baseline["result"],
        "changed_result": changed["result"],
        "rename": {
            "description": "mix/entry renamed to renamedMix/renamedEntry without semantic change",
            "source_sha256": sha256(renamed_source),
            "program_ll_sha256": sha256(renamed_dir / "program.ll"),
            "image_sha256": sha256(renamed_dir / "image.elf"),
            "result": renamed["result"],
            "matches_baseline": True,
        },
    }


def run_audit_regression(
    *,
    root: Path,
    baseline_dir: Path,
    output_dir: Path,
    fixture: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=False)
    for name in audit_core0.REQUIRED_ARTIFACTS:
        shutil.copy2(baseline_dir / name, output_dir / name)
    shutil.copy2(fixture, output_dir / "foreign-runtime.ll")
    object_command = [
        "llc",
        *LLC_ARGUMENTS,
        "-O2",
        "foreign-runtime.ll",
        "-o",
        "foreign-runtime.o",
    ]
    checked(object_command, cwd=output_dir, timeout_seconds=timeout_seconds)
    link_command = [
        "ld.lld",
        *LINK_ARGUMENTS,
        "--undefined=lean_alloc_object",
        "-o",
        "image.elf",
        "startup.o",
        "program.o",
        "foreign-runtime.o",
    ]
    checked(link_command, cwd=output_dir, timeout_seconds=timeout_seconds)
    undefined = checked(
        ("llvm-nm", "--undefined-only", "image.elf"),
        cwd=output_dir,
        timeout_seconds=30,
    ).stdout.decode("utf-8", errors="strict")
    if undefined.strip():
        raise Core0Error(
            "audit regression ELF was not statically resolved before audit:\n" + undefined
        )
    defined = checked(
        ("llvm-nm", "--defined-only", "image.elf"),
        cwd=output_dir,
        timeout_seconds=30,
    ).stdout.decode("utf-8", errors="strict")
    for symbol in ("lean_alloc_object", "lemma_forbidden_foreign_runtime"):
        if symbol not in defined:
            raise Core0Error(f"linker did not retain audit-regression symbol {symbol}")
    provenance_path = output_dir / "provenance.json"
    provenance = load_json(provenance_path)
    if not isinstance(provenance, dict) or not isinstance(provenance.get("linked_inputs"), list):
        raise Core0Error("baseline provenance was malformed during audit regression")
    provenance["linked_inputs"].append(
        {
            "path": "foreign-runtime.o",
            "kind": "unexpected-foreign-runtime",
            "sha256": sha256(output_dir / "foreign-runtime.o"),
            "generation_command": object_command,
            "source": str(fixture.relative_to(root)),
            "source_sha256": sha256(fixture),
            "purpose": "deliberate statically resolved audit-regression dependency",
        }
    )
    provenance["link_command"] = link_command
    write_json(provenance_path, provenance)
    try:
        audit_core0.audit(output_dir, root)
    except Core0Error as error:
        diagnostic = str(error)
    else:
        raise Core0Error("closure audit accepted a statically resolved foreign runtime object")
    if "exactly the two linked objects" not in diagnostic and "unexpected linked object" not in diagnostic:
        raise Core0Error(f"audit regression failed for an unexpected reason: {diagnostic}")
    return {
        "status": "pass",
        "fixture": str(fixture.relative_to(root)),
        "fixture_sha256": sha256(fixture),
        "foreign_object_sha256": sha256(output_dir / "foreign-runtime.o"),
        "final_undefined_symbols": [],
        "retained_symbols": ["lean_alloc_object", "lemma_forbidden_foreign_runtime"],
        "expected_audit_failure": diagnostic,
    }


def check(
    *,
    root: Path,
    work: Path,
    cases_path: Path,
    rejections_path: Path,
    foreign_fixture: Path,
    clean: bool,
    timeout_seconds: float,
    qemu_timeout: float,
) -> dict[str, object]:
    # Validate every checked-in corpus before inspecting tools or creating build
    # output.  An empty/malformed corpus can therefore never degrade to a skip.
    corpus = load_case_corpus(cases_path)
    rejections = load_rejections(rejections_path, root)
    foreign_fixture = _safe_repo_file(
        root, str(foreign_fixture.relative_to(root)), suffix=".ll"
    )
    require_tools()
    prepare_output_directory(work, root, clean=clean)

    builds: dict[str, Path] = {"O0": work / "O0", "O2": work / "O2"}
    audits: dict[str, object] = {}
    platforms: dict[str, object] = {}
    export_source = root / "examples/core0/Build.lean"
    for index, optimization in enumerate(("O0", "O2")):
        build(
            root=root,
            output_dir=builds[optimization],
            opt_level=optimization,
            export_source=export_source,
            build_lean=index == 0,
            timeout_seconds=timeout_seconds,
        )
        platforms[optimization] = validate_platform(builds[optimization], root)
        audits[optimization] = audit_core0.audit(builds[optimization], root)
        manifest = audits[optimization].get("manifest")
        if not isinstance(manifest, dict) or manifest.get("root") != corpus.root:
            observed = manifest.get("root") if isinstance(manifest, dict) else None
            raise Core0Error(
                f"{optimization} target manifest root {observed!r} "
                f"does not match case/reference root {corpus.root!r}"
            )

    if sha256(builds["O0"] / "core0-manifest.json") != sha256(
        builds["O2"] / "core0-manifest.json"
    ):
        raise Core0Error("O0/O2 target manifests are not byte-identical")

    # Build the library before checking isolated rejection fixtures.  This order
    # is required in a clean checkout where no untracked `.lake` cache exists.
    negative_records = run_rejection_suite(
        rejections,
        root=root,
        output_dir=work / "rejections",
        timeout_seconds=timeout_seconds,
    )

    reference_values = evaluate_reference(
        corpus,
        root=root,
        output_dir=work,
        timeout_seconds=timeout_seconds,
    )
    differential: list[dict[str, object]] = []
    for case, expected in zip(corpus.cases, reference_values, strict=True):
        target_results: dict[str, str] = {}
        run_records: dict[str, str] = {}
        for optimization in ("O0", "O2"):
            record = run_case(
                root=root,
                image=builds[optimization] / "image.elf",
                output_dir=builds[optimization] / "runs",
                case_id=case.case_id,
                args=case.args,
                timeout_seconds=qemu_timeout,
            )
            observed = int(str(record["result"]), 0)
            if observed != expected:
                raise Core0Error(
                    f"{optimization} target/reference mismatch for {case.name}: "
                    f"0x{observed:016x} != 0x{expected:016x}"
                )
            target_results[optimization] = f"0x{observed:016x}"
            run_records[optimization] = str(
                (builds[optimization] / "runs" / f"run-{case.case_id:016x}.json").relative_to(root)
            )
        if target_results["O0"] != target_results["O2"]:
            raise Core0Error(f"O0/O2 target mismatch for {case.name}")
        differential.append(
            {
                "name": case.name,
                "case_id": f"0x{case.case_id:016x}",
                "args": [f"0x{value:016x}" for value in case.args],
                "covers": list(case.covers),
                "reference": f"0x{expected:016x}",
                "target": target_results,
                "run_records": run_records,
            }
        )

    repetitions: list[dict[str, object]] = []
    for optimization in ("O0", "O2"):
        repeat = work / f"{optimization}-repeat"
        build(
            root=root,
            output_dir=repeat,
            opt_level=optimization,
            export_source=export_source,
            build_lean=False,
            timeout_seconds=timeout_seconds,
        )
        validate_platform(repeat, root)
        audit_core0.audit(repeat, root)
        repetitions.append(
            compare_rebuilds(builds[optimization], repeat, root=root, optimization=optimization)
        )

    mutation = run_mutation_test(
        root=root,
        work=work,
        timeout_seconds=timeout_seconds,
        qemu_timeout=qemu_timeout,
    )
    audit_regression = run_audit_regression(
        root=root,
        baseline_dir=builds["O2"],
        output_dir=work / "audit-regression",
        fixture=foreign_fixture,
        timeout_seconds=timeout_seconds,
    )

    report: dict[str, object] = {
        "schema_version": 1,
        "status": "pass",
        "scope": "Task 001 scalar Core0 freestanding slice; not all of G1",
        "case_manifest": str(cases_path.relative_to(root)),
        "case_manifest_sha256": sha256(cases_path),
        "rejection_manifest": str(rejections_path.relative_to(root)),
        "rejection_manifest_sha256": sha256(rejections_path),
        "seed": f"0x{corpus.seed:016x}",
        "root": corpus.root,
        "fresh_qemu_boots": len(differential) * 2 + int(mutation["fresh_qemu_boots"]),
        "differential_cases": differential,
        "negative_cases": negative_records,
        "audits": audits,
        "platforms": platforms,
        "reproducibility": repetitions,
        "source_mutation": mutation,
        "audit_regression": audit_regression,
        "limitations": [
            "Finite differential tests are not a compiler-correctness proof.",
            "Repeated target artifact directories are fresh; the pinned Lake dependency cache is reused.",
            "This result does not complete the remaining G1 machine and conformance obligations.",
        ],
    }
    write_json(work / "check-results.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=Path("build/core0/check"))
    parser.add_argument("--cases", type=Path, default=Path("tests/core0/cases.json"))
    parser.add_argument(
        "--rejections", type=Path, default=Path("tests/core0/rejections.json")
    )
    parser.add_argument(
        "--foreign-fixture",
        type=Path,
        default=Path("tests/core0/fixtures/foreign-runtime.ll"),
    )
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--qemu-timeout", type=float, default=5.0)
    ns = parser.parse_args()
    root = repo_root()

    def resolve(path: Path) -> Path:
        return (root / path).resolve() if not path.is_absolute() else path.resolve()

    work = resolve(ns.work_dir)
    try:
        report = check(
            root=root,
            work=work,
            cases_path=resolve(ns.cases),
            rejections_path=resolve(ns.rejections),
            foreign_fixture=resolve(ns.foreign_fixture),
            clean=ns.clean,
            timeout_seconds=ns.timeout,
            qemu_timeout=ns.qemu_timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        if work.is_dir():
            try:
                write_json(
                    work / "check-failure.json",
                    {"schema_version": 1, "status": "fail", "error": str(error)},
                )
            except OSError:
                pass
        print(f"CORE0 CHECK FAIL: {error}", file=sys.stderr)
        return 1
    print(
        f"CORE0 CHECK PASS: {len(report['differential_cases'])} cases at O0/O2; "
        f"{len(report['negative_cases'])} expected rejections"
    )
    print(f"evidence: {work / 'check-results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
