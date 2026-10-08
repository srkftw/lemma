#!/usr/bin/env python3
"""Exhaustive direct-Lean versus checked-Core0 comparison for UInt8 anchors."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Sequence

from core0_common import (
    CommandResult,
    Core0Error,
    repo_root,
    require_tools,
    run_bounded,
    sha256,
    write_json,
)


PROFILE = "gate2-u8-exhaustive-v1"
PAIR_COUNT = 256 * 256
ROOTS: tuple[tuple[str, str, str], ...] = (
    ("u8-add", "Lemma.Examples.Foundation.Conformance.u8Add", "u8"),
    ("u8-sub", "Lemma.Examples.Foundation.Conformance.u8Sub", "u8"),
    ("u8-lt", "Lemma.Examples.Foundation.Conformance.u8Lt", "bool"),
    ("u8-le", "Lemma.Examples.Foundation.Conformance.u8Le", "bool"),
    ("u8-eq", "Lemma.Examples.Foundation.Conformance.u8Eq", "bool"),
)
EXPECTED_BYTES = PAIR_COUNT * len(ROOTS)

MODEL_SUPPORT = Path("Lemma/Compiler/Test/ExhaustiveU8.lean")
SOURCE_DRIVER = Path("examples/foundation/ExhaustiveU8Source.lean")
EXAMPLE_SOURCES: tuple[Path, ...] = (
    Path("examples/foundation/ConformanceSupport.lean"),
    Path("examples/foundation/ConformanceMovedA.lean"),
    Path("examples/foundation/ConformanceMovedB.lean"),
    Path("examples/foundation/ConformanceImportBase.lean"),
    Path("examples/foundation/ConformanceImportExtra.lean"),
    Path("examples/foundation/Conformance.lean"),
)


def _display(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _command_record(result: CommandResult) -> dict[str, object]:
    return {
        "argv": list(result.argv),
        "returncode": result.returncode,
        "elapsed_seconds": round(result.elapsed_seconds, 6),
    }


def _run(
    argv: Sequence[str],
    *,
    root: Path,
    deadline: float,
    env: dict[str, str] | None = None,
) -> CommandResult:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Core0Error(f"{PROFILE} exhausted its total timeout before: {' '.join(argv)}")
    result = run_bounded(
        argv,
        cwd=root,
        timeout_seconds=remaining,
        env=env,
    )
    if result.returncode != 0:
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise Core0Error(
            f"{PROFILE} command failed with exit {result.returncode}: {' '.join(argv)}\n"
            f"stdout:\n{stdout}\nstderr:\n{stderr}"
        )
    return result


def _olean_path(root: Path, source: Path) -> Path:
    return root / ".lake/build/lib/lean" / source.with_suffix(".olean")


def _compile_module(
    root: Path,
    source: Path,
    *,
    deadline: float,
) -> CommandResult:
    output = _olean_path(root, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    return _run(
        (
            "lake",
            "env",
            "lean",
            "-o",
            str(output.relative_to(root)),
            str(source),
        ),
        root=root,
        deadline=deadline,
    )


def _render_model_driver(model_output: Path) -> str:
    output_literal = json.dumps(str(model_output.resolve()))
    roots = "\n  ".join(root for _, root, _ in ROOTS)
    return (
        "import Lemma.Compiler.Test.ExhaustiveU8\n"
        "import examples.foundation.Conformance\n\n"
        "set_option maxHeartbeats 0\n\n"
        f"#core0_exhaustive_u8_model {output_literal}\n"
        f"  {roots}\n"
    )


def _first_mismatch(source: bytes, model: bytes) -> tuple[int, int, int, int, int] | None:
    for index, (source_value, model_value) in enumerate(zip(source, model, strict=True)):
        if source_value != model_value:
            root_index, pair_index = divmod(index, PAIR_COUNT)
            x, y = divmod(pair_index, 256)
            return root_index, x, y, source_value, model_value
    return None


def _validate_and_describe(source: bytes, model: bytes) -> list[dict[str, object]]:
    if len(source) != EXPECTED_BYTES:
        raise Core0Error(
            f"direct-source exhaustive artifact has {len(source)} bytes; "
            f"expected {EXPECTED_BYTES}"
        )
    if len(model) != EXPECTED_BYTES:
        raise Core0Error(
            f"checked-model exhaustive artifact has {len(model)} bytes; "
            f"expected {EXPECTED_BYTES}"
        )
    mismatch = _first_mismatch(source, model)
    if mismatch is not None:
        root_index, x, y, source_value, model_value = mismatch
        operation, root_name, _ = ROOTS[root_index]
        raise Core0Error(
            "exhaustive UInt8 mismatch: "
            f"operation={operation}, root={root_name}, x={x}, y={y}, "
            f"direct-source={source_value}, checked-model={model_value}"
        )

    descriptions: list[dict[str, object]] = []
    for index, (operation, root_name, result_type) in enumerate(ROOTS):
        start = index * PAIR_COUNT
        end = start + PAIR_COUNT
        source_slice = source[start:end]
        model_slice = model[start:end]
        if result_type == "bool" and not set(source_slice).issubset({0, 1}):
            raise Core0Error(f"direct-source Bool matrix is noncanonical for {root_name}")
        if result_type == "bool" and not set(model_slice).issubset({0, 1}):
            raise Core0Error(f"checked-model Bool matrix is noncanonical for {root_name}")
        descriptions.append(
            {
                "operation": operation,
                "root": root_name,
                "signature": {"args": ["u8", "u8"], "result": result_type},
                "ordered_pair_count": PAIR_COUNT,
                "offset_bytes": start,
                "direct_source_sha256": hashlib.sha256(source_slice).hexdigest(),
                "checked_model_sha256": hashlib.sha256(model_slice).hexdigest(),
                "match": source_slice == model_slice,
            }
        )
    return descriptions


def run_exhaustive(
    root: Path,
    output_dir: Path,
    timeout_seconds: float,
) -> dict[str, object]:
    """Run the bounded exhaustive comparison and return its retained PASS report."""

    root = root.resolve()
    output_dir = output_dir.resolve()
    if timeout_seconds <= 0:
        raise Core0Error("exhaustive UInt8 timeout must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "exhaustive-u8.json"
    report_partial = output_dir / "exhaustive-u8.partial.json"
    # Remove an earlier PASS before any check that can fail.  Consumers must
    # never confuse a stale report with the outcome of this invocation.
    report_path.unlink(missing_ok=True)
    report_partial.unlink(missing_ok=True)
    required = (root / "lakefile.toml", root / MODEL_SUPPORT, root / SOURCE_DRIVER)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise Core0Error("missing exhaustive UInt8 inputs: " + ", ".join(missing))
    source_text = (root / SOURCE_DRIVER).read_text(encoding="utf-8")
    imports = [line for line in source_text.splitlines() if line.startswith("import ")]
    if imports != ["import examples.foundation.Conformance"]:
        raise Core0Error(
            "direct-source exhaustive driver must import only examples.foundation.Conformance"
        )
    model_text = (root / MODEL_SUPPORT).read_text(encoding="utf-8")
    if "Lemma.Core0.checkAndLower" not in model_text or "Lemma.Core0.evalProgram" not in model_text:
        raise Core0Error("checked-model exhaustive support bypasses its required Core0 route")

    require_tools(("lean", "lake"))
    source_path = output_dir / "exhaustive-u8-source.bin"
    model_path = output_dir / "exhaustive-u8-model.bin"
    source_partial = output_dir / "exhaustive-u8-source.partial.bin"
    model_partial = output_dir / "exhaustive-u8-model.partial.bin"
    model_driver = output_dir / "ExhaustiveU8Model.lean"
    source_stdout = output_dir / "exhaustive-u8-source.stdout"
    source_stderr = output_dir / "exhaustive-u8-source.stderr"
    model_stdout = output_dir / "exhaustive-u8-model.stdout"
    model_stderr = output_dir / "exhaustive-u8-model.stderr"
    transient = (
        report_path,
        report_partial,
        source_path,
        model_path,
        source_partial,
        model_partial,
    )
    for path in transient:
        path.unlink(missing_ok=True)

    started = time.monotonic()
    deadline = started + timeout_seconds
    commands: list[dict[str, object]] = []
    try:
        support = _compile_module(root, MODEL_SUPPORT, deadline=deadline)
        commands.append(_command_record(support))
        for source in EXAMPLE_SOURCES:
            if not (root / source).is_file():
                raise Core0Error(f"missing exhaustive source dependency: {source}")
            commands.append(
                _command_record(_compile_module(root, source, deadline=deadline))
            )

        source_env = os.environ.copy()
        source_env["LEMMA_GATE2_EXHAUSTIVE_SOURCE_OUT"] = str(source_partial)
        source_result = _run(
            ("lake", "env", "lean", "--run", str(SOURCE_DRIVER)),
            root=root,
            deadline=deadline,
            env=source_env,
        )
        commands.append(_command_record(source_result))
        source_stdout.write_bytes(source_result.stdout)
        source_stderr.write_bytes(source_result.stderr)
        source_log = source_result.stdout + source_result.stderr
        if b"CORE0_U8_EXHAUSTIVE_SOURCE:5:327680" not in source_log:
            raise Core0Error("direct-source exhaustive completion marker is missing")

        model_driver.write_text(_render_model_driver(model_partial), encoding="utf-8")
        model_result = _run(
            ("lake", "env", "lean", str(model_driver)),
            root=root,
            deadline=deadline,
        )
        commands.append(_command_record(model_result))
        model_stdout.write_bytes(model_result.stdout)
        model_stderr.write_bytes(model_result.stderr)
        model_log = model_result.stdout + model_result.stderr
        if b"CORE0_U8_EXHAUSTIVE_MODEL:5:327680" not in model_log:
            raise Core0Error("checked-model exhaustive completion marker is missing")

        if not source_partial.is_file() or not model_partial.is_file():
            raise Core0Error("an exhaustive UInt8 evaluator did not write its result artifact")
        source_bytes = source_partial.read_bytes()
        model_bytes = model_partial.read_bytes()
        root_results = _validate_and_describe(source_bytes, model_bytes)
        source_partial.replace(source_path)
        model_partial.replace(model_path)

        elapsed = time.monotonic() - started
        report: dict[str, object] = {
            "schema_version": 1,
            "profile": PROFILE,
            "status": "pass",
            "enumeration": {
                "root_order": [root_name for _, root_name, _ in ROOTS],
                "input_order": "x-major-then-y, each 0..255 inclusive",
                "seed": None,
            },
            "root_count": len(ROOTS),
            "ordered_pairs_per_root": PAIR_COUNT,
            "total_comparisons": EXPECTED_BYTES,
            "roots": root_results,
            "routes": {
                "direct_source": (
                    "original elaborated Conformance declarations invoked directly; "
                    "no Core0 checker/model import"
                ),
                "checked_model": "checkAndLower once per root, then evalProgram per pair",
                "host": "orchestration, byte equality, hashing, and mismatch localization only",
            },
            "inputs": {
                "direct_source_driver": _display(root / SOURCE_DRIVER, root),
                "direct_source_driver_sha256": sha256(root / SOURCE_DRIVER),
                "checked_model_support": _display(root / MODEL_SUPPORT, root),
                "checked_model_support_sha256": sha256(root / MODEL_SUPPORT),
                "generated_model_driver": _display(model_driver, root),
                "generated_model_driver_sha256": sha256(model_driver),
            },
            "artifacts": {
                "direct_source": {
                    "path": _display(source_path, root),
                    "bytes": source_path.stat().st_size,
                    "sha256": sha256(source_path),
                },
                "checked_model": {
                    "path": _display(model_path, root),
                    "bytes": model_path.stat().st_size,
                    "sha256": sha256(model_path),
                },
                "logs": [
                    _display(source_stdout, root),
                    _display(source_stderr, root),
                    _display(model_stdout, root),
                    _display(model_stderr, root),
                ],
            },
            "commands": commands,
            "elapsed_seconds": round(elapsed, 6),
        }
        write_json(report_partial, report)
        report_partial.replace(report_path)
        return report
    except Exception:
        report_path.unlink(missing_ok=True)
        report_partial.unlink(missing_ok=True)
        source_partial.unlink(missing_ok=True)
        model_partial.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    try:
        report = run_exhaustive(repo_root(), args.output_dir, args.timeout_seconds)
    except Core0Error as error:
        print(f"gate2 exhaustive check failed: {error}", file=sys.stderr)
        return 1
    print(
        "Gate 2 UInt8 exhaustive comparison: "
        f"{report['total_comparisons']} source/model matches across {report['root_count']} roots"
    )
    print(f"report: {(args.output_dir.resolve() / 'exhaustive-u8.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
