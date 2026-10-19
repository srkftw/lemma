#!/usr/bin/env python3
"""Build and pin the hosted Lean school executables and consumed source identity.

Run inside the pinned Nix environment. This is hosted native production, separate
from the Core0 RV64 worker. Lake may reuse validated ordinary host build outputs.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import time

from build_actions import lean_source_inputs
from core0_common import repo_root, sha256


def inputs(root):
    paths = lean_source_inputs(root, [root / "Lemma/School/Main.lean", root / "Lemma/School/CurriculumMain.lean"])
    for name in ("fixtures/school/Distributivity.txt", "lakefile.toml", "lake-manifest.json",
                 "lean-toolchain", "flake.nix", "flake.lock", "tooling/toolchain-lock.json",
                 "scripts/build_school.py", "scripts/school_fs_barrier.py"):
        paths[name] = root / name
    return {name: sha256(path) for name, path in sorted(paths.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = repo_root()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = inputs(root)
    start = time.monotonic()
    command = ["lake", "build", "school", "school-curriculum"]
    result = {"schema": "lemma-school-host-production/1", "result": "FAIL", "command": command,
              "sourceInputs": before, "boundary": "hosted Lean native executable with upstream host runtime; no freestanding server claim"}
    try:
        with (output / "production.log").open("x") as log:
            process = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        if process.returncode:
            raise RuntimeError("actual Lake production failed; inspect retained production.log")
        if inputs(root) != before:
            raise RuntimeError("consumed host source changed during production")
        binaries = {}
        for name in ("school", "school-curriculum"):
            source = root / ".lake/build/bin" / name
            destination = output / name
            shutil.copy2(source, destination)
            binaries[name] = {"path": str(destination), "sha256": sha256(destination)}
        shutil.copy2(root / "scripts/school_fs_barrier.py", output / "school_fs_barrier.py")
        result["hostPrimitives"] = {"school_fs_barrier.py": {
            "path": str(output / "school_fs_barrier.py"),
            "sha256": sha256(output / "school_fs_barrier.py"),
            "scope": "fsync one Lean-selected file/directory; no domain policy"}}
        result.update(result="PASS", binaries=binaries,
                      leanVersion=subprocess.check_output(["lean", "--version"], cwd=root, text=True).strip(),
                      sourceCommit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                      sourceTree=subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, text=True).strip(),
                      worktree="source inventory above includes current uncommitted inputs; commit identity alone is not production identity")
    except Exception as error:
        result["error"] = str(error)
    result["elapsedSeconds"] = time.monotonic() - start
    (output / "production.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"result": result["result"], "receipt": str(output / "production.json"),
                      "elapsedSeconds": result["elapsedSeconds"]}))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
