#!/usr/bin/env python3
"""Build the Gate 8 ``core0-v0.7`` machine-timer test image."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from build_core0 import build
from core0_common import Core0Error, repo_root


EXPORT_SOURCE = Path("examples/foundation/TimerBuild.lean")
ELABORATION_SOURCES = (
    Path("examples/foundation/DeviceConformanceSupport.lean"),
    Path("examples/foundation/TrapConformance.lean"),
    Path("examples/foundation/TimerConformance.lean"),
)
HOST_INPUTS = (
    Path("scripts/build_timer_suite.py"),
    Path("scripts/audit_core0.py"),
    Path("scripts/audit_device.py"),
    Path("scripts/audit_memory.py"),
    Path("scripts/audit_timer.py"),
    Path("scripts/audit_trap.py"),
    Path("scripts/check_foundation.py"),
    Path("scripts/gate8_corpus.py"),
    Path("scripts/run_timer_case.py"),
    Path("scripts/run_trap_case.py"),
    Path("scripts/check_foundation_gate8.py"),
    Path("examples/foundation/TimerFrontendProbes.lean"),
    Path("examples/foundation/TimerPolicyProbes.lean"),
    Path("examples/foundation/gate8-reject/HiddenExternTimer.lean"),
    Path("examples/foundation/gate8-reject/PureTimerResult.lean"),
    Path("examples/foundation/gate8-reject/StoredTimerContinuation.lean"),
    Path("examples/foundation/gate8-reject/V06Timer.lean"),
    Path("examples/foundation/gate8-reject/rejections.json"),
    Path("docs/audits/timers-core0-v07.md"),
)


def build_timer_suite(
    *,
    root: Path,
    output_dir: Path,
    opt_level: str,
    mutation: int = 0,
    clean: bool = False,
    build_lean: bool = True,
    timeout_seconds: float = 180.0,
) -> dict[str, object]:
    """Build a closed timer artifact; mutation is test-only 0, 1, or 2."""
    if (
        isinstance(mutation, bool)
        or not isinstance(mutation, int)
        or mutation not in {0, 1, 2}
    ):
        raise Core0Error("timer mutation must be the integer 0, 1, or 2")
    return build(
        root=root,
        output_dir=output_dir,
        opt_level=opt_level,
        export_source=root / EXPORT_SOURCE,
        clean=clean,
        build_lean=build_lean,
        timeout_seconds=timeout_seconds,
        artifact_category="test-timer-suite",
        additional_source_inputs=HOST_INPUTS,
        elaboration_sources=ELABORATION_SOURCES,
        export_environment={"LEMMA_TIMER_MUTATION": str(mutation)},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opt-level", choices=("O0", "O2"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mutation", type=int, choices=(0, 1, 2), default=0)
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
        record = build_timer_suite(
            root=root,
            output_dir=output_dir,
            opt_level=ns.opt_level,
            mutation=ns.mutation,
            clean=ns.clean,
            timeout_seconds=ns.timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"TIMER SUITE BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
