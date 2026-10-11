#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the exact public digital collateral; never install opaque macros."""
from pathlib import Path
import argparse
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "build/silicon/deps/ihp-open-pdk")
    args = ap.parse_args()
    path = args.output_dir.resolve()
    pin = json.loads((ROOT / "tooling/silicon/physical-lock.json").read_text())["pdk"]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", pin["repository"], str(path)],
                       check=True, timeout=300)
        # Keep only inputs used by this digital recipe, plus their licenses.
        subprocess.run(["git", "-C", str(path), "sparse-checkout", "set", "--no-cone",
                        "/LICENSE", "/README.md", "/ihp-sg13g2/libs.ref/sg13g2_stdcell/",
                        "/ihp-sg13g2/libs.tech/librelane/", "/ihp-sg13g2/libs.tech/openroad/",
                        "/ihp-sg13g2/libs.tech/magic/", "/ihp-sg13g2/libs.tech/netgen/"],
                       check=True, timeout=60)
        subprocess.run(["git", "-C", str(path), "checkout", "--detach", pin["revision"]],
                       check=True, timeout=300)
    revision = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip()
    if revision != pin["revision"] or dirty:
        raise RuntimeError("Existing PDK is modified or at another revision; preserve it and use a new output path")
    print(json.dumps({"pdk": str(path), "revision": revision, "license": pin["license"]}, indent=2))


if __name__ == "__main__":
    main()
