#!/usr/bin/env python3
"""Bounded actual-guest checks of the production kernel's FDT acceptance boundary.

Fixtures are edits of this image's audited QEMU-generated platform.dts, compiled
by the pinned host DTC. The host does not decide whether a DTB is usable: the
compiled guest parser must report each acceptance or denial before host cleanup.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import time

from build_core0 import prepare_output_directory
from build_kernel import source_inputs
from core0_common import Core0Error, load_json, repo_root, require_tools, run_bounded, sha256, write_json
from run_kernel import Session


RESERVED_POOL = """
\treserved-memory {
\t\t#address-cells = <0x02>;
\t\t#size-cells = <0x02>;
\t\tranges;
\t\tpool@82000000 {
\t\t\treg = <0x00 0x82000000 0x00 0x00200000>;
\t\t\tno-map;
\t\t};
\t};
"""
NEGATIVE_CASES = {"reserved-pool": (62, 1), "root-cells": (62, 1)}


def fixture_text(source: str, kind: str) -> str:
    """Change one exact property/node in the pinned audited DTS representation."""
    if not source.startswith("/dts-v1/;\n\n/ {\n"):
        raise Core0Error("fixture source is not the supported QEMU DTC root representation")
    if kind == "reserved-pool":
        marker = "\n\tpoweroff {"
        if source.count(marker) != 1 or re.search(r"\breserved-memory\s*{", source):
            raise Core0Error("cannot inject one new reserved-memory node into platform DTS")
        return source.replace(marker, RESERVED_POOL + marker, 1)
    if kind == "root-cells":
        before = "/dts-v1/;\n\n/ {\n\t#address-cells = <0x02>;"
        after = "/dts-v1/;\n\n/ {\n\t#address-cells = <0x01>;"
        if source.count(before) != 1:
            raise Core0Error("cannot locate the exact root #address-cells fixture property")
        return source.replace(before, after, 1)
    raise Core0Error(f"unknown DTB fixture kind: {kind}")


def command(report: dict, argv: tuple[str, ...], *, root: Path, output_dir: Path,
            label: str, timeout: float) -> None:
    result = run_bounded(argv, cwd=root, timeout_seconds=timeout)
    raw = {}
    for suffix, data in (("stdout", result.stdout), ("stderr", result.stderr)):
        path = output_dir / f"{label}.{suffix}.bin"
        path.write_bytes(data)
        raw[path.name] = sha256(path)
    report["commands"].append({"label": label, "argv": list(result.argv),
                               "returncode": result.returncode,
                               "elapsed_seconds": round(result.elapsed_seconds, 6),
                               "raw_artifacts": raw})
    if result.returncode != 0:
        raise Core0Error(f"{label} failed with exit {result.returncode}; retained stdout/stderr")


def observe(*, root: Path, image: Path, output_dir: Path, kind: str,
            fixture: Path | None, timeout: float, report: dict) -> None:
    case_dir = output_dir / kind
    try:
        with Session(root=root, image=image, output_dir=case_dir, timeout=timeout, dtb=fixture) as session:
            record = session.record()
            if kind == "ordinary":
                if record[0] != 0xa or record[2:] != (0, 512, 0x82000000) or not 0x87e00000 <= record[1] < 0x88000000:
                    raise Core0Error(f"ordinary boot facts differ: {record}")
                observed = {"protocol": "bootinfo-ordinary-v1", "boot": list(record),
                            "allocator_initialization": "observed", "user_execution": "not_run"}
            else:
                status, depth = NEGATIVE_CASES[kind]
                if record[:2] != (0xe0, status) or record[3:] != (depth, 0):
                    raise Core0Error(f"{kind} did not produce the expected early parser denial: {record}")
                if not 0x87e00000 <= record[2] < 0x88000000:
                    raise Core0Error(f"{kind} diagnostic cursor is outside the actual DTB envelope: {record}")
                observed = {"protocol": f"bootinfo-{kind}-denial-v1", "error": list(record),
                            "allocator_initialization": "not_run", "user_execution": "not_run"}
            session.finish(observed)
    finally:
        result_path = case_dir / "result.json"
        if result_path.is_file():
            result = load_json(result_path)
            report["cases"].append({"kind": kind, "result": str(result_path),
                                     "result_sha256": sha256(result_path), "status": result.get("status"),
                                     "records": result.get("records"), "cleanup": result.get("cleanup"),
                                     "returncode": result.get("returncode")})
    result = load_json(case_dir / "result.json")
    if result.get("status") != "PASS" or result.get("cleanup") != {
            "explicit_host_stop": True, "process_group_killed": True, "process_reaped": True}:
        raise Core0Error(f"{kind} lacks passing observation and confirmed QEMU cleanup")


def check(*, root: Path, image: Path, output_dir: Path, timeout: float,
          clean: bool) -> dict:
    root, image, output_dir = root.resolve(), image.resolve(), output_dir.resolve()
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise Core0Error("boot-info case timeout must be finite and positive")
    try:
        image.relative_to(output_dir)
    except ValueError:
        pass
    else:
        raise Core0Error("refusing an output directory containing the input image")
    prepare_output_directory(output_dir, root, clean=clean)
    started = time.monotonic()
    report = {"schema_version": 1, "status": "FAIL", "artifact_category": "kernel-bootinfo-guest-check",
              "image": str(image), "started_at": datetime.now(timezone.utc).isoformat(),
              "timeout_per_case_seconds": timeout, "required_cases": ["ordinary", "reserved-pool", "root-cells"],
              "checker_sha256": sha256(Path(__file__)), "commands": [], "fixtures": [], "cases": []}
    try:
        manifest_path = image.parent / "build.json"
        manifest = load_json(manifest_path)
        if not isinstance(manifest, dict) or (manifest.get("status"), manifest.get("configuration"), manifest.get("stage")) != ("BUILT", "normal", "bootstrap-m"):
            raise Core0Error("boot-info checks require a built normal bootstrap-m image")
        dts_path = image.parent / "platform.dts"
        dtb_path = image.parent / "platform.dtb"
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, dict) or any(artifacts.get(path.name) != sha256(path) for path in (image, dts_path, dtb_path)):
            raise Core0Error("image/platform artifact hashes differ from the build manifest")
        source = dts_path.read_text(encoding="utf-8")
        if not source:
            raise Core0Error("platform DTS fixture corpus is empty")
        sources = source_inputs(root)
        report.update(image_sha256=sha256(image), build_manifest_sha256=sha256(manifest_path),
                      source_inputs=sources, platform_dts=str(dts_path), platform_dts_sha256=sha256(dts_path),
                      platform_dtb_sha256=sha256(dtb_path),
                      transport_sha256=sha256(root / "scripts/run_kernel.py"))
        dtc = require_tools(("dtc",))["dtc"]
        command(report, (dtc, "--version"), root=root, output_dir=output_dir, label="dtc-version", timeout=timeout)
        # This fresh ordinary run includes the full source/artifact audit before
        # any altered DTB receives credit for a target denial.
        observe(root=root, image=image, output_dir=output_dir, kind="ordinary", fixture=None,
                timeout=timeout, report=report)
        for kind in ("reserved-pool", "root-cells"):
            dts, dtb = output_dir / f"{kind}.dts", output_dir / f"{kind}.dtb"
            dts.write_text(fixture_text(source, kind), encoding="utf-8")
            command(report, (dtc, "-I", "dts", "-O", "dtb", "-o", str(dtb), str(dts)),
                    root=root, output_dir=output_dir, label=f"dtc-{kind}", timeout=timeout)
            if not dtb.is_file() or dtb.stat().st_size == 0:
                raise Core0Error(f"DTC did not produce a nonempty {kind} fixture")
            digests = {"dts_sha256": sha256(dts), "dtb_sha256": sha256(dtb)}
            report["fixtures"].append({"kind": kind, "dts": str(dts), "dtb": str(dtb), **digests})
            observe(root=root, image=image, output_dir=output_dir, kind=kind, fixture=dtb,
                    timeout=timeout, report=report)
            if digests != {"dts_sha256": sha256(dts), "dtb_sha256": sha256(dtb)}:
                raise Core0Error(f"{kind} fixture changed during observation")
        if len(report["cases"]) != 3 or any(case["status"] != "PASS" for case in report["cases"]):
            raise Core0Error("boot-info corpus is incomplete or contains a failing observation")
        if source_inputs(root) != sources or sha256(image) != report["image_sha256"] or sha256(manifest_path) != report["build_manifest_sha256"]:
            raise Core0Error("source/image/build manifest changed during boot-info checks")
        if sha256(Path(__file__)) != report["checker_sha256"] or sha256(root / "scripts/run_kernel.py") != report["transport_sha256"]:
            raise Core0Error("checker/transport changed during boot-info checks")
        report["status"] = "PASS"
    except Exception as error:
        report.update(error=str(error), failure_category="boot-info-check-failure")
        raise
    finally:
        report.update(elapsed_seconds=round(time.monotonic() - started, 6),
                      finished_at=datetime.now(timezone.utc).isoformat())
        write_json(output_dir / "result.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    try:
        check(root=repo_root(), image=args.image, output_dir=args.output_dir, timeout=args.timeout,
              clean=args.clean)
        print("PASS: actual ordinary boot, reserved-pool denial and root-cells denial; three QEMU guests killed and reaped")
        return 0
    except (Core0Error, OSError, ValueError, TypeError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
