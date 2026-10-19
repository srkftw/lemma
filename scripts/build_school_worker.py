#!/usr/bin/env python3
"""Build the distinct school-linear-worker-v1 through existing cached LLVM actions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_core0 import build
from core0_common import repo_root

SOURCES = (
    Path("Lemma/Numerics/Quantized.lean"),
    Path("Lemma/Platform/LemmaVM/ConsoleDevice.lean"),
    Path("Lemma/School/Worker.lean"),
    Path("Lemma/Compiler/SchoolWorkerExport.lean"),
)


def build_worker(output: Path, *, optimization: str = "O2", fresh: bool = False):
    root = repo_root()
    return build(root=root, output_dir=output.resolve(), opt_level=optimization,
                 export_source=root / "examples/school/WorkerBuild.lean",
                 artifact_category="school-worker", build_lean=False,
                 elaboration_sources=SOURCES,
                 additional_source_inputs=(Path("scripts/build_school_worker.py"),
                                           Path("scripts/check_school_worker.py")),
                 timeout_seconds=300, fresh=fresh)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--opt-level", choices=("O0", "O2"), default="O2")
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build_worker(args.output_dir, optimization=args.opt_level, fresh=args.fresh),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
