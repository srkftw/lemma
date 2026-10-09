#!/usr/bin/env python3
"""Build the additive Gate 2 typed multi-root freestanding image."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from build_core0 import build
from core0_common import Core0Error, repo_root


SCALAR_EXPORT_SOURCE = Path("examples/foundation/ScalarBuild.lean")
SCALAR_ELABORATION_SOURCES = (
    Path("examples/foundation/ConformanceSupport.lean"),
    Path("examples/foundation/ConformanceMovedA.lean"),
    Path("examples/foundation/ConformanceMovedB.lean"),
    Path("examples/foundation/ConformanceImportBase.lean"),
    Path("examples/foundation/ConformanceImportExtra.lean"),
    Path("examples/foundation/Conformance.lean"),
)
SCALAR_HOST_INPUTS = (
    Path("scripts/build_scalar_suite.py"),
    Path("scripts/gate2_corpus.py"),
    Path("scripts/run_scalar_batch.py"),
)


def build_scalar_suite(
    *,
    root: Path,
    output_dir: Path,
    opt_level: str,
    suite_id: int,
    source_seed: int,
    runtime_seed: int,
    clean: bool = False,
    build_lean: bool = True,
    timeout_seconds: float = 180.0,
) -> dict[str, object]:
    for label, value in (
        ("suite id", suite_id),
        ("source seed", source_seed),
        ("runtime seed", runtime_seed),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << 64:
            raise Core0Error(f"scalar-suite {label} is outside UInt64")
    return build(
        root=root,
        output_dir=output_dir,
        opt_level=opt_level,
        export_source=root / SCALAR_EXPORT_SOURCE,
        clean=clean,
        build_lean=build_lean,
        timeout_seconds=timeout_seconds,
        artifact_category="test-frontend-suite",
        additional_source_inputs=SCALAR_HOST_INPUTS,
        elaboration_sources=SCALAR_ELABORATION_SOURCES,
        export_environment={
            "LEMMA_SCALAR_SUITE_ID": str(suite_id),
            "LEMMA_SCALAR_SOURCE_SEED": str(source_seed),
            "LEMMA_SCALAR_RUNTIME_SEED": str(runtime_seed),
        },
    )


def _u64(text: str) -> int:
    try:
        value = int(text, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid UInt64: {text}") from error
    if not 0 <= value < 1 << 64:
        raise argparse.ArgumentTypeError(f"UInt64 is out of range: {text}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opt-level", choices=("O0", "O2"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--suite-id", type=_u64, required=True)
    parser.add_argument("--source-seed", type=_u64, required=True)
    parser.add_argument("--runtime-seed", type=_u64, required=True)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=180.0)
    ns = parser.parse_args()
    root = repo_root()
    output_dir = (
        (root / ns.output_dir).resolve()
        if not ns.output_dir.is_absolute()
        else ns.output_dir.resolve()
    )
    try:
        record = build_scalar_suite(
            root=root,
            output_dir=output_dir,
            opt_level=ns.opt_level,
            suite_id=ns.suite_id,
            source_seed=ns.source_seed,
            runtime_seed=ns.runtime_seed,
            clean=ns.clean,
            timeout_seconds=ns.timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"SCALAR SUITE BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
