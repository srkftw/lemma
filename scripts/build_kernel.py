#!/usr/bin/env python3
"""Host-only construction of separately compiled firmware/kernel/user units.

Lean elaboration and the checked Core0 exporter create all target code and layout.
This driver invokes pinned LLVM tools and packages immutable user bytes; it does
not allocate target frames, create mappings, schedule tasks, or handle guest IPC.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
from typing import Sequence

from build_core0 import (LLC_ARGUMENTS, OPT_PASSES, STARTUP_ARGUMENTS,
                        capture_platform_dtb, prepare_output_directory)
from core0_common import Core0Error, load_json, repo_root, require_tools, run_bounded, sha256, write_json

ROLE_ROOTS = {
    "firmware": (("Lemma.Platform.RiscV.Firmware.dispatch", ("u64", "u64", "u64")),),
    "kernel": (("Lemma.Kernel.Entry.boot", ()), ("Lemma.Kernel.Entry.dispatch", ("u64", "u64", "u64"))),
    "user": (("Lemma.User.Entry.main", ("u64",)),),
}
ROLE_MODULES = {"firmware": "Lemma.Platform.RiscV.Firmware", "kernel": "Lemma.Kernel.Entry", "user": "Lemma.User.Entry"}
CONFIGURATIONS = ("normal", "frames-development", "machine-origin-development",
                  "user-isolation-development", "user-csr-development", "user-nx-development",
                  "user-kernel-fetch-development", "user-misaligned-development", "user-syscall-development", "tasks-development")
CONTRACTS = {role: f"core0-{role}-v0.1" for role in ROLE_ROOTS}
CONTRACTS["kernel"] = "core0-kernel-v0.2"
BOOT_FILES = ("startup.S", "user-startup.S", "link.ld", "user-link.ld", "layout.json",
              "primitive-catalog.json", "boot-package.S", "package-contract.json")
UNIT_FILES = ("program.ll", "unit.json", "normalized.txt", "symbols.txt")
BOOT_OBJECTS = ("startup.o", "firmware/program.o", "kernel/program.o", "boot-package.o")
USER_OBJECTS = ("user/startup.o", "user/program.o")
MULTI_BOOT_FILES = ("startup.S", "link.ld", "layout.json", "primitive-catalog.json",
                    "boot-package.S", "package-contract.json", "user-image-catalog.json")
USER_IMAGE_FILES = ("startup.S", "link.ld", "layout.json", "primitive-catalog.json")
# Same immutable realization expression and UInt audit hash used by Task002
# Gate3. Each independent CI job must realize this input itself; a tool binary
# in the development shell does not retain the compiler's upstream sources.
LEAN_SOURCE_EXPRESSION = ("let flake = builtins.getFlake (toString ./.); "
                          "pkgs = import flake.inputs.nixpkgs { system = builtins.currentSystem; }; "
                          "in pkgs.lean4.src")
LEAN_UINT_SOURCE_SHA256 = "d0f463c78f6c92585caffef53154cadd3c3e0f3b1681584f19e85d8e5da15c94"


def validate_lean_source_realization(lean_lock: dict, output: str, info: object) -> dict:
    paths = [line.strip() for line in output.splitlines() if line.strip()]
    expected = lean_lock.get("source_path")
    if len(paths) != 1 or not isinstance(expected, str) or not expected.startswith("/nix/store/") or paths[0] != expected:
        raise Core0Error("Lean source realization must return exactly its immutable locked store path")
    if isinstance(info, dict) and set(info) == {expected}:
        row = info[expected]
    elif isinstance(info, list) and len(info) == 1 and isinstance(info[0], dict) and info[0].get("path") == expected:
        row = info[0]
    else:
        raise Core0Error("Lean source NAR evidence lacks its exact single locked output")
    if (not isinstance(row, dict) or row.get("narHash") != lean_lock.get("source_sha256")
            or type(row.get("narSize")) is not int or row["narSize"] != lean_lock.get("source_nar_size")
            or lean_lock.get("source_hash_kind") != "nix-recursive-nar-sha256"):
        raise Core0Error("realized Lean source NAR differs from the immutable audited input")
    return {"source_path": expected, "revision": lean_lock["revision"],
            "narHash": row["narHash"], "narSize": row["narSize"]}


def configuration_roots(configuration: str) -> dict:
    if configuration not in CONFIGURATIONS:
        raise Core0Error("unknown kernel configuration")
    if configuration == "tasks-development":
        return {"firmware": ROLE_ROOTS["firmware"], "kernel": (("Lemma.Kernel.Development.TasksEntry.boot", ()),
                   ("Lemma.Kernel.Development.TasksEntry.dispatch", ("u64", "u64", "u64")))}
    if configuration == "frames-development":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Kernel.Development.FramesEntry.boot", ()),
                                        ("Lemma.Kernel.Development.FramesEntry.dispatch", ("u64", "u64", "u64")))}
    if configuration == "user-isolation-development":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Kernel.Development.IsolationEntry.boot", ()),
                                        ("Lemma.Kernel.Development.IsolationEntry.dispatch", ("u64", "u64", "u64"))),
                "user": (("Lemma.User.Development.Isolation.main", ("u64",)),)}
    if configuration == "user-syscall-development":
        return {**ROLE_ROOTS, "user": (("Lemma.User.Development.Syscall.main", ("u64",)),)}
    return ROLE_ROOTS


def configuration_modules(configuration: str) -> dict:
    configuration_roots(configuration)
    if configuration == "tasks-development":
        return {"firmware": ROLE_MODULES["firmware"], "kernel": "Lemma.Kernel.Development.TasksEntry"}
    if configuration == "frames-development":
        return {**ROLE_MODULES, "kernel": "Lemma.Kernel.Development.FramesEntry"}
    if configuration == "user-isolation-development":
        return {**ROLE_MODULES, "kernel": "Lemma.Kernel.Development.IsolationEntry", "user": "Lemma.User.Development.Isolation"}
    if configuration == "user-syscall-development":
        return {**ROLE_MODULES, "user": "Lemma.User.Development.Syscall"}
    return ROLE_MODULES


def development_role(configuration: str, role: str) -> bool:
    configuration_roots(configuration)
    return (configuration == "tasks-development" and role == "kernel"
            or configuration == "frames-development" and role == "kernel"
            or configuration == "user-isolation-development" and role in {"kernel", "user"}
            or configuration == "user-syscall-development" and role == "user")


def startup_case(configuration: str) -> str:
    configuration_roots(configuration)
    return "machine-origin-probe" if configuration == "machine-origin-development" else "normal"


def user_startup_case(configuration: str) -> str:
    configuration_roots(configuration)
    return {"user-csr-development": "supervisor-csr", "user-nx-development": "execute-data",
            "user-kernel-fetch-development": "execute-kernel", "user-misaligned-development": "execute-misaligned"}.get(configuration, "none")


def validate_configuration_stage(configuration: str, stage: str) -> None:
    configuration_roots(configuration)
    if stage not in {"bootstrap-m", "supervisor"}:
        raise Core0Error("unknown execution stage")
    if configuration == "machine-origin-development" and stage != "bootstrap-m":
        raise Core0Error("machine-origin-development requires bootstrap-m")
    if configuration in {"user-isolation-development", "user-csr-development", "user-nx-development",
                         "user-kernel-fetch-development", "user-misaligned-development", "user-syscall-development", "tasks-development"} and stage != "supervisor":
        raise Core0Error("user isolation configurations require supervisor")


def artifact_category(configuration: str) -> str:
    configuration_roots(configuration)
    return ("production" if configuration == "normal" else "development") + "-kernel-boot-package"


def source_inputs(root: Path) -> dict[str, str]:
    inputs = [root / name for name in ("flake.nix", "flake.lock", "lean-toolchain", "lakefile.toml",
                                     "tooling/toolchain-lock.json", "scripts/core0_common.py", "scripts/build_core0.py",
                                     "scripts/audit_core0.py", "scripts/audit_device.py",
                                     "scripts/audit_memory.py", "scripts/audit_monitor.py", "scripts/audit_timer.py", "scripts/audit_trap.py",
                                     "scripts/build-kernel.sh", "scripts/audit-kernel.sh",
                                     "scripts/build_kernel.py", "scripts/audit_kernel.py", "scripts/build_user.py", "scripts/build-user.sh")]
    inputs += sorted((root / "Lemma").rglob("*.lean"))
    return {str(path.relative_to(root)): sha256(path) for path in inputs}


def module_closure(root: Path, module: str, seen: set[str] | None = None, *, allow_development: bool = False,
                   development_module: str | None = None) -> dict[str, str]:
    import re
    if seen is None and allow_development and development_module is None:
        development_module = module
    seen = set() if seen is None else seen
    if module in seen or not module.startswith("Lemma."):
        return {}
    seen.add(module)
    if ".Test." in module or module.startswith("Lemma.Compiler.Test") or "Mutation" in module:
        raise Core0Error(f"production dependency imports a test/mutation module: {module}")
    if ".Development." in module and not allow_development:
        raise Core0Error(f"normal production dependency imports development code: {module}")
    if ".Development." in module and module != development_module:
        raise Core0Error(f"dependency imports another development image/module: {module}")
    path = root / (module.replace(".", "/") + ".lean")
    if not path.is_file():
        raise Core0Error(f"missing production module: {module}")
    text = path.read_text()
    result = {str(path.relative_to(root)): sha256(path)}
    for line in re.findall(r"(?m)^\s*import\s+([^\n]+)", text):
        for dependency in line.split():
            if dependency.startswith(("examples.", "tests.")) or ".Test." in dependency:
                raise Core0Error(f"production dependency imports test source: {dependency}")
            result.update(module_closure(root, dependency, seen, allow_development=allow_development,
                                         development_module=development_module))
    return result


def _nonempty(directory: Path, names: Sequence[str]) -> None:
    for name in names:
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise Core0Error(f"missing/empty mandatory generated artifact: {path}")


def command_invoker(root: Path, output_dir: Path, tools: dict, timeout_seconds: float, commands: list):
    """Shared bounded command recording for boot and independent user builds."""
    def invoke(argv: Sequence[str], cwd: Path = output_dir, env: dict[str, str] | None = None) -> bytes:
        actual = [tools.get(argv[0], argv[0]), *argv[1:]]
        try:
            result = run_bounded(actual, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
        except (Core0Error, OSError) as error:
            commands.append({"argv": list(actual), "cwd": str(cwd.relative_to(root)), "returncode": None,
                             "error": str(error), "completed": False})
            write_json(output_dir / "commands.json", commands)
            raise
        commands.append({"argv": list(actual), "cwd": str(cwd.relative_to(root)), "returncode": result.returncode,
                         "elapsed_seconds": result.elapsed_seconds,
                         "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace")})
        write_json(output_dir / "commands.json", commands)
        if result.returncode != 0:
            raise Core0Error(f"command failed ({result.returncode}): {' '.join(argv)}\n"
                             + (result.stdout + result.stderr).decode(errors='replace'))
        return result.stdout
    return invoke


def export_user_catalog(root: Path, output_dir: Path, configuration: str, invoke) -> dict:
    from audit_kernel import validate_user_image_catalog
    consumer = output_dir / "CatalogExport.lean"
    consumer.write_text("import Lemma.Compiler.KernelExport\n\n#lemma_export_user_catalog\n")
    env = {**os.environ, "LEMMA_KERNEL_OUT": str(output_dir), "LEMMA_KERNEL_CONFIGURATION": configuration}
    invoke(("lake", "env", "lean", str(consumer.relative_to(root))), root, env)
    return validate_user_image_catalog(load_json(output_dir / "user-image-catalog.json"))


def export_user_image(root: Path, output_dir: Path, configuration: str, image: dict,
                      opt_level: str, invoke) -> dict:
    """Always elaborate fresh. No prebuilt-object or cached-image input exists."""
    from audit_kernel import validate_unit
    directory = output_dir / image["directory"]
    directory.mkdir(parents=True)
    consumer = directory / "Export.lean"
    consumer.write_text(f'import {image["module"]}\nimport Lemma.Compiler.KernelExport\n\n'
                        f'#lemma_export_user_image "{image["key"]}" [{image["source"]}]\n')
    env = {**os.environ, "LEMMA_KERNEL_OUT": str(output_dir), "LEMMA_KERNEL_CONFIGURATION": configuration}
    invoke(("lake", "env", "lean", str(consumer.relative_to(root))), root, env)
    _nonempty(directory, UNIT_FILES)
    unit = validate_unit(load_json(directory / "unit.json"), "user", configuration=configuration, image_key=image["key"])
    invoke(("opt", "-S", f"-passes={OPT_PASSES[opt_level]}", "program.ll", "-o", "program.opt.ll"), directory)
    invoke(("llc", *LLC_ARGUMENTS, "-stack-size-section", f"-{opt_level}", "program.opt.ll", "-o", "program.o"), directory)
    return unit


def export_user_files(root: Path, output_dir: Path, configuration: str, image: dict, invoke) -> None:
    consumer = output_dir / "UserFilesExport.lean"
    consumer.write_text(f'import Lemma.Compiler.KernelExport\n\n#lemma_export_user_files "{image["key"]}"\n')
    env = {**os.environ, "LEMMA_KERNEL_OUT": str(output_dir), "LEMMA_KERNEL_CONFIGURATION": configuration}
    invoke(("lake", "env", "lean", str(consumer.relative_to(root))), root, env)
    _nonempty(output_dir / image["directory"], USER_IMAGE_FILES)


def link_user_image(output_dir: Path, image: dict, invoke) -> None:
    """Link/extract a single ELF at its declared virtual layout, independently."""
    relative = image["directory"]
    directory = output_dir / relative
    _nonempty(directory, USER_IMAGE_FILES)
    invoke(("clang", *STARTUP_ARGUMENTS, f"{relative}/startup.S", "-o", f"{relative}/startup.o"))
    invoke(("ld.lld", "-m", "elf64lriscv", "--no-relax", "-T", f"{relative}/link.ld", f"-Map={relative}/image.map",
            f"{relative}/startup.o", f"{relative}/program.o", "-o", f"{relative}/image.elf"))
    for section, name in ((".text", "text.bin"), (".data", "data.bin")):
        invoke(("llvm-objcopy", "-O", "binary", f"--only-section={section}", f"{relative}/image.elf", f"{relative}/{name}"))
        if not (directory / name).is_file():
            raise Core0Error(f"objcopy did not produce {relative}/{name}")
    layout = load_json(directory / "layout.json")
    if not isinstance(layout, dict) or not isinstance(layout.get("user"), dict):
        raise Core0Error("malformed per-image user layout")
    user = layout["user"]
    text_bytes = (directory / "text.bin").stat().st_size
    if not 0 < text_bytes <= user["text_limit"] - user["text_base"]:
        raise Core0Error("independent user text is empty or exceeds declared capacity")
    if (directory / "data.bin").stat().st_size > user["data_bytes"]:
        raise Core0Error("independent user initialized data exceeds declared capacity")
    # Loader ownership quota includes the eleven initial page tables, data,
    # user stack and authoritative paired kernel stack. Runtime arena grants
    # remain checked by the allocator; this rejects an impossible initial load.
    if 11 + math.ceil(text_bytes / layout["frame_bytes"]) + 1 + user["stack_pages"] + layout["task_kernel_stack_pages"] > 32:
        raise Core0Error("independent user image cannot fit the loader's 32-frame owner quota")


def realize_toolchain(root: Path, tools: dict, invoke) -> tuple[dict, dict]:
    versions = {}
    expected_versions = {"lean": "4.34.1", "lake": "5.0.0-src", "opt": "20.1.8", "llc": "20.1.8",
                         "clang": "20.1.8", "ld.lld": "20.1.8", "qemu-system-riscv64": "11.1.1", "dtc": "1.8.1"}
    for name, expected in expected_versions.items():
        version = invoke((name, "--version"), root).decode().strip()
        if expected not in version:
            raise Core0Error(f"unpinned {name} version: {version}")
        versions[name] = {"path": tools[name], "version": version}
    pin = load_json(root / "tooling/toolchain-lock.json")
    if not isinstance(pin, dict) or pin.get("status") != "pinned":
        raise Core0Error("toolchain lock is not pinned")
    source_output = invoke(("nix", "build", "--no-link", "--print-out-paths", "--impure", "--expr", LEAN_SOURCE_EXPRESSION), root).decode(errors="strict")
    lean_pin = pin["tools"]["lean"]
    source_info = json.loads(invoke(("nix", "path-info", "--json", lean_pin["source_path"]), root))
    source_realization = validate_lean_source_realization(lean_pin, source_output, source_info)
    uint_source = Path(source_realization["source_path"]) / "src/Init/Data/UInt/Basic.lean"
    if not uint_source.is_file() or sha256(uint_source) != LEAN_UINT_SOURCE_SHA256:
        raise Core0Error("realized Lean UInt source differs from the audited Task002 input")
    source_realization.update(uint_source=str(uint_source), uint_source_sha256=sha256(uint_source))
    for name, key in (("lean", "lean"), ("lake", "lean"), ("llc", "llvm"), ("opt", "llvm"), ("llvm-objcopy", "llvm"),
                      ("llvm-readelf", "llvm"), ("llvm-nm", "llvm"), ("llvm-objdump", "llvm"),
                      ("ld.lld", "lld"), ("qemu-system-riscv64", "qemu")):
        if not str(Path(tools[name])).startswith(pin["tools"][key]["store_path"] + "/"):
            raise Core0Error(f"{name} store output differs from immutable toolchain lock")
    if not tools["clang"].startswith(pin["tools"]["llvm"]["outputs"]["clang_unwrapped"]["store_path"] + "/"):
        raise Core0Error("cross compilation must use the pinned unwrapped Clang")
    return versions, source_realization


def build(*, root: Path, output_dir: Path, opt_level: str, stage: str = "bootstrap-m", configuration: str = "normal",
          clean: bool = False, timeout_seconds: float = 300) -> dict[str, object]:
    try:
        output_relative = output_dir.resolve().relative_to((root / "build/kernel").resolve())
    except ValueError as error:
        raise Core0Error("kernel outputs must be an ignored build/kernel subdirectory") from error
    if not output_relative.parts:
        raise Core0Error("refusing to replace the whole build/kernel evidence root")
    if opt_level not in OPT_PASSES or stage not in {"bootstrap-m", "supervisor"}:
        raise Core0Error("unknown optimization or execution stage")
    roots, modules = configuration_roots(configuration), configuration_modules(configuration)
    validate_configuration_stage(configuration, stage)
    case, user_case = startup_case(configuration), user_startup_case(configuration)
    category = artifact_category(configuration)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise Core0Error("build timeout must be finite and positive")
    tools = require_tools(("git", "nix", "lake", "lean", "opt", "llc", "clang", "ld.lld", "llvm-objcopy",
                           "llvm-readelf", "llvm-nm", "llvm-objdump", "qemu-system-riscv64", "dtc"))
    prepare_output_directory(output_dir, root, clean=clean)
    commands: list[dict[str, object]] = []

    invoke = command_invoker(root, output_dir, tools, timeout_seconds, commands)

    try:
        dependencies = {role: module_closure(root, module, allow_development=development_role(configuration, role))
                        for role, module in modules.items()}
        source_before = source_inputs(root)
        versions, source_realization = realize_toolchain(root, tools, invoke)
        images = []
        if configuration == "tasks-development":
            invoke(("lake", "build", "Lemma.Compiler.KernelExport"), root)
            catalog = export_user_catalog(root, output_dir, configuration, invoke)
            images = catalog["images"]
            dependencies["users"] = {image["key"]: module_closure(root, image["module"], allow_development=True)
                                     for image in images}
        invoke(("lake", "build", *modules.values(), *(image["module"] for image in images), "Lemma.Compiler.KernelExport"), root)
        from audit_kernel import validate_unit
        units = {}
        for role, module in modules.items():
            directory = output_dir / role
            directory.mkdir()
            consumer = directory / "Export.lean"
            consumer.write_text(f"import {module}\nimport Lemma.Compiler.KernelExport\n\n"
                                f'#lemma_export_unit "{role}" [' + ", ".join(name for name, _ in roots[role]) + "]\n")
            env = {**os.environ, "LEMMA_KERNEL_OUT": str(directory), "LEMMA_KERNEL_CONFIGURATION": configuration}
            invoke(("lake", "env", "lean", str(consumer.relative_to(root))), root, env)
            _nonempty(directory, UNIT_FILES)
            units[role] = validate_unit(load_json(directory / "unit.json"), role, configuration=configuration)
            invoke(("opt", "-S", f"-passes={OPT_PASSES[opt_level]}", "program.ll", "-o", "program.opt.ll"), directory)
            invoke(("llc", *LLC_ARGUMENTS, "-stack-size-section", f"-{opt_level}", "program.opt.ll", "-o", "program.o"), directory)
        if images:
            units["users"] = {image["key"]: export_user_image(root, output_dir, configuration, image, opt_level, invoke)
                              for image in images}
        consumer = output_dir / "BootExport.lean"
        consumer.write_text("import Lemma.Compiler.KernelExport\n\n#lemma_export_boot_files\n")
        env = {**os.environ, "LEMMA_KERNEL_OUT": str(output_dir), "LEMMA_KERNEL_STAGE": stage, "LEMMA_KERNEL_CONFIGURATION": configuration}
        invoke(("lake", "env", "lean", str(consumer.relative_to(root))), root, env)
        generated_files = list(MULTI_BOOT_FILES if images else BOOT_FILES)
        _nonempty(output_dir, generated_files)
        if images:
            for image in images:
                generated_files.extend(f'{image["directory"]}/{filename}' for filename in USER_IMAGE_FILES)
                link_user_image(output_dir, image, invoke)
        else:
            invoke(("clang", *STARTUP_ARGUMENTS, "user-startup.S", "-o", "user/startup.o"))
            invoke(("ld.lld", "-m", "elf64lriscv", "--no-relax", "-T", "user-link.ld", "-Map=user/image.map", *USER_OBJECTS, "-o", "user/image.elf"))
            for section, name in ((".text", "user-text.bin"), (".data", "user-data.bin")):
                invoke(("llvm-objcopy", "-O", "binary", f"--only-section={section}", "user/image.elf", name))
                if not (output_dir / name).is_file():
                    raise Core0Error(f"objcopy did not produce {name}")
            layout = load_json(output_dir / "layout.json")
            if not isinstance(layout, dict) or not isinstance(layout.get("user"), dict):
                raise Core0Error("malformed user layout")
            user_layout = layout["user"]
            if not 0 < (output_dir / "user-text.bin").stat().st_size <= user_layout["text_limit"] - user_layout["text_base"]:
                raise Core0Error("independently compiled user text is empty or outside package text capacity")
            if (output_dir / "user-data.bin").stat().st_size > user_layout["data_bytes"]:
                raise Core0Error("user initialized data exceeds declared capacity")
        invoke(("clang", *STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"))
        invoke(("clang", *STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"))
        invoke(("ld.lld", "-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"))
        capture_platform_dtb(output_dir=output_dir, root=root, command_log=commands, timeout_seconds=timeout_seconds)
        write_json(output_dir / "commands.json", commands)
        after = source_inputs(root)
        if source_before != after:
            raise Core0Error("compiler/production inputs changed during build")
        commit = invoke(("git", "rev-parse", "HEAD"), root).decode().strip()
        dirty = invoke(("git", "status", "--porcelain=v1", "--untracked-files=all"), root).decode().splitlines()
        artifacts = {str(path.relative_to(output_dir)): sha256(path) for path in sorted(output_dir.rglob("*"))
                     if path.is_file() and path.name not in {"commands.json", "build.json", "provenance.json"}}
        linked_inputs = ({"boot": list(BOOT_OBJECTS), "users": {image["key"]: [f'{image["directory"]}/startup.o', f'{image["directory"]}/program.o'] for image in images}}
                         if images else {"boot": list(BOOT_OBJECTS), "user": list(USER_OBJECTS)})
        unit_contracts = {role: value["contract_version"] for role, value in units.items() if role != "users"}
        if images:
            unit_contracts["users"] = {key: value["contract_version"] for key, value in units["users"].items()}
        provenance = {"schema_version": 2 if images else 1, "artifact_category": category, "configuration": configuration, "startup_case": case, "user_startup_case": user_case,
                      "lean_source_realization": source_realization,
                      "stage": stage, "optimization": opt_level, "source_commit": commit, "dirty_paths": dirty,
                      "source_inputs": source_before, "target_module_closures": dependencies, "tools": versions,
                      "commands": commands, "generated_by_lean": generated_files,
                      "linked_inputs": linked_inputs, "artifacts": artifacts, "unit_contracts": unit_contracts}
        write_json(output_dir / "provenance.json", provenance)
        record = {"schema_version": 2 if images else 1, "status": "BUILT", "artifact_category": category, "configuration": configuration, "startup_case": case, "user_startup_case": user_case,
                  "lean_source_realization": source_realization,
                  "stage": stage, "optimization": opt_level, "artifacts": artifacts,
                  "provenance_sha256": sha256(output_dir / "provenance.json"),
                  "kernel_execution_privilege": "M" if stage == "bootstrap-m" else "S",
                  "user_execution": "separately linked; execution requires later guest loading"}
        write_json(output_dir / "build.json", record)
        return record
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        write_json(output_dir / "build-failure.json", {"schema_version": 1, "status": "FAIL", "error": str(error), "commands": commands})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--opt-level", choices=("O0", "O2"), required=True)
    parser.add_argument("--stage", choices=("bootstrap-m", "supervisor"), default="bootstrap-m")
    parser.add_argument("--configuration", choices=CONFIGURATIONS, default="normal")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--timeout", type=float, default=300)
    ns = parser.parse_args()
    root = repo_root()
    output = (root / ns.output_dir).resolve()
    try:
        result = build(root=root, output_dir=output, opt_level=ns.opt_level, stage=ns.stage, configuration=ns.configuration, clean=ns.clean, timeout_seconds=ns.timeout)
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        print(f"KERNEL BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print(f"KERNEL BUILD COMPLETE: {output / 'image.elf'}; {result['configuration']}, {result['stage']}, {result['optimization']}; audit separately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
