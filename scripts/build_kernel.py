#!/usr/bin/env python3
"""Host-only construction of separately compiled firmware/kernel/user units.

Lean elaboration and the checked Core0 exporter create all target code and layout.
This driver invokes pinned LLVM tools and packages immutable user bytes; it does
not allocate target frames, create mappings, schedule tasks, or handle guest IPC.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import re
from pathlib import Path
import sys
from typing import Sequence

from course_deployment import CONFIGURATIONS as LEGACY_COURSE_NOTEBOOK_CONFIGURATIONS
from course_await_deployment import (CONFIGURATIONS as COURSE_AWAIT_CONFIGURATIONS,
                                     library_source_allowed as course_await_library_source_allowed)
from package_closure_deployment import CONFIGURATIONS as PACKAGE_NOTEBOOK_CONFIGURATIONS
from reader_deployment import CONFIGURATIONS as READER_NOTEBOOK_CONFIGURATIONS
from product_reader_deployment import (ALL_CONFIGURATIONS as PRODUCT_READER_NOTEBOOK_CONFIGURATIONS,
 BOOT_ROOT as PRODUCT_READER_BOOT_ROOT, DISPATCH_ROOT as PRODUCT_READER_DISPATCH_ROOT)
from chooser_reader_deployment import CONFIGURATIONS as CHOOSER_NOTEBOOK_CONFIGURATIONS
from multimodal_deployment import CONFIGURATIONS as MULTIMODAL_CONFIGURATIONS
from integrated_deployment import CONFIGURATIONS as INTEGRATED_CONFIGURATIONS
AWAIT_NOTEBOOK_CONFIGURATIONS=COURSE_AWAIT_CONFIGURATIONS+PACKAGE_NOTEBOOK_CONFIGURATIONS+READER_NOTEBOOK_CONFIGURATIONS+PRODUCT_READER_NOTEBOOK_CONFIGURATIONS+CHOOSER_NOTEBOOK_CONFIGURATIONS+MULTIMODAL_CONFIGURATIONS+INTEGRATED_CONFIGURATIONS
COURSE_NOTEBOOK_CONFIGURATIONS=LEGACY_COURSE_NOTEBOOK_CONFIGURATIONS+AWAIT_NOTEBOOK_CONFIGURATIONS
from closure_deployment import KERNEL_CONFIGURATIONS as CLOSURE_NOTEBOOK_CONFIGURATIONS, KERNEL_ENTRIES as CLOSURE_KERNEL_ENTRIES
CLOSURE_NOTEBOOK_CONFIGURATIONS += MULTIMODAL_CONFIGURATIONS + INTEGRATED_CONFIGURATIONS
from build_core0 import (LLC_ARGUMENTS, OPT_PASSES, STARTUP_ARGUMENTS,
                        capture_platform_dtb, prepare_output_directory)
from core0_common import Core0Error, action_lease, load_json, repo_root, require_tools, run_bounded, sha256, write_json
from lean_export_host import command as export_command, for_source as export_host_policy, environment as export_host_environment

ROLE_ROOTS = {
    "firmware": (("Lemma.Platform.RiscV.Firmware.dispatch", ("u64", "u64", "u64")),),
    "kernel": (("Lemma.Kernel.Entry.boot", ()), ("Lemma.Kernel.Entry.dispatch", ("u64", "u64", "u64"))),
    "user": (("Lemma.User.Entry.main", ("u64",)),),
}
ROLE_MODULES = {"firmware": "Lemma.Platform.RiscV.Firmware", "kernel": "Lemma.Kernel.Entry", "user": "Lemma.User.Entry"}
USER_INSTRUCTION_CONFIGURATIONS = {
    "user-halfword-ecall-development": "halfword-ecall",
    "user-return-supervisor-development": "return-supervisor",
    "user-return-machine-development": "return-machine",
}
SERVICE_INSTRUCTION_CONFIGURATIONS = {
    "service-halfword-ecall-development": "halfword-ecall",
    "service-return-supervisor-development": "return-supervisor",
    "service-return-machine-development": "return-machine",
}
ARITHMETIC_DEVELOPMENT_CONFIGURATIONS = ('lemmasim-silicon-power-arithmetic-oom-development', 'lemmasim-silicon-power-arithmetic-fault-development', 'lemmasim-silicon-power-arithmetic-stall-development')
MANAGED_NOTEBOOK_CONFIGURATIONS = ("lemmasim-silicon-managed-notebook", "lemmasim-silicon-managed-initialize")
STRING_NOTEBOOK_CONFIGURATIONS = ("lemmasim-silicon-string-bulk-notebook", "lemmasim-silicon-string-bulk-initialize", "lemmasim-silicon-string-arithmetic-oom-development")
ARRAY_NOTEBOOK_CONFIGURATIONS = LEGACY_COURSE_NOTEBOOK_CONFIGURATIONS + COURSE_AWAIT_CONFIGURATIONS + ("lemmasim-silicon-array-bulk-notebook", "lemmasim-silicon-array-bulk-initialize", "lemmasim-silicon-array-arithmetic-oom-development")
BYTES_NOTEBOOK_CONFIGURATIONS = ("lemmasim-silicon-bytes-bulk-notebook", "lemmasim-silicon-bytes-bulk-initialize", "lemmasim-silicon-bytes-arithmetic-oom-development")
from package_companion_deployment import ALL_CONFIGURATIONS as USB_PACKAGE_RECOVERY_NOTEBOOK_CONFIGURATIONS, ALL_BOOT_ROOTS as PACKAGE_RECOVERY_BOOT_ROOTS, DISPATCH_ROOT as PACKAGE_RECOVERY_DISPATCH_ROOT
from usb_closure_recovery_deployment import CONFIGURATIONS as USB_CLOSURE_RECOVERY_NOTEBOOK_CONFIGURATIONS
USB_RECOVERY_NOTEBOOK_CONFIGURATIONS = ('lemmasim-silicon-usb-clocked-retry-bulk-notebook','lemmasim-silicon-usb-clocked-retry-bulk-initialize')
USB_CLOCKED_NOTEBOOK_CONFIGURATIONS = ('lemmasim-silicon-usb-clocked-bulk-notebook','lemmasim-silicon-usb-clocked-bulk-initialize')
USB_WIRE_NOTEBOOK_CONFIGURATIONS = ('lemmasim-silicon-usb-wire-bulk-notebook','lemmasim-silicon-usb-wire-bulk-initialize')
USB_NEXT_NOTEBOOK_CONFIGURATIONS = ('lemmasim-silicon-usb-next-bulk-notebook','lemmasim-silicon-usb-next-bulk-initialize')
PRODUCT_EXECUTED_NOTEBOOK_CONFIGURATIONS = ('lemmasim-silicon-product-executed-bulk-notebook',)
PRODUCT_NEXT_NOTEBOOK_CONFIGURATIONS = ('lemmasim-silicon-product-next-bulk-notebook',)
NEXT_NOTEBOOK_CONFIGURATIONS = USB_NEXT_NOTEBOOK_CONFIGURATIONS + PRODUCT_NEXT_NOTEBOOK_CONFIGURATIONS
BULK_NOTEBOOK_CONFIGURATIONS = USB_PACKAGE_RECOVERY_NOTEBOOK_CONFIGURATIONS + USB_CLOSURE_RECOVERY_NOTEBOOK_CONFIGURATIONS + USB_RECOVERY_NOTEBOOK_CONFIGURATIONS + USB_CLOCKED_NOTEBOOK_CONFIGURATIONS + USB_WIRE_NOTEBOOK_CONFIGURATIONS + PRODUCT_EXECUTED_NOTEBOOK_CONFIGURATIONS + NEXT_NOTEBOOK_CONFIGURATIONS + ('lemmasim-silicon-bulk-notebook', 'lemmasim-silicon-bulk-initialize', 'lemmasim-silicon-product-bulk-notebook', 'lemmasim-silicon-usb-bulk-notebook', 'lemmasim-silicon-usb-bulk-initialize') + BYTES_NOTEBOOK_CONFIGURATIONS + ARRAY_NOTEBOOK_CONFIGURATIONS + STRING_NOTEBOOK_CONFIGURATIONS + CLOSURE_NOTEBOOK_CONFIGURATIONS
SUMS_NOTEBOOK_CONFIGURATIONS = ("lemmasim-silicon-sums-notebook", "lemmasim-silicon-sums-initialize", "lemmasim-silicon-sums-arithmetic-oom-development") + tuple(x for x in BULK_NOTEBOOK_CONFIGURATIONS if x not in USB_PACKAGE_RECOVERY_NOTEBOOK_CONFIGURATIONS + USB_CLOSURE_RECOVERY_NOTEBOOK_CONFIGURATIONS + BYTES_NOTEBOOK_CONFIGURATIONS + ARRAY_NOTEBOOK_CONFIGURATIONS + STRING_NOTEBOOK_CONFIGURATIONS + CLOSURE_NOTEBOOK_CONFIGURATIONS)
USB_NOTEBOOK_CONFIGURATIONS = USB_PACKAGE_RECOVERY_NOTEBOOK_CONFIGURATIONS + USB_CLOSURE_RECOVERY_NOTEBOOK_CONFIGURATIONS + USB_RECOVERY_NOTEBOOK_CONFIGURATIONS + USB_CLOCKED_NOTEBOOK_CONFIGURATIONS + USB_WIRE_NOTEBOOK_CONFIGURATIONS + USB_NEXT_NOTEBOOK_CONFIGURATIONS + ("lemmasim-silicon-usb-notebook", "lemmasim-silicon-usb-initialize", "lemmasim-silicon-usb-bulk-notebook", "lemmasim-silicon-usb-bulk-initialize")
PRODUCT_NOTEBOOK_CONFIGURATIONS = INTEGRATED_CONFIGURATIONS + PRODUCT_READER_NOTEBOOK_CONFIGURATIONS + PRODUCT_EXECUTED_NOTEBOOK_CONFIGURATIONS + PRODUCT_NEXT_NOTEBOOK_CONFIGURATIONS + ("lemmasim-silicon-product-notebook", "lemmasim-silicon-product-bulk-notebook")
ARITHMETIC_CONFIGURATIONS = (*PRODUCT_NOTEBOOK_CONFIGURATIONS, *USB_NOTEBOOK_CONFIGURATIONS, *BYTES_NOTEBOOK_CONFIGURATIONS, *ARRAY_NOTEBOOK_CONFIGURATIONS, *STRING_NOTEBOOK_CONFIGURATIONS, *CLOSURE_NOTEBOOK_CONFIGURATIONS, *SUMS_NOTEBOOK_CONFIGURATIONS, "lemmasim-silicon-power-notebook", "lemmasim-silicon-power-initialize", *ARITHMETIC_DEVELOPMENT_CONFIGURATIONS, *MANAGED_NOTEBOOK_CONFIGURATIONS)
SILICON_MULTI_CONFIGURATIONS = (*PRODUCT_NOTEBOOK_CONFIGURATIONS, *USB_NOTEBOOK_CONFIGURATIONS, *BYTES_NOTEBOOK_CONFIGURATIONS, *ARRAY_NOTEBOOK_CONFIGURATIONS, *STRING_NOTEBOOK_CONFIGURATIONS, *CLOSURE_NOTEBOOK_CONFIGURATIONS, *SUMS_NOTEBOOK_CONFIGURATIONS, *MANAGED_NOTEBOOK_CONFIGURATIONS, *ARITHMETIC_DEVELOPMENT_CONFIGURATIONS, "lemmasim-silicon-power-notebook", "lemmasim-silicon-power-initialize", "silicon-service-development", "lemmasim-silicon-full-notebook", "lemmasim-silicon-full-initialize", "lemmasim-silicon-notebook", "lemmasim-silicon-initialize")
WIFI_COMMON_CONFIGURATIONS = ("lemmasim-silicon-wifi-common-probe", "lemmasim-silicon-wifi-common-read-probe")
SILICON_CONFIGURATIONS = (*SILICON_MULTI_CONFIGURATIONS, *WIFI_COMMON_CONFIGURATIONS, "lemmasim-silicon-devices", "lemmasim-silicon-power-probe", "lemmasim-silicon-power-safety-probe", "lemmasim-silicon-ble-link-probe", "lemmasim-silicon-usb-link-probe")
CONFIGURATIONS = (*SILICON_CONFIGURATIONS, "lemmasim-isolation-development", "lemmasim-notebook", "lemmasim-initialize", "lemmasim-bringup", "normal", "frames-development", "machine-origin-development",
                  "user-isolation-development", "user-csr-development", "user-nx-development",
                  "user-kernel-fetch-development", "user-misaligned-development", "user-syscall-development",
                  "tasks-development", "tasks-fault-development", "capabilities-development", "ipc-development",
                  "service-normal", "service-development", *USER_INSTRUCTION_CONFIGURATIONS,
                  *SERVICE_INSTRUCTION_CONFIGURATIONS)
MULTI_CONFIGURATIONS = (*SILICON_MULTI_CONFIGURATIONS, "lemmasim-isolation-development", "lemmasim-notebook", "lemmasim-initialize", "tasks-development", "tasks-fault-development", "capabilities-development", "ipc-development",
                       "service-normal", "service-development", *SERVICE_INSTRUCTION_CONFIGURATIONS)
SERVICE_CONFIGURATIONS = ("silicon-service-development", "service-normal", "service-development", *SERVICE_INSTRUCTION_CONFIGURATIONS)
INDEPENDENT_IMAGE_KEYS = {"lemmasim-isolation-development": {"store", "notebook", "isolation"}, "lemmasim-notebook": {"store", "notebook"},
                          "lemmasim-initialize": {"store", "notebook"}, "tasks-development": {"compute", "sleeper", "busy"},
                          "tasks-fault-development": {"compute", "sleeper", "busy", "fault"},
                          "capabilities-development": {"capabilities", "peer", "busy", "tamper"},
                          "ipc-development": {"server", "clienta", "clientb", "busy", "fault"},
                          "service-normal": {"server", "cli", "peer", "busy"},
                          "service-development": {"server", "cli", "peer", "busy", "fault"}}
INDEPENDENT_IMAGE_KEYS.update({"lemmasim-silicon-power-notebook": {"store", "notebook"}, "lemmasim-silicon-power-initialize": {"store", "notebook"}, "silicon-service-development": {"server", "cli", "peer", "busy", "fault"},
                               "lemmasim-silicon-full-notebook": {"store", "notebook"}, "lemmasim-silicon-notebook": {"store", "notebook"},
                               "lemmasim-silicon-full-initialize": {"store", "notebook"}, "lemmasim-silicon-initialize": {"store", "notebook"}})
INDEPENDENT_IMAGE_KEYS.update({configuration: {"store", "notebook", "arithmetic"} for configuration in ARITHMETIC_CONFIGURATIONS})
INDEPENDENT_IMAGE_KEYS.update({configuration: {"store", "notebook", "arithmetic", "course"} for configuration in COURSE_NOTEBOOK_CONFIGURATIONS})
INDEPENDENT_IMAGE_KEYS.update({configuration: {"server", "cli", "peer", "busy", "fault"}
                               for configuration in SERVICE_INSTRUCTION_CONFIGURATIONS})
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
# Resolve the locked flake through Nix's Git fetcher so ignored build/.lake
# outputs cannot be copied into the store. Tracked working-tree edits remain
# visible; target source identity is independently bound by source_inputs. Each
# CI job still realizes and verifies the immutable upstream Lean source itself.
LEAN_SOURCE_EXPRESSION = ('let flake = builtins.getFlake ("git+file://" + toString ./.); '
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
    if configuration in INTEGRATED_CONFIGURATIONS:
        from integrated_deployment import BOOT_ROOT, DISPATCH_ROOT
        return {"firmware":ROLE_ROOTS["firmware"], "kernel":((BOOT_ROOT,()),(DISPATCH_ROOT,("u64","u64","u64")))}
    if configuration in MULTIMODAL_CONFIGURATIONS:
        from multimodal_deployment import BOOT_ROOTS
        return {"firmware": ROLE_ROOTS["firmware"], "kernel": (
            ("Lemma.Platform.LemmaSim.NotebookKernel." + BOOT_ROOTS[configuration], ()),
            ("Lemma.Platform.LemmaSim.NotebookKernel.dispatchMultimodalBulk", ("u64", "u64", "u64")))}
    if configuration in PRODUCT_READER_NOTEBOOK_CONFIGURATIONS:
        from product_reader_deployment import roots_for
        boot, dispatch = roots_for(configuration)
        return {"firmware": ROLE_ROOTS["firmware"], "kernel": (
            (boot, ()), (dispatch, ("u64", "u64", "u64")))}
    if configuration in USB_PACKAGE_RECOVERY_NOTEBOOK_CONFIGURATIONS:
        return {"firmware": ROLE_ROOTS["firmware"], "kernel": (
            ("Lemma.Platform.LemmaSim.NotebookKernel."+PACKAGE_RECOVERY_BOOT_ROOTS[configuration], ()),
            ("Lemma.Platform.LemmaSim.NotebookKernel."+PACKAGE_RECOVERY_DISPATCH_ROOT, ("u64", "u64", "u64")))}
    if configuration in CLOSURE_NOTEBOOK_CONFIGURATIONS:
        entry=CLOSURE_KERNEL_ENTRIES[configuration]
        return {"firmware":ROLE_ROOTS["firmware"],"kernel":(
          ("Lemma.Platform.LemmaSim.NotebookKernel."+entry,()),
          ("Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk",("u64","u64","u64")))}
    if configuration in {*ARITHMETIC_CONFIGURATIONS, "lemmasim-notebook", "lemmasim-initialize", "lemmasim-isolation-development", "lemmasim-silicon-full-notebook", "lemmasim-silicon-notebook", "lemmasim-silicon-full-initialize", "lemmasim-silicon-initialize"}:
        entry = {"lemmasim-silicon-usb-clocked-closure-retry-bulk-notebook":"siliconUSBClosureRecoveryBoot", "lemmasim-silicon-usb-clocked-closure-retry-bulk-initialize":"siliconUSBClosureRecoveryInitializeMedium", "lemmasim-silicon-course-await-bulk-notebook":"siliconCourseAwaitBoot", "lemmasim-silicon-course-await-bulk-initialize":"siliconCourseAwaitInitializeMedium", "lemmasim-silicon-usb-clocked-retry-bulk-notebook":"siliconUSBRecoveryBoot", "lemmasim-silicon-usb-clocked-retry-bulk-initialize":"siliconUSBRecoveryInitializeMedium", "lemmasim-silicon-course-bulk-notebook":"siliconCourseBoot", "lemmasim-silicon-course-bulk-initialize":"siliconCourseInitializeMedium", "lemmasim-silicon-usb-clocked-bulk-notebook":"siliconUSBClockedBoot", "lemmasim-silicon-usb-clocked-bulk-initialize":"siliconUSBClockedInitializeMedium", "lemmasim-silicon-usb-wire-bulk-notebook":"siliconUSBWireBoot", "lemmasim-silicon-usb-wire-bulk-initialize":"siliconUSBWireInitializeMedium", "lemmasim-silicon-product-executed-bulk-notebook":"siliconProductExecutedBoot", "lemmasim-silicon-string-bulk-notebook":"siliconPowerBoot", "lemmasim-silicon-string-bulk-initialize":"siliconPowerInitializeMedium", "lemmasim-silicon-string-arithmetic-oom-development":"arithmeticOOMBoot", "lemmasim-silicon-usb-next-bulk-notebook":"siliconUSBNextBoot", "lemmasim-silicon-usb-next-bulk-initialize":"siliconUSBNextInitializeMedium", "lemmasim-silicon-product-next-bulk-notebook":"siliconProductNextBoot", "lemmasim-silicon-array-bulk-notebook": "siliconPowerBoot", "lemmasim-silicon-array-bulk-initialize": "siliconPowerInitializeMedium", "lemmasim-silicon-array-arithmetic-oom-development": "arithmeticOOMBoot", "lemmasim-silicon-bytes-bulk-notebook": "siliconPowerBoot", "lemmasim-silicon-bytes-bulk-initialize": "siliconPowerInitializeMedium", "lemmasim-silicon-bytes-arithmetic-oom-development": "arithmeticOOMBoot", "lemmasim-silicon-usb-bulk-notebook": "siliconUSBBoot", "lemmasim-silicon-usb-bulk-initialize": "siliconUSBInitializeMedium", "lemmasim-silicon-product-bulk-notebook": "siliconProductBoot", "lemmasim-silicon-bulk-notebook": "siliconPowerBoot", "lemmasim-silicon-bulk-initialize": "siliconPowerInitializeMedium", "lemmasim-silicon-product-notebook": "siliconProductBoot", "lemmasim-silicon-usb-notebook": "siliconUSBBoot", "lemmasim-silicon-usb-initialize": "siliconUSBInitializeMedium", "lemmasim-silicon-sums-notebook": "siliconPowerBoot", "lemmasim-silicon-sums-initialize": "siliconPowerInitializeMedium", "lemmasim-silicon-sums-arithmetic-oom-development": "arithmeticOOMBoot", "lemmasim-silicon-managed-notebook": "siliconPowerBoot", "lemmasim-silicon-managed-initialize": "siliconPowerInitializeMedium", "lemmasim-silicon-power-arithmetic-oom-development": "arithmeticOOMBoot", "lemmasim-silicon-power-arithmetic-fault-development": "arithmeticFaultBoot", "lemmasim-silicon-power-arithmetic-stall-development": "arithmeticStallBoot", "lemmasim-silicon-power-notebook": "siliconPowerBoot", "lemmasim-silicon-power-initialize": "siliconPowerInitializeMedium", "lemmasim-silicon-full-notebook": "siliconFullBoot", "lemmasim-silicon-full-initialize": "siliconFullInitializeMedium", "lemmasim-silicon-notebook": "siliconBoot", "lemmasim-silicon-initialize": "siliconInitializeMedium", "lemmasim-initialize": "initializeMedium", "lemmasim-isolation-development": "isolationBoot"}.get(configuration, "boot")
        return {"firmware": ROLE_ROOTS["firmware"], "kernel": (("Lemma.Platform.LemmaSim.NotebookKernel." + entry, ()),
                 ("Lemma.Platform.LemmaSim.NotebookKernel." + ("dispatchUSBClosureRecoveryBulk" if configuration in USB_CLOSURE_RECOVERY_NOTEBOOK_CONFIGURATIONS else "dispatchUSBRecoveryBulk" if configuration in USB_RECOVERY_NOTEBOOK_CONFIGURATIONS else "dispatchUSBClockedBulk" if configuration in USB_CLOCKED_NOTEBOOK_CONFIGURATIONS else "dispatchUSBWireBulk" if configuration in USB_WIRE_NOTEBOOK_CONFIGURATIONS else "dispatchProductExecutedBulk" if configuration in PRODUCT_EXECUTED_NOTEBOOK_CONFIGURATIONS else "dispatchUSBNextBulk" if configuration in USB_NEXT_NOTEBOOK_CONFIGURATIONS else "dispatchProductNextBulk" if configuration in PRODUCT_NEXT_NOTEBOOK_CONFIGURATIONS else "dispatchUSBBulk" if configuration in USB_NOTEBOOK_CONFIGURATIONS and configuration in BULK_NOTEBOOK_CONFIGURATIONS else "dispatchProductBulk" if configuration == "lemmasim-silicon-product-bulk-notebook" else "dispatchBulk" if configuration in BULK_NOTEBOOK_CONFIGURATIONS else "dispatchProduct" if configuration in PRODUCT_NOTEBOOK_CONFIGURATIONS else "dispatchUSB" if configuration in USB_NOTEBOOK_CONFIGURATIONS else "dispatch"), ("u64", "u64", "u64")))}
    if configuration == "lemmasim-silicon-usb-link-probe":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.Silicon.Development.USBLink.boot", ()),
                 ("Lemma.Platform.Silicon.Development.USBLink.dispatch", ("u64", "u64", "u64"))),
                 "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration == "lemmasim-silicon-wifi-common-read-probe":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.Silicon.Development.WiFiCommonReadProbe.boot", ()),
                 ("Lemma.Platform.Silicon.Development.WiFiCommonReadProbe.dispatch", ("u64", "u64", "u64"))),
                 "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration == "lemmasim-silicon-wifi-common-probe":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.Silicon.Development.WiFiCommonProbe.boot", ()),
                 ("Lemma.Platform.Silicon.Development.WiFiCommonProbe.dispatch", ("u64", "u64", "u64"))),
                 "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration == "lemmasim-silicon-ble-link-probe":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.Silicon.Development.BLELink.boot", ()),
                 ("Lemma.Platform.Silicon.Development.BLELink.dispatch", ("u64", "u64", "u64"))),
                 "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration == "lemmasim-silicon-power-safety-probe":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.Silicon.Development.PowerSafety.boot", ()),
                 ("Lemma.Platform.Silicon.Development.PowerSafety.dispatch", ("u64", "u64", "u64"))),
                 "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration == "lemmasim-silicon-power-probe":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.LemmaSim.NotebookKernel.siliconPowerProbe", ()),
                 ("Lemma.Platform.LemmaSim.NotebookKernel.dispatch", ("u64", "u64", "u64"))),
                 "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration == "lemmasim-silicon-devices":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.Silicon.Development.DeviceEntry.boot", ()),
                 ("Lemma.Platform.Silicon.Development.DeviceEntry.dispatch", ("u64", "u64", "u64"))),
                "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration == "lemmasim-bringup":
        return {**ROLE_ROOTS, "kernel": (("Lemma.Platform.LemmaSim.Entry.boot", ()),
                 ("Lemma.Platform.LemmaSim.Entry.dispatch", ("u64", "u64", "u64"))),
                "user": (("Lemma.User.DeviceWorker.main", ("u64",)),)}
    if configuration in MULTI_CONFIGURATIONS:
        module = "Lemma.Kernel.Development.ServiceEntry" if configuration in (*SERVICE_INSTRUCTION_CONFIGURATIONS, "silicon-service-development") else {
                  "tasks-development": "Lemma.Kernel.Development.TasksEntry",
                  "tasks-fault-development": "Lemma.Kernel.Development.FaultEntry",
                  "capabilities-development": "Lemma.Kernel.Development.CapsEntry",
                  "ipc-development": "Lemma.Kernel.Development.IPCEntry",
                  "service-normal": "Lemma.Kernel.ServiceEntry",
                  "service-development": "Lemma.Kernel.Development.ServiceEntry"}[configuration]
        return {"firmware": ROLE_ROOTS["firmware"], "kernel": ((module + (".siliconBoot" if configuration == "silicon-service-development" else ".boot"), ()),
                   (module + ".dispatch", ("u64", "u64", "u64")))}
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
    if configuration in MULTI_CONFIGURATIONS:
        return {"firmware": ROLE_MODULES["firmware"], "kernel": configuration_roots(configuration)["kernel"][0][0].rsplit(".", 1)[0]}
    if configuration == "lemmasim-silicon-usb-link-probe":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.Silicon.Development.USBLink", "user": "Lemma.User.DeviceWorker"}
    if configuration == "lemmasim-silicon-wifi-common-read-probe":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.Silicon.Development.WiFiCommonReadProbe", "user": "Lemma.User.DeviceWorker"}
    if configuration == "lemmasim-silicon-wifi-common-probe":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.Silicon.Development.WiFiCommonProbe", "user": "Lemma.User.DeviceWorker"}
    if configuration == "lemmasim-silicon-ble-link-probe":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.Silicon.Development.BLELink", "user": "Lemma.User.DeviceWorker"}
    if configuration == "lemmasim-silicon-power-safety-probe":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.Silicon.Development.PowerSafety", "user": "Lemma.User.DeviceWorker"}
    if configuration == "lemmasim-silicon-power-probe":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.LemmaSim.NotebookKernel", "user": "Lemma.User.DeviceWorker"}
    if configuration == "lemmasim-silicon-devices":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.Silicon.Development.DeviceEntry", "user": "Lemma.User.DeviceWorker"}
    if configuration == "lemmasim-bringup":
        return {**ROLE_MODULES, "kernel": "Lemma.Platform.LemmaSim.Entry", "user": "Lemma.User.DeviceWorker"}
    if configuration == "frames-development":
        return {**ROLE_MODULES, "kernel": "Lemma.Kernel.Development.FramesEntry"}
    if configuration == "user-isolation-development":
        return {**ROLE_MODULES, "kernel": "Lemma.Kernel.Development.IsolationEntry", "user": "Lemma.User.Development.Isolation"}
    if configuration == "user-syscall-development":
        return {**ROLE_MODULES, "user": "Lemma.User.Development.Syscall"}
    return ROLE_MODULES


def development_role(configuration: str, role: str) -> bool:
    configuration_roots(configuration)
    return (configuration in MULTI_CONFIGURATIONS and configuration != "service-normal" and role == "kernel"
            or configuration in {*WIFI_COMMON_CONFIGURATIONS, "frames-development", "lemmasim-silicon-devices", "lemmasim-silicon-power-safety-probe", "lemmasim-silicon-ble-link-probe", "lemmasim-silicon-usb-link-probe"} and role == "kernel"
            or configuration == "user-isolation-development" and role in {"kernel", "user"}
            or configuration == "user-syscall-development" and role == "user")


def configuration_development_modules(configuration: str, role: str) -> tuple[str, ...]:
    modules = configuration_modules(configuration)
    if configuration == "lemmasim-silicon-devices" and role == "kernel":
        return ("Lemma.Platform.Silicon.Development.DeviceEntry", "Lemma.Platform.Silicon.Development.DeviceProbe")
    if configuration == "tasks-fault-development" and role == "kernel":
        return ("Lemma.Kernel.Development.FaultEntry", "Lemma.Kernel.Development.TasksEntry",
                "Lemma.Kernel.Development.Pressure")
    if configuration == "capabilities-development" and role == "kernel":
        return ("Lemma.Kernel.Development.CapsEntry", "Lemma.Kernel.Development.CapAlias",
                "Lemma.Kernel.Development.TasksEntry", "Lemma.Kernel.Development.CapabilityGeneration")
    if configuration == "ipc-development" and role == "kernel":
        return ("Lemma.Kernel.Development.IPCEntry", "Lemma.Kernel.Development.TasksEntry")
    return (modules[role],) if development_role(configuration, role) else ()


def managed_policy(configuration: str) -> str | None:
    configuration_roots(configuration)
    if configuration in ARITHMETIC_CONFIGURATIONS:
        return "lemma-notebook-arithmetic-v1"
    if configuration in { "lemmasim-notebook", "lemmasim-initialize", "lemmasim-isolation-development", "lemmasim-silicon-full-notebook", "lemmasim-silicon-notebook", "lemmasim-silicon-full-initialize", "lemmasim-silicon-initialize"}:
        return "lemma-notebook-v1"
    if configuration in SERVICE_CONFIGURATIONS:
        return "lemma-buffer-service-v1"
    return {"capabilities-development": "lemma-capabilities-v1", "ipc-development": "lemma-ipc-v1",
            "service-normal": "lemma-buffer-service-v1", "service-development": "lemma-buffer-service-v1"}.get(configuration)


def startup_case(configuration: str) -> str:
    configuration_roots(configuration)
    return "machine-origin-probe" if configuration == "machine-origin-development" else "normal"


def user_startup_case(configuration: str) -> str:
    configuration_roots(configuration)
    return {"user-csr-development": "supervisor-csr", "user-nx-development": "execute-data",
            "user-kernel-fetch-development": "execute-kernel", "user-misaligned-development": "execute-misaligned",
            **USER_INSTRUCTION_CONFIGURATIONS}.get(configuration, "none")


def validate_configuration_stage(configuration: str, stage: str) -> None:
    configuration_roots(configuration)
    if stage not in {"bootstrap-m", "supervisor"}:
        raise Core0Error("unknown execution stage")
    if configuration == "machine-origin-development" and stage != "bootstrap-m":
        raise Core0Error("machine-origin-development requires bootstrap-m")
    if configuration in {*WIFI_COMMON_CONFIGURATIONS, "lemmasim-silicon-ble-link-probe", "lemmasim-silicon-usb-link-probe", "lemmasim-silicon-power-probe", "lemmasim-silicon-power-safety-probe", "user-isolation-development", "user-csr-development", "user-nx-development",
                         "user-kernel-fetch-development", "user-misaligned-development", "user-syscall-development",
                         *USER_INSTRUCTION_CONFIGURATIONS, *MULTI_CONFIGURATIONS} and stage != "supervisor":
        raise Core0Error("user isolation configurations require supervisor")


def artifact_category(configuration: str) -> str:
    configuration_roots(configuration)
    return ("production" if configuration in {"normal", "service-normal", "lemmasim-notebook", "lemmasim-initialize"} else "development") + "-kernel-boot-package"


def user_artifact_category(configuration: str) -> str:
    configuration_roots(configuration)
    return ("production" if configuration in {"service-normal", "lemmasim-notebook", "lemmasim-initialize"} else "development") + "-user-image"


def service_executable_module(module: str) -> bool:
    return (module in {"Lemma.Services.Arithmetic.ServerV7", "Lemma.Services.Arithmetic.ServerV8"} or module == "Lemma.Courses.PackageInstaller" or module.startswith("Lemma.Courses.PackageInstaller.")
            or module.startswith("Lemma.Applications.") or module == "Lemma.Services.Store.Server"
            or module.startswith("Lemma.Services.Store.Server.") or module == "Lemma.Services.Store.ServerSchool" or module.startswith("Lemma.Services.Store.ServerSchool.") or module == "Lemma.Services.Buffer.Server"
            or module.startswith("Lemma.Services.Buffer.Server.") or module == "Lemma.User.Development.BufferFault"
            or module.startswith("Lemma.User.Development.BufferFault.")
            or module == "Lemma.User.Development.NotebookIsolation"
            or module.startswith("Lemma.User.Development.NotebookIsolation."))


def user_module_closure(root: Path, image: dict, configuration: str) -> dict[str, str]:
    """Selected target source only; exporter/compiler host imports are separate."""
    course_await_library = (configuration in AWAIT_NOTEBOOK_CONFIGURATIONS
                            and type(image.get("id")) is int and image["id"] == 1
                            and image.get("boot_role") == "store-server"
                            and course_await_library_source_allowed("user", "Lemma.Services.Store.Server", image))
    return module_closure(root, image["module"], allow_development=".Development." in image["module"],
                          forbid_user_privileged_imports=managed_policy(configuration) is not None,
                          allow_course_await_library=course_await_library,
                          selected_executable_module=image["module"] if configuration in (*SERVICE_CONFIGURATIONS, *ARITHMETIC_CONFIGURATIONS, "lemmasim-notebook", "lemmasim-initialize", "lemmasim-isolation-development", "lemmasim-silicon-full-notebook", "lemmasim-silicon-full-initialize", "lemmasim-silicon-notebook", "lemmasim-silicon-initialize") else None)


def source_inputs(root: Path) -> dict[str, str]:
    # Current HTML contracts are required consumed inputs. Old immutable source
    # archives retain their original Markdown layout and hashes.
    documentation_map = root / "docs/document-map.json"
    if any((root / guide).is_file() for guide in ("docs/contributor-guide.html", "docs/contributing.html")) and not documentation_map.is_file():
        raise Core0Error("Current source is missing its documentation identity map")
    def documented_input(relative: str) -> Path:
        selected = root / relative
        if relative.startswith("docs/contracts/") and relative.endswith(".html"):
            if documentation_map.is_file() and not selected.is_file():
                raise Core0Error("Missing required current contract source: " + relative)
            legacy = selected.with_suffix(".md")
            if not documentation_map.is_file() and legacy.is_file():
                return legacy
        return selected
    inputs = [root / name for name in ("flake.nix", "flake.lock", "lean-toolchain", "lakefile.toml",
                                     "tooling/toolchain-lock.json", "scripts/core0_common.py", "scripts/build_core0.py",
                                     "scripts/audit_core0.py", "scripts/audit_device.py",
                                     "scripts/audit_memory.py", "scripts/audit_monitor.py", "scripts/audit_timer.py", "scripts/audit_trap.py",
                                     "scripts/build-kernel.sh", "scripts/audit-kernel.sh",
                                     "scripts/build_kernel.py", "scripts/audit_kernel.py", "scripts/lemmasim_readonly.py", "scripts/audit_lemmasim_capacity.py", "scripts/build_user.py", "scripts/build-user.sh")]
    # Old immutable source archives predate this additive audit helper. Current
    # selected optimization builds import it and fail if unavailable.
    closed_inline = root / "scripts/closed_inline.py"
    if closed_inline.is_file():inputs.append(closed_inline)
    records = root / "scripts/managed_records.py"
    if records.is_file():inputs.append(records)
    for helper in ("surface_word_inline.py", "package_closure_deployment.py", "package_notebook_target.py","package_companion_deployment.py","package_entry2_deployment.py","package_entry2_target.py","package_companion_target.py","aligned_notebook_target.py", "control_notebook_target.py", "task_entry_borrow.py", "usb_closure_recovery_deployment.py", "usb_closure_recovery_target.py", "kernel_source_workspace.py","surface_bulk_borrow.py","usercopy_page_words.py","course_deployment.py","course_await_deployment.py","ipc_poll_borrow.py","ipc_call_borrow.py","ipc_rpc_borrow.py", "arithmetic_execution_identity.py", "managed_sums.py", "arithmetic_sums_identity.py", "paper_bulk.py", "managed_bytes.py", "arithmetic_bytes_identity.py", "managed_array.py", "arithmetic_array_identity.py", "managed_string.py", "arithmetic_string_identity.py", "closure_deployment.py", "managed_closure.py", "arithmetic_closure_identity.py", "paper_next.py", "paper_executed.py", "paper_wire.py", "paper_clocked.py", "usb_recovery_target.py", "wifi_common.py", "wifi_owned_read.py"):
        additive = root / "scripts" / helper
        if additive.is_file():inputs.append(additive)
    # Legacy archives predate the additive owned-record/PCM service version.
    # A tree declaring that service must retain its actual contract; deleting
    # the current contract cannot downgrade it to the legacy input closure.
    multimodal_service = root / "Lemma/Platform/LemmaSim/MultimodalService.lean"
    if (multimodal_service.is_file() and re.search(
            r"^def version\s*:\s*UInt64\s*:=", multimodal_service.read_text(), re.M)):
        owned_io = root / "docs/contracts/009-multimodal-owned-io-v1.html"
        if not owned_io.is_file():
            raise Core0Error("Missing required owned record/PCM service contract")
        inputs.append(owned_io)
    notebook = root / "Lemma/Applications/Notebook.lean"
    if notebook.is_file() and re.search(r"^private def deferredSaved\s*:", notebook.read_text(), re.M):
        receipt_contract = root / "docs/contracts/009-notebook-commit-receipt-v2.html"
        if not receipt_contract.is_file():
            raise Core0Error("Missing required Notebook deferred commit receipt contract")
        inputs.append(receipt_contract)
    inputs += [root / "scripts/silicon_profile.py", root / "sim/profiles/lemma-silicon-dev-0.1.0.json", root / "sim/profiles/lemma-silicon-dev-0.2.0.json", root / "sim/profiles/lemma-silicon-dev-0.3.0.json"]
    # Historical immutable source archives predate additive Power-v2. Their
    # complete old inventories remain exact; selected 0.4 builds separately
    # require/validate their profile through configuration_profile/generate.
    safety_profile=root / "sim/profiles/lemma-silicon-dev-0.4.0.json"
    if safety_profile.is_file():inputs.append(safety_profile)
    ble_profile=root / "sim/profiles/lemma-silicon-dev-0.5.0.json"
    if ble_profile.is_file():inputs.append(ble_profile)
    usb_profile=root / "sim/profiles/lemma-silicon-dev-0.6.0.json"
    if usb_profile.is_file():inputs.append(usb_profile)
    product_profile=root / "sim/profiles/lemma-silicon-dev-0.7.0.json"
    if product_profile.is_file():inputs.append(product_profile)
    for number in (8,9,10,11,12,13,14,15):
        next_profile=root / f"sim/profiles/lemma-silicon-dev-0.{number}.0.json"
        if next_profile.is_file():inputs.append(next_profile)
    recovery_authority=root / "tooling/usb-recovery-target-authority.json"
    if recovery_authority.is_file():inputs.append(recovery_authority)
    closure_recovery_authority=root / "tooling/usb-closure-recovery-target-authority.json"
    if closure_recovery_authority.is_file():inputs.append(closure_recovery_authority)
    common_authority=root / "tooling/wifi_common-authority.json"
    if common_authority.is_file():inputs.append(common_authority)
    read_authority=root / "tooling/wifi-owned-read-authority.json"
    if read_authority.is_file():inputs.append(read_authority)
    package_recovery_authority=root / "tooling/package-companion-target-authority.json"
    if package_recovery_authority.is_file():inputs.append(package_recovery_authority)
    aligned_authority=root / 'tooling/aligned-notebook-target-authority.json'
    if aligned_authority.is_file():inputs.append(aligned_authority)
    control_authority=root / 'tooling/control-notebook-target-authority.json'
    if control_authority.is_file():inputs.append(control_authority)
    for additive in ("scripts/trial_watchdog_target.py", "tooling/trial-watchdog-target-authority.json", "docs/contracts/006-trial-boot-watchdog-v1.html", "scripts/chooser_reader_deployment.py", "scripts/chooser_reader_target.py", "tooling/chooser-reader-target-authority.json", "scripts/companion_reader_deployment.py", "scripts/companion_reader_target.py", "tooling/companion-reader-target-authority.json", "docs/contracts/006-companion-course-reader-deployment-v1.html", "scripts/product_reader_deployment.py", "scripts/product_reader_target.py", "tooling/product-reader-target-authority.json", "docs/contracts/006-product-course-reader-deployment-v1.html", "scripts/reader_deployment.py", "scripts/reader_notebook_target.py", "tooling/reader-notebook-target-authority.json"):
        path = documented_input(additive)
        if path.is_file():inputs.append(path)
    dirty_helper=root / 'scripts/dirty_batch_notebook_target.py'
    if dirty_helper.is_file():inputs.append(dirty_helper)
    dirty_authority=root / 'tooling/dirty-batch-notebook-target-authority.json'
    if dirty_authority.is_file():inputs.append(dirty_authority)
    export_host_policy(root)  # Missing current helper must not downgrade to a historical command.
    for additive in ("scripts/companion_number_pad_target.py", "tooling/companion-number-pad-target-authority.json", "tooling/package-entry2-target-authority.json", "docs/contracts/006-package-entry2-deployment-v1.html"):
        path = documented_input(additive)
        if path.is_file():inputs.append(path)
    for additive in ('scripts/notebook_control_backlog_target.py', 'tooling/notebook-control-backlog-target-authority.json', 'docs/contracts/006-notebook-control-backlog-v1.html', 'tooling/notebook-control-backlog-target-authority-v2.json', 'docs/contracts/006-notebook-control-backlog-v2.html', 'scripts/authored_hint_target.py', 'tooling/authored-hint-target-authority.json', 'docs/contracts/006-authored-hint-visibility-v1.html', 'tooling/authored-hint-publication-target-authority-v2.json', 'docs/contracts/006-authored-hint-publication-v2.html', 'scripts/kernel_pool_read_target.py', 'tooling/kernel-pool-read-target-authority.json', 'docs/contracts/006-kernel-pool-read-v1.html'):
        path = documented_input(additive)
        if path.is_file():inputs.append(path)
    export_host = root / "scripts/lean_export_host.py"
    if export_host.is_file():inputs.append(export_host)
    for helper in ("scripts/action_cache.py", "scripts/action_worker.py", "scripts/build_actions.py", "scripts/build_dependencies.py", "scripts/build_admission.py", "scripts/toolchain_preparation.py", "lake-manifest.json", "scripts/silicon_reset_rom.py"):
        if (root / helper).is_file(): inputs.append(root / helper)
    if documentation_map.is_file(): inputs.append(documentation_map)
    # An archive predating Integrated15 has no dependency on its new contract.
    # A source tree that installs the registry must retain its actual helpers
    # and contract; a missing current file never downgrades to an old authority.
    if (root / "scripts/integrated_deployment.py").is_file():
        for relative in ("scripts/integrated_deployment.py", "scripts/integrated_target.py",
                         "docs/contracts/009-core0-kernel-v0.10.html"):
            required = root / relative
            if not required.is_file():
                raise Core0Error("Missing required Integrated15 dependency: " + relative)
            inputs.append(required)
        authority = root / "tooling/integrated-target-authority.json"
        if authority.is_file(): inputs.append(authority)
    # The additive deployment is imported by this builder. Its current helpers
    # and contracts are mandatory inputs; immutable pre-multimodal archives do
    # not contain the deployment and retain their original closure. Authority
    # pins are collected from genuine exports, then required by the IR auditor.
    if (root / "scripts/multimodal_deployment.py").is_file():
        for relative in ("scripts/multimodal_deployment.py", "scripts/multimodal_target.py",
                         "docs/contracts/007-core0-kernel-v0.9.html",
                         "docs/contracts/007-converter-v1.html",
                         "docs/contracts/007-extended-multimodal-v0.2.0.html",
                         "docs/source-artifacts/LEMMA_EXTENDED_MULTIMODAL_SPEC_v0.2.0.txt",
                         "docs/source-artifacts/extended-multimodal-html-conversion.json",
                         "LEMMA_MACHINE_CONTRACT.html"):
            required = root / relative
            if not required.is_file():
                raise Core0Error("Missing required multimodal dependency: " + relative)
            inputs.append(required)
        authority = root / "tooling/multimodal-target-authority.json"
        if authority.is_file(): inputs.append(authority)
    if (root / "scripts/school_deployment.py").is_file():
        school_registry=(root / "scripts/school_deployment.py").read_text()
        if "INTEGRATED_PCM=" in school_registry:
            for relative in ("docs/contracts/009-multimodal-pcm-ring-v1.html", "sim/profiles/lemma-silicon-dev-0.16.0.json"):
                required=root/relative
                if not required.is_file():raise Core0Error("Missing Integrated16 owned PCM dependency: "+relative)
                inputs.append(required)
        school_contract="docs/contracts/009-school-submission-v2.html" if "lemma-school-notebook-deployment/2" in school_registry else "docs/contracts/009-school-submission-v1.html"
        for relative in ("scripts/school_deployment.py", "scripts/school_target.py", school_contract):
            required=root/relative
            if not required.is_file():raise Core0Error("Missing School dependency: "+relative)
            inputs.append(required)
        authority=root/"tooling/school-target-authority.json"
        if authority.is_file():inputs.append(authority)
    inputs += sorted((root / "Lemma").rglob("*.lean"))
    return {str(path.relative_to(root)): sha256(path) for path in inputs}


def module_closure(root: Path, module: str, seen: set[str] | None = None, *, allow_development: bool = False,
                   development_module: str | None = None,
                   development_modules: tuple[str, ...] | None = None,
                   forbid_user_privileged_imports: bool = False,
                   selected_executable_module: str | None = None,
                   allow_course_await_library: bool = False) -> dict[str, str]:
    import re
    if development_modules is None:
        development_modules = ((development_module or module,) if allow_development else ())
    seen = set() if seen is None else seen
    if module in seen or not module.startswith("Lemma."):
        return {}
    seen.add(module)
    if forbid_user_privileged_imports and module.startswith(("Lemma.Kernel.", "Lemma.Compiler.")):
        raise Core0Error(f"managed user dependency imports privileged/compiler code: {module}")
    recovery_library = (selected_executable_module == "Lemma.Services.Store.ServerRecovery" and module == "Lemma.Services.Store.Server") or (
        selected_executable_module == "Lemma.Services.Store.ServerRecoveryAwait" and
        module in {"Lemma.Services.Store.ServerRecovery", "Lemma.Services.Store.ServerAwait", "Lemma.Services.Store.Server"}) or (
        selected_executable_module == "Lemma.Services.Store.ServerSchool" and
        module in {"Lemma.Services.Store.ServerRecovery", "Lemma.Services.Store.ServerAwait", "Lemma.Services.Store.Server"})
    # The exact Await Store1 root borrows existing engine/dispatcher source.
    # Full IR admission separately excludes the old executable entry bodies.
    # The flag is derived only from the closed pair/role/root catalog above and
    # does not authorize any other executable or privileged dependency.
    course_await_library = (allow_course_await_library
                            and selected_executable_module == "Lemma.Services.Store.ServerAwait"
                            and module == "Lemma.Services.Store.Server")
    parameterized_library = (selected_executable_module == "Lemma.Services.Arithmetic.ServerV8"
                             and module == "Lemma.Services.Arithmetic.ServerV7")
    if selected_executable_module is not None and service_executable_module(module) and module != selected_executable_module and not recovery_library and not course_await_library and not parameterized_library:
        raise Core0Error(f"user dependency imports another executable module: {module}")
    if ".Test." in module or module.startswith("Lemma.Compiler.Test") or "Mutation" in module:
        raise Core0Error(f"production dependency imports a test/mutation module: {module}")
    if ".Development." in module and not allow_development:
        raise Core0Error(f"normal production dependency imports development code: {module}")
    if ".Development." in module and module not in development_modules:
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
                                         development_modules=development_modules,
                                         forbid_user_privileged_imports=forbid_user_privileged_imports,
                                         selected_executable_module=selected_executable_module,
                                         allow_course_await_library=allow_course_await_library))
    return result


def _nonempty(directory: Path, names: Sequence[str]) -> None:
    for name in names:
        path = directory / name
        if not path.is_file() or path.stat().st_size == 0:
            raise Core0Error(f"missing/empty mandatory generated artifact: {path}")


def command_invoker(root: Path, output_dir: Path, tools: dict, timeout_seconds: float, commands: list,
                    *, fresh: bool = False, cache_dir: Path | None = None, action_reuse: bool = True):
    """Shared bounded command recording for boot and independent user builds."""
    actions = None
    def invoke(argv: Sequence[str], cwd: Path = output_dir, env: dict[str, str] | None = None) -> bytes:
        nonlocal actions
        candidate = (Path(argv[0]).name in {"lake", "opt", "llc", "clang", "ld.lld", "llvm-objcopy"}
                     and list(argv[1:]) != ["--version"])
        if action_reuse and candidate and (output_dir / "action-source").is_dir():
            from build_actions import BuildActions
            if actions is None:
                actions = BuildActions(root, output_dir, tools, timeout_seconds, commands, fresh=fresh, cache_dir=cache_dir)
            result = actions.invoke(argv, cwd, env)
            if result is not None: return result
        actual = [tools.get(argv[0], argv[0]), *argv[1:]]
        host_environment = (export_host_environment(export_host_policy(root))
                            if Path(actual[0]).name == "lake" else {})
        recorded_environment = {"host_environment": host_environment} if host_environment else {}
        if host_environment:
            env = {**(os.environ if env is None else env), **host_environment}
        try:
            if Path(actual[0]).name == "lake":
                lock_path = root / "build/lake.lock"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                with lock_path.open("a+b") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    with action_lease(lock.fileno()):
                        result = run_bounded(actual, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
            else:
                result = run_bounded(actual, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
        except (Core0Error, OSError) as error:
            commands.append({"argv": list(actual), "cwd": str(cwd.relative_to(root)), "returncode": None,
                             "error": str(error), "completed": False, **recorded_environment})
            write_json(output_dir / "commands.json", commands)
            raise
        commands.append({"argv": list(actual), "cwd": str(cwd.relative_to(root)), "returncode": result.returncode,
                         "elapsed_seconds": result.elapsed_seconds,
                         "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace"), **recorded_environment})
        write_json(output_dir / "commands.json", commands)
        if result.returncode != 0:
            raise Core0Error(f"command failed ({result.returncode}): {' '.join(argv)}\n"
                             + (result.stdout + result.stderr).decode(errors='replace'))
        return result.stdout
    invoke.command_rows = commands
    invoke.output_dir = output_dir
    invoke.action_reuse = action_reuse
    invoke.cache_dir = cache_dir
    invoke.fresh = fresh
    return invoke


def export_user_catalog(root: Path, output_dir: Path, configuration: str, invoke) -> dict:
    from audit_kernel import validate_user_image_catalog
    consumer = output_dir / "CatalogExport.lean"
    consumer.write_text("import Lemma.Compiler.KernelExport\n\n#lemma_export_user_catalog\n")
    env = {**os.environ, "LEMMA_KERNEL_OUT": str(output_dir), "LEMMA_KERNEL_CONFIGURATION": configuration}
    invoke(export_command(consumer.relative_to(root), source_root=root), root, env)
    return validate_user_image_catalog(load_json(output_dir / "user-image-catalog.json"))


def export_user_image(root: Path, output_dir: Path, configuration: str, image: dict,
                      opt_level: str, invoke) -> dict:
    """Elaborate selected declarations or admit their exact prior action result."""
    from audit_kernel import validate_unit
    directory = output_dir / image["directory"]
    directory.mkdir(parents=True)
    consumer = directory / "Export.lean"
    consumer.write_text(f'import {image["module"]}\nimport Lemma.Compiler.KernelExport\n\n'
                        f'#lemma_export_user_image "{image["key"]}" [{image["source"]}]\n')
    env = {**os.environ, "LEMMA_KERNEL_OUT": str(output_dir), "LEMMA_KERNEL_CONFIGURATION": configuration}
    invoke(export_command(consumer.relative_to(root), source_root=root), root, env)
    _nonempty(directory, UNIT_FILES)
    unit = validate_unit(load_json(directory / "unit.json"), "user", configuration=configuration, image_key=image["key"])
    invoke(("opt", "-S", f"-passes={OPT_PASSES[opt_level]}", "program.ll", "-o", "program.opt.ll"), directory)
    invoke(("llc", *LLC_ARGUMENTS, "-stack-size-section", f"-{opt_level}", "program.opt.ll", "-o", "program.o"), directory)
    return unit


def export_user_files(root: Path, output_dir: Path, configuration: str, image: dict, invoke) -> None:
    consumer = output_dir / "UserFilesExport.lean"
    consumer.write_text(f'import Lemma.Compiler.KernelExport\n\n#lemma_export_user_files "{image["key"]}"\n')
    env = {**os.environ, "LEMMA_KERNEL_OUT": str(output_dir), "LEMMA_KERNEL_CONFIGURATION": configuration}
    invoke(export_command(consumer.relative_to(root), source_root=root), root, env)
    _nonempty(output_dir / image["directory"], USER_IMAGE_FILES)


def configuration_lemmasim(layout: dict) -> bool:
    return layout.get("configuration") in {*ARITHMETIC_CONFIGURATIONS, "lemmasim-notebook", "lemmasim-initialize", "lemmasim-bringup", "lemmasim-isolation-development", "lemmasim-silicon-full-notebook", "lemmasim-silicon-notebook", "lemmasim-silicon-full-initialize", "lemmasim-silicon-initialize", "lemmasim-silicon-devices", "lemmasim-silicon-power-probe", "lemmasim-silicon-power-safety-probe", "lemmasim-silicon-ble-link-probe", "lemmasim-silicon-usb-link-probe"}


def link_user_image(output_dir: Path, image: dict, invoke) -> None:
    """Link/extract a single ELF at its declared virtual layout, independently."""
    relative = image["directory"]
    directory = output_dir / relative
    _nonempty(directory, USER_IMAGE_FILES)
    from lemmasim_readonly import course_literal_link_options
    literal_options = course_literal_link_options(directory)
    invoke(("clang", *STARTUP_ARGUMENTS, f"{relative}/startup.S", "-o", f"{relative}/startup.o"))
    invoke(("ld.lld", "-m", "elf64lriscv", "--no-relax", *literal_options, "-T", f"{relative}/link.ld", f"-Map={relative}/image.map",
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
    # user stack and the current four-page owned kernel stack. Runtime arena grants
    # remain checked by the allocator; this rejects an impossible initial load.
    base_tables = 21 if configuration_lemmasim(layout) else 11
    if layout.get("configuration", "").startswith("lemmasim-silicon-"):
        from silicon_profile import profile, configuration_profile
        owner_quota = profile(configuration_profile(layout["configuration"]))["frame_quota"]
    else:
        owner_quota = 8192 if configuration_lemmasim(layout) else 32
    if base_tables + math.ceil(text_bytes / layout["frame_bytes"]) + 1 + user["stack_pages"] + layout["task_kernel_stack_pages"] > owner_quota:
        raise Core0Error("independent user image cannot fit the selected loader owner quota")
    validate_service_user_quota(layout, image, text_bytes)


def validate_service_user_quota(layout: dict, image: dict, text_bytes: int) -> dict | None:
    """Reserve the Server's four real arena pages in its initial image budget.

    The descriptor belongs to owner1 and contributes to global accounting,
    separately from the eighteen task-owned fixed pages:11 tables,1 data,
    2 User-stack pages and4 kernel-stack pages.
    """
    if layout.get("configuration") not in SERVICE_CONFIGURATIONS:
        return None
    if type(text_bytes) is not int or text_bytes <= 0 or layout.get("frame_bytes") != 4096:
        raise Core0Error("service text extent/frame size is invalid")
    pages = (text_bytes + 4095) // 4096
    reserve = 4 if image["key"] == "server" else 0
    if 18 + pages + reserve > 32:
        raise Core0Error("service user image leaves insufficient owned-page quota for its backing pages")
    return {"base_owned_task_frames": 18, "base_global_task_frames": 19,
            "text_pages": pages, "reserved_arena_pages": reserve, "owner_quota": 32}


def _realize_toolchain_fresh(root: Path, tools: dict, invoke, *, realization_dir: Path | None = None) -> tuple[dict, dict]:
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
    if realization_dir is None:
        expression, realization_cwd = LEAN_SOURCE_EXPRESSION, root
    else:
        from kernel_source_workspace import PATH_SOURCE_EXPRESSION
        expression, realization_cwd = PATH_SOURCE_EXPRESSION, realization_dir
    source_output = invoke(("nix", "build", "--no-link", "--print-out-paths", "--impure", "--expr", expression), realization_cwd).decode(errors="strict")
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


def realize_toolchain(root: Path, tools: dict, invoke, *, realization_dir: Path | None = None) -> tuple[dict, dict]:
    from build_actions import fresh_requested
    if (getattr(invoke, "action_reuse", False) and realization_dir is None
            and not fresh_requested(getattr(invoke, "fresh", True))):
        from toolchain_preparation import prepare
        from action_cache import CacheError
        try:
            return prepare(root, tools, invoke, output_dir=invoke.output_dir,
                           cache_dir=invoke.cache_dir, fresh=False, produce=lambda: _realize_toolchain_fresh(root, tools, invoke))
        except CacheError as error:
            raise Core0Error("toolchain cache rejected preparation: " + str(error)) from error
    return _realize_toolchain_fresh(root, tools, invoke, realization_dir=realization_dir)


def build(*, root: Path, output_dir: Path, opt_level: str, stage: str = "bootstrap-m", configuration: str = "normal",
          clean: bool = False, timeout_seconds: float = 300, archive_source_root: Path | None = None,
          fresh: bool = True, cache_dir: Path | None = None) -> dict[str, object]:
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

    invoke = command_invoker(root, output_dir, tools, timeout_seconds, commands, fresh=fresh, cache_dir=cache_dir,
                             action_reuse=archive_source_root is None)

    try:
        dependencies = {role: module_closure(root, module, allow_development=development_role(configuration, role),
                                            development_modules=configuration_development_modules(configuration, role),
                                            selected_executable_module="" if configuration in SERVICE_CONFIGURATIONS else None)
                        for role, module in modules.items()}
        source_before = source_inputs(root)
        if archive_source_root is None:
            from build_actions import retain_source
            retain_source(root, output_dir, source_before)
        workspace, realization_dir, orchestrator_before = None, None, None
        if archive_source_root is not None:
            from kernel_source_workspace import prepare, host_inputs
            workspace, realization_dir = prepare(root, output_dir, archive_source_root, repo_root(), source_inputs)
            orchestrator_before = host_inputs(repo_root(), source_inputs)
        versions, source_realization = (realize_toolchain(root, tools, invoke) if workspace is None else
                                       realize_toolchain(root, tools, invoke, realization_dir=realization_dir))
        images = []
        if configuration in MULTI_CONFIGURATIONS:
            invoke(("lake", "build", "Lemma.Compiler.KernelExport"), root)
            catalog = export_user_catalog(root, output_dir, configuration, invoke)
            images = catalog["images"]
            dependencies["users"] = {image["key"]: user_module_closure(root, image, configuration)
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
            invoke(export_command(consumer.relative_to(root), source_root=root), root, env)
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
        invoke(export_command(consumer.relative_to(root), source_root=root), root, env)
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
        if configuration in SILICON_CONFIGURATIONS:
            from silicon_profile import generate, configuration_profile
            generate(output_dir, devices=configuration.startswith("lemmasim-"), name=configuration_profile(configuration))
        else:
            capture_platform_dtb(output_dir=output_dir, root=root, command_log=commands, timeout_seconds=timeout_seconds)
        write_json(output_dir / "commands.json", commands)
        after = source_inputs(root)
        if source_before != after:
            raise Core0Error("compiler/production inputs changed during build")
        commit = invoke(("git", "rev-parse", "HEAD"), root).decode().strip()
        dirty = invoke(("git", "status", "--porcelain=v1", "--untracked-files=all"), root).decode().splitlines()
        if workspace is not None:
            from kernel_source_workspace import host_inputs, validate_flake_input
            if host_inputs(repo_root(), source_inputs) != orchestrator_before:
                raise Core0Error("archive compiler host orchestrator changed during build")
            validate_flake_input(realization_dir, workspace['flake_input_sha256'])
            workspace.update(parent_git_root=invoke(("git", "rev-parse", "--show-toplevel"), root).decode().strip(),
                             parent_git_prefix=invoke(("git", "rev-parse", "--show-prefix"), root).decode().strip(),
                             parent_git_head=commit, host_orchestrator_inputs=orchestrator_before)
        artifacts = {str(path.relative_to(output_dir)): sha256(path) for path in sorted(output_dir.rglob("*"))
                     if path.is_file() and path.name not in {"commands.json", "build.json", "provenance.json"}}
        linked_inputs = ({"boot": list(BOOT_OBJECTS), "users": {image["key"]: [f'{image["directory"]}/startup.o', f'{image["directory"]}/program.o'] for image in images}}
                         if images else {"boot": list(BOOT_OBJECTS), "user": list(USER_OBJECTS)})
        unit_contracts = {role: value["contract_version"] for role, value in units.items() if role != "users"}
        if images:
            unit_contracts["users"] = {key: value["contract_version"] for key, value in units["users"].items()}
        image_startup_fields = ({"user_startup_cases": {image["key"]: image["startup_case"] for image in images}}
                                if configuration == "tasks-fault-development" or configuration in SERVICE_INSTRUCTION_CONFIGURATIONS else {})
        managed_fields = ({"managed_policy": managed_policy(configuration),
                           "boot_roles": {image["key"]: image["boot_role"] for image in images}}
                          if managed_policy(configuration) is not None else {})
        provenance = {"schema_version": 2 if images else 1, "artifact_category": category, "configuration": configuration, "startup_case": case, "user_startup_case": user_case,
                      **image_startup_fields, **managed_fields,
                      "lean_source_realization": source_realization,
                      "stage": stage, "optimization": opt_level, "source_commit": commit, "dirty_paths": dirty,
                      **({"compiler_source_workspace": workspace} if workspace is not None else {}),
                      "source_inputs": source_before, "host_export_policy": export_host_policy(root),
                      "target_module_closures": dependencies, "tools": versions,
                      "commands": commands, "generated_by_lean": generated_files,
                      "linked_inputs": linked_inputs, "artifacts": artifacts, "unit_contracts": unit_contracts}
        write_json(output_dir / "provenance.json", provenance)
        record = {"schema_version": 2 if images else 1, "status": "BUILT", "artifact_category": category, "configuration": configuration, "startup_case": case, "user_startup_case": user_case,
                  **image_startup_fields, **managed_fields,
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
    parser.add_argument("--source-archive", type=Path, help="Complete original source-input archive; requires an unused --source-workspace")
    parser.add_argument("--source-workspace", type=Path, help="Unused private compiler copy under build/kernel; --output-dir is relative to this copy")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="Execute production actions, bypassing cache reads; qualification uses LEMMA_BUILD_FRESH=1")
    parser.add_argument("--cache-dir", type=Path, help="Shared local validated action cache (default build/action-cache)")
    parser.add_argument("--timeout", type=float, default=300)
    ns = parser.parse_args()
    root = repo_root()
    if (ns.source_archive is None) != (ns.source_workspace is None):
        parser.error("--source-archive and --source-workspace must be provided together")
    try:
        source_archive = None
        if ns.source_archive is not None:
            from kernel_source_workspace import copy_inputs
            source_archive = (root / ns.source_archive).resolve()
            root = copy_inputs(source_archive, (root / ns.source_workspace).resolve(), root, source_inputs)
        output = (root / ns.output_dir).resolve()
        result = build(root=root, output_dir=output, opt_level=ns.opt_level, stage=ns.stage, configuration=ns.configuration, clean=ns.clean, timeout_seconds=ns.timeout, archive_source_root=source_archive, fresh=ns.fresh, cache_dir=ns.cache_dir)
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        print(f"KERNEL BUILD FAIL: {error}", file=sys.stderr)
        return 1
    print(f"KERNEL BUILD COMPLETE: {output / 'image.elf'}; {result['configuration']}, {result['stage']}, {result['optimization']}; audit separately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
