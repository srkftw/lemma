#!/usr/bin/env python3
"""Build the Gate 7 ``core0-v0.6`` synchronous-trap test image."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from build_core0 import build
from core0_common import Core0Error, repo_root


EXPORT_SOURCE = Path("examples/foundation/TrapBuild.lean")
ELABORATION_SOURCES = (
    Path("examples/foundation/DeviceConformanceSupport.lean"),
    Path("examples/foundation/TrapConformance.lean"),
)
HOST_INPUTS = (
    Path("scripts/build_trap_suite.py"),
    Path("scripts/audit_core0.py"),
    Path("scripts/audit_trap.py"),
    Path("scripts/check_foundation.py"),
    Path("scripts/gate7_corpus.py"),
    Path("scripts/run_trap_case.py"),
    Path("scripts/check_foundation_gate7.py"),
    Path("examples/foundation/TrapFrontendProbes.lean"),
    Path("examples/foundation/TrapPolicyProbes.lean"),
    Path("examples/foundation/gate7-reject/HiddenExternTrap.lean"),
    Path("examples/foundation/gate7-reject/PureTrapResult.lean"),
    Path("examples/foundation/gate7-reject/StoredTrapContinuation.lean"),
    Path("examples/foundation/gate7-reject/V05Trap.lean"),
    Path("examples/foundation/gate7-reject/rejections.json"),
)


def build_trap_suite(
    *,
    root: Path,
    output_dir: Path,
    opt_level: str,
    mutation: int = 0,
    clean: bool = False,
    build_lean: bool = True,
    timeout_seconds: float = 180.0,
) -> dict[str, object]:
    """Build one closed trap-suite artifact; ``mutation`` is test-only 0 or 1."""
    if isinstance(mutation, bool) or not isinstance(mutation, int) or mutation not in {0, 1}:
        raise Core0Error("trap restore mutation must be the integer 0 or 1")
    return build(
        root=root,
        output_dir=output_dir,
        opt_level=opt_level,
        export_source=root / EXPORT_SOURCE,
        clean=clean,
        build_lean=build_lean,
        timeout_seconds=timeout_seconds,
        artifact_category="test-trap-suite",
        additional_source_inputs=HOST_INPUTS,
        elaboration_sources=ELABORATION_SOURCES,
        export_environment={"LEMMA_TRAP_RESTORE_MUTATION": str(mutation)},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opt-level", choices=("O0", "O2"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mutation", type=int, choices=(0, 1), default=0)
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
        record = build_trap_suite(
            root=root,
            output_dir=output_dir,
            opt_level=ns.opt_level,
            mutation=ns.mutation,
            clean=ns.clean,
            timeout_seconds=ns.timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"TRAP SUITE BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
