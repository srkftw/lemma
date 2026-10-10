#!/usr/bin/env python3
"""Check retained production-Action medium observations independently.

Input is evidence only. This command never edits or repairs the guest medium.
"""
import argparse
import hashlib
import json
from pathlib import Path

from store_oracle import recover


def check(directory: Path) -> dict:
    expected = {
        "append": 3, "checkpoint": 3, "recovered": 3, "failed-flush": 3,
        "torn-publication": 3, "flushed-before-ack": 4, "after-ack": 4,
        **{f"cut-{phase}": 3 for phase in range(16, 22)},
        **{f"checkpoint-cut-{phase}": 3 for phase in range(32, 41)},
    }
    results = []
    for name, sequence in expected.items():
        image_path = directory / (name + ".img")
        trace_path = directory / (name + ".trace")
        image = image_path.read_bytes()
        trace = trace_path.read_text()
        if not trace.strip():
            raise ValueError(f"empty operation trace: {name}")
        root, actual, records = recover(image)
        if actual != sequence:
            raise ValueError(f"sequence mismatch: {name}: {actual} != {sequence}")
        if records[(1, 1)].payload != b"first revised" or records[(2, 1)].payload != b"second notebook":
            raise ValueError(f"cross-notebook/acknowledged data changed: {name}")
        if sequence == 3 and set(records) != {(1, 1), (2, 1)}:
            raise ValueError(f"partial or phantom transaction: {name}")
        if sequence == 4:
            if records[(1, 2)].payload not in (b"durable fourth", b"durable before ack"):
                raise ValueError(f"pending transaction not recovered wholly: {name}")
        if name in ("checkpoint", "recovered") and (root.generation != 2 or root.checkpoint_count != 2):
            raise ValueError(f"checkpoint root not observed: {name}")
        results.append({"name": name, "sequence": actual, "generation": root.generation,
                        "keys": len(records), "image_sha256": hashlib.sha256(image).hexdigest(),
                        "trace_sha256": hashlib.sha256(trace.encode()).hexdigest()})
    return {"schema_version": 1, "scope": "host Action effects and independent disk oracle; not RV64/device acceptance",
            "status": "PASS", "observations": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    result = check(args.directory)
    data = json.dumps(result, indent=2) + "\n"
    if args.result:
        if args.result.exists():
            raise ValueError("refusing to overwrite retained result")
        args.result.write_text(data)
    print(data, end="")


if __name__ == "__main__":
    main()
