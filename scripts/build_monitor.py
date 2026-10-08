#!/usr/bin/env python3
"""Build the closed Gate 9 ``core0-v0.7`` interactive monitor image."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from build_core0 import build
from core0_common import Core0Error, repo_root


EXPORT_SOURCE = Path("examples/foundation/MonitorBuild.lean")
ELABORATION_SOURCES = (
    Path("examples/foundation/DeviceConformanceSupport.lean"),
    Path("examples/foundation/TrapConformance.lean"),
    Path("examples/foundation/TimerConformance.lean"),
    Path("examples/foundation/MonitorProtocol.lean"),
    Path("examples/foundation/Monitor.lean"),
)

# These inputs are part of the monitor artifact's host-side trust envelope.
# They are mandatory: a final image cannot be built with a partial checker or
# session-runner closure and then acquire those trust inputs after the fact.
HOST_INPUTS = (
    Path("scripts/build_monitor.py"),
    Path("scripts/audit_core0.py"),
    Path("scripts/audit_device.py"),
    Path("scripts/audit_memory.py"),
    Path("scripts/audit_monitor.py"),
    Path("scripts/audit_timer.py"),
    Path("scripts/audit_trap.py"),
    Path("scripts/check_foundation.py"),
    Path("scripts/gate8_corpus.py"),
    Path("scripts/gate6_corpus.py"),
    Path("scripts/run_device_session.py"),
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
    Path("scripts/gate9_corpus.py"),
    Path("scripts/run_monitor_session.py"),
    Path("scripts/check_foundation_gate9.py"),
    Path("examples/foundation/MonitorPolicyProbes.lean"),
    Path("docs/audits/monitor-core0-v07.md"),
)


def _source_inputs(root: Path) -> tuple[Path, ...]:
    del root
    return HOST_INPUTS


def build_monitor_image(
    *,
    root: Path,
    output_dir: Path,
    opt_level: str,
    clean: bool = False,
    build_lean: bool = True,
    timeout_seconds: float = 180.0,
) -> dict[str, object]:
    """Build the sole clean monitor image; Gate 9 has no fault selector."""
    return build(
        root=root,
        output_dir=output_dir,
        opt_level=opt_level,
        export_source=root / EXPORT_SOURCE,
        clean=clean,
        build_lean=build_lean,
        timeout_seconds=timeout_seconds,
        artifact_category="test-monitor-image",
        additional_source_inputs=_source_inputs(root),
        elaboration_sources=ELABORATION_SOURCES,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opt-level", choices=("O0", "O2"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
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
        record = build_monitor_image(
            root=root,
            output_dir=output_dir,
            opt_level=ns.opt_level,
            clean=ns.clean,
            timeout_seconds=ns.timeout,
        )
    except (Core0Error, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"MONITOR BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
