#!/usr/bin/env python3
"""Build one closed user image independently; never build or import a kernel ELF."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys

from build_core0 import OPT_PASSES, prepare_output_directory
from build_kernel import (INDEPENDENT_IMAGE_KEYS, MULTI_CONFIGURATIONS, USER_IMAGE_FILES, command_invoker, export_user_catalog,
                          export_user_files, export_user_image, link_user_image,
                          managed_policy, user_module_closure, user_artifact_category, realize_toolchain, source_inputs)
from core0_common import Core0Error, repo_root, require_tools, sha256, write_json


def build(*, root: Path, output_dir: Path, image_key: str, opt_level: str,
          configuration: str = "tasks-development", clean: bool = False,
          timeout_seconds: float = 300) -> dict:
    try:
        relative = output_dir.resolve().relative_to((root / "build/user").resolve())
    except ValueError as error:
        raise Core0Error("independent user outputs must be a build/user subdirectory") from error
    if not relative.parts:
        raise Core0Error("refusing to replace the whole build/user evidence root")
    if image_key not in INDEPENDENT_IMAGE_KEYS.get(configuration, set()):
        raise Core0Error("unknown closed independent user image selection")
    if opt_level not in OPT_PASSES or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise Core0Error("unknown optimization or invalid finite build timeout")
    tools = require_tools(("git", "nix", "lake", "lean", "opt", "llc", "clang", "ld.lld", "llvm-objcopy",
                           "llvm-readelf", "llvm-nm", "llvm-objdump", "qemu-system-riscv64", "dtc"))
    prepare_output_directory(output_dir, root, clean=clean)
    commands: list[dict] = []
    invoke = command_invoker(root, output_dir, tools, timeout_seconds, commands)
    try:
        before = source_inputs(root)
        versions, realization = realize_toolchain(root, tools, invoke)
        invoke(("lake", "build", "Lemma.Compiler.KernelExport"), root)
        catalog = export_user_catalog(root, output_dir, configuration, invoke)
        selected = [image for image in catalog["images"] if image["key"] == image_key]
        if len(selected) != 1:
            raise Core0Error("closed registry omitted/duplicated the selected user image")
        image = selected[0]
        dependencies = user_module_closure(root, image, configuration)
        invoke(("lake", "build", image["module"], "Lemma.Compiler.KernelExport"), root)
        unit = export_user_image(root, output_dir, configuration, image, opt_level, invoke)
        export_user_files(root, output_dir, configuration, image, invoke)
        link_user_image(output_dir, image, invoke)
        if before != source_inputs(root):
            raise Core0Error("compiler/production inputs changed during independent user build")
        commit = invoke(("git", "rev-parse", "HEAD"), root).decode().strip()
        dirty = invoke(("git", "status", "--porcelain=v1", "--untracked-files=all"), root).decode().splitlines()
        artifacts = {str(path.relative_to(output_dir)): sha256(path) for path in sorted(output_dir.rglob("*"))
                     if path.is_file() and path.name not in {"commands.json", "user-build.json", "user-provenance.json"}}
        common = {"schema_version": 2, "artifact_category": user_artifact_category(configuration), "configuration": configuration,
                  "image_key": image_key, "image_id": image["id"], "stage": "supervisor", "startup_case": "normal",
                  "user_startup_case": image["startup_case"], "optimization": opt_level, "lean_source_realization": realization,
                  "artifacts": artifacts}
        if managed_policy(configuration) is not None:
            common.update(managed_policy=managed_policy(configuration), boot_role=image["boot_role"])
        provenance = {**common, "source_commit": commit, "dirty_paths": dirty, "source_inputs": before,
                      "target_module_closures": {"users": {image_key: dependencies}}, "tools": versions, "commands": commands,
                      "generated_by_lean": ["user-image-catalog.json", *(f'{image["directory"]}/{name}' for name in USER_IMAGE_FILES)],
                      "linked_inputs": {"users": {image_key: [f'{image["directory"]}/startup.o', f'{image["directory"]}/program.o']}},
                      "unit_contracts": {"users": {image_key: unit["contract_version"]}}}
        write_json(output_dir / "user-provenance.json", provenance)
        record = {**common, "status": "BUILT", "provenance_sha256": sha256(output_dir / "user-provenance.json"),
                  "user_execution": "separately linked; execution requires later guest loading"}
        write_json(output_dir / "user-build.json", record)
        return record
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        write_json(output_dir / "user-build-failure.json", {"schema_version": 2, "status": "FAIL", "error": str(error), "commands": commands})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--configuration", choices=MULTI_CONFIGURATIONS, default="tasks-development")
    parser.add_argument("--image-key", choices=sorted(set().union(*INDEPENDENT_IMAGE_KEYS.values())), required=True)
    parser.add_argument("--opt-level", choices=("O0", "O2"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    root = repo_root()
    try:
        result = build(root=root, output_dir=(root / args.output_dir).resolve(), image_key=args.image_key,
                       configuration=args.configuration, opt_level=args.opt_level,
                       clean=args.clean, timeout_seconds=args.timeout)
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        print(f"USER BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print(f"USER BUILD COMPLETE: {args.image_key}; {result['optimization']}; audit separately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
