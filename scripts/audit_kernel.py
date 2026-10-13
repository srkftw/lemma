#!/usr/bin/env python3
"""Fail-closed host artifact audit for the versioned production kernel package.

This checks declared source/object/privilege closure and actual ELF artifacts.
It is neither a compiler-correctness proof nor evidence of S/U execution.
"""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path
import re
import struct
import sys

from audit_core0 import (alloc_section_names, defined_function_symbols, numeric_symbols, parse_definitions_and_calls,
                         parse_load_segments, relocation_types, parse_stack_sizes,
                         validate_loop_stack_call_graph, _ir_definition_body, _structured_ir_blocks, _structured_successors, _structured_reachable)
from build_core0 import LLC_ARGUMENTS, OPT_PASSES, STARTUP_ARGUMENTS, invalidate_output_file
from build_kernel import (BOOT_FILES, BOOT_OBJECTS, CONTRACTS, ROLE_MODULES, ROLE_ROOTS,
                          UNIT_FILES, USER_OBJECTS, artifact_category, configuration_modules,
                          configuration_roots, development_role, module_closure, source_inputs, startup_case, user_startup_case,
                          configuration_development_modules,
                          SERVICE_CONFIGURATIONS, USER_INSTRUCTION_CONFIGURATIONS, SERVICE_INSTRUCTION_CONFIGURATIONS,
                          service_executable_module, user_module_closure, user_artifact_category,
                          validate_configuration_stage, validate_lean_source_realization,
                          LEAN_SOURCE_EXPRESSION, LEAN_UINT_SOURCE_SHA256, SILICON_CONFIGURATIONS,
                          ARITHMETIC_CONFIGURATIONS, ARITHMETIC_DEVELOPMENT_CONFIGURATIONS)
from core0_common import Core0Error, load_json, repo_root, require_tools, run_bounded, sha256, write_json
from audit_device import (_access_op, _valid_access_alignment, _line_functions, DIRECT_ADDRESS, FENCE_CALL, SITE_MARKER,
                          validate_platform_evidence)

MACHINE_SYMBOLS = {
    "_start", "core0_io_fence", "lemma_exec_read_time", "lemma_exec_set_machine_compare",
    "lemma_exec_forward_supervisor", "lemma_exec_firmware_call", "lemma_exec_syscall",
    "lemma_exec_install_satp", "lemma_exec_fence_instruction", "lemma_exec_enter_user",
    "lemma_exec_wait_interrupt", "lemma_machine_fatal", "lemma_machine_double_fault",
    "lemma_supervisor_fatal", "lemma_supervisor_double_fault",
    "lemma_exec_supervisor_pending",
}
SUPERVISOR_SYMBOLS = {"lemma_machine_vector", "lemma_supervisor_vector", "lemma_supervisor_start"}
M_SYMBOLS = {"_start", "lemma_exec_read_time", "lemma_exec_set_machine_compare",
             "lemma_exec_forward_supervisor", "lemma_machine_fatal", "lemma_machine_double_fault", "lemma_machine_vector"}
EXECUTION_OPERATIONS = {
    "physicalRead8": ("physical-read8", None, 0, "word", {"firmware", "kernel"}),
    "physicalRead64": ("physical-read64", None, 0, "word", {"firmware", "kernel"}),
    "physicalWrite8": ("physical-write8", None, 0, "word", {"firmware", "kernel"}),
    "physicalWrite64": ("physical-write64", None, 0, "word", {"firmware", "kernel"}),
    "virtualRead8": ("virtual-read8", None, 0, "word", {"user"}),
    "virtualRead64": ("virtual-read64", None, 0, "word", {"user"}),
    "virtualWrite8": ("virtual-write8", None, 0, "word", {"user"}),
    "virtualWrite64": ("virtual-write64", None, 0, "word", {"user"}),
    "readTime": ("read-time", "lemma_exec_read_time", 0, "word", {"firmware"}),
    "setMachineCompare": ("set-machine-compare", "lemma_exec_set_machine_compare", 1, "word", {"firmware"}),
    "forwardSupervisor": ("forward-supervisor", "lemma_exec_forward_supervisor", 1, "word", {"firmware"}),
    "firmwareCall": ("firmware-call", "lemma_exec_firmware_call", 6, "checked", {"kernel"}),
    "syscall": ("syscall", "lemma_exec_syscall", 6, "checked", {"user"}),
    "installSatp": ("install-satp", "lemma_exec_install_satp", 1, "word", {"kernel"}),
    "fenceInstruction": ("fence-instruction", "lemma_exec_fence_instruction", 0, "word", {"kernel"}),
    "enterUser": ("enter-user", "lemma_exec_enter_user", 1, "word", {"kernel"}),
    "waitInterrupt": ("wait-interrupt", "lemma_exec_wait_interrupt", 0, "word", {"kernel"}),
    "readSupervisorPending": ("supervisor-pending", "lemma_exec_supervisor_pending", 0, "word", {"kernel"}),
}
INTEGER_INSTRUCTIONS = set("add addi addiw addw sub subw mul mulh mulhsu mulhu mulw div divu divw divuw rem remu remw remuw and andi or ori xor xori sll slli sllw slliw srl srli srlw srliw sra srai sraw sraiw slt slti sltu sltiu lui auipc ld lw lwu lh lhu lb lbu sd sw sh sb jal jalr beq bne blt bge bltu bgeu j jr ret mv li nop neg negw not seqz snez sltz sgtz sext.w zext.w beqz bnez blez bgez bltz bgtz bgt ble bgtu bleu fence fence.i sfence.vma csrrw csrrs csrrc csrrwi csrrsi csrrci csrr csrw csrs csrc csrwi csrsi csrci rdcycle rdtime rdinstret wfi mret sret ecall".split())
KNOWN_CSRS = {"mstatus", "mie", "mip", "mcause", "mepc", "mtval", "mtvec", "mscratch", "medeleg", "mideleg",
              "mcounteren", "scounteren", "sstatus", "sie", "sip", "scause", "sepc", "stval", "stvec", "sscratch",
              "satp", "pmpcfg0", "pmpaddr0", "pmpaddr1", "pmpaddr2", "pmpaddr3", "pmpaddr4"}
# These integer optimizer intrinsics have no guest runtime and must disappear
# into the audited integer object closure. No memory intrinsic/helper is allowed.
OPTIMIZER_INTRINSICS = {f"llvm.{operation}.i{width}" for operation in ("umin", "umax", "smin", "smax") for width in (8, 32, 64)}
ROLE_EFFECTS = {
    "firmware": set("checked-access physical-read physical-write mmio-read mmio-write io-order machine-state timer-state interrupt-state".split()),
    "kernel": set("checked-access physical-read physical-write mmio-read mmio-write io-order machine-state firmware-call address-space instruction-sync privilege-transition wait-state interrupt-state may-diverge".split()),
    "user": set("checked-access virtual-read virtual-write user-syscall privilege-transition io-order may-diverge".split()),
}
PRIMITIVE_EFFECTS = {
    "_start": "boot/privilege/pmp/delegation", "core0_io_fence": "io-order",
    "lemma_machine_vector": "machine-trap/context", "lemma_supervisor_vector": "supervisor-trap/context",
    "lemma_exec_read_time": "machine-timer-read", "lemma_exec_set_machine_compare": "machine-timer-write",
    "lemma_exec_forward_supervisor": "supervisor-notification", "lemma_exec_firmware_call": "private-firmware-call",
    "lemma_exec_syscall": "user-syscall", "lemma_exec_install_satp": "address-space/invalidation",
    "lemma_exec_fence_instruction": "instruction-synchronization", "lemma_exec_enter_user": "sanitized-context-return",
    "lemma_exec_wait_interrupt": "interrupt-wait", "lemma_machine_fatal": "fatal-diagnostic",
    "lemma_machine_double_fault": "fatal-diagnostic", "lemma_supervisor_fatal": "fatal-diagnostic",
    "lemma_supervisor_double_fault": "fatal-diagnostic",
    "lemma_supervisor_start": "boot-supervisor-entry",
    "lemma_exec_supervisor_pending": "supervisor-notification-read",
}
CONTEXT_LAYOUT = {"bytes": 288, "kernel_resume_base": 0x80500000, "boot_stack_floor": 0x80501000,
                  "pc_offset": 256, "status_offset": 264, "translation_offset": 272, "scratch_offset": 280}
# Actual relocation-free RV64 body, independently inspected and decoded against
# complete caller/U states. These fingerprints certify artifact identity only.
ENTER_USER_SHA256 = "e5e9881a4880bb062e631ba2a400af5bdea00526dbfc298a263de563e61250ca"
SUPERVISOR_RESTORE_SHA256 = "c6a293d9390c5d362c93068d083a5f4419eb56b650cf13753f4fcd7c76ac1792"
GPR_NAMES = "zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6".split()
USER_ATTACKS = {
    "supervisor-csr": ("lemma_user_attack_supervisor_csr", "adversarial-supervisor-csr-read", (0x10002573, 0x00008067)),
    "execute-data": ("lemma_user_attack_execute_data", "adversarial-nx-fetch", (0x000202b7, 0x00028067)),
    "execute-kernel": ("lemma_user_attack_kernel_fetch", "adversarial-kernel-fetch", (0x40100293, 0x01529293, 0x00028067)),
    "execute-misaligned": ("lemma_user_attack_misaligned", "adversarial-illegal-halfword-fetch", (0x000102b7, 0x0022829b, 0x00028067)),
    "halfword-ecall": ("lemma_user_attack_halfword_ecall", "adversarial-halfword-ecall", (0x00000297, 0x01028293, 0x00228293, 0x00028067, 0x00730013, 0)),
    "return-supervisor": ("lemma_user_attack_supervisor_return", "adversarial-supervisor-return", (0x10200073,)),
    "return-machine": ("lemma_user_attack_machine_return", "adversarial-machine-return", (0x30200073,)),
}
INSTRUCTION_CASES = {"halfword-ecall": (18, 0x00000073),
                     "return-supervisor": (0, 0x10200073), "return-machine": (0, 0x30200073)}
USER_ABI_INITIAL_DATA = struct.pack("<2Q", 0, 1)
USER_SYSCALL_WORDS = (0x00050893, 0x00058513, 0x00060593, 0x00068613,
                      0x00070693, 0x00078713, 0x00000073, 0x00008067)
TASK_USER_IMAGES = tuple({"key": key, "id": index, "module": "Lemma.User.Development.Tasks." + module,
                          "source": "Lemma.User.Development.Tasks." + module + ".main", "args": ["u64"],
                          "symbol_prefix": "lemma_user_" + key + "_", "startup_case": "none",
                          "directory": "users/" + key}
                         for index, (key, module) in enumerate((("compute", "Compute"), ("sleeper", "Sleeper"), ("busy", "Busy")), 1))
TASK_FAULT_USER_IMAGES = (*TASK_USER_IMAGES, {
    "key": "fault", "id": 4, "module": "Lemma.User.Development.Tasks.Fault",
    "source": "Lemma.User.Development.Tasks.Fault.main", "args": ["u64"],
    "symbol_prefix": "lemma_user_fault_", "startup_case": "supervisor-csr", "directory": "users/fault"})
MANAGED_POLICY = "lemma-capabilities-v1"
CAPABILITY_USER_IMAGES = tuple({"key": key, "id": index, "module": module, "source": module + ".main", "args": ["u64"],
                               "symbol_prefix": "lemma_user_" + key + "_", "startup_case": "none", "directory": "users/" + key,
                               "boot_role": key}
                              for index, (key, module) in enumerate((("capabilities", "Lemma.User.Development.Capabilities"),
                                  ("peer", "Lemma.User.Development.CapabilitiesPeer"), ("busy", "Lemma.User.Development.Tasks.Busy"),
                                  ("tamper", "Lemma.User.Development.CapabilitiesTamper")), 1))
IPC_POLICY = "lemma-ipc-v1"
IPC_USER_IMAGES = tuple({"key":key,"id":index,"module":module,"source":module+"."+root,"args":["u64"],
                        "symbol_prefix":"lemma_user_"+key+"_","startup_case":"none","directory":"users/"+key,
                        "boot_role":role}
                       for index,(key,module,root,role) in enumerate((
                           ("server","Lemma.User.Development.IPCServer","main","ipc-server"),
                           ("clienta","Lemma.User.Development.IPCClients","clientA","ipc-client-a"),
                           ("clientb","Lemma.User.Development.IPCClients","clientB","ipc-client-b"),
                           ("busy","Lemma.User.Development.Tasks.Busy","main","background-no-grants"),
                           ("fault","Lemma.User.Development.IPCFault","main","ipc-fault-client")),1))
BUFFER_POLICY = "lemma-buffer-service-v1"
SERVICE_USER_IMAGES = tuple({"key":key,"id":index,"module":module,"source":module+".main","args":["u64"],
                            "symbol_prefix":"lemma_user_"+key+"_","startup_case":"none","directory":"users/"+key,
                            "boot_role":role}
                           for index,(key,module,role) in enumerate((
                               ("server","Lemma.Services.Buffer.Server","buffer-server"),
                               ("cli","Lemma.Applications.BufferCLI","buffer-cli"),
                               ("peer","Lemma.Applications.BufferPeer","buffer-peer"),
                               ("busy","Lemma.Applications.CPUBound","background-no-grants")),1))
SERVICE_DEVELOPMENT_USER_IMAGES = (*SERVICE_USER_IMAGES, {
    "key":"fault","id":5,"module":"Lemma.User.Development.BufferFault",
    "source":"Lemma.User.Development.BufferFault.main","args":["u64"],"symbol_prefix":"lemma_user_fault_",
    "startup_case":"none","directory":"users/fault","boot_role":"buffer-fault-client"})
MANAGED_POLICIES = {"capabilities-development":MANAGED_POLICY,"ipc-development":IPC_POLICY,
                    "service-normal":BUFFER_POLICY,"service-development":BUFFER_POLICY}
MANAGED_POLICIES.update({configuration: BUFFER_POLICY for configuration in SERVICE_INSTRUCTION_CONFIGURATIONS})
MANAGED_POLICIES.update({"lemmasim-silicon-power-notebook": "lemma-notebook-v1", "lemmasim-silicon-power-initialize": "lemma-notebook-v1", "silicon-service-development": BUFFER_POLICY, "lemmasim-silicon-full-notebook": "lemma-notebook-v1", "lemmasim-silicon-notebook": "lemma-notebook-v1", "lemmasim-silicon-full-initialize": "lemma-notebook-v1", "lemmasim-silicon-initialize": "lemma-notebook-v1"})
MANAGED_POLICIES.update({"lemmasim-notebook": "lemma-notebook-v1", "lemmasim-initialize": "lemma-notebook-v1", "lemmasim-isolation-development": "lemma-notebook-v1"})
MULTI_USER_CONFIGURATIONS = {"tasks-development": TASK_USER_IMAGES, "tasks-fault-development": TASK_FAULT_USER_IMAGES,
                             "capabilities-development": CAPABILITY_USER_IMAGES, "ipc-development":IPC_USER_IMAGES,
                             "service-normal":SERVICE_USER_IMAGES,"service-development":SERVICE_DEVELOPMENT_USER_IMAGES}
MULTI_USER_CONFIGURATIONS.update({configuration: (*SERVICE_USER_IMAGES, {
    "key": "fault", "id": 5, "module": "Lemma.User.Entry", "source": "Lemma.User.Entry.main", "args": ["u64"],
    "symbol_prefix": "lemma_user_fault_", "startup_case": case, "directory": "users/fault", "boot_role": "buffer-fault-client"})
    for configuration, case in SERVICE_INSTRUCTION_CONFIGURATIONS.items()})


NOTEBOOK_USER_IMAGES = tuple({"key": key, "id": index, "module": module, "source": module + ".main", "args": ["u64"],
                              "symbol_prefix": "lemma_user_" + key + "_", "startup_case": "none", "directory": "users/" + key,
                              "boot_role": role}
                             for index, (key, module, role) in enumerate((("store", "Lemma.Services.Store.Server", "store-server"),
                                 ("notebook", "Lemma.Applications.Notebook", "notebook")), 1))
ARITHMETIC_NOTEBOOK_IMAGES = (*NOTEBOOK_USER_IMAGES, {"key": "arithmetic", "id": 3,
    "module": "Lemma.Services.Arithmetic.Server", "source": "Lemma.Services.Arithmetic.Server.main",
    "args": ["u64"], "symbol_prefix": "lemma_user_arithmetic_", "startup_case": "none",
    "directory": "users/arithmetic", "boot_role": "arithmetic-server"})
NOTEBOOK_ISOLATION_IMAGES = (*NOTEBOOK_USER_IMAGES, {"key": "isolation", "id": 3,
    "module": "Lemma.User.Development.NotebookIsolation", "source": "Lemma.User.Development.NotebookIsolation.main",
    "args": ["u64"], "symbol_prefix": "lemma_user_isolation_", "startup_case": "none",
    "directory": "users/isolation", "boot_role": "notebook-isolation-client"})
MULTI_USER_CONFIGURATIONS.update({"lemmasim-notebook": NOTEBOOK_USER_IMAGES, "lemmasim-initialize": NOTEBOOK_USER_IMAGES,
                                 "lemmasim-isolation-development": NOTEBOOK_ISOLATION_IMAGES})
MULTI_USER_CONFIGURATIONS.update({"lemmasim-silicon-power-notebook": NOTEBOOK_USER_IMAGES, "lemmasim-silicon-power-initialize": NOTEBOOK_USER_IMAGES, "silicon-service-development": SERVICE_DEVELOPMENT_USER_IMAGES,
                                 "lemmasim-silicon-full-notebook": NOTEBOOK_USER_IMAGES, "lemmasim-silicon-notebook": NOTEBOOK_USER_IMAGES, "lemmasim-silicon-full-initialize": NOTEBOOK_USER_IMAGES, "lemmasim-silicon-initialize": NOTEBOOK_USER_IMAGES})
LEMMASIM_CONFIGURATIONS = frozenset({"lemmasim-silicon-power-safety-probe", "lemmasim-silicon-power-probe", "lemmasim-silicon-power-notebook", "lemmasim-silicon-power-initialize", "lemmasim-silicon-devices","lemmasim-silicon-full-notebook", "lemmasim-silicon-notebook", "lemmasim-silicon-full-initialize", "lemmasim-silicon-initialize", "lemmasim-bringup", "lemmasim-notebook", "lemmasim-initialize", "lemmasim-isolation-development"})
LEMMASIM_NOTEBOOK_CONFIGURATIONS = frozenset({"lemmasim-silicon-power-notebook", "lemmasim-silicon-power-initialize", "lemmasim-silicon-full-notebook", "lemmasim-silicon-notebook", "lemmasim-silicon-full-initialize", "lemmasim-silicon-initialize", "lemmasim-notebook", "lemmasim-initialize", "lemmasim-isolation-development"})
POWER_CONFIGURATIONS = frozenset({"lemmasim-silicon-power-safety-probe", "lemmasim-silicon-power-probe", "lemmasim-silicon-power-notebook", "lemmasim-silicon-power-initialize"})

# Explicit software deployment successor, preserving every legacy registry.
MANAGED_POLICIES.update({configuration: "lemma-notebook-arithmetic-v1" for configuration in ARITHMETIC_CONFIGURATIONS})
MULTI_USER_CONFIGURATIONS.update({configuration: ARITHMETIC_NOTEBOOK_IMAGES for configuration in ARITHMETIC_CONFIGURATIONS})
LEMMASIM_CONFIGURATIONS = LEMMASIM_CONFIGURATIONS | frozenset(ARITHMETIC_DEVELOPMENT_CONFIGURATIONS)
LEMMASIM_NOTEBOOK_CONFIGURATIONS = LEMMASIM_NOTEBOOK_CONFIGURATIONS | frozenset(ARITHMETIC_DEVELOPMENT_CONFIGURATIONS)
POWER_CONFIGURATIONS = POWER_CONFIGURATIONS | frozenset(ARITHMETIC_DEVELOPMENT_CONFIGURATIONS)
BLE_CONFIGURATIONS = frozenset({'lemmasim-silicon-ble-link-probe'})
LEMMASIM_CONFIGURATIONS = LEMMASIM_CONFIGURATIONS | BLE_CONFIGURATIONS

def kernel_contract(configuration: str) -> str:
    return "core0-kernel-v0.5" if configuration in BLE_CONFIGURATIONS else "core0-kernel-v0.4" if configuration in POWER_CONFIGURATIONS else "core0-kernel-v0.3" if configuration in LEMMASIM_CONFIGURATIONS else CONTRACTS["kernel"]


def optimizer_intrinsics(unit: dict) -> set[str]:
    # LLVM's saturating unsigned subtraction and funnel shift lower to ordinary
    # RV64 integer code, with no foreign runtime boundary. Only the new profile's
    # genuine store/notebook consumer authorizes these observed optimizations.
    return (OPTIMIZER_INTRINSICS
            | ({"llvm.usub.sat.i64", "llvm.fshl.i64"} if unit.get("configuration") in LEMMASIM_CONFIGURATIONS else set())
            | ({"llvm.bitreverse.i4"} if unit.get("configuration") in BLE_CONFIGURATIONS
               and unit.get("role")=="kernel" else set()))


BLE_HEADER_SHAPES = {
    False: '9948d829801f423a94de257639db303304266aca273b192516426213087b2ecc',
    True: '94965b0dcfc63e3b87df94fcf20867e327125e146682ac51f15ca4a7346c50d5',
}


def validate_ble_header_intrinsic(ir: str, unit: dict, *, optimized: bool,
                                  optimization: str | None = None) -> dict:
    """One actual LLVM20 i4 bit permutation; no general intrinsic admission."""
    intrinsic='llvm.bitreverse.i4'; source='Lemma.Radio.BLE.Link.headerResult'
    selected=unit.get('configuration') in BLE_CONFIGURATIONS and unit.get('role')=='kernel'
    if not selected:
        if '@'+intrinsic+'(' in ir:raise Core0Error('BLE header intrinsic escapes selected kernel')
        return {}
    sources=[re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']) for row in unit['functions']]
    if len(sources)!=len(set(sources)):raise Core0Error('BLE header source inventory duplicates declarations')
    rows=dict(zip(sources,unit['functions'])); row=rows.get(source)
    if row is None or row.get('args')!=['u64']*3 or row.get('effects')!=[]:
        raise Core0Error('BLE header lacks its pure three-word genuine declaration')
    names={value['symbol']:key for key,value in rows.items()}
    body=_ir_definition_body(ir,row['symbol'])
    rebound=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),body)
    normalized=' '.join(line.split(';',1)[0].strip() for line in rebound.splitlines())
    normalized=' '.join(normalized.split())
    transformed=optimized and optimization!='O0'
    digest=hashlib.sha256(normalized.encode()).hexdigest()
    if digest!=BLE_HEADER_SHAPES[transformed]:raise Core0Error('BLE header differs from pinned checked bit-permutation body')
    sites=[line.strip() for line in ir.splitlines() if '@'+intrinsic+'(' in line]
    if transformed:
        if (len(sites)!=2 or sites.count('%mask = call i4 @llvm.bitreverse.i4(i4 %0)')!=1
            or not any(re.fullmatch(r'declare i4 @llvm\.bitreverse\.i4\(i4\)(?: #[0-9]+)?',line) for line in sites)
            or '%mask = call i4 @llvm.bitreverse.i4(i4 %0)' not in body):
            raise Core0Error('BLE intrinsic has an extra site or altered width/signature/owner')
    elif sites:raise Core0Error('BLE intrinsic appears before the selected O2 optimization')
    return {'source':source,'body_sha256':digest,'optimized':transformed,
            'intrinsic':intrinsic if transformed else None,
            'input_mask':3,'output_bits':[2,3],'foreign_runtime':False}


def managed_fields(configuration: str, image: dict | None = None) -> dict:
    if configuration not in MANAGED_POLICIES:
        return {}
    return {"managed_policy": MANAGED_POLICIES[configuration], **({"boot_role": image["boot_role"]} if image is not None else {})}


def validate_managed_provenance(build: dict, provenance: dict, *, configuration: str, images: list[dict]) -> None:
    if configuration in MANAGED_POLICIES:
        selected=image_specs(configuration)
        expected = {"managed_policy": MANAGED_POLICIES[configuration], "boot_roles": {row["key"]: row["boot_role"] for row in selected}}
        if (images != list(selected) or any("boot_role" in record for record in (build, provenance))
                or any(record.get(key) != value for record in (build, provenance) for key, value in expected.items())):
            raise Core0Error("managed policy/boot roles differ from the closed source-selected deployment")
    elif any(key in record for record in (build, provenance) for key in ("managed_policy", "boot_roles", "boot_role")):
        raise Core0Error("managed authority metadata appears outside its closed deployment")


def validate_standalone_managed_provenance(build: dict, provenance: dict, *, configuration: str, image: dict) -> None:
    expected=managed_fields(configuration,image)
    if configuration in MANAGED_POLICIES:
        if any("boot_roles" in record or any(record.get(key)!=value for key,value in expected.items()) for record in (build,provenance)):
            raise Core0Error("independent managed policy/boot role differs from its selected source")
    elif any(key in record for record in (build,provenance) for key in ("managed_policy","boot_role","boot_roles")):
        raise Core0Error("independent managed authority metadata appears outside its selected deployment")


def image_specs(configuration: str) -> tuple[dict, ...]:
    if not isinstance(configuration, str) or configuration not in MULTI_USER_CONFIGURATIONS:
        raise Core0Error("unknown closed multi-image configuration")
    return MULTI_USER_CONFIGURATIONS[configuration]


def image_spec(configuration: str, image_key: str) -> dict:
    matches = [row for row in image_specs(configuration) if row["key"] == image_key]
    if len(matches) != 1:
        raise Core0Error("unknown selected user image")
    return matches[0]


def development_modules(configuration: str, role: str) -> tuple[str, ...]:
    expected = (("Lemma.Kernel.Development.FaultEntry", "Lemma.Kernel.Development.TasksEntry", "Lemma.Kernel.Development.Pressure")
                if (configuration, role) == ("tasks-fault-development", "kernel") else
                ("Lemma.Kernel.Development.CapsEntry", "Lemma.Kernel.Development.CapAlias", "Lemma.Kernel.Development.TasksEntry",
                 "Lemma.Kernel.Development.CapabilityGeneration")
                if (configuration, role) == ("capabilities-development", "kernel") else
                ("Lemma.Kernel.Development.IPCEntry","Lemma.Kernel.Development.TasksEntry")
                if (configuration, role) == ("ipc-development", "kernel") else
                ("Lemma.Platform.Silicon.Development.DeviceEntry", "Lemma.Platform.Silicon.Development.DeviceProbe")
                if (configuration, role) == ("lemmasim-silicon-devices", "kernel") else
                (configuration_modules(configuration)[role],) if development_role(configuration, role) else ())
    if configuration_development_modules(configuration, role) != expected:
        raise Core0Error("selected role Development authority differs from its exact audited module catalog")
    return expected


def validate_image_case_provenance(build: dict, provenance: dict, *, configuration: str, images: list[dict]) -> None:
    if configuration == "tasks-fault-development" or configuration in SERVICE_INSTRUCTION_CONFIGURATIONS:
        expected = {row["key"]: row["startup_case"] for row in image_specs(configuration)}
        if (images != list(image_specs(configuration)) or build.get("user_startup_cases") != expected
                or provenance.get("user_startup_cases") != expected):
            raise Core0Error("mixed-image startup cases are missing or differ from the closed registry")
    elif "user_startup_cases" in build or "user_startup_cases" in provenance:
        raise Core0Error("per-image mixed startup metadata appears outside its selected configuration")


def validate_user_image_catalog(value: object, *, configuration: str | None = None) -> dict:
    """Admit only the ordered Lean deployment catalog for the selected gate."""
    catalog = _object(value, "user image catalog")
    selected = catalog.get("configuration") if configuration is None else configuration
    images = image_specs(selected)
    expected = {"schema_version": 1, "contract_version": "lemma-user-image-catalog-v1",
                "configuration": selected, "stage": "supervisor", "image_count": len(images),
                "images": list(images), **managed_fields(selected)}
    # Exact equality also closes paths, IDs, per-image prefixes and source roots.
    if (type(catalog.get("schema_version")) is not int or type(catalog.get("image_count")) is not int
            or catalog != expected or any(type(row.get("id")) is not int for row in catalog.get("images", []))):
        raise Core0Error("closed user image registry/source/path catalog differs")
    return catalog


def selected_user_image(catalog: object, image_key: str) -> dict:
    catalog = validate_user_image_catalog(catalog)
    matches = [row for row in catalog["images"] if row["key"] == image_key]
    if len(matches) != 1:
        raise Core0Error("unknown selected user image")
    return matches[0]


def machine_frame(source: str, symbol: str) -> int:
    """Account the fixed local storage of an already audited typed primitive."""
    match = re.search(rf"^{re.escape(symbol)}:\n(.*?)^\.size {re.escape(symbol)},", source, re.M | re.S)
    if match is None:
        raise Core0Error(f"missing generated machine primitive body: {symbol}")
    body, writes = match[1], []
    for line in body.splitlines():
        instruction = re.match(r"\s*([a-z][a-z0-9.]*)\s+(.*)$", line)
        if instruction is None:
            continue
        operation, operands = instruction.groups()
        fields = [part.strip() for part in operands.split(",")]
        if fields[0] != "sp" or operation in {"sd", "sw", "sh", "sb", "beq", "bne", "blt", "bge", "bltu", "bgeu", "beqz", "bnez"}:
            continue
        writes.append(line.strip())
    sanctioned = {
        "lemma_exec_enter_user": ["addi sp, sp, -16", "addi sp, sp, 16", "mv sp, a0", "ld sp, 16(sp)"],
        "lemma_machine_vector": ["csrrw sp, mscratch, sp", "addi sp, sp, -288", "mv sp, a1", "ld sp, 16(sp)"],
        "lemma_supervisor_vector": ["csrrw sp, sscratch, sp", "addi sp, sp, -288", "mv sp, a1", "ld sp, 16(sp)"],
    }
    if symbol in sanctioned:
        if writes != sanctioned[symbol]:
            raise Core0Error(f"typed context stack switches differ from the closed symbol inventory: {symbol}")
    elif any(re.fullmatch(r"addi sp, sp, -?[0-9]+", line) is None for line in writes):
        raise Core0Error(f"unaccounted generated stack-pointer write: {symbol}")
    amounts = [int(value) for line in writes if (match := re.fullmatch(r"addi sp, sp, (-?[0-9]+)", line))
               for value in (match[1],)]
    if any(amount % 16 for amount in amounts):
        raise Core0Error("typed primitive stack allocation violates 16-byte alignment")
    return sum(-amount for amount in amounts if amount < 0)


def validate_compiled_stack(machine: str, frames: dict[str, int]) -> None:
    """Reject SP writes which cannot be reconciled with LLVM's fixed frames."""
    current = None
    allocations = {symbol: 0 for symbol in frames}
    for line in machine.splitlines():
        label = re.fullmatch(r"([0-9a-fA-F]+) <([A-Za-z_.$][A-Za-z0-9_.$-]*)>:", line.strip())
        if label:
            # LLVM retains local PC-relative labels inside a function. They
            # are not a new executable function or a new stack allocation.
            if label[2] in frames:
                current = label[2]
            elif not label[2].startswith(".L"):
                current = None
            continue
        instruction = re.match(r"\s*[0-9a-fA-F]+:\s+([a-z][a-z0-9.]*)\s+(.*)$", line)
        if instruction is None:
            continue
        operation, operands = instruction.groups()
        words = [word.strip() for word in operands.split(",")]
        if not words or words[0] != "sp" or operation in {"sd", "sw", "sh", "sb"}:
            continue
        if (current not in frames or operation != "addi" or len(words) != 3 or words[1] != "sp"
                or not re.fullmatch(r"-?(?:0x[0-9a-f]+|[0-9]+)", words[2])):
            raise Core0Error(f"unaccounted compiled stack-pointer write: {line.strip()}")
        amount = int(words[2], 16 if "0x" in words[2] else 10)
        if amount % 16:
            raise Core0Error("compiled stack adjustment violates 16-byte alignment")
        if amount < 0:
            allocations[current] += -amount
    if allocations != frames:
        raise Core0Error("compiled fixed stack allocation differs from LLVM frame metadata")


def weighted_stack_graph(ir: str, frames: dict[str, int], primitive_frames: dict[str, int]) -> dict:
    """Reuse the legacy closure/cycle audit and add closed external frame costs."""
    base = validate_loop_stack_call_graph(ir, frames)
    if any(type(size) is not int or size < 0 or size % 16 for size in frames.values()):
        raise Core0Error("LLVM stack frames must be nonnegative aligned byte counts")
    if re.search(r"\b(?:alloca|llvm\.stacksave|llvm\.stackrestore|invoke|callbr)\b", ir):
        raise Core0Error("dynamic/explicit stack allocation or unsupported call boundary")
    calls = {}
    for symbol in frames:
        body = _ir_definition_body(ir, symbol)
        for line in body.splitlines():
            instruction = re.match(r"^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:(?:tail|musttail|notail)\s+)?call\b", line)
            if instruction and not re.search(r"@[A-Za-z0-9_.$-]+\(", line):
                raise Core0Error("indirect stack call is not statically bounded")
        _defined, _declared, called = parse_definitions_and_calls(body)
        unknown = called - set(frames) - set(primitive_frames)
        if unknown:
            raise Core0Error(f"unaccounted external frame below {symbol}: {sorted(unknown)}")
        calls[symbol] = sorted(called)
    memo = {}
    def longest(symbol):
        if symbol in primitive_frames:
            return primitive_frames[symbol], [symbol]
        if symbol not in memo:
            size, path = max((longest(child) for child in calls[symbol]), default=(0, []), key=lambda row: row[0])
            memo[symbol] = frames[symbol] + size, [symbol, *path]
        return memo[symbol]
    for symbol in sorted(frames):
        longest(symbol)
    return {"compiled_graph": base, "primitive_frames": dict(sorted(primitive_frames.items())),
            "weighted_frame_chains": {name: {"bytes": size, "chain": path} for name, (size, path) in sorted(memo.items())}}


def validate_stack_entries(unit: dict, graph: dict, *, capacities: dict[str, int], vector_bytes: int) -> list[dict]:
    entries = []
    for index, root in enumerate(unit["roots"]):
        role = unit["role"]
        domain, extra = (("machine", vector_bytes) if role == "firmware" else
                         ("user", 0) if role == "user" else ("boot", 0) if index == 0 else ("kernel-trap", vector_bytes))
        chain = graph["weighted_frame_chains"].get(root["symbol"])
        if not isinstance(chain, dict):
            raise Core0Error("source root lacks emitted stack chain")
        total, capacity = chain["bytes"] + extra, capacities[domain]
        if total >= capacity:
            raise Core0Error(f"{root['source']} requires {total} bytes against strict {capacity}-byte {domain} stack")
        entries.append({"source": root["source"], "symbol": root["symbol"], "domain": domain,
                        "compiled_and_primitive_chain_bytes": chain["bytes"], "vector_bytes": extra,
                        "total_bytes": total, "capacity_bytes": capacity, "margin_bytes": capacity - total,
                        "chain": chain["chain"]})
    return entries


def validate_owned_task_stack(layout: dict, unit: dict, pre_ir: str) -> dict:
    if unit.get('configuration') in ('lemmasim-silicon-power-probe','lemmasim-silicon-power-safety-probe','lemmasim-silicon-ble-link-probe'):
        # This selected S-mode probe links the ordinary dispatch boundary but
        # never constructs/enters a User task. Do not claim an allocation test
        # for absent construction; bind the actual boot call graph instead.
        normalized = {re.sub(r'^_private\..*?\.[0-9]+\.', '', row['source']): row['symbol']
                      for row in unit['functions']}
        root = 'Lemma.Platform.LemmaSim.NotebookKernel.siliconPowerProbe'
        expected = {'Lemma.Platform.LemmaVM.ConsoleDevice.initialize14',
            'Lemma.Kernel.BootInfo.validate',
            'Lemma.Platform.LemmaSim.Descriptor.validateSiliconPower',
            'Lemma.Platform.LemmaSim.MachineServices.validateSilicon',
            'Lemma.Platform.LemmaSim.PowerControl.configure',
            'Lemma.Drivers.PLIC.initializePower', 'Lemma.Kernel.Console.record',
            'Lemma.Platform.LemmaSim.PowerControl.step',
            'Lemma.Platform.LemmaSim.NotebookKernel.fatal'}
        if unit['configuration']=='lemmasim-silicon-power-safety-probe':
            root='Lemma.Platform.Silicon.Development.PowerSafety.boot'
            expected={'Lemma.Platform.LemmaVM.ConsoleDevice.initialize14','Lemma.Kernel.BootInfo.validate',
                'Lemma.Platform.LemmaSim.Descriptor.validateSiliconSafety','Lemma.Platform.LemmaSim.MachineServices.validateSilicon',
                'Lemma.Drivers.PowerSafety.initialize','Lemma.Drivers.PowerSafety.resetEpoch','Lemma.Drivers.PowerSafety.arm',
                'Lemma.Kernel.Console.record','Lemma.Platform.Silicon.Development.PowerSafety.waitStep',
                'Lemma.Platform.Silicon.Development.PowerSafety.fatal'}
        elif unit['configuration']=='lemmasim-silicon-ble-link-probe':
            root='Lemma.Platform.Silicon.Development.BLELink.boot'
            expected={'Lemma.Platform.LemmaVM.ConsoleDevice.initialize14','Lemma.Kernel.BootInfo.validate',
                'Lemma.Platform.LemmaSim.Descriptor.validateBinding','Lemma.Platform.LemmaSim.MachineServices.validateSilicon',
                'Lemma.Radio.BLE.Controller.initialize','Lemma.Radio.BLE.Controller.configure',
                'Lemma.Platform.Silicon.Development.BLELink.base',
                'Lemma.Platform.Silicon.Development.BLELink.configureIRQ',
                'Lemma.Platform.Silicon.Development.BLELink.transaction',
                'Lemma.Platform.Silicon.Development.BLELink.waitStep',
                'Lemma.Platform.Silicon.Development.BLELink.fatal'}
        if unit['configuration']=='lemmasim-silicon-ble-link-probe':
            address='Lemma.Platform.Silicon.Development.BLELink.base'
            if address not in normalized or re.fullmatch(r'\s*entry:\s*ret i64 268502528\s*',_ir_definition_body(pre_ir,normalized[address])) is None:
                raise Core0Error('BLE probe base differs from exact controller aperture')
        if root not in normalized or not expected <= normalized.keys():
            raise Core0Error('Power probe genuine boot/policy source closure missing')
        calls = {symbol: parse_definitions_and_calls(_ir_definition_body(pre_ir, symbol))[2]
                 for symbol in normalized.values()}
        if calls[normalized[root]] != {normalized[name] for name in expected}:
            raise Core0Error('Power probe boot has a different direct call closure')
        visited=set(); pending=[normalized[root]]
        while pending:
            symbol=pending.pop()
            if symbol in visited: continue
            visited.add(symbol); pending.extend(calls.get(symbol,set()) - visited)
        forbidden = {'Lemma.Kernel.Process.construct', 'Lemma.Kernel.Process.run',
            'Lemma.Kernel.Loader.load', 'Lemma.Kernel.Loader.allocateStack',
            'Lemma.Kernel.Memory.AddressSpace.create', 'Lemma.Kernel.Memory.Frames.allocate',
            'Lemma.Kernel.Memory.Batch.allocate', 'Lemma.Kernel.Task.capture'}
        if any(normalized.get(name) in visited for name in forbidden):
            raise Core0Error('Power probe reached User construction, allocation or dispatch')
        if (layout['task_kernel_stack_pages'],layout['task_kernel_stack_bytes']) != (4,16384):
            raise Core0Error('Power probe linked dispatch stack layout differs')
        return {'scope':'S-mode device probe; linked User dispatch is unreachable from this boot',
                'owned_task_construction':'not executed or qualified', 'allocated_pages':0,
                'boot_source':root, 'reachable_source_functions':len(visited),
                'linked_dispatch_stack_pages':4, 'linked_dispatch_stack_bytes':16384}
    if unit.get("configuration") in LEMMASIM_CONFIGURATIONS:
        # The selected audit checks the genuinely elaborated construction,
        # registry, validation and cleanup closure for this larger profile.
        from audit_lemmasim_capacity import construction
        report = construction(unit, pre_ir)
        if (layout["task_kernel_stack_pages"], layout["task_kernel_stack_bytes"]) != (4, 16384):
            raise Core0Error("expanded stack source/layout contract differs")
        return report
    if layout.get('task_kernel_stack_pages') == 4:
        from audit_lemmasim_capacity import construction
        report=construction(unit,pre_ir,expanded=False)
        if layout.get('task_kernel_stack_bytes')!=16384:
            raise Core0Error('current four-page owned stack layout differs')
        names=report['source_symbols']
        all_names={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row['symbol'] for row in unit['functions']}
        p='Lemma.Kernel.'
        entry={'tasks-development':p+'Development.TasksEntry.dispatch',
               'tasks-fault-development':p+'Development.FaultEntry.dispatch',
               'capabilities-development':p+'Development.CapsEntry.dispatch',
               'ipc-development':p+'Development.IPCEntry.dispatch',
               'service-normal':p+'ServiceEntry.dispatch','service-development':p+'Development.ServiceEntry.dispatch',
               'silicon-service-development':p+'Development.ServiceEntry.dispatch'}
        entry.update({cfg:p+'Development.ServiceEntry.dispatch' for cfg in SERVICE_INSTRUCTION_CONFIGURATIONS})
        dispatch=entry.get(unit.get('configuration'))
        edges=({dispatch:[p+'Scheduler.dispatch'],p+'Scheduler.dispatch':[p+'Task.capture'],
                p+'Task.capture':[p+'Process.validateFrame'],p+'Task.context':[p+'Process.validateStackAt']}
               if dispatch else {p+'Process.dispatch':[p+'Process.validateFrame']})
        edges[p+'Process.validateFrame']=[p+'Process.validateStackAt']
        required=set(edges)|{callee for callees in edges.values() for callee in callees}
        required|={p+'BootServices.bootServicesFor',p+'Memory.Frames.configure',p+'Memory.Frames.init'}
        if not required<=all_names.keys(): raise Core0Error('four-page stack lacks its checked trap dispatch closure')
        for caller,callees in edges.items():
            if not {all_names[callee] for callee in callees}<=parse_definitions_and_calls(_ir_definition_body(pre_ir,all_names[caller]))[2]:
                raise Core0Error('four-page stack omits a checked trap validation edge')
        boot=_ir_definition_body(pre_ir,all_names[p+'BootServices.bootServicesFor'])
        configurations=re.findall(r'call \{ i64, i64 \} @'+re.escape(all_names[p+'Memory.Frames.configure'])+r'\(([^\n]*)\)',boot)
        if configurations!=['i64 512, i64 32, i64 4']:
            raise Core0Error('ordinary current boot does not select its actual four-page owned stack')
        validate_checked_call_gate(boot,all_names[p+'Memory.Frames.configure'],all_names[p+'Memory.Frames.init'])
        sources={**names,**{name:all_names[name] for name in required}}
        return {'pages':4,'bytes':16384,'usable_bytes':16352,'sentinel_bytes':32,
                'construction':'owned-physically-contiguous-four','sentinels_are_hardware_guards':False,
                'first_handle_offset':2400,'second_handle_offset':2480,
                'third_handle_offset':2488,'fourth_handle_offset':2496,'pages_offset':2504,'base_offset':2512,
                **({'base_owned_task_frames':18,'base_global_task_frames':19}
                   if unit.get('configuration') in SERVICE_CONFIGURATIONS else {'base_owned_task_frames':19}),
                'source_functions':sources}
    """Bind the capacity to genuine reachable construction and cleanup code."""
    by_source = {}
    for row in unit["functions"]:
        source = re.sub(r"^_private\..*?\.[0-9]+\.", "", row["source"])
        by_source[source] = row["symbol"]
    required = {"Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue",
                "Lemma.Kernel.Memory.Frames.allocateContiguous2", "Lemma.Kernel.Loader.allocateStack",
                "Lemma.Kernel.Loader.installStackPair", "Lemma.Kernel.Loader.storedStack", "Lemma.Kernel.Loader.stackPair",
                "Lemma.Kernel.Loader.releaseStackHandle", "Lemma.Kernel.Loader.teardown",
                "Lemma.Kernel.Process.validateFrame", "Lemma.Kernel.Process.validateStack",
                "Lemma.Kernel.Loader.kernelStackHandleOffset", "Lemma.Kernel.Loader.kernelStackSecondHandleOffset"}
    task_dispatch = {"tasks-development": "Lemma.Kernel.Development.TasksEntry.dispatch",
                     "tasks-fault-development": "Lemma.Kernel.Development.FaultEntry.dispatch",
                     "capabilities-development": "Lemma.Kernel.Development.CapsEntry.dispatch",
                     "ipc-development":"Lemma.Kernel.Development.IPCEntry.dispatch",
                     "service-normal":"Lemma.Kernel.ServiceEntry.dispatch",
                     "service-development":"Lemma.Kernel.Development.ServiceEntry.dispatch",
                     "silicon-service-development":"Lemma.Kernel.Development.ServiceEntry.dispatch"}
    task_dispatch.update({configuration: "Lemma.Kernel.Development.ServiceEntry.dispatch"
                          for configuration in SERVICE_INSTRUCTION_CONFIGURATIONS})
    dispatch_edges = ({task_dispatch[unit["configuration"]]: ["Lemma.Kernel.Scheduler.dispatch"],
                       "Lemma.Kernel.Scheduler.dispatch": ["Lemma.Kernel.Task.capture"],
                       "Lemma.Kernel.Task.capture": ["Lemma.Kernel.Process.validateFrame"],
                       "Lemma.Kernel.Task.context": ["Lemma.Kernel.Process.validateStack"]}
                      if unit.get("configuration") in task_dispatch else
                      {"Lemma.Kernel.Process.dispatch": ["Lemma.Kernel.Process.validateFrame"]})
    required.update(dispatch_edges)
    if not required <= set(by_source):
        raise Core0Error("8-KiB stack lacks its genuine pair construction/validation/teardown source closure")
    for source, value in (("Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue", layout["task_kernel_stack_bytes"]),
                          ("Lemma.Kernel.Loader.kernelStackHandleOffset", 2400),
                          ("Lemma.Kernel.Loader.kernelStackSecondHandleOffset", 2480)):
        body = _ir_definition_body(pre_ir, by_source[source])
        if re.fullmatch(r"\s*entry:\s*ret i64 " + str(value) + r"\s*", body) is None:
            raise Core0Error("task-stack source constant differs from its exact emitted UInt64 value")
    for caller, callees in {
        "Lemma.Kernel.Loader.allocateStack": ["Lemma.Kernel.Memory.Frames.allocateContiguous2"],
        "Lemma.Kernel.Loader.installStackPair": ["Lemma.Kernel.Loader.stackPair"],
        "Lemma.Kernel.Loader.teardown": ["Lemma.Kernel.Loader.storedStack", "Lemma.Kernel.Loader.releaseStackHandle"],
        "Lemma.Kernel.Loader.storedStack": ["Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue"],
        "Lemma.Kernel.Process.validateFrame": ["Lemma.Kernel.Process.validateStack"],
        "Lemma.Kernel.Process.validateStack": ["Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue"],
        **dispatch_edges,
    }.items():
        calls = parse_definitions_and_calls(_ir_definition_body(pre_ir, by_source[caller]))[2]
        if not {by_source[callee] for callee in callees} <= calls:
            raise Core0Error("owned task-stack source call chain omits pair construction or validation")
    return {"pages": layout["task_kernel_stack_pages"], "bytes": layout["task_kernel_stack_bytes"],
            "construction": "owned-physically-contiguous-pair", "first_handle_offset": 2400, "second_handle_offset": 2480,
            **({"base_owned_task_frames": 14 + layout["task_kernel_stack_pages"],
                "base_global_task_frames": 15 + layout["task_kernel_stack_pages"]}
               if unit.get("configuration") in SERVICE_CONFIGURATIONS else
               {"base_owned_task_frames": 15 + layout["task_kernel_stack_pages"]}),
            "source_functions": {source: by_source[source] for source in sorted(required)}}


def validate_call_precedes(body: str, before: str, after: str, *,
                          before_arguments: str | None = None, after_arguments: str | None = None) -> dict:
    """Every reachable protected call must follow a particular emitted call.

    This checks the genuine pre-optimization CFG, including alternate paths and
    same-block instruction order. It does not infer successful return status.
    """
    blocks = _structured_ir_blocks(body)
    successors = _structured_successors(blocks)
    if "entry" not in blocks:
        raise Core0Error("ordered source call audit lacks the exact entry block")
    before_pattern = re.compile(r"\bcall\s+[^@\n]*@" + re.escape(before) + r"\(" +
                                (before_arguments + r"\)" if before_arguments is not None else ""))
    after_pattern = re.compile(r"\bcall\s+[^@\n]*@" + re.escape(after) + r"\(" +
                               (after_arguments + r"\)" if after_arguments is not None else ""))
    pending, seen, protected = [("entry", False)], set(), set()
    while pending:
        block, observed = pending.pop()
        if (block, observed) in seen:
            continue
        seen.add((block, observed))
        for index, line in enumerate(blocks[block]):
            if after_pattern.search(line):
                if not observed:
                    raise Core0Error("protected source call has a path before required checked lifecycle call")
                protected.add((block, index))
            if before_pattern.search(line):
                observed = True
        pending.extend((target, observed) for target in successors[block])
    if not protected:
        raise Core0Error("ordered source call audit found no reachable protected call")
    return {"before": before, "after": after, "protected_sites": [list(site) for site in sorted(protected)]}


def validate_checked_call_gate(body: str, checked: str, protected: str, *, component: str = "status", value: int = 0) -> dict:
    """Require an exact checked-result comparison before every protected call.

    The failed comparison branch must not reach the protected operation, and
    removing the successful edge must make every protected site unreachable.
    Only the structured aggregate ABI and literal equality are admitted.
    """
    if component not in {"status", "value"} or type(value) is not int:
        raise Core0Error("unknown checked source gate component/value")
    blocks = _structured_ir_blocks(body)
    successors = _structured_successors(blocks)
    checked_calls = re.findall(r"(%[A-Za-z0-9_.$-]+) = call \{ i64, i64 \} @" + re.escape(checked) + r"\([^\n]*\)", body)
    protected_blocks = {block for block, lines in blocks.items()
                        if any(re.search(r"\bcall\s+[^@\n]*@" + re.escape(protected) + r"\(", line) for line in lines)}
    if not checked_calls or not protected_blocks or "entry" not in blocks:
        raise Core0Error("checked source gate lacks genuine calls/entry")
    gates=[]
    for result in checked_calls:
        extracted = re.findall(r"(%[A-Za-z0-9_.$-]+) = extractvalue \{ i64, i64 \} " + re.escape(result)
                               + r", " + ("0" if component == "status" else "1") + r"$", body, re.M)
        if len(extracted) != 1:
            raise Core0Error("checked source gate lacks its exact aggregate extraction")
        operand=extracted[0];width="i64"
        if component == "status":
            narrowed=re.findall(r"(%[A-Za-z0-9_.$-]+) = trunc i64 " + re.escape(operand) + r" to i8$",body,re.M)
            if len(narrowed)!=1:
                raise Core0Error("checked source gate lacks its exact status narrowing")
            operand=narrowed[0];width="i8"
        comparisons=re.findall(r"(%[A-Za-z0-9_.$-]+) = icmp eq " + width + " " + re.escape(operand) + ", " + str(value) + r"$",body,re.M)
        for comparison in comparisons:
            for block, lines in blocks.items():
                if re.fullmatch(r"br i1 " + re.escape(comparison) + r", label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+",lines[-1]):
                    success,failure=successors[block]
                    reachable={site for site in protected_blocks if _structured_reachable(successors,success,site)}
                    if any(_structured_reachable(successors,failure,site) for site in protected_blocks):
                        raise Core0Error("failed checked source gate can reach protected operation")
                    removed={label:tuple(target for target in targets if (label,target)!=(block,success)) for label,targets in successors.items()}
                    dominated={site for site in reachable if not _structured_reachable(removed,"entry",site)}
                    gates.append({"block":block,"success":success,"failure":failure,"protected_blocks":sorted(dominated)})
    if not protected_blocks <= {site for gate in gates for site in gate["protected_blocks"]}:
        raise Core0Error("protected operation lacks an exact successful checked-result gate")
    validate_call_precedes(body,checked,protected)
    return {"checked":checked,"protected":protected,"component":component,"equals":value,"gates":gates}



def validate_failed_call_gate(body: str, checked: str, protected: str, failed: str,
                              failed_body: str, *, checked_branch_only: bool = False) -> dict:
    """Bind an emitted checked status to the exact nonzero-failure helper.

    Core0 preserves static scalar helpers. Prove this helper's closed Boolean
    body before treating its false edge as the successful checked-result edge.
    This adds no accepted IR shape or status convention to the target compiler.
    """
    exact_failed=(r"\s*entry:\s*%cmp0 = icmp eq i8 %arg0, 0\s*"
                  r"br i1 %cmp0, label %if.then.0, label %if.else.1\s*"
                  r"if.then.0:\s*br label %if.merge.2\s*"
                  r"if.else.1:\s*br label %if.merge.2\s*"
                  r"if.merge.2:\s*%if.result1 = phi i1 \[ 0, %if.then.0 \], \[ 1, %if.else.1 \]\s*"
                  r"ret i1 %if.result1\s*")
    if re.fullmatch(exact_failed,failed_body) is None:
        raise Core0Error("checked source failure helper differs from exact nonzero status")
    variable=r"%[A-Za-z0-9_.$-]+"
    calls=re.findall(r"("+variable+r") = call \{ i64, i64 \} @"+re.escape(checked)+r"\([^\n]*\)",body)
    if len(calls)!=1:
        raise Core0Error("checked helper gate requires one exact checked call")
    extracted=re.findall(r"("+variable+r") = extractvalue \{ i64, i64 \} "+re.escape(calls[0])+r", 0$",body,re.M)
    if len(extracted)!=1:
        raise Core0Error("checked helper gate lacks one exact status extraction")
    narrowed=re.findall(r"("+variable+r") = trunc i64 "+re.escape(extracted[0])+r" to i8$",body,re.M)
    if len(narrowed)!=1:
        raise Core0Error("checked helper gate lacks exact UInt8 status narrowing")
    helpers=re.findall(r"("+variable+r") = call zeroext i1 @"+re.escape(failed)+r"\(i8 zeroext "+re.escape(narrowed[0])+r"\)",body)
    if len(helpers)!=1:
        raise Core0Error("checked helper gate lacks its exact failure helper/status binding")
    comparisons=re.findall(r"("+variable+r") = icmp eq i1 "+re.escape(helpers[0])+r", 1$",body,re.M)
    if len(comparisons)!=1:
        raise Core0Error("checked helper gate lacks exact true-failure comparison")
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    scope=None
    if checked_branch_only:
        origins=[label for label,lines in blocks.items() if any(
            re.search(re.escape(calls[0])+r" = call ",line) for line in lines)]
        if len(origins)!=1:
            raise Core0Error("branch-scoped checked gate lacks one checked origin")
        scope={label for label in blocks if _structured_reachable(successors,origins[0],label)}
    gate=validate_boolean_gate(body,comparisons[0],protected,success_when_true=False,protected_scope=scope)
    if not checked_branch_only:
        validate_call_precedes(body,checked,protected)
    return {"checked":checked,"protected":protected,"failure_helper":failed,
            "component":"status","equals":0,"gate":gate}


def validate_fresh_descriptor_base_call(body: str, checked: str, protected: str,
                                        failed: str | None = None, failed_body: str | None = None) -> dict:
    """Bind a closed stack-helper call to this call's fresh descriptor result.

    This is deliberately restricted to one UInt64 base argument, not a generic
    unchecked-helper allowance. Status success must dominate every helper site.
    """
    variable=r'%[A-Za-z0-9_.$-]+'
    results=re.findall(r'('+variable+r') = call \{ i64, i64 \} @'+re.escape(checked)+r'\([^\n]*\)',body)
    if len(results)!=1:
        raise Core0Error('stack helper lacks one fresh descriptor validation')
    values=re.findall(r'('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(results[0])+r', 1$',body,re.M)
    arguments=re.findall(r'call \{ i64, i64 \} @'+re.escape(protected)+r'\(i64 ('+variable+r'|[0-9]+)\)',body)
    if len(values)!=1 or not arguments or any(argument!=values[0] for argument in arguments):
        raise Core0Error('stack helper does not receive the exact fresh descriptor base')
    if failed is None:
        gate=validate_checked_call_gate(body,checked,protected)
    else:
        if failed_body is None: raise Core0Error('stack helper lacks its closed status predicate')
        gate=validate_failed_call_gate(body,checked,protected,failed,failed_body)
    return {'validated_base':values[0],**gate}


def validate_capability_base_borrow(body: str, checked: str, helper: str,
                                     failed: str, failed_body: str,
                                     readonly_calls: set[str]) -> dict:
    """Closed two-argument capability helper, using this caller's fresh base.

    The complete caller may only invoke the enumerated read-only helpers. This
    rejects scheduling, writes and another descriptor, even on a success path.
    It adds no target primitive or persisted authority cache.
    """
    variable=r'%[A-Za-z0-9_.$-]+'
    calls=re.findall(r'('+variable+r') = call \{ i64, i64 \} @'+re.escape(checked)+r'\(([^\n]*)\)',body)
    if len(calls)!=1 or calls[0][1]!='i64 %arg0':
        raise Core0Error('capability helper lacks one exact caller descriptor validation')
    values=re.findall(r'('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(calls[0][0])+r', 1$',body,re.M)
    arguments=re.findall(r'call \{ i64, i64 \} @'+re.escape(helper)+r'\(([^\n]*)\)',body)
    if len(values)!=1 or arguments!=['i64 %arg0, i64 '+values[0]]:
        raise Core0Error('capability helper does not borrow this exact descriptor/base pair')
    actual=parse_definitions_and_calls(body)[2]
    if not actual <= readonly_calls | {checked,helper} or re.search(r'\b(store|atomicrmw|cmpxchg|fence)\b',body):
        raise Core0Error('capability base borrow has an intervening effect or unapproved helper')
    return {'validated_base':values[0], 'readonly_calls':sorted(actual),
            **validate_failed_call_gate(body,checked,helper,failed,failed_body)}


def _local_checked_result(body: str, symbol: str, arguments: str) -> tuple[str,str]:
    var=r'%[A-Za-z0-9_.$-]+'
    calls=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(symbol)+r'\('+re.escape(arguments)+r'\)',body)
    if len(calls)!=1: raise Core0Error('local borrow lacks one exact checked argument tuple')
    values=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(calls[0])+r', 1$',body,re.M)
    if len(values)!=1: raise Core0Error('local borrow lacks its exact checked value result')
    return calls[0],values[0]


def _local_call_arguments(body: str, symbol: str) -> list[str]:
    return re.findall(r'call \{ i64, i64 \} @'+re.escape(symbol)+r'\(([^\n]*)\)',body)


def _local_closed_calls(body: str, allowed: set[str]) -> None:
    if not parse_definitions_and_calls(body)[2] <= allowed or re.search(r'\b(store|atomicrmw|cmpxchg|fence)\b',body):
        raise Core0Error('local borrow contains an unapproved call or direct effect')


def _local_callers(unit: dict, ir: str, helper: str, allowed: set[str], names: dict[str,str]) -> None:
    observed={source for source,symbol in names.items() if names[helper] in
              parse_definitions_and_calls(_ir_definition_body(ir,symbol))[2]}
    if not observed or not observed <= allowed:
        raise Core0Error('local borrow helper has an unapproved caller or no validated route')


def _local_selected_failed_gate(body: str, checked: str, arguments: str, protected: str,
                                failed: str, failed_body: str) -> dict:
    selected=checked+'__selected_local_audit'
    original='@'+checked+'('+arguments+')'
    if body.count(original)!=1:raise Core0Error('local gate selected call is missing or duplicated')
    rewritten=body.replace(original,'@'+selected+'('+arguments+')')
    report=validate_failed_call_gate(rewritten,selected,protected,failed,failed_body)
    report['checked']=checked;report['checked_arguments']=arguments
    return report


def _local_arithmetic(body: str, constants: dict[str,int]) -> dict[str,object]:
    """Closed scalar operands for this emitted nonzero-literal arithmetic only."""
    var=r'%[A-Za-z0-9_.$-]+';values=_ipc_scalar_operands(body,constants)
    def value(operand):return values.get(operand,int(operand) if operand.isdecimal() else operand)
    for line in body.splitlines():
        m=re.fullmatch(r'\s*('+var+r') = (add|sub|mul|udiv|urem) i64 ([^,]+), ([^ ]+)',line)
        if m:values[m[1]]=(m[2],value(m[3]),value(m[4]));continue
        m=re.fullmatch(r'\s*('+var+r') = zext i32 ('+var+r') to i64',line)
        if m:values[m[1]]=('zext32',m[2]);continue
        m=re.fullmatch(r'\s*('+var+r') = phi i64 \[ ('+var+r'|[0-9]+), %[^ ]+ \], \[ ('+var+r'|[0-9]+), %[^ ]+ \]',line)
        if m:
            second=value(m[3])
            if isinstance(second,tuple) and second[0] in {'udiv','urem'} and type(second[2])is int and second[2]!=0:
                values[m[1]]=second
    return values


LOCAL_BORROW_SHAPES_V1 = {
    # Closed emitted bodies for the four new/refactored local helpers. Names
    # are rebound to their genuine source declarations before hashing, so a
    # different reachability order cannot change authority. This is a narrow
    # pinned lowering-shape audit, in addition to the independent CFG/operand
    # checks below; it is not a claim of general compiler correctness.
    'Lemma.Kernel.Task.findStep': '9670f690a926604dab388501d947d87b6b86e0d5d99792f1430f8efe5dc459a8',
    'Lemma.Kernel.Task.lookupRecord': 'c37a6226e4724171df44737aaef87a59cbd4165048ecdaf86950dbc80628cf1e',
    'Lemma.Kernel.Memory.UserCopy.copyFromUserResult': '76c50b4e2ef51923b87add161f46482645a01a802e40f46aaef9014c2754f1e2',
    'Lemma.Kernel.Memory.UserCopy.copyFromUserReusingReadPage': 'e15e931ce16ea05ad270eccba2179d703a7ea647b705b2760a158f8f0884ade6',
}


def _local_pinned_shapes(ir: str, names: dict[str,str], sources: tuple[str,...]) -> dict:
    reverse={symbol:source for source,symbol in names.items()};result={}
    for source in sources:
        body=_ir_definition_body(ir,names[source])
        rebound=re.sub(r'@([^ (]+)',lambda m:'@'+reverse.get(m[1],m[1]),body)
        digest=hashlib.sha256(' '.join(rebound.split()).encode()).hexdigest()
        if digest!=LOCAL_BORROW_SHAPES_V1[source]:raise Core0Error('local helper differs from its pinned checked lowering shape: '+source)
        result[source]=digest
    return result


def validate_task_capture_borrow(unit: dict, ir: str) -> dict:
    """Closed fresh frame/descriptor/stack borrow in a single trap capture."""
    rows={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r for r in unit['functions']}
    n={s:r['symbol'] for s,r in rows.items()};t='Lemma.Kernel.Task.';p='Lemma.Kernel.Process.'
    a='Lemma.Kernel.Memory.AddressSpace.';x='Lemma.Kernel.Memory.Access.'
    required={t+s for s in ('capture','contextAt','copyStep','lookupRecord','findStep','table','failed','fatal','stride','stateOffset','running','runnable','dying')}
    required|={p+'validateFrame',a+'base',a+'userContextOffset',x+'read64',x+'write64','Lemma.Core0.Memory.Status.iterationStop'}
    # Status is a scalar source constant and may retain its public spelling.
    required.discard('Lemma.Core0.Memory.Status.iterationStop')
    if unit.get('role')!='kernel' or not required<=n.keys():raise Core0Error('task capture borrow lacks its closed kernel inventory')
    for s,args,effects in [(t+'contextAt',['u64']*3,{'checked-access','physical-read','physical-write'}),
                            (t+'lookupRecord',['u64'],{'checked-access','physical-read'}),
                            (t+'copyStep',['u32','u32']+['u64']*5,{'checked-access','physical-read','physical-write'})]:
        if rows[s].get('args')!=args or set(rows[s].get('effects',[]))!=effects:raise Core0Error('task capture helper signature/effects differ')
    _local_callers(unit,ir,t+'contextAt',{t+'capture'},n)
    _local_callers(unit,ir,t+'lookupRecord',{t+'lookup',t+'contextAt'},n)
    body=_ir_definition_body(ir,n[t+'capture']);failed=_ir_definition_body(ir,n[t+'failed'])
    _,actual=_local_checked_result(body,n[p+'validateFrame'],'i64 %arg1')
    _,base=_local_checked_result(body,n[a+'base'],'i64 %arg0')
    _local_closed_calls(body,{n[s] for s in (p+'validateFrame',a+'base',a+'userContextOffset',t+'failed',t+'fatal',t+'copyStep',t+'contextAt')})
    comparisons=re.findall(r'(%[A-Za-z0-9_.$-]+) = icmp eq i64 '+re.escape(actual)+r', %arg0$',body,re.M)
    if len(comparisons)!=1:raise Core0Error('capture substitutes the validated frame descriptor')
    gates=[validate_failed_call_gate(body,n[p+'validateFrame'],n[a+'base'],n[t+'failed'],failed),
           validate_boolean_gate(body,comparisons[0],n[a+'base']),
           validate_failed_call_gate(body,n[a+'base'],n[t+'copyStep'],n[t+'failed'],failed),
           validate_failed_call_gate(body,n[a+'base'],n[t+'contextAt'],n[t+'failed'],failed)]
    if re.fullmatch(r'\s*entry:\s*ret i64 2048\s*',_ir_definition_body(ir,n[a+'userContextOffset'])) is None:
        raise Core0Error('capture saved-context layout differs')
    operands=_ipc_scalar_operands(body,{n[a+'userContextOffset']:2048})
    calls=_local_call_arguments(body,n[t+'contextAt'])
    if len(calls)!=1:raise Core0Error('capture lacks one closed sanitization call')
    args=calls[0].split(', ')
    if len(args)!=3 or args[:2]!=['i64 %arg0','i64 '+base] or operands.get(args[2][4:])!=('add','%arg1',288):
        raise Core0Error('capture does not borrow this fresh descriptor/base/owned stack top')
    loop=_local_call_arguments(body,n[t+'copyStep'])
    var=r'%[A-Za-z0-9_.$-]+'
    if len(loop)!=1 or re.fullmatch(r'i32 signext '+var+r', i32 signext 36, i64 '+var+r', i64 %arg1, i64 '+var+r', i64 0, i64 0',loop[0]) is None:
        raise Core0Error('capture no longer copies exactly the original 36-word frame')
    if operands.get(loop[0].split(', ')[4][4:])!=('add',base,2048):raise Core0Error('capture copy overlaps authority metadata')
    if len(re.findall(r'icmp ule i32 36, 36$',body,re.M))!=1 or len(re.findall(r'icmp ult i32 '+var+r', 36$',body,re.M))!=1:
        raise Core0Error('capture loop lost its exact bounded word count')
    counts=re.findall(r'('+var+r') = icmp eq i64 ('+var+r'), 36$',body,re.M)
    if len(counts)!=1:raise Core0Error('capture lacks its complete-copy publication check')
    gates.append(validate_boolean_gate(body,counts[0][0],n[t+'contextAt']))
    callback=_ir_definition_body(ir,n[t+'copyStep']);_local_closed_calls(callback,{n[s] for s in (x+'read64',x+'write64',t+'failed',t+'fatal')})
    # Preserve one checked source word then one checked saved-context word.
    if len(_local_call_arguments(callback,n[x+'read64']))!=1 or len(_local_call_arguments(callback,n[x+'write64']))!=1:
        raise Core0Error('capture callback changed its one-read/one-write word path')
    gates.append(validate_failed_call_gate(callback,n[x+'read64'],n[x+'write64'],n[t+'failed'],failed))
    operands=_local_arithmetic(callback,{})
    readarg=_local_call_arguments(callback,n[x+'read64'])[0]
    reads=_local_checked_result(callback,n[x+'read64'],readarg)
    writeargs=_local_call_arguments(callback,n[x+'write64'])[0].split(', ')
    index=('mul',('zext32','%arg0'),8)
    if operands.get(readarg[4:])!=('add','%arg3',index) or operands.get(writeargs[0][4:])!=('add','%arg4',index) or writeargs[1]!='i64 '+reads[1]:
        raise Core0Error('capture callback substitutes original frame or disjoint saved word/value')
    helper=_ir_definition_body(ir,n[t+'contextAt']);_local_closed_calls(helper,{n[s] for s in (t+'lookupRecord',t+'failed',t+'fatal',t+'stateOffset',t+'running',a+'userContextOffset',x+'read64',x+'write64')})
    _local_checked_result(helper,n[t+'lookupRecord'],'i64 %arg0')
    values=_ipc_scalar_operands(helper,{n[a+'userContextOffset']:2048,n[t+'stateOffset']:8,n[t+'running']:3})
    writes=[(values.get(arg.split(', ')[0][4:],arg.split(', ')[0][4:]),arg.split(', ')[1]) for arg in _local_call_arguments(helper,n[x+'write64'])]
    saved=('add','%arg1',2048)
    if writes!=[(saved,'i64 0'),(('add',saved,264),'i64 8589934624'),(('add',saved,280),'i64 %arg2')]:
        raise Core0Error('capture sanitization changed its exact disjoint context writes')
    gates.append(validate_failed_call_gate(helper,n[t+'lookupRecord'],n[x+'write64'],n[t+'failed'],failed))
    gates.append(validate_ipc_read_guard(helper,n[x+'read64'],{n[a+'userContextOffset']:2048,n[t+'stateOffset']:8,n[t+'running']:3},
        ('add',_local_checked_result(helper,n[t+'lookupRecord'],'i64 %arg0')[1],8),3,n[x+'write64']))
    translation_args=[arg for arg in _local_call_arguments(helper,n[x+'read64']) if values.get(arg[4:])==('add','%arg1',72)]
    if len(translation_args)!=1:raise Core0Error('capture helper dropped its live translation load')
    _,translation=_local_checked_result(helper,n[x+'read64'],translation_args[0])
    gates.append(validate_ipc_read_guard(helper,n[x+'read64'],{n[a+'userContextOffset']:2048},('add',saved,272),translation,n[x+'write64']))
    for arg in _local_call_arguments(helper,n[x+'read64']):
        gates.append(_local_selected_failed_gate(helper,n[x+'read64'],arg,n[x+'write64'],n[t+'failed'],failed))
    # The live task-row scanner retains state and descriptor checks, including
    # first malformed/failing rows. No cached task pointer is admitted.
    record=_ir_definition_body(ir,n[t+'lookupRecord']);_local_closed_calls(record,{n[s] for s in (t+'table',t+'findStep',t+'failed',t+'fatal',t+'stride')} |
        {symbol for source,symbol in n.items() if source.endswith('Status.iterationStop')})
    if len(_local_call_arguments(record,n[t+'findStep']))!=1 or not re.search(r'i32 signext 8, i64 '+var+r', i64 '+var+r', i64 %arg0, i64 0, i64 0',record):
        raise Core0Error('capture live row lookup lost its eight-row descriptor scan')
    return {'helper':t+'contextAt','copied_words':36,'saved_context_offset':2048,'stack_top_from_original_frame':288,
            'gates':gates,'pinned_shapes':_local_pinned_shapes(ir,n,(t+'findStep',t+'lookupRecord')),'scope':'same nonpreemptible capture; original frame/stack and fresh descriptor checks retained; live row scan after copy'}


def validate_surface_read_page_borrow(unit: dict, ir: str) -> dict:
    """Only the surface metadata path may borrow a checked same-page read alias."""
    rows={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r for r in unit['functions']};n={s:r['symbol'] for s,r in rows.items()}
    d='Lemma.Platform.LemmaSim.DeviceService.';u='Lemma.Kernel.Memory.UserCopy.';x='Lemma.Kernel.Memory.Access.'
    f='Lemma.Kernel.Memory.Frames.resolvePurpose';paper='Lemma.Drivers.Paper.upload'
    required={d+s for s in ('upload','uploadOrdinary','uploadBorrowed','get','fatal')}|{u+s for s in ('copyFromUser','copyFromUserResult','copyFromUserReadPage','copyFromUserReusingReadPage','scratch','validRange','maximumLength','wordsAligned','fromStep','fromWordStep')}|{f,paper,x+'read64'}
    if unit.get('role')!='kernel' or not required<=n.keys():raise Core0Error('surface read-page borrow lacks its closed kernel inventory')
    for source,count in ((u+'copyFromUserReadPage',5),(u+'copyFromUserReusingReadPage',7),(u+'copyFromUserResult',6)):
        if rows[source].get('args')!=['u64']*count or set(rows[source].get('effects',[]))!={'checked-access','physical-read','physical-write'}:
            raise Core0Error('read-page copy helper signature/effects differ')
    _local_callers(unit,ir,d+'uploadBorrowed',{d+'upload'},n)
    _local_callers(unit,ir,u+'copyFromUserReadPage',{d+'uploadBorrowed'},n)
    _local_callers(unit,ir,u+'copyFromUserReusingReadPage',{d+'uploadBorrowed'},n)
    _local_callers(unit,ir,u+'copyFromUserResult',{u+'copyFromUser',u+'copyFromUserReadPage'},n)
    for source,mode in ((u+'copyFromUser',0),(u+'copyFromUserReadPage',1)):
        body=_ir_definition_body(ir,n[source]);_local_closed_calls(body,{n[u+'copyFromUserResult']})
        if _local_call_arguments(body,n[u+'copyFromUserResult'])!=['i64 '+str(mode)+', '+', '.join('i64 %arg'+str(i) for i in range(5))]:
            raise Core0Error('read-page wrapper lost its fixed ordinary/alias result mode')
    result=_ir_definition_body(ir,n[u+'copyFromUserResult'])
    base_checked=u+'checkedBase';lookup=u+'checkedLookupAt'
    if base_checked not in n or lookup not in n:raise Core0Error('read-page producer lacks its original address-space checks')
    _,base=_local_checked_result(result,n[base_checked],'i64 %arg1, i64 %arg2, i64 1')
    _,first_value=_local_checked_result(result,n[lookup],'i64 '+base+', i64 %arg2, i64 1')
    # Both word/byte success branches return this exact first checked leaf when
    # the fixed alias-result wrapper selected mode1. Ordinary mode0 keeps count.
    variable=r'%[A-Za-z0-9_.$-]+'
    modes=re.findall(r'('+variable+r') = icmp eq i64 %arg0, 1$',result,re.M)
    alias_phis=re.findall(r'('+variable+r') = phi i64 \[ '+re.escape(first_value)+r', %[^ ]+ \], \[ ('+variable+r'), %[^ ]+ \]',result)
    if len(modes)!=2 or len(alias_phis)!=2:raise Core0Error('read-page producer substituted the checked first-leaf result')
    validate_checked_call_gate(result,n[base_checked],n[lookup])
    wrapper=_ir_definition_body(ir,n[d+'upload']);_,handle=_local_checked_result(wrapper,n[d+'get'],'i64 24')
    _local_closed_calls(wrapper,{n[d+s] for s in ('get','fatal','uploadOrdinary','uploadBorrowed')})
    if _local_call_arguments(wrapper,n[d+'uploadBorrowed'])!=['i64 %arg0, i64 %arg1, i64 %arg2, i64 '+handle]:
        raise Core0Error('upload lost its fresh scratch handle argument')
    neq=re.findall(r'(%[A-Za-z0-9_.$-]+) = icmp eq i64 '+re.escape(handle)+r', %arg0$',wrapper,re.M)
    if len(neq)!=1:raise Core0Error('upload omitted the descriptor/scratch alias fallback')
    gates=[validate_checked_call_gate(wrapper,n[d+'get'],n[d+'uploadBorrowed']),validate_boolean_gate(wrapper,neq[0],n[d+'uploadBorrowed'],success_when_true=False)]
    body=_ir_definition_body(ir,n[d+'uploadBorrowed']);_,first=_local_checked_result(body,n[u+'copyFromUserReadPage'],'i64 %arg0, i64 %arg1, i64 %arg3, i64 1024, i64 32')
    _,handle=_local_checked_result(body,n[d+'get'],'i64 24')
    arguments=_local_call_arguments(body,n[u+'copyFromUserReusingReadPage'])
    var=r'%[A-Za-z0-9_.$-]+'
    if len(arguments)!=1 or re.fullmatch(re.escape('i64 %arg0, i64 %arg1, i64 '+first+', i64 %arg2, i64 '+handle+', i64 0, i64 ')+var,arguments[0]) is None:
        raise Core0Error('upload does not reuse the exact successful descriptor/read-page alias')
    same=re.findall(r'('+var+r') = icmp eq i64 '+re.escape(handle)+r', %arg3$',body,re.M)
    if len(same)!=1:raise Core0Error('upload lost its second live scratch-handle equality')
    gates.extend([validate_checked_call_gate(body,n[u+'copyFromUserReadPage'],n[u+'copyFromUserReusingReadPage']),
                  validate_checked_call_gate(body,n[d+'get'],n[u+'copyFromUserReusingReadPage']),
                  validate_boolean_gate(body,same[0],n[u+'copyFromUserReusingReadPage'])])
    # Enumerate every call that can reach reuse; paper/DMA work occurs afterward.
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    sites={label for label,lines in blocks.items() if any('@'+n[u+'copyFromUserReusingReadPage']+'(' in line for line in lines)}
    readonly={n[source] for source in (u+'copyFromUserReadPage',u+'copyFromUserReusingReadPage',d+'get',f,x+'read64')}
    for label,lines in blocks.items():
        if any(_structured_reachable(successors,label,site) for site in sites):
            _local_closed_calls('\n'.join(lines),readonly)
    reuse=_ir_definition_body(ir,n[u+'copyFromUserReusingReadPage'])
    allowed={n[source] for source in (u+'copyFromUser',u+'scratch',u+'validRange',u+'maximumLength',u+'wordsAligned',u+'fromStep',u+'fromWordStep')}
    allowed|={symbol for source,symbol in n.items() if source.startswith('Lemma.User.ABI.')}
    _local_closed_calls(reuse,allowed)
    for callback in (u+'fromStep',u+'fromWordStep'):
        gates.append(validate_checked_call_gate(reuse,n[u+'scratch'],n[callback]))
    if len(re.findall(r'udiv i64 %arg1, 4096$',reuse,re.M))!=1 or len(re.findall(r'udiv i64 %arg3, 4096$',reuse,re.M))!=1:
        raise Core0Error('read-page reuse changed its exact page equality')
    quotient=re.findall(r'('+var+r') = phi i64 \[ 0, %[^ ]+ \], \[ ('+var+r'), %[^ ]+ \]',reuse)
    divs=dict(re.findall(r'('+var+r') = udiv i64 (%arg[13]), 4096$',reuse,re.M))
    pages={divs[v]:result for result,v in quotient if v in divs}
    pagecmp=re.findall(r'('+var+r') = icmp eq i64 '+re.escape(pages.get('%arg1','NO_PAGE'))+', '+re.escape(pages.get('%arg3','NO_PAGE'))+r'$',reuse,re.M)
    remaining=re.findall(r'('+var+r') = sub i64 4096, ('+var+r')$',reuse,re.M)
    remainder=set(re.findall(r'('+var+r') = urem i64 %arg3, 4096$',reuse,re.M))
    remainder_phis=[result for result,v in re.findall(r'('+var+r') = phi i64 \[ %arg3, %[^ ]+ \], \[ ('+var+r'), %[^ ]+ \]',reuse) if v in remainder]
    bounds=[result for result,right in re.findall(r'('+var+r') = icmp ule i64 %arg6, ('+var+r')$',reuse,re.M) if any(address==right and rem in remainder_phis for address,rem in remaining)]
    if len(pagecmp)!=1 or len(bounds)!=1:raise Core0Error('read-page reuse lost its exact whole-span page bound')
    for callback in (u+'fromStep',u+'fromWordStep'):
        gates.extend([validate_boolean_gate(reuse,pagecmp[0],n[callback]),validate_boolean_gate(reuse,bounds[0],n[callback])])
    operands=_local_arithmetic(reuse,{})
    source=('add',('sub','%arg2',('urem','%arg1',4096)),('urem','%arg3',4096))
    _,destination=_local_checked_result(reuse,n[u+'scratch'],'i64 %arg4, i64 %arg5, i64 %arg6')
    for callback in (u+'fromStep',u+'fromWordStep'):
        args=_local_call_arguments(reuse,n[callback])
        if len(args)!=1:raise Core0Error('read-page reuse changed the bounded copy callback count')
        fields=args[0].split(', ')
        if len(fields)!=7 or operands.get(fields[3][4:])!=source or fields[4]!='i64 0' or fields[5]!='i64 '+destination or fields[6]!='i64 %arg6':
            raise Core0Error('read-page reuse substituted checked page arithmetic or scratch span')
    if _local_call_arguments(reuse,n[u+'copyFromUser'])!=['i64 %arg0, i64 %arg3, i64 %arg4, i64 %arg5, i64 %arg6']*2:
        raise Core0Error('read-page fallback lost complete ordinary validation')
    return {'helper':u+'copyFromUserReusingReadPage','metadata_bytes':32,'metadata_scratch_offset':1024,'page_bytes':4096,
            'gates':gates,'pinned_shapes':_local_pinned_shapes(ir,n,(u+'copyFromUserResult',u+'copyFromUserReusingReadPage')),'scope':'same nonpreemptible surface upload; exact checked alias, distinct descriptor scratch, freshly owned destination; ordinary path outside checked page'}


def validate_capability_header_helpers(unit: dict, pre_ir: str) -> dict:
    """Keep the private same-Action header helper closed at every compiled use."""
    rows={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row for row in unit['functions']}
    names={source:row['symbol'] for source,row in rows.items()}
    c='Lemma.Kernel.Capability.';o='Lemma.Kernel.Objects.'
    a='Lemma.Kernel.Memory.AddressSpace.base';v='Lemma.User.CapabilityABI.invalidHandle'
    helper=c+'headerAt';callers={c+'header',c+'managed'}
    required={helper,*callers,a,v,c+'failed',o+'get',o+'registryDescriptor',c+'headerOffset',
              c+'zeroHeaderStep',c+'fatal',c+'active',c+'magic',c+'constructing',c+'capacity',o+'registryCapacity'}
    if unit.get('role')!='kernel' or not required <= names.keys():
        raise Core0Error('capability header helper lacks its closed kernel source inventory')
    if rows[helper].get('args')!=['u64','u64'] or set(rows[helper].get('effects',[]))!={'checked-access','physical-read'}:
        raise Core0Error('capability header helper is not a read-only descriptor/base Action')
    body=_ir_definition_body(pre_ir,names[helper])
    if not re.search(r'^define \{ i64, i64 \} @'+re.escape(names[helper])+r'\(i64 %arg0, i64 %arg1\) nounwind noinline "disable-tail-calls"="true" \{',pre_ir,re.M):
        raise Core0Error('capability header helper emitted signature differs')
    constants={names[c+'headerOffset']:2560,names[c+'magic']:0x31504143414d454c,
               names[c+'active']:1,names[c+'constructing']:2,names[c+'capacity']:16,names[o+'registryCapacity']:8}
    for symbol,value in constants.items():
        if re.fullmatch(r'\s*entry:\s*ret i64 '+str(value)+r'\s*',_ir_definition_body(pre_ir,symbol)) is None:
            raise Core0Error('capability helper scalar metadata constant differs')
    operands=_ipc_scalar_operands(body,constants)
    addresses=[operands.get(operand,operand) for operand in re.findall(
        r'call \{ i64, i64 \} @'+re.escape(names[o+'get'])+r'\(i64 ([^\n)]+)\)',body)]
    root=('add','%arg1',2560)
    if addresses!=[root,*[('add',root,offset) for offset in range(8,64,8)]]:
        raise Core0Error('capability helper changed its eight exact live header fields')
    if len(re.findall(r'call \{ i64, i64 \} @'+re.escape(names[o+'registryDescriptor'])+r'\(',body))!=1:
        raise Core0Error('capability helper dropped its live registered descriptor check')
    if not parse_definitions_and_calls(body)[2] <= {names[source] for source in required-{a,*callers,c+'zeroHeaderStep',helper}}:
        raise Core0Error('capability header helper has an unapproved effect or call')
    failed_body=_ir_definition_body(pre_ir,names[c+'failed']);observed=set();gates=[]
    for source,symbol in names.items():
        caller=_ir_definition_body(pre_ir,symbol)
        if names[helper] not in parse_definitions_and_calls(caller)[2]: continue
        if source not in callers: raise Core0Error('capability header helper has an unapproved caller')
        observed.add(source)
        allowed=({v,c+'failed'} if source==c+'header' else
                 {c+'failed',o+'get',c+'headerOffset',c+'zeroHeaderStep',c+'fatal',c+'active'})
        gates.append({'source':source,**validate_capability_base_borrow(caller,names[a],names[helper],names[c+'failed'],failed_body,{names[item] for item in allowed})})
    if observed!=callers: raise Core0Error('capability header helper lacks both validated entry routes')
    return {'helper':helper,'borrowed_fields':['caller_descriptor','fresh_checked_base'],
            'header_read_offsets':list(range(0,64,8)), 'checked_cfg_gates':gates,
            'scope':'same nonpreemptible Action; no writes, scheduling or cross-entry cache'}


def validate_fresh_descriptor_helpers(unit: dict, pre_ir: str) -> dict:
    """Closed kernel-only helper inventory for within-call stack validation."""
    names={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row['symbol'] for row in unit['functions']}
    p='Lemma.Kernel.'
    base=p+'Memory.AddressSpace.base'
    process=p+'Process.validateStackAt';loader=p+'Loader.validateExpandedStackAt'
    allowed={process:{p+'Process.validateStack',p+'Process.validateFrame',p+'Task.context',p+'Task.savedContext'},
             loader:{p+'Loader.validateExpandedStack',process}}
    required={base,process,loader,p+'Process.failed'}
    required|={p+'Memory.Access.read64',p+'Loader.kernelStackPagesOffset'}
    if not required<=names.keys(): raise Core0Error('fresh stack helper closure is missing')
    if unit.get('role')!='kernel': raise Core0Error('stack helper requires the kernel role')
    by_source={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row for row in unit['functions']}
    for helper in (process,loader):
        if by_source[helper].get('args')!=['u64'] or set(by_source[helper].get('effects',[]))!={'checked-access','physical-read'}:
            raise Core0Error('stack helper signature differs from its single checked base')
        if not re.search(r'^define \{ i64, i64 \} @'+re.escape(names[helper])+r'\(i64 %arg0\) nounwind noinline "disable-tail-calls"="true" \{',pre_ir,re.M):
            raise Core0Error('stack helper emitted signature is not one checked base')
    callers={helper:set() for helper in allowed};gates=[]
    for source,symbol in names.items():
        body=_ir_definition_body(pre_ir,symbol)
        called=parse_definitions_and_calls(body)[2]
        for helper in allowed:
            if names[helper] not in called: continue
            if source not in allowed[helper]: raise Core0Error('stack helper has an unapproved caller')
            callers[helper].add(source)
            if source==process and helper==loader:
                arguments=re.findall(r'call \{ i64, i64 \} @'+re.escape(names[loader])+r'\(([^\n]*)\)',body)
                if arguments!=['i64 %arg0']: raise Core0Error('expanded stack helper lost the current validated base')
                # Only the exact four-page branch may enter the four-page helper.
                comparisons=re.findall(r'(%[A-Za-z0-9_.$-]+) = icmp eq i64 (%[A-Za-z0-9_.$-]+), 4$',body,re.M)
                if len(comparisons)!=1: raise Core0Error('expanded stack helper lacks its exact page-count branch')
                variable=r'%[A-Za-z0-9_.$-]+'
                offsets=re.findall(r'('+variable+r') = call i64 @'+re.escape(names[p+'Loader.kernelStackPagesOffset'])+r'\(\)',body)
                address=re.findall(r'('+variable+r') = add i64 %arg0, '+re.escape(offsets[0] if len(offsets)==1 else '<missing>')+r'$',body,re.M)
                reads=re.findall(r'('+variable+r') = call \{ i64, i64 \} @'+re.escape(names[p+'Memory.Access.read64'])+r'\(i64 '+re.escape(address[0] if len(address)==1 else '<missing>')+r'\)',body)
                values=re.findall(r'('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(reads[0] if len(reads)==1 else '<missing>')+r', 1$',body,re.M)
                if len(values)!=1 or values[0]!=comparisons[0][1]:
                    raise Core0Error('expanded stack helper page branch is not the actual descriptor field')
                if re.fullmatch(r'\s*entry:\s*ret i64 2504\s*',_ir_definition_body(pre_ir,names[p+'Loader.kernelStackPagesOffset'])) is None:
                    raise Core0Error('expanded stack helper page field moved')
                gates.append({'source':source,**validate_boolean_gate(body,comparisons[0][0],names[loader])})
            else:
                failed=None if source==p+'Loader.validateExpandedStack' else p+('Task.failed' if source.startswith(p+'Task.') else 'Process.failed')
                if failed is not None and failed not in names: raise Core0Error('fresh stack caller lacks its failure predicate')
                gates.append({'source':source,**validate_fresh_descriptor_base_call(body,names[base],names[helper],
                    None if failed is None else names[failed],None if failed is None else _ir_definition_body(pre_ir,names[failed]))})
    if not callers[process] or callers[loader]!={process} and callers[loader]!={process,p+'Loader.validateExpandedStack'}:
        raise Core0Error('fresh stack helper has no complete validated entry route')
    return {'scope':'closed kernel stack helpers; fresh base shared only within a single call',
            'callers':{helper:sorted(values) for helper,values in callers.items()},'gates':gates}


def validate_boolean_gate(body: str, comparison: str, protected: str, *, success_when_true: bool = True,
                          protected_scope: set[str] | None = None) -> dict:
    """Require the true edge of one emitted predicate before protected calls."""
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    if "entry" not in blocks:
        raise Core0Error("boolean source gate lacks its exact entry block")
    branches=[block for block,lines in blocks.items() if re.fullmatch(
        r"br i1 "+re.escape(comparison)+r", label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+",lines[-1])]
    sites={block for block,lines in blocks.items() if any(re.search(
        r"\bcall\s+[^@\n]*@"+re.escape(protected)+r"\(",line) for line in lines)}
    if protected_scope is not None:
        sites &= protected_scope
    if len(branches)!=1 or not sites:
        raise Core0Error("boolean source gate lacks one branch/protected operation")
    block=branches[0];success,failure=successors[block]
    if not success_when_true:
        success,failure=failure,success
    removed={label:tuple(target for target in targets if (label,target)!=(block,success))
             for label,targets in successors.items()}
    if any(_structured_reachable(successors,failure,site) or
           _structured_reachable(removed,"entry",site) or
           not _structured_reachable(successors,success,site) for site in sites):
        raise Core0Error("protected operation bypasses the exact successful boolean gate")
    return {"comparison":comparison,"success_when_true":success_when_true,"block":block,"success":success,"failure":failure,"protected_blocks":sorted(sites)}



def validate_h_endpoint_budget(body: str, by_source: dict[str,str], *, reply: bool = False,
                               pre_ir: str | None = None) -> dict:
    """Bind the compiled bounded count/limit to preallocation CFG guards."""
    objects="Lemma.Kernel.Objects.";var=r"%[A-Za-z0-9_.$-]+";label=r"[A-Za-z0-9_.$-]+"
    counter="replyCountStep" if reply else "endpointCountStep"
    capacity="replyCapacity" if reply else "endpointCapacity"
    callback=by_source[objects+counter]
    folds=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(callback)+
        r"\(i32 signext ("+var+r"), i32 signext 16, i64 ("+var+r"), i64 ("+var+r"), i64 0, i64 0, i64 0\)",body)
    if len(folds)!=1:
        raise Core0Error("endpoint budget lacks one exact 16-row count callback")
    result,index,accumulator,base=folds[0]
    values=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(result)+r", 1$",body,re.M)
    statuses=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(result)+r", 0$",body,re.M)
    if len(values)!=1 or len(statuses)!=1:
        raise Core0Error("endpoint count callback lacks checked status/value extraction")
    narrowed=re.findall(r"("+var+r") = trunc i64 "+re.escape(statuses[0])+r" to i8$",body,re.M)
    if len(narrowed)!=1:
        raise Core0Error("endpoint count callback lacks UInt8 status")
    headers=re.findall(re.escape(index)+r" = phi i32 \[ 0, %("+label+r") \], \[ ("+var+r"), %("+label+r") \]",body)
    if len(headers)!=1:
        raise Core0Error("endpoint count index lacks exact zero-based bounded loop")
    preheader,next_index,latch=headers[0]
    if (re.search(re.escape(accumulator)+r" = phi i64 \[ 0, %"+re.escape(preheader)+r" \], \[ "+re.escape(values[0])+r", %"+re.escape(latch)+r" \]",body) is None
        or re.search(re.escape(next_index)+r" = add i32 "+re.escape(index)+r", 1$",body,re.M) is None
        or re.search(r"icmp ult i32 "+re.escape(index)+r", 16$",body,re.M) is None):
        raise Core0Error("endpoint count accumulator/increment/bound differs")
    outcomes=re.findall(r"("+var+r") = phi i64 \[ 0, %("+label+r") \], \[ "+re.escape(values[0])+r", %("+label+r") \], \[ "+re.escape(accumulator)+r", %("+label+r") \]",body)
    if len(outcomes)!=1:
        raise Core0Error("endpoint count lacks exact checked fold outcome")
    value,exhausted,stopped,done=outcomes[0]
    outcome_status=re.findall(r"("+var+r") = phi i8 \[ 9, %"+re.escape(exhausted)+r" \], \[ "+re.escape(narrowed[0])+r", %"+re.escape(stopped)+r" \], \[ 0, %"+re.escape(done)+r" \]",body)
    runtime = by_source.get(objects+("runtimeReplyCapacity" if reply else "runtimeEndpointCapacity"))
    arithmetic = objects+"arithmeticEndpointCapacity" in by_source
    runtime_calls = [] if runtime is None else re.findall(
        r"("+var+r") = call \{ i64, i64 \} @"+re.escape(runtime)+r"\(\)",body)
    if runtime_calls:
        if len(runtime_calls)!=1 or pre_ir is None:
            raise Core0Error("versioned endpoint capacity lacks its checked source closure")
        limits=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(runtime_calls[0])+r", 1$",body,re.M)
        if len(limits)!=1:
            raise Core0Error("versioned endpoint capacity lacks its exact returned value")
    else:
        limits=re.findall(r"("+var+r") = call i64 @"+re.escape(by_source[objects+capacity])+r"\(\)",body)
    comparisons=[]
    for limit in limits:
        comparisons.extend(re.findall(r"("+var+r") = icmp ult i64 "+re.escape(value)+r", "+re.escape(limit)+r"$",body,re.M))
    if len(outcome_status)!=1 or len(comparisons)!=1:
        raise Core0Error("endpoint preallocation guard differs from count < exact capacity")
    failed=re.findall(r"("+var+r") = call zeroext i1 @"+re.escape(by_source[objects+"failed"])+r"\(i8 zeroext "+re.escape(outcome_status[0])+r"\)",body)
    status_comparisons=[]
    for status in failed:
        status_comparisons.extend(re.findall(r"("+var+r") = icmp eq i1 "+re.escape(status)+r", 1$",body,re.M))
    if len(status_comparisons)!=1:
        raise Core0Error("endpoint budget lacks the exact checked fold-status guard")
    gates=[]
    protected_sources=[objects+"freeObjectStep"] if reply else [objects+"freeObjectStep","Lemma.Kernel.Memory.Frames.allocate"]
    for protected in protected_sources:
        gates.append({"protected_source":protected,"limit":validate_boolean_gate(body,comparisons[0],by_source[protected]),
                      "status":validate_boolean_gate(body,status_comparisons[0],by_source[protected],success_when_true=False)})
        if runtime_calls:
            gates[-1]["capacity_status"]=validate_failed_call_gate(body,runtime,by_source[protected],
                by_source[objects+"failed"],_ir_definition_body(pre_ir,by_source[objects+"failed"]))
    return {"capacity":({"version1":8,"version2":8,"version3":7} if reply else {"version1":4,"version2":5,"version3":6}) if arithmetic and runtime_calls else 8 if reply else {"version1":4,"version2":5} if runtime_calls else 4,
            "capacity_source":objects+("runtimeReplyCapacity" if reply else "runtimeEndpointCapacity") if runtime_calls else objects+capacity,
            "counted_rows":16,"counter_source":objects+counter,"base_operand":base,
            "count_result":value,"checked_outcome_status":outcome_status[0],"preallocation_gates":gates}


def _object_scalar_cases(body: str, constants: dict[str,int], *, header: bool,
                         version_only: bool = False, encoded: bool = False, arithmetic: bool = False, replies: bool = False) -> list[dict]:
    """Observe the closed equality/phi CFG over its complete input partitions.

    Version comparisons may only distinguish1/2; header-limit comparisons may
    only distinguish0/5. There is no memory, arithmetic, foreign call or other
    predicate in this admitted observer scope. Thus these partitions cover all
    u64 inputs, rather than treating a sampled scalar corpus as equivalence.
    """
    blocks=_structured_ir_blocks(body)
    variable=r'%[A-Za-z0-9_.$-]+'
    observations=[];visited=set()
    for version in ((0,1,2,3,4,(1<<64)-1) if arithmetic else (0,1,2,3,(1<<64)-1)):
      for limit in ((0,4,5,6,(1<<64)-1) if header and not version_only else (0,)):
        values={'%arg0':version,'%arg1':limit};label='entry';previous=None
        def operand(value):
            if value in values:return values[value]
            if re.fullmatch(r'[0-9]+',value) and int(value) in ({0,1,2,3,4,5,6,7,8} if arithmetic else {0,1,2,4,5}):return int(value)
            raise Core0Error('Objects scalar guard has an unknown operand')
        for _ in range(64):
            if label not in blocks:raise Core0Error('Objects scalar guard has an unknown block')
            visited.add(label);next_label=None;returned=None
            for line in blocks[label]:
                match=re.fullmatch('('+variable+r') = icmp eq i64 (%arg[01]), ('+variable+r'|[0-9]+)',line)
                if match:
                    result,arg,right=match.groups();bound=operand(right)
                    if (arg=='%arg0' and bound not in ({1,2,3} if arithmetic else {1,2})) or (arg=='%arg1' and (not header or version_only or bound not in ({0,5,6} if arithmetic else {0,5}))):
                        raise Core0Error('Objects scalar guard comparison leaves its closed partitions')
                    values[result]=int(values[arg]==bound);continue
                match=re.fullmatch('('+variable+r') = call i64 @([A-Za-z0-9_.$-]+)\(\)',line)
                if match:
                    result,callee=match.groups()
                    if callee not in constants:raise Core0Error('Objects scalar guard has an unreviewed call')
                    values[result]=constants[callee];continue
                match=re.fullmatch('('+variable+r') = phi (i1|i64) (.+)',line)
                if match:
                    result,ty,incoming=match.groups()
                    pairs=re.findall(r'\[ ('+variable+r'|[0-9]+), %([A-Za-z0-9_.$-]+) \]',incoming)
                    if ', '.join('[ '+v+', %'+p+' ]' for v,p in pairs)!=incoming:
                        raise Core0Error('Objects scalar phi has an unsupported form')
                    selected=[v for v,p in pairs if p==previous]
                    if len(selected)!=1:raise Core0Error('Objects scalar phi has no exact predecessor')
                    value=operand(selected[0])
                    if ty=='i1' and value not in {0,1}:raise Core0Error('Objects scalar Boolean is malformed')
                    values[result]=value;continue
                match=re.fullmatch(r'br i1 ('+variable+r'), label %([A-Za-z0-9_.$-]+), label %([A-Za-z0-9_.$-]+)',line)
                if match:
                    condition,yes,no=match.groups();value=operand(condition)
                    if value not in {0,1}:raise Core0Error('Objects scalar branch is malformed')
                    next_label=yes if value else no;continue
                match=re.fullmatch(r'br label %([A-Za-z0-9_.$-]+)',line)
                if match:next_label=match[1];continue
                match=re.fullmatch(r'ret '+('i1' if header else 'i64')+' ('+variable+r'|[0-9]+)',line)
                if match:returned=operand(match[1]);continue
                raise Core0Error('Objects scalar guard has an unsupported instruction')
            if returned is not None:
                expected=(int(version in ({1,2,3} if arithmetic else {1,2})) if version_only else int((version,limit) in ({(1,0),(2,5),(3,6)} if arithmetic else {(1,0),(2,5)}))) if header else (5 if version==2 else 6 if arithmetic and version==3 else 0) if encoded else (8 if version in {1,2} else 7 if version==3 else 0) if replies else 4 if version==1 else 5 if version==2 else 6 if arithmetic and version==3 else 0
                if returned!=expected:raise Core0Error('Objects scalar version/header quota semantics differ')
                observations.append({'version':version,'encoded_limit':limit if header else None,'result':returned});break
            if next_label is None:raise Core0Error('Objects scalar guard has no terminator')
            previous,label=label,next_label
        else:raise Core0Error('Objects scalar guard exceeds its bounded acyclic scope')
    if visited!=set(blocks):raise Core0Error('Objects scalar guard has an unobserved block')
    return observations


def _object_checked_return(body: str, fatal: str, expected_value: str) -> str:
    """Trace the paired return: one exact success, otherwise the fatal pair."""
    var=r'%[A-Za-z0-9_.$-]+'
    assignments={m[1]:m[2] for m in re.finditer(r'^\s*('+var+r') = (.+)$',body,re.M)}
    returned=re.findall(r'ret \{ i64, i64 \} ('+var+r')$',body,re.M)
    if len(returned)!=1:raise Core0Error('Objects checked return ABI differs')
    complete=re.fullmatch(r'insertvalue \{ i64, i64 \} ('+var+r'), i64 ('+var+r'), 1',assignments.get(returned[0],''))
    partial=None if complete is None else re.fullmatch(r'insertvalue \{ i64, i64 \} poison, i64 ('+var+r'), 0',assignments.get(complete[1],''))
    widened=None if partial is None else re.fullmatch(r'zext i8 ('+var+r') to i64',assignments.get(partial[1],''))
    if widened is None:raise Core0Error('Objects checked status return provenance differs')
    pending=[(widened[1],complete[2])];visited=set();leaves=[]
    while pending:
        status,value=pending.pop()
        if (status,value) in visited:continue
        visited.add((status,value))
        phi_s=re.fullmatch(r'phi i8 (.+)',assignments.get(status,''))
        phi_v=re.fullmatch(r'phi i64 (.+)',assignments.get(value,''))
        if phi_s and phi_v:
            def pairs(text):
                rows=re.findall(r'\[ ('+var+r'|[0-9]+), %([A-Za-z0-9_.$-]+) \]',text)
                if ', '.join('[ '+v+', %'+p+' ]' for v,p in rows)!=text or len({p for _,p in rows})!=len(rows):
                    raise Core0Error('Objects checked return phi differs')
                return {p:v for v,p in rows}
            statuses,values=pairs(phi_s[1]),pairs(phi_v[1])
            if statuses.keys()!=values.keys():raise Core0Error('Objects checked pair lost predecessor binding')
            for origin,s in statuses.items():
                v=values[origin]
                if s=='0':
                    if v!=expected_value:raise Core0Error('Objects success returns an unvalidated value')
                    leaves.append(origin)
                elif s.startswith('%') and v.startswith('%'):pending.append((s,v))
                else:raise Core0Error('Objects malformed path fabricated a checked return')
            continue
        narrowed=re.fullmatch(r'trunc i64 ('+var+r') to i8',assignments.get(status,''))
        extracted=None if narrowed is None else re.fullmatch(r'extractvalue \{ i64, i64 \} ('+var+r'), 0',assignments.get(narrowed[1],''))
        got_value=re.fullmatch(r'extractvalue \{ i64, i64 \} ('+var+r'), 1',assignments.get(value,''))
        if extracted is None or got_value is None or extracted[1]!=got_value[1] or assignments.get(extracted[1])!='call { i64, i64 } @'+fatal+'()':
            raise Core0Error('Objects failed checked pair is not its declared fatal result')
    if len(leaves)!=1:raise Core0Error('Objects checked return lacks one exact success leaf')
    return leaves[0]


def _object_invalid_init_path(body: str, start: str, invalid: str) -> None:
    """Follow the one rejected-version path; it returns(16,0), without effects."""
    blocks=_structured_ir_blocks(body);values={};previous=None;label=start
    var=r'%[A-Za-z0-9_.$-]+'
    def value(operand):
        if operand.isdecimal():return int(operand)
        if operand in values:return values[operand]
        raise Core0Error('Objects rejected initializer has an unknown value')
    for _ in range(64):
        target=None
        for line in blocks.get(label,[]):
            match=re.fullmatch('('+var+r') = call zeroext i8 @'+re.escape(invalid)+r'\(\)',line)
            if match:values[match[1]]=16;continue
            match=re.fullmatch('('+var+r') = phi (?:i8|i64) (.+)',line)
            if match:
                selected=[v for v,p in re.findall(r'\[ ('+var+r'|[0-9]+), %([A-Za-z0-9_.$-]+) \]',match[2]) if p==previous]
                if len(selected)!=1:raise Core0Error('Objects rejected initializer phi differs')
                values[match[1]]=value(selected[0]);continue
            match=re.fullmatch('('+var+r') = zext i8 ('+var+r') to i64',line)
            if match:values[match[1]]=value(match[2]);continue
            match=re.fullmatch('('+var+r') = insertvalue \{ i64, i64 \} (poison|'+var+r'), i64 ('+var+r'|[0-9]+), ([01])',line)
            if match:
                result,pair,operand,index=match.groups();pair=[None,None] if pair=='poison' else list(value(pair));pair[int(index)]=value(operand);values[result]=tuple(pair);continue
            match=re.fullmatch(r'br label %([A-Za-z0-9_.$-]+)',line)
            if match:target=match[1];continue
            match=re.fullmatch(r'ret \{ i64, i64 \} ('+var+')',line)
            if match:
                if value(match[1])!=(16,0):raise Core0Error('Objects rejected initializer fabricated success')
                return
            raise Core0Error('Objects rejected initializer has effects or an unsupported path')
        if target is None:raise Core0Error('Objects rejected initializer has no return route')
        previous,label=label,target
    raise Core0Error('Objects rejected initializer exceeds its bounded route')


def validate_object_initialization(unit: dict, pre_ir: str, names: dict[str,str]) -> dict:
    """Bind the successor constructor to exact wrappers and header publication."""
    o='Lemma.Kernel.Objects.';f='Lemma.Kernel.Memory.Frames.';var=r'%[A-Za-z0-9_.$-]+'
    if o+'initFor' not in names:return {'scope':'initializer not reachable; historical direct initializer unchanged'}
    needed={o+s for s in ('init','initFor','initStep','powerEndpointCapacity','capacity','put','get','control','magic','failed')}
    needed|={f+'allocate',f+'resolvePurpose','Lemma.User.CapabilityABI.invalidArgument'}
    if not needed<=names.keys():raise Core0Error('Objects versioned initializer closure missing')
    arithmetic=o+'initArithmetic' in names
    wrappers={o+'init':1}
    if arithmetic:wrappers[o+'initArithmetic']=3
    if o+'initPower' in names:wrappers[o+'initPower']=2
    expected='''entry:
  %action.call.result0 = call { i64, i64 } @INIT(i64 VERSION)
  %action.call.status-word1 = extractvalue { i64, i64 } %action.call.result0, 0
  %action.call.status2 = trunc i64 %action.call.status-word1 to i8
  %action.call.value3 = extractvalue { i64, i64 } %action.call.result0, 1
  %action.result.status-word4 = zext i8 %action.call.status2 to i64
  %action.result.partial5 = insertvalue { i64, i64 } poison, i64 %action.result.status-word4, 0
  %action.result.complete6 = insertvalue { i64, i64 } %action.result.partial5, i64 %action.call.value3, 1
  ret { i64, i64 } %action.result.complete6'''.replace('@INIT(', '@'+names[o+'initFor']+'(')
    for source,version in wrappers.items():
        if _ir_definition_body(pre_ir,names[source]).split()!=expected.replace('VERSION',str(version)).split():
            raise Core0Error('Objects initializer wrapper changed its fixed version/return')
    invalid=names['Lemma.User.CapabilityABI.invalidArgument']
    if re.fullmatch(r'\s*entry:\s*ret i8 16\s*',_ir_definition_body(pre_ir,invalid)) is None:
        raise Core0Error('Objects invalid initializer status differs')
    body=_ir_definition_body(pre_ir,names[o+'initFor']);blocks=_structured_ir_blocks(body)
    tests=re.findall('('+var+r') = icmp eq i1 ('+var+r'), 0$',body,re.M)
    if len(tests)!=1:raise Core0Error('Objects initializer lacks one closed version gate')
    comparison,predicate=tests[0]
    prefix=body[:body.index(comparison+' =')]+'ret i1 '+predicate+'\n'
    version_cases=_object_scalar_cases(prefix,{},header=True,version_only=True,arithmetic=arithmetic)
    gates=[validate_boolean_gate(body,comparison,names[source],success_when_true=False) for source in (f+'allocate',o+'get',o+'put')]
    _object_invalid_init_path(body,gates[0]['failure'],invalid)
    resolved=re.findall('('+var+r') = call \{ i64, i64 \} @'+re.escape(names[f+'resolvePurpose'])+r'\(i64 1, i64 ('+var+r'), i64 1\)',body)
    if len(resolved)!=1:raise Core0Error('Objects initializer loses owner1/purpose1 resolution')
    resolved_result,handle=resolved[0]
    address_values=re.findall('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(resolved_result)+r', 1$',body,re.M)
    if len(address_values)!=1:raise Core0Error('Objects initializer loses its resolved frame')
    address=address_values[0];operands=_ipc_scalar_operands(body,{names[o+'control']:0x80400620,names[o+'magic']:0x314a424f414d454c})
    puts=re.findall('('+var+r') = call \{ i64, i64 \} @'+re.escape(names[o+'put'])+r'\(i64 ([^,]+), i64 ([^)]+)\)',body)
    locations={}
    for field,location in (('version',('add',address,8)),('limit',('add',address,24)),('magic',address),('publish',0x80400620)):
        matches=[(result,pointer,value) for result,pointer,value in puts if operands.get(pointer,pointer)==location]
        if len(matches)!=1:raise Core0Error('Objects initializer lacks one exact '+field+' publication')
        locations[field]=matches[0]
    if locations['version'][2]!='%arg0' or operands.get(locations['magic'][2],locations['magic'][2])!=0x314a424f414d454c or locations['publish'][2]!=handle:
        raise Core0Error('Objects initializer header/global publication lost source values')
    encoded=locations['limit'][2]
    if arithmetic:
        helper=o+'encodedLimitFor'
        if helper not in names or o+'arithmeticEndpointCapacity' not in names:
            raise Core0Error('Objects-v3 initializer lacks its closed encoded-limit helper')
        exact=re.findall('('+var+r') = call i64 @'+re.escape(names[helper])+r'\(i64 %arg0\)',body)
        if exact!=[encoded]:raise Core0Error('Objects-v3 initializer substitutes its exact version encoding')
        encoded_cases=_object_scalar_cases(_ir_definition_body(pre_ir,names[helper]),
            {names[o+'powerEndpointCapacity']:5,names[o+'arithmeticEndpointCapacity']:6},header=False,encoded=True,arithmetic=True)
    else:
        phi=re.findall(re.escape(encoded)+r' = phi i64 \[ ('+var+r'), %([A-Za-z0-9_.$-]+) \], \[ 0, %([A-Za-z0-9_.$-]+) \]',body)
        if len(phi)!=1:raise Core0Error('Objects initializer encoded limit is not version2/5 versus legacy0')
        limit_value,yes,no=phi[0]
        if re.findall(re.escape(limit_value)+r' = call i64 @'+re.escape(names[o+'powerEndpointCapacity'])+r'\(\)',body)!=[limit_value+' = call i64 @'+names[o+'powerEndpointCapacity']+'()']:
            raise Core0Error('Objects initializer lost the exact successor capacity')
        candidate=[]
        for cmp in re.findall('('+var+r') = icmp eq i64 %arg0, 2$',body,re.M):
            try:candidate.append(validate_boolean_gate(body,cmp,names[o+'powerEndpointCapacity']))
            except Core0Error:pass
        if len(candidate)!=1 or (candidate[0]['success'],candidate[0]['failure'])!=(yes,no):
            raise Core0Error('Objects initializer limit branch is not exact version2')
        bound=candidate[0];merge=re.findall(r'br label %([A-Za-z0-9_.$-]+)', '\n'.join(blocks[yes]))
        if len(merge)!=1 or blocks[no]!=['br label %'+merge[0]]:
            raise Core0Error('Objects initializer encoded-limit merge has other effects')
        selected='entry:\n  '+bound['comparison']+' = icmp eq i64 %arg0, 2\n  br i1 '+bound['comparison']+', label %'+yes+', label %'+no+'\n'
        selected+=yes+':\n  '+'\n  '.join(blocks[yes])+'\n'+no+':\n  '+'\n  '.join(blocks[no])+'\n'+merge[0]+':\n  '+encoded+' = phi i64 [ '+limit_value+', %'+yes+' ], [ 0, %'+no+' ]\n  ret i64 '+encoded+'\n'
        encoded_cases=_object_scalar_cases(selected,{names[o+'powerEndpointCapacity']:5},header=False,encoded=True)
    aliased=body
    for field,(_,pointer,value) in locations.items():
        aliased=aliased.replace('@'+names[o+'put']+'(i64 '+pointer+', i64 '+value+')','@objects_init_'+field+'(i64 '+pointer+', i64 '+value+')')
    failed_body=_ir_definition_body(pre_ir,names[o+'failed'])
    if re.findall(r'call \{ i64, i64 \} @'+re.escape(names[f+'allocate'])+r'\(([^\n]*)\)',body)!=['i64 1, i64 1']:
        raise Core0Error('Objects initializer allocation loses owner1/purpose1')
    for before,after in ((o+'get',f+'allocate'),(f+'allocate',f+'resolvePurpose'),
                         (f+'resolvePurpose',o+'initStep'),(f+'resolvePurpose',o+'put')):
        gates.append(validate_failed_call_gate(body,names[before],names[after],names[o+'failed'],failed_body))
    for before,after in (('version','limit'),('limit','magic'),('magic','publish')):
        gates.append(validate_failed_call_gate(aliased,'objects_init_'+before,'objects_init_'+after,names[o+'failed'],failed_body))
    construct='Lemma.Platform.LemmaSim.NotebookKernel.construct';callers=[];binding_gates=[]
    selected=o+('initArithmetic' if arithmetic else 'initPower')
    for source,symbol in names.items():
        other=_ir_definition_body(pre_ir,symbol);calls=parse_definitions_and_calls(other)[2]
        if names[o+'initFor'] in calls and source not in wrappers:
            raise Core0Error('Objects versioned initializer has a non-wrapper caller')
        if selected not in names or names[selected] not in calls:continue
        if source!=construct:raise Core0Error('Objects power initializer escapes the selected machine constructor')
        admitted=[]
        for cmp in re.findall('('+var+r') = icmp eq i64 %arg2, 3$',other,re.M):
            try:admitted.append((validate_boolean_gate(other,cmp,names[selected]),validate_boolean_gate(other,cmp,names[o+'init'],success_when_true=False)))
            except Core0Error:pass
        if len(admitted)!=1:raise Core0Error('Objects power initializer lacks the exact binding3 selection')
        binding_gates.extend(admitted[0]);callers.append(source)
    if selected in names and callers!=[construct]:raise Core0Error('Objects power initializer has no exact constructor')
    return {'wrappers':wrappers,'version_cases':version_cases,'encoded_limit_cases':encoded_cases,
        'publication_status_gates':gates,'power_callers':callers,'binding3_gates':binding_gates}


def validate_object_budget(unit: dict, pre_ir: str) -> dict:
    """Independent emitted obligations for the volatile Objects-v2 successor.

    Historical units with direct constant4 keep their existing H/H_I audits.
    The successor must bind exact headers to checked table resolution, return
    its capacity only after successful reads, and gate both slot search and
    frame allocation on the checked capacity and count.
    """
    o='Lemma.Kernel.Objects.'
    names={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row['symbol'] for row in unit['functions']}
    if not any(source.startswith(o) for source in names):
        return {'scope':'Objects not reachable in this unit; no quota claim'}
    if o+'runtimeEndpointCapacity' not in names:
        if any(o+tail in names for tail in ('headerAdmitted','endpointLimitFor','initFor','initPower','powerEndpointCapacity')):
            raise Core0Error('Objects successor has an incomplete runtime quota closure')
        return {'scope':'historical direct constant4; existing H/H_I obligations unchanged'}
    if unit.get('role')!='kernel':raise Core0Error('Objects successor requires kernel authority')
    required={o+s for s in ('headerAdmitted','endpointLimitFor','runtimeEndpointCapacity','endpointCapacity',
        'powerEndpointCapacity','replyCapacity','capacity','table','get','failed','fatal','createEndpoint','endpointCountStep','freeObjectStep')}
    required|={'Lemma.Kernel.Memory.Frames.allocate','Lemma.Kernel.Memory.Frames.resolvePurpose','Lemma.User.CapabilityABI.fatal'}
    if not required<=names.keys():raise Core0Error('Objects successor source closure missing')
    arithmetic=o+'arithmeticEndpointCapacity' in names
    if arithmetic:required|={o+t for t in ('arithmeticEndpointCapacity','arithmeticReplyCapacity','replyLimitFor','runtimeReplyCapacity','replyAvailable','replyCountStep')}
    if not required<=names.keys():raise Core0Error('Objects-v3 endpoint/reply closure missing')
    bodies={s:_ir_definition_body(pre_ir,names[s]) for s in required}
    rows={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row for row in unit['functions']}
    for tail,value in (('endpointCapacity',4),('powerEndpointCapacity',5),('replyCapacity',8),('capacity',16),*((('arithmeticEndpointCapacity',6),('arithmeticReplyCapacity',7)) if arithmetic else ())):
        source=o+tail
        if rows[source]['args']!=[] or rows[source]['effects']!=[] or re.fullmatch(r'\s*entry:\s*ret i64 '+str(value)+r'\s*',bodies[source]) is None:
            raise Core0Error('Objects unchanged or successor capacity differs: '+tail)
    for tail,args in (('headerAdmitted',['u64','u64']),('endpointLimitFor',['u64']),*((('replyLimitFor',['u64']),) if arithmetic else ())):
        if rows[o+tail]['args']!=args or rows[o+tail]['effects']!=[]:
            raise Core0Error('Objects scalar quota signature/effects differ')
    scalar={names[o+'endpointCapacity']:4,names[o+'powerEndpointCapacity']:5}
    if arithmetic:scalar[names[o+'arithmeticEndpointCapacity']]=6
    header=_object_scalar_cases(bodies[o+'headerAdmitted'],scalar,header=True,arithmetic=arithmetic)
    limits=_object_scalar_cases(bodies[o+'endpointLimitFor'],scalar,header=False,arithmetic=arithmetic)
    if re.fullmatch(r'\s*entry:\s*ret i8 255\s*',bodies['Lemma.User.CapabilityABI.fatal']) is None:
        raise Core0Error('Objects malformed-header failure status differs')
    expected_fatal='''entry:
  %call0 = call zeroext i8 @FATAL()
  %action.result.status-word1 = zext i8 %call0 to i64
  %action.result.partial2 = insertvalue { i64, i64 } poison, i64 %action.result.status-word1, 0
  %action.result.complete3 = insertvalue { i64, i64 } %action.result.partial2, i64 0, 1
  ret { i64, i64 } %action.result.complete3'''.replace('@FATAL(', '@'+names['Lemma.User.CapabilityABI.fatal']+'(')
    if bodies[o+'fatal'].split()!=expected_fatal.split():raise Core0Error('Objects fatal pair was changed')
    runtime=bodies[o+'runtimeEndpointCapacity'];var=r'%[A-Za-z0-9_.$-]+'
    table_calls=re.findall('('+var+r') = call \{ i64, i64 \} @'+re.escape(names[o+'table'])+r'\(\)',runtime)
    if len(table_calls)!=1:raise Core0Error('Objects runtime capacity lacks one checked table')
    bases=re.findall('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(table_calls[0])+r', 1$',runtime,re.M)
    addresses=re.findall('('+var+r') = add i64 '+re.escape(bases[0] if len(bases)==1 else '<missing>')+r', 8$',runtime,re.M)
    reads=re.findall('('+var+r') = call \{ i64, i64 \} @'+re.escape(names[o+'get'])+r'\(i64 '+re.escape(addresses[0] if len(addresses)==1 else '<missing>')+r'\)',runtime)
    versions=re.findall('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(reads[0] if len(reads)==1 else '<missing>')+r', 1$',runtime,re.M)
    if len(versions)!=1 or re.findall(r'call i64 @'+re.escape(names[o+'endpointLimitFor'])+r'\(([^\n]*)\)',runtime)!=['i64 '+versions[0]]:
        raise Core0Error('Objects runtime quota is not its validated table version')
    runtime_gates=[validate_failed_call_gate(runtime,names[o+'table'],names[o+'get'],names[o+'failed'],bodies[o+'failed']),
        validate_failed_call_gate(runtime,names[o+'get'],names[o+'endpointLimitFor'],names[o+'failed'],bodies[o+'failed'])]
    scalar_result=re.findall('('+var+r') = call i64 @'+re.escape(names[o+'endpointLimitFor'])+r'\(i64 '+re.escape(versions[0])+r'\)',runtime)
    runtime_leaf=_object_checked_return(runtime,names[o+'fatal'],scalar_result[0])
    marked=runtime.replace(runtime_leaf+':\n',runtime_leaf+':\n  call void @objects_capacity_success()\n')
    runtime_gates.append(validate_failed_call_gate(marked,names[o+'get'],'objects_capacity_success',names[o+'failed'],bodies[o+'failed']))
    # The successful table return must be the actual owner1/purpose1 resolved
    # frame, and every failed pair remains fatal rather than a forged success.
    table=bodies[o+'table']
    resolved=re.findall('('+var+r') = call \{ i64, i64 \} @'+re.escape(names['Lemma.Kernel.Memory.Frames.resolvePurpose'])+r'\(i64 1, i64 '+var+r', i64 1\)',table)
    addresses=re.findall('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(resolved[0] if len(resolved)==1 else '<missing>')+r', 1$',table,re.M)
    if len(addresses)!=1:raise Core0Error('Objects table return lost owner1/purpose1 resolution')
    address=addresses[0];leaf=_object_checked_return(table,names[o+'fatal'],address)
    predicates=re.findall('('+var+r') = call zeroext i1 @'+re.escape(names[o+'headerAdmitted'])+r'\(i64 ('+var+r'), i64 ('+var+r')\)',table)
    if len(predicates)!=1:raise Core0Error('Objects table lacks one exact header predicate')
    predicate,version,limit=predicates[0];aliased=table
    read_results={}
    for field,offset,value in (('version',8,version),('encoded_limit',24,limit)):
        locations=re.findall('('+var+r') = add i64 '+re.escape(address)+', '+str(offset)+r'$',table,re.M)
        calls=re.findall('('+var+r') = call \{ i64, i64 \} @'+re.escape(names[o+'get'])+r'\(i64 '+re.escape(locations[0] if len(locations)==1 else '<missing>')+r'\)',table)
        if len(calls)!=1 or re.findall('('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(calls[0])+r', 1$',table,re.M)!=[value]:
            raise Core0Error('Objects header predicate lost its actual '+field+' field')
        alias='objects_checked_'+field
        aliased=aliased.replace('@'+names[o+'get']+'(i64 '+locations[0]+')','@'+alias+'(i64 '+locations[0]+')')
        read_results[field]=alias
    comparisons=re.findall('('+var+r') = icmp eq i1 '+re.escape(predicate)+r', 1$',table,re.M)
    if len(comparisons)!=1:raise Core0Error('Objects header predicate lacks its true gate')
    # This host-observer marker identifies the existing returned success leaf;
    # it is never target code, an allocation, or a replacement table algorithm.
    needle=leaf+':\n';aliased=aliased.replace(needle,needle+'  call void @objects_table_success()\n')
    table_gates=[validate_boolean_gate(aliased,comparisons[0],'objects_table_success')]
    table_gates += [validate_failed_call_gate(aliased,alias,'objects_table_success',names[o+'failed'],bodies[o+'failed']) for alias in read_results.values()]
    endpoint=validate_h_endpoint_budget(bodies[o+'createEndpoint'],names,pre_ir=pre_ir)
    if endpoint['capacity']!=({'version1':4,'version2':5,'version3':6} if arithmetic else {'version1':4,'version2':5}):raise Core0Error('Objects successor allocation bypasses runtime quota')
    reply_result={}
    if arithmetic:
        reply_limits=_object_scalar_cases(bodies[o+'replyLimitFor'],{names[o+'replyCapacity']:8,names[o+'arithmeticReplyCapacity']:7},header=False,arithmetic=True,replies=True)
        reply_runtime=bodies[o+'runtimeReplyCapacity']
        expected_runtime=runtime.replace(names[o+'endpointLimitFor'],names[o+'replyLimitFor'])
        if reply_runtime.split()!=expected_runtime.split():
            raise Core0Error('Objects-v3 reply capacity loses checked table/version/status/return')
        reply_budget=validate_h_endpoint_budget(bodies[o+'replyAvailable'],names,reply=True,pre_ir=pre_ir)
        if reply_budget['capacity']!={'version1':8,'version2':8,'version3':7}:
            raise Core0Error('Objects-v3 reply allocation bypasses runtime quota')
        reply_result={'reply_cases':reply_limits,'reply':reply_budget}
    return {'scope':'volatile Objects-v3 quota; legacy Endpoints4/5 Replies8, v3 Endpoints6 Replies7, total16' if arithmetic else 'volatile Objects-v2 quota; historical4, successor5, total16 and Replies8',**reply_result,
        'header_cases':header,'limit_cases':limits,'runtime_status_gates':runtime_gates,
        'table_header_gates':table_gates,'endpoint':endpoint,
        'initialization':validate_object_initialization(unit,pre_ir,names)}


def validate_h_alias(unit: dict, pre_ir: str, by_source: dict[str,str]) -> dict:
    prefix="Lemma.Kernel.Development.CapAlias."
    address="Lemma.Kernel.Memory.AddressSpace."
    access="Lemma.Kernel.Memory.Access."
    body=_ir_definition_body(pre_ir,by_source[prefix+"install"])
    var=r"%[A-Za-z0-9_.$-]+"
    base_calls=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[address+"base"])+r"\(i64 %arg0\)",body)
    if len(base_calls)!=1:
        raise Core0Error("H descriptor alias lacks one checked descriptor-derived base")
    base_values=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(base_calls[0])+r", 1$",body,re.M)
    if len(base_values)!=1:
        raise Core0Error("H descriptor alias lacks exact base result extraction")
    base=base_values[0]
    table_calls=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[prefix+"checkedTable"])+r"\(i64 "+re.escape(base)+r", i64 ("+var+r"), i64 ([0-9]+)\)",body)
    if [int(row[2]) for row in table_calls]!=[0,7,8] or len({row[1] for row in table_calls})!=1:
        raise Core0Error("H alias table geometry/checked ownership differs")
    low_values=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(table_calls[-1][0])+r", 1$",body,re.M)
    alias_values=re.findall(r"("+var+r") = call i64 @"+re.escape(by_source[prefix+"aliasPage"])+r"\(\)",body)
    slots=[]
    for low in low_values:
        for page in alias_values:
            slots.extend(re.findall(r"("+var+r") = call i64 @"+re.escape(by_source[address+"tableSlot"])+r"\(i64 "+re.escape(low)+r", i64 "+re.escape(page)+r"\)",body))
    writes=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[access+"write64"])+r"\(i64 ("+var+r"), i64 ("+var+r")\)",body)
    if len(writes)!=1 or writes[0][1] not in slots:
        raise Core0Error("H descriptor alias does not publish one exact owned low-table slot")
    ptes=[]
    for count,right in re.findall(r"("+var+r") = and i64 12, 63\n\s*("+var+r") = lshr i64 "+re.escape(base)+r", \1",body):
        for shift,left in re.findall(r"("+var+r") = and i64 10, 63\n\s*("+var+r") = shl i64 "+re.escape(right)+r", \1",body):
            ptes.extend(re.findall(r"("+var+r") = or i64 "+re.escape(left)+r", 199$",body,re.M))
    if writes[0][2] not in ptes or len(ptes)!=2:
        raise Core0Error("H descriptor alias PTE is not descriptorPPN plus exact S RW/NX/U0 flags")
    readbacks=[]
    for slot in slots:
        readbacks.extend(re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(by_source[access+"read64"])+r"\(i64 "+re.escape(slot)+r"\)",body))
    verified=[]
    for result in readbacks:
        for loaded in re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(result)+r", 1$",body,re.M):
            for pte in ptes:
                verified.extend(re.findall(r"("+var+r") = icmp eq i64 "+re.escape(loaded)+r", "+re.escape(pte)+r"$",body,re.M))
    if len(verified)!=1:
        raise Core0Error("H descriptor alias lacks one exact PTE readback comparison")
    readback_gate=validate_boolean_gate(body,verified[0],by_source[address+"flushCurrent"])
    for before in ("Lemma.Kernel.Task.prepared",address+"base",prefix+"checkedHeader",prefix+"checkedTable"):
        validate_call_precedes(body,by_source[before],by_source[access+"write64"])
    validate_call_precedes(body,by_source[access+"write64"],by_source[address+"flushCurrent"])
    return {"source":prefix+"install","symbol":by_source[prefix+"install"],"virtual_page":0x31000,"attack_va":0x31a00,
            "descriptor_header_offset":2560,"table_indices":[0,7,8],"pte_flags":199,"user_access":False,
            "writes":1,"descriptor_base_extraction":base,"pte_value":writes[0][2],"readback_comparisons":verified,"readback_gate":readback_gate}


def validate_h_legacy_console_denial(body: str, by_source: dict[str,str]) -> dict:
    console=by_source["Lemma.User.ABI.console"];legacy=by_source["Lemma.Kernel.Syscall.dispatchLegacy"]
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    values=re.findall(r"(%[A-Za-z0-9_.$-]+) = call i64 @"+re.escape(console)+r"\(\)",body)
    if len(values)!=1:
        raise Core0Error("managed dispatch lacks its exact legacy console selector")
    comparisons=re.findall(r"(%[A-Za-z0-9_.$-]+) = icmp eq i64 %arg1, "+re.escape(values[0])+r"$",body,re.M)
    if len(comparisons)!=1:
        raise Core0Error("managed legacy-console guard differs")
    branches=[block for block,lines in blocks.items() if re.fullmatch(r"br i1 "+re.escape(comparisons[0])+r", label %[A-Za-z0-9_.$-]+, label %[A-Za-z0-9_.$-]+",lines[-1])]
    if len(branches)!=1:
        raise Core0Error("managed legacy-console guard lacks exact successors")
    denied,ordinary=successors[branches[0]]
    protected={block for block,lines in blocks.items() if any("@"+legacy+"(" in line for line in lines)}
    if any(_structured_reachable(successors,denied,block) for block in protected) or len(blocks[denied])!=1 or len(successors[denied])!=1:
        raise Core0Error("managed console number2 can bypass capability lookup through legacy dispatch")
    merge=blocks[successors[denied][0]]
    if not any(re.search(r"phi i8 .*\[ 72, %"+re.escape(denied)+r" \]",line) for line in merge):
        raise Core0Error("managed legacy console does not return exact permission denial72")
    return {"legacy_console_number":2,"denied_status":72,"guard_block":branches[0],"denied_block":denied,"ordinary_block":ordinary}


def validate_h_console_router(pre_ir: str, by_source: dict[str,str]) -> dict:
    """Bind H's capability-checked read intermediary to the closed mode router.

    The mode call must succeed before either read, mode zero alone selects the
    legacy read, and only the emitted mode-one-or-two predicate selects buffered
    input. Every read keeps the actual descriptor/pointer/complete offered length.
    """
    y="Lemma.Kernel.Syscall.";n="Lemma.Kernel.KernelInput."
    wrapper=_ir_definition_body(pre_ir,by_source[y+"capConsole"])
    dispatcher=_ir_definition_body(pre_ir,by_source[y+"dispatchManaged"])
    protected_sources=(y+"selectedConsoleRead",y+"consoleRead",y+"consoleWrite",n+"read")
    if {by_source[source] for source in protected_sources} & parse_definitions_and_calls(dispatcher)[2]:
        raise Core0Error("managed dispatch directly bypasses capability-checked console wrapper")
    capability=validate_checked_call_gate(wrapper,by_source["Lemma.Kernel.Capability.lookup"],by_source[y+"selectedConsoleRead"])
    if re.findall(r"call \{ i64, i64 \} @"+re.escape(by_source[y+"selectedConsoleRead"])+r"\(([^\n]*)\)",wrapper)!=["i64 %arg0, i64 %arg3, i64 %arg4"]:
        raise Core0Error("H capability wrapper changed actual caller/pointer/length")
    body=_ir_definition_body(pre_ir,by_source[y+"selectedConsoleRead"])
    failed=_ir_definition_body(pre_ir,by_source[y+"failed"])
    mode=by_source[n+"mode"];raw=by_source[y+"consoleRead"];buffered=by_source[n+"read"]
    checked=[validate_failed_call_gate(body,mode,protected,by_source[y+"failed"],failed)
             for protected in (raw,buffered)]
    legacy=validate_checked_call_gate(body,mode,raw,component="value",value=0)
    for protected in (raw,buffered):
        arguments=re.findall(r"call \{ i64, i64 \} @"+re.escape(protected)+r"\(([^\n]*)\)",body)
        if arguments!=["i64 %arg0, i64 %arg1, i64 %arg2"]:
            raise Core0Error("H console router changed caller/pointer/complete offered length")
    var=r"%[A-Za-z0-9_.$-]+"
    results=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(mode)+r"\(\)",body)
    values=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(results[0] if len(results)==1 else "NO_MODE")+r", 1$",body,re.M)
    if len(results)!=1 or len(values)!=1:
        raise Core0Error("H console router lacks one actual mode result")
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    def branch(number):
        comparisons=re.findall(r"("+var+r") = icmp eq i64 "+re.escape(values[0])+", "+str(number)+r"$",body,re.M)
        origins=[label for label,lines in blocks.items() if len(comparisons)==1 and lines[-1].startswith("br i1 "+comparisons[0]+",")]
        if len(origins)!=1:
            raise Core0Error("H console router lost its exact mode comparison")
        return comparisons[0],origins[0],successors[origins[0]]
    zero,zorigin,_=branch(0);one,origin,(yes1,no1)=branch(1);two,origin2,(yes2,no2)=branch(2)
    nonzero=validate_boolean_gate(body,zero,buffered,success_when_true=False)
    if (origin2!=no1 or blocks[no1]!=[two+" = icmp eq i64 "+values[0]+", 2", "br i1 "+two+", label %"+yes2+", label %"+no2]
            or len(successors[yes1])!=1 or len(successors[yes2])!=1 or successors[yes2]!=successors[no2]):
        raise Core0Error("H buffered console lost its exact mode-one-or-two predicate")
    merge1=successors[yes1][0];merge2=successors[yes2][0]
    inner=re.findall(r"("+var+r") = phi i1 \[ 1, %"+re.escape(yes2)+r" \], \[ 0, %"+re.escape(no2)+r" \]$",body,re.M)
    outer=re.findall(r"("+var+r") = phi i1 \[ 1, %"+re.escape(yes1)+r" \], \[ "+re.escape(inner[0] if len(inner)==1 else "NO_INNER")+", %"+re.escape(merge2)+r" \]$",body,re.M)
    predicates=re.findall(r"("+var+r") = icmp eq i1 "+re.escape(outer[0] if len(outer)==1 else "NO_OUTER")+r", 1$",body,re.M)
    if len(inner)!=1 or len(outer)!=1 or len(predicates)!=1:
        raise Core0Error("H buffered console predicate has changed Boolean values")
    phi2=inner[0]+" = phi i1 [ 1, %"+yes2+" ], [ 0, %"+no2+" ]"
    phi1=outer[0]+" = phi i1 [ 1, %"+yes1+" ], [ "+inner[0]+", %"+merge2+" ]"
    if (blocks[yes1]!=["br label %"+merge1] or blocks[yes2]!=["br label %"+merge2] or blocks[no2]!=["br label %"+merge2]
            or blocks[merge2]!=[phi2,"br label %"+merge1]
            or len(blocks[merge1])!=3 or blocks[merge1][:2]!=[phi1,predicates[0]+" = icmp eq i1 "+outer[0]+", 1"]
            or {p for p,s in successors.items() if merge1 in s}!={yes1,merge2}
            or {p for p,s in successors.items() if merge2 in s}!={yes2,no2}
            or {p for p,s in successors.items() if no1 in s}!={origin}):
        raise Core0Error("H buffered console predicate has an alternate entry or changed merge")
    admitted=validate_boolean_gate(body,predicates[0],buffered)
    return {"source":y+"selectedConsoleRead","mode_source":n+"mode","raw_mode":0,"buffered_modes":[1,2],
            "arguments":["caller_descriptor","pointer","complete_offered_length"],
            "capability_status_gate":capability,"successful_mode_gates":checked,"raw_mode_gate":legacy,"nonzero_gate":nonzero,"buffered_mode_gate":admitted}


def validate_managed_capability_graph(unit: dict, pre_ir: str) -> dict:
    """Bind H labels to actual compiled enrollment, gates and teardown paths.

    These are artifact/source constraints, not a proof of capability semantics.
    Target execution and the independent state model supply separate evidence.
    """
    if unit.get("configuration") != "capabilities-development" or unit.get("role") != "kernel":
        raise Core0Error("managed lifecycle audit requires the exact H kernel unit")
    by_source={}
    for row in unit["functions"]:
        source=re.sub(r"^_private\..*?\.[0-9]+\.","",row["source"])
        if source in by_source:
            raise Core0Error("managed lifecycle source identity is ambiguous after private authorization")
        by_source[source]=row["symbol"]
    caps="Lemma.Kernel.Capability."
    objects="Lemma.Kernel.Objects."
    task="Lemma.Kernel.Task."
    syscalls="Lemma.Kernel.Syscall."
    entry="Lemma.Kernel.Development.CapsEntry."
    alias="Lemma.Kernel.Development.CapAlias."
    generation="Lemma.Kernel.Development.CapabilityGeneration."
    address="Lemma.Kernel.Memory.AddressSpace."
    frames="Lemma.Kernel.Memory.Frames."
    userabi="Lemma.User.CapabilityABI."
    edges={
        entry+"boot":[objects+"init",task+"init",entry+"launch"],
        entry+"launch":[task+"prepareManaged",entry+"configure"],
        entry+"configure":[objects+"configureManagement",entry+"seedEndpoint",objects+"createEndpoint",entry+"initialGrants",task+"activateManaged"],
        entry+"seedEndpoint":[generation+"seedOneFree",generation+"seedResult"],
        entry+"initialGrants":[entry+"grant"],
        entry+"grant":[caps+"grantBoot"],
        entry+"createTamper":[task+"prepareManaged",entry+"grant",alias+"install",task+"activateManaged"],
        entry+"command":[entry+"createTamper",generation+"advance","Lemma.Kernel.Development.TasksEntry.command"],
        task+"prepareManaged":[task+"prepare",caps+"attach",task+"abort",task+"prepared"],
        task+"activateManaged":[task+"prepared",caps+"activate",task+"activate"],
        task+"activate":[task+"prepared",task+"checkedActivation"],
        task+"checkedActivation":[caps+"managed",caps+"requireActive"],
        task+"abort":[task+"inactiveDescriptor",task+"detachManaged","Lemma.Kernel.Loader.teardown"],
        task+"reapOne":[task+"detachManaged","Lemma.Kernel.Loader.teardown"],
        task+"detachManaged":[caps+"detach"],
        caps+"attach":[address+"base",objects+"register"],
        caps+"header":[address+"base",caps+"headerAt"],
        caps+"headerAt":[objects+"get",objects+"registryDescriptor"],
        caps+"managed":[address+"base",caps+"headerAt",caps+"zeroHeaderStep"],
        caps+"requireActive":[caps+"header"],
        caps+"lookupEntry":[caps+"requireActive",objects+"resolve"],
        caps+"lookup":[caps+"lookupEntry",objects+"resolve",userabi+"rightsSubset"],
        caps+"grantBoot":[caps+"header",caps+"grant"],
        caps+"grant":[objects+"resolve",userabi+"rightsValid",caps+"freeSlot",objects+"nextSerial",caps+"publish"],
        caps+"freeSlot":[caps+"header",caps+"entryCount"],
        caps+"publish":[caps+"header",objects+"reference",objects+"publishSerial"],
        caps+"duplicate":[caps+"lookupEntry",userabi+"rightsSubset",caps+"grant"],
        caps+"transfer":[caps+"management",caps+"requireActive",caps+"lookupEntry",userabi+"rightsSubset",caps+"grant"],
        caps+"management":[caps+"lookup",objects+"resolve"],
        caps+"createEndpoint":[caps+"management",caps+"freeSlot",objects+"nextSerial",objects+"createEndpoint",caps+"publish"],
        caps+"close":[caps+"lookupEntry",caps+"requireActive",caps+"drop"],
        caps+"drop":[caps+"clearEntryStep",objects+"dereference"],
        caps+"revoke":[caps+"lookup",caps+"revokeKey"],
        caps+"revokeKey":[objects+"beginRevoke",caps+"revokeTaskStep",objects+"destroy"],
        caps+"revokeTaskStep":[objects+"registryDescriptor",caps+"header",caps+"revokeEntryStep"],
        caps+"revokeEntryStep":[caps+"drop"],
        caps+"detach":[address+"base",caps+"header",objects+"table",caps+"ownedObjectStep",caps+"detachEntryStep",objects+"clearManagement",objects+"unregister",caps+"clearHeaderStep"],
        caps+"ownedObjectStep":[caps+"revokeKey"],
        caps+"detachEntryStep":[caps+"drop"],
        objects+"init":[frames+"allocate",frames+"resolvePurpose",objects+"initStep"],
        objects+"table":[frames+"resolvePurpose",frames+"mappingCount"],
        objects+"resolve":[objects+"resolveState"],
        objects+"resolveState":[objects+"table",objects+"keyValid"],
        objects+"reference":[objects+"resolve"],
        objects+"dereference":[objects+"resolveRevoking",objects+"destroy"],
        objects+"destroy":[objects+"resolveRevoking",frames+"resolvePurpose",frames+"mappingCount",frames+"release"],
        objects+"createEndpoint":[address+"base",objects+"endpointCountStep",objects+"endpointCapacity",objects+"freeObjectStep",objects+"failed",frames+"allocate"],
        objects+"endpointCountStep":[objects+"get",objects+"live",objects+"revoking",userabi+"typeValid",userabi+"endpointType"],
        syscalls+"dispatch":[caps+"managed",syscalls+"dispatchManaged",syscalls+"dispatchLegacy"],
        syscalls+"dispatchManaged":[caps+"bootGrant",caps+"info",caps+"check",caps+"duplicate",caps+"close",caps+"revoke",syscalls+"capConsole",caps+"createEndpoint",caps+"transfer",caps+"scopedTarget",caps+"inspect",syscalls+"dispatchLegacy"],
        syscalls+"capConsole":[caps+"lookup",syscalls+"selectedConsoleRead",syscalls+"consoleWrite"],
        syscalls+"selectedConsoleRead":["Lemma.Kernel.KernelInput.mode",syscalls+"consoleRead","Lemma.Kernel.KernelInput.read",syscalls+"failed"],
        "Lemma.Kernel.Scheduler.dispatch":["Lemma.Kernel.Task.capture","Lemma.Kernel.Scheduler.call"],
        "Lemma.Kernel.Scheduler.call":[syscalls+"dispatch"],
        alias+"install":[task+"prepared",address+"base",alias+"checkedHeader",frames+"mappingCount",address+"owner",address+"root",alias+"checkedTable",address+"flushCurrent"],
        alias+"checkedTable":[frames+"resolvePurpose",frames+"mappingCount"],
        generation+"seedOneFree":[objects+"table",generation+"freeStep",objects+"maxGeneration"],
        generation+"advance":[objects+"nextSerial",objects+"table",objects+"maxSerial"],
    }
    if objects+'runtimeEndpointCapacity' in by_source:
        edges[objects+'createEndpoint']=[objects+'runtimeEndpointCapacity' if callee==objects+'endpointCapacity' else callee for callee in edges[objects+'createEndpoint']]
        edges[objects+'runtimeEndpointCapacity']=[objects+'table',objects+'get',objects+'endpointLimitFor']
    if objects+'initFor' in by_source:
        edges[objects+'initFor']=edges[objects+'init']
        edges[objects+'init']=[objects+'initFor']
    constants={caps+"magic":0x31504143414d454c,caps+"headerOffset":2560,caps+"entriesOffset":2624,
               caps+"capacity":16,caps+"stride":64,caps+"active":1,caps+"constructing":2,
               objects+"magic":0x314a424f414d454c,objects+"capacity":16,objects+"endpointCapacity":4,objects+"registryCapacity":8,
               objects+"rows":256,objects+"stride":128,objects+"maxGeneration":0x0fffffffffffffff,
               objects+"maxSerial":0x0fffffffffffffff,objects+"consoleKey":16,objects+"managementKey":17,
               objects+"live":1,objects+"revoking":2,userabi+"endpointType":2,
               task+"managedOffset":120,alias+"aliasPage":0x31000,alias+"attackAddress":0x31a00,
               "Lemma.Platform.LemmaVM.Layout.capabilityControlValue":0x80400620,"Lemma.User.ABI.console":2}
    required=set(constants)|set(edges)|{callee for callees in edges.values() for callee in callees}
    if not required<=set(by_source):
        raise Core0Error("managed kernel lacks its genuine source lifecycle closure: "+str(sorted(required-set(by_source))))
    observed_edges=[]
    for caller,callees in edges.items():
        calls=parse_definitions_and_calls(_ir_definition_body(pre_ir,by_source[caller]))[2]
        for callee in callees:
            if by_source[callee] not in calls:
                raise Core0Error("managed source call edge is absent: "+caller+" -> "+callee)
            observed_edges.append([caller,callee])
    for source,value in constants.items():
        body=_ir_definition_body(pre_ir,by_source[source])
        if re.fullmatch(r"\s*entry:\s*ret i64 "+str(value)+r"\s*",body) is None:
            raise Core0Error("managed storage/generation source constant differs: "+source)
    ordered=[]
    for caller,before,after in [
        (task+"prepareManaged",task+"prepare",caps+"attach"),
        (task+"activateManaged",caps+"activate",task+"activate"),
        (task+"abort",task+"detachManaged","Lemma.Kernel.Loader.teardown"),
        (task+"reapOne",task+"detachManaged","Lemma.Kernel.Loader.teardown"),
        (entry+"configure",entry+"initialGrants",task+"activateManaged"),
        (entry+"configure",entry+"seedEndpoint",objects+"createEndpoint"),
        (entry+"createTamper",entry+"grant",alias+"install"),
        (entry+"createTamper",alias+"install",task+"activateManaged"),
        (caps+"header",address+"base",caps+"headerAt"),
        (caps+"lookupEntry",caps+"requireActive",objects+"resolve"),
        (caps+"publish",objects+"reference",objects+"publishSerial"),
        (caps+"revokeKey",objects+"beginRevoke",objects+"destroy"),
    ]:
        ordered.append({"source":caller,**validate_call_precedes(_ir_definition_body(pre_ir,by_source[caller]),by_source[before],by_source[after])})
    gates=[]
    for protected in (syscalls+"dispatchManaged",syscalls+"dispatchLegacy"):
        gates.append({"source":syscalls+"dispatch",**validate_checked_call_gate(_ir_definition_body(pre_ir,by_source[syscalls+"dispatch"]),by_source[caps+"managed"],by_source[protected])})
    gates.append({"source":syscalls+"dispatch",**validate_checked_call_gate(_ir_definition_body(pre_ir,by_source[syscalls+"dispatch"]),by_source[caps+"managed"],by_source[syscalls+"dispatchManaged"],component="value",value=1)})
    for protected in (syscalls+"selectedConsoleRead",syscalls+"consoleWrite"):
        gates.append({"source":syscalls+"capConsole",**validate_checked_call_gate(_ir_definition_body(pre_ir,by_source[syscalls+"capConsole"]),by_source[caps+"lookup"],by_source[protected])})
    # Only the capability wrapper may call the actual UART/copy routines from
    # the managed dispatcher; its legacy fallthrough rejects console number2.
    managed_body=_ir_definition_body(pre_ir,by_source[syscalls+"dispatchManaged"])
    if {by_source[syscalls+"selectedConsoleRead"],by_source[syscalls+"consoleRead"],by_source[syscalls+"consoleWrite"],by_source["Lemma.Kernel.KernelInput.read"]} & parse_definitions_and_calls(managed_body)[2]:
        raise Core0Error("managed dispatch directly bypasses capability-checked console wrapper")
    for row in re.findall(r"(?m)^.*\bcall[^@\n]*@([^ (]+)\(([^\n]*)\)$",managed_body):
        if row[0] in {by_source[source] for source in edges[syscalls+"dispatchManaged"] if source.startswith(caps)} and not row[1].startswith("i64 %arg0,"):
            raise Core0Error("managed syscall changed caller-local descriptor to a user-selected identity")
    router_report=validate_h_console_router(pre_ir,by_source)
    endpoint_report=validate_h_endpoint_budget(_ir_definition_body(pre_ir,by_source[objects+"createEndpoint"]),by_source,pre_ir=pre_ir)
    validate_object_budget(unit,pre_ir)
    # Bind the helper's status inversion; a count callback failure must never
    # be accepted as a successful preallocation result.
    failed_body=_ir_definition_body(pre_ir,by_source[objects+"failed"])
    if re.fullmatch(r"\s*entry:\s*%cmp0 = icmp eq i8 %arg0, 0\s*br i1 %cmp0, label %if.then.0, label %if.else.1\s*if.then.0:\s*br label %if.merge.2\s*if.else.1:\s*br label %if.merge.2\s*if.merge.2:\s*%if.result1 = phi i1 \[ 0, %if.then.0 \], \[ 1, %if.else.1 \]\s*ret i1 %if.result1\s*",failed_body) is None:
        raise Core0Error("endpoint count status helper differs from exact nonzero failure")
    alias_report=validate_h_alias(unit,pre_ir,by_source)
    denial_report=validate_h_legacy_console_denial(managed_body,by_source)
    launch_body=_ir_definition_body(pre_ir,by_source[entry+"launch"])
    tamper_body=_ir_definition_body(pre_ir,by_source[entry+"createTamper"])
    pattern=r"call \{ i64, i64 \} @"+re.escape(by_source[task+"prepareManaged"])+r"\(i64 ([0-9]+),"
    if re.findall(pattern,launch_body)!=["0","1","2"] or re.findall(pattern,tamper_body)!=["3"]:
        raise Core0Error("managed image preparation differs from exact source-selected boot roles")
    return {"capability_header_borrow":validate_capability_header_helpers(unit,pre_ir),"selected_console_router":router_report,"endpoint_budget":endpoint_report,"alias":alias_report,"legacy_console_denial":denial_report,"managed_policy":MANAGED_POLICY,"storage":{"control":0x80400620,"header_offset":2560,"entries_offset":2624,"capacity":16,"entry_bytes":64,"object_capacity":16,"max_generation":0x0fffffffffffffff,"max_serial":0x0fffffffffffffff},
            "source_constants":{source:{"symbol":by_source[source],"value":value} for source,value in sorted(constants.items())},
            "source_call_edges":observed_edges,"ordered_cfg_calls":ordered,"checked_cfg_gates":gates,
            "limitations":["Compiled call/CFG/storage binding, not a proof of authority semantics or guest execution."]}


def _ipc_scalar_operands(body: str, constants: dict[str,int]) -> dict[str,object]:
    var=r"%[A-Za-z0-9_.$-]+"
    values={result:value for result,symbol in re.findall(r"("+var+r") = call i64 @([^ (]+)\(\)",body)
            if (value:=constants.get(symbol)) is not None}
    for result,left,right in re.findall(r"("+var+r") = add i64 ([^,\n]+), ([^\n]+)$",body,re.M):
        a=values.get(left,int(left) if left.isdecimal() else left)
        b=values.get(right,int(right) if right.isdecimal() else right)
        values[result]=a+b if type(a)is int and type(b)is int else ("add",a,b)
    return values


def validate_ipc_read_guard(body: str, read: str, constants: dict[str,int], address: object,
                            expected: object, protected: str, *, equal: bool = True) -> dict:
    """Bind one loaded owned field to an exact equality CFG guard."""
    var=r"%[A-Za-z0-9_.$-]+";values=_ipc_scalar_operands(body,constants)
    rows=[(result,operand) for result,operand in re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(read)+r"\(i64 ([^\n)]+)\)",body)
          if values.get(operand,int(operand) if operand.isdecimal() else operand)==address]
    if len(rows)!=1:raise Core0Error("IPC guard lacks one exact checked field load")
    extracted=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(rows[0][0])+r", 1$",body,re.M)
    comparisons=[result for result,left,right in re.findall(r"("+var+r") = icmp eq i64 ([^,\n]+), ([^\n]+)$",body,re.M)
                 if left in extracted and values.get(right,int(right) if right.isdecimal() else right)==expected]
    if len(extracted)!=1 or len(comparisons)!=1:raise Core0Error("IPC guard lost its exact loaded field/expected binding")
    return {'address':address,'expected':expected,**validate_boolean_gate(body,comparisons[0],protected,success_when_true=equal)}


def validate_ipc_block_bridge(body: str, syscall_dispatch: str, wait_info: str,
                              reply: str, block: str, return_kernel: str,
                              blocked_status: str, failed: str, failed_body: str) -> dict:
    """The internal254 path advances PC exactly once before suspension.

    Ordinary/error paths are separate. Wakeup is audited elsewhere and must
    write only a0/a1 plus Task bookkeeping, with no second syscallReply call.
    """
    var=r"%[A-Za-z0-9_.$-]+";blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    calls=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(syscall_dispatch)+r"\([^\n]*\)",body)
    statuses=re.findall(r"("+var+r") = extractvalue \{ i64, i64 \} "+re.escape(calls[0] if len(calls)==1 else 'NO_CALL')+r", 0$",body,re.M)
    narrowed=re.findall(r"("+var+r") = trunc i64 "+re.escape(statuses[0] if len(statuses)==1 else 'NO_STATUS')+r" to i8$",body,re.M)
    constants=re.findall(r"("+var+r") = call zeroext i8 @"+re.escape(blocked_status)+r"\(\)",body)
    comparisons=re.findall(r"("+var+r") = icmp eq i8 "+re.escape(narrowed[0] if len(narrowed)==1 else 'NO_NARROW')+r", "+re.escape(constants[0] if len(constants)==1 else 'NO_CONSTANT')+r"$",body,re.M)
    if len(calls)!=1 or len(statuses)!=1 or len(narrowed)!=1 or len(constants)!=1 or len(comparisons)!=1:
        raise Core0Error('IPC blocked bridge lacks the actual returned status254 binding')
    gate=validate_boolean_gate(body,comparisons[0],block)
    branch=gate['success'];scope={label for label in blocks if _structured_reachable(successors,branch,label)}
    zero_replies=[line for label in scope for line in blocks[label] if re.search(
        r" = call \{ i64, i64 \} @"+re.escape(reply)+r"\(i64 %arg1, i64 %arg2, i8 zeroext 0, i64 0\)$",line)]
    all_replies=[line for label in scope for line in blocks[label] if re.search(r"\bcall[^@\n]*@"+re.escape(reply)+r"\(",line)]
    if len(zero_replies)!=1 or all_replies!=zero_replies:
        raise Core0Error('IPC blocked bridge changes or repeats its one actual PC advance')
    renamed=body.replace('@'+reply+'(i64 %arg1, i64 %arg2, i8 zeroext 0, i64 0)',
                         '@ipc_single_pc_advance(i64 %arg1, i64 %arg2, i8 zeroext 0, i64 0)')
    advance=validate_failed_call_gate(renamed,'ipc_single_pc_advance',block,failed,failed_body)
    wait=validate_failed_call_gate(body,wait_info,block,failed,failed_body)
    returned=[line for label in scope for line in blocks[label] if re.search(r'\bcall[^@\n]*@'+re.escape(return_kernel)+r'\(',line)]
    if len(returned)!=1 or re.search(r'\(i64 %arg0, i64 6, i64 %arg2\)$',returned[0]) is None:
        raise Core0Error('IPC blocked bridge does not return exact scheduler reason6')
    return {'internal_status':254,'pc_advances':1,'reason':6,'blocked_gate':gate,'advance_success':advance,'wait_binding':wait}


def validate_ipc_write_inventory(body: str, write: str, constants: dict[str,int],
                                 expected: list[tuple[object,object]], failed: str,
                                 failed_body: str) -> dict:
    """Pin each compiled mutable write and successful publication edge.

    Constants are already bound to genuine no-argument Lean definitions. Only
    literal constants, argument operands and their simple emitted additions are
    resolved here; unfamiliar expressions fail rather than acquire authority.
    """
    var=r"%[A-Za-z0-9_.$-]+"
    values=_ipc_scalar_operands(body,constants)
    rows=re.findall(r"("+var+r") = call \{ i64, i64 \} @"+re.escape(write)+r"\(i64 ([^,\n]+), i64 ([^\n)]+)\)",body)
    observed=[(values.get(a,int(a) if a.isdecimal() else a),values.get(b,int(b) if b.isdecimal() else b)) for _,a,b in rows]
    if observed!=expected or not rows:
        raise Core0Error("IPC mutable write address/value inventory differs: "+str(observed))
    # Every next write is dominated by the preceding write's actual status0
    # edge. A final state publication therefore cannot precede earlier writes.
    gates=[]
    for (result,_,_),(following,_,_) in zip(rows,rows[1:]):
        renamed=body.replace(following+" = call { i64, i64 } @"+write+"(",following+" = call { i64, i64 } @ipc_next_write(")
        # Give this one result an unambiguous checked-call identity without
        # changing its status/extraction/CFG. Other writes keep their identity.
        renamed=renamed.replace(result+" = call { i64, i64 } @"+write+"(",result+" = call { i64, i64 } @ipc_previous_write(")
        gates.append(validate_failed_call_gate(renamed,"ipc_previous_write","ipc_next_write",failed,failed_body))
    return {"writes":[{"address":a,"value":b} for a,b in observed],"successful_write_gates":gates}


def validate_current_ipc_saved_context(body: str, names: dict[str, str],
                                       constants: dict[str, int], failed_body: str) -> dict:
    """Exact four-page blocked context reads from one freshly checked base.

    Internal names below only distinguish existing checked read sites for CFG
    inspection; they never add a machine primitive or an unchecked target call.
    """
    p='Lemma.Kernel.';t=p+'Task.';a=p+'Memory.AddressSpace.'
    read=names[p+'Memory.Access.read64'];base=names[a+'base']
    lookup=names[t+'lookup'];stack=names[p+'Process.validateStackAt'];failed=names[t+'failed']
    variable=r'%[A-Za-z0-9_.$-]+'
    def result(symbol):
        calls=re.findall(r'('+variable+r') = call \{ i64, i64 \} @'+re.escape(symbol)+r'\(([^\n]*)\)',body)
        if len(calls)!=1: raise Core0Error('current IPC context lacks one exact checked call')
        values=re.findall(r'('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(calls[0][0])+r', 1$',body,re.M)
        if len(values)!=1: raise Core0Error('current IPC context lost its checked value')
        return calls[0],values[0]
    lookup_call,record=result(lookup);base_call,address=result(base);stack_call,top=result(stack)
    if lookup_call[1]!='i64 %arg0' or base_call[1]!='i64 %arg0' or stack_call[1]!='i64 '+address:
        raise Core0Error('current IPC context changed descriptor or exact fresh helper base')
    saved=('add',address,2048);scalars=_ipc_scalar_operands(body,constants)
    expected=[('add',record,8),('add',address,64),0x80400600,('add',address,72),
              ('add',saved,272),saved,('add',saved,264),('add',saved,280)]
    reads=re.findall(r'('+variable+r') = call \{ i64, i64 \} @'+re.escape(read)+r'\(i64 ([^\n)]+)\)',body)
    actual=[scalars.get(operand,int(operand) if operand.isdecimal() else operand) for _,operand in reads]
    if actual!=expected: raise Core0Error('current IPC context read addresses/order differ')
    aliases=[];values=[];bound=body
    for index,(call,operand) in enumerate(reads):
        alias='ipc_saved_context_read_'+str(index);aliases.append(alias)
        bound=bound.replace(call+' = call { i64, i64 } @'+read+'(',call+' = call { i64, i64 } @'+alias+'(')
        extracted=re.findall(r'('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(call)+r', 1$',body,re.M)
        if len(extracted)!=1: raise Core0Error('current IPC context lost an exact read value')
        values.append(extracted[0])
    allowed={lookup,base,stack,read,failed,names[t+'fatal'],names[t+'stateOffset'],
             names[t+'blocked'],names[a+'activeRoot'],names[a+'userContextOffset']}
    if parse_definitions_and_calls(body)[2]-allowed:
        raise Core0Error('current IPC saved context has an unexpected call or mutation')
    status_gates=[]
    for before,after in [(lookup,aliases[0]),(aliases[0],base),(base,aliases[1]),
                         (aliases[1],aliases[2]),(aliases[2],aliases[3]),
                         (aliases[3],aliases[4]),(aliases[4],aliases[5]),
                         (aliases[5],aliases[6]),(aliases[6],stack),(stack,aliases[7])]:
        status_gates.append(validate_failed_call_gate(bound,before,after,failed,failed_body))
    fresh=validate_fresh_descriptor_base_call(body,base,stack,failed,failed_body)
    fields=[validate_ipc_read_guard(bound,aliases[0],constants,expected[0],5,base)]
    for protected in (*aliases[3:],stack):
        fields.append(validate_ipc_read_guard(bound,aliases[2],constants,expected[2],values[1],protected,equal=False))
    for protected in (*aliases[5:],stack):
        fields.append(validate_ipc_read_guard(bound,aliases[4],constants,expected[4],values[3],protected))
    for protected in (aliases[6],aliases[7],stack):
        fields.append(validate_ipc_read_guard(bound,aliases[5],constants,saved,0,protected))
    for protected in (aliases[7],stack):
        fields.append(validate_ipc_read_guard(bound,aliases[6],constants,expected[6],0x200000020,protected))
    # Pin the sole successful return diamond to storedTop=validatedTop. All
    # other source branches use the independently pinned Task.fatal result.
    blocks=_structured_ir_blocks(bound);successors=_structured_successors(blocks)
    comparisons=re.findall(r'('+variable+r') = icmp eq i64 '+re.escape(values[7])+r', '+re.escape(top)+r'$',bound,re.M)
    branches=[label for label,lines in blocks.items() if len(comparisons)==1 and
              lines[-1].startswith('br i1 '+comparisons[0]+', ')]
    if len(branches)!=1: raise Core0Error('current IPC context lost its stored trap-stack top check')
    success,failure=successors[branches[0]];lines=blocks[success]
    if len(lines)!=3 or not re.fullmatch(variable+r' = call i64 @'+re.escape(names[a+'userContextOffset'])+r'\(\)',lines[0]):
        raise Core0Error('current IPC context successful return invokes unexpected code')
    offset=lines[0].split(' = ',1)[0];pointer=re.fullmatch('('+variable+r') = add i64 '+re.escape(address)+r', '+re.escape(offset),lines[1])
    if pointer is None or len(successors[success])!=1 or _structured_reachable(successors,failure,success):
        raise Core0Error('current IPC context successful pointer is not the fresh context base')
    merge=successors[success][0];out=blocks[merge]
    denied=blocks[failure]
    failure_call=re.fullmatch('('+variable+r') = call \{ i64, i64 \} @'+re.escape(names[t+'fatal'])+r'\(\)',denied[0]) if len(denied)==5 else None
    if failure_call is None or successors[failure]!=(merge,):
        raise Core0Error('current IPC top mismatch does not take its exact fatal return')
    failure_word=re.fullmatch('('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(failure_call[1])+r', 0',denied[1])
    failure_status=re.fullmatch('('+variable+r') = trunc i64 '+re.escape(failure_word[1] if failure_word else '<missing>')+r' to i8',denied[2])
    failure_value=re.fullmatch('('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(failure_call[1])+r', 1',denied[3])
    if failure_status is None or failure_value is None or len(out)!=3 or not re.fullmatch(variable+r' = phi i8 \[ 0, %'+re.escape(success)+r' \], \[ '+re.escape(failure_status[1])+r', %'+re.escape(failure)+r' \]',out[0]) or not re.fullmatch(variable+r' = phi i64 \[ '+re.escape(pointer[1])+r', %'+re.escape(success)+r' \], \[ '+re.escape(failure_value[1])+r', %'+re.escape(failure)+r' \]',out[1]):
        raise Core0Error('current IPC context does not publish the exact checked pointer/status0')
    if len(re.findall(r'\[ 0, %[A-Za-z0-9_.$-]+ \]', '\n'.join(line for line in body.splitlines() if ' = phi i8 ' in line)))!=1 or len(re.findall(r'^\s*ret \{ i64, i64 \}',body,re.M))!=1:
        raise Core0Error('current IPC context has another successful return route')
    # Carry this checked pair unchanged through the generated Action merge
    # chain. A valid context computed above cannot be replaced at the final
    # aggregate return, and an error must not be converted to a success there.
    status=out[0].split(' = ',1)[0];value=out[1].split(' = ',1)[0]
    predecessor=merge;visited={merge}
    while len(successors[predecessor])==1:
        following=successors[predecessor][0]
        if following in visited: raise Core0Error('current IPC return merge chain is cyclic')
        visited.add(following);tail=blocks[following]
        if tail[0].find(' = phi i8 ')!=-1:
            if len(tail)<3 or tail[1].find(' = phi i64 ')==-1:
                raise Core0Error('current IPC return pair has a malformed merge')
            if len(re.findall(r'\[ '+re.escape(status)+r', %'+re.escape(predecessor)+r' \]',tail[0]))!=1 or len(re.findall(r'\[ '+re.escape(value)+r', %'+re.escape(predecessor)+r' \]',tail[1]))!=1:
                raise Core0Error('current IPC return merge changes the checked status/pointer')
            status=tail[0].split(' = ',1)[0];value=tail[1].split(' = ',1)[0];tail=tail[2:]
        if len(tail)==1 and len(successors[following])==1:
            predecessor=following
            continue
        if len(tail)!=4:
            raise Core0Error('current IPC checked context does not reach its exact aggregate return')
        wide=re.fullmatch('('+variable+r') = zext i8 '+re.escape(status)+r' to i64',tail[0])
        partial=re.fullmatch('('+variable+r') = insertvalue \{ i64, i64 \} poison, i64 '+re.escape(wide[1] if wide else '<missing>')+r', 0',tail[1])
        complete=re.fullmatch('('+variable+r') = insertvalue \{ i64, i64 \} '+re.escape(partial[1] if partial else '<missing>')+r', i64 '+re.escape(value)+r', 1',tail[2])
        if complete is None or tail[3]!='ret { i64, i64 } '+complete[1] or successors[following]:
            raise Core0Error('current IPC aggregate return changes the checked status/pointer')
        break
    else:
        raise Core0Error('current IPC checked pair lacks one aggregate return route')
    returned=bound.replace(lines[0],lines[0].replace('@'+names[a+'userContextOffset']+'(', '@ipc_saved_context_success('))
    fields.append(validate_ipc_read_guard(returned,aliases[7],constants,expected[7],top,'ipc_saved_context_success'))
    status_gates.append(validate_failed_call_gate(returned,aliases[7],'ipc_saved_context_success',failed,failed_body))
    return {'descriptor_base':address,'context_offset':2048,'read_addresses':actual,
            'fresh_descriptor_gate':fresh,'checked_read_gates':status_gates,'loaded_field_gates':fields,
            'success_block':success,'saved_pointer':pointer[1],'scope':'exact current four-page blocked context; no cross-call cache'}


def validate_ipc_graph(unit: dict, pre_ir: str) -> dict:
    """Bind the selected IPC policy to its genuine source/CFG/storage closure.

    This reports compiled structural obligations, not a proof or a substitute
    for the independent IPC model and observed User execution.
    """
    if unit.get("configuration") not in {"ipc-development",*SERVICE_CONFIGURATIONS} or unit.get("role")!="kernel":
        raise Core0Error("IPC graph audit requires its exact selected kernel unit")
    service = unit["configuration"] in SERVICE_CONFIGURATIONS
    by_source={re.sub(r"^_private\..*?\.[0-9]+\.","",row["source"]):row["symbol"] for row in unit["functions"]}
    e="Lemma.Kernel.Development.IPCEntry.";t="Lemma.Kernel.Task.";c="Lemma.Kernel.Capability."
    o="Lemma.Kernel.Objects.";s="Lemma.Kernel.IPCStorage.";i="Lemma.Kernel.IPC."
    a="Lemma.Kernel.Memory.AddressSpace.";f="Lemma.Kernel.Memory.Frames.";u="Lemma.Kernel.Memory.UserCopy."
    y="Lemma.Kernel.Syscall.";q="Lemma.Kernel.Scheduler.";p="Lemma.Kernel.Process."
    b="Lemma.User.IPCABI.";v="Lemma.User.CapabilityABI.";x="Lemma.Kernel.Memory.Access."
    current_context=p+'validateStackAt' in by_source
    edges={
      e+"boot":[e+"launch",t+"init",o+"init",p+"init"],e+"dispatch":[q+"dispatch"],
      e+"launch":["Lemma.Kernel.Development.TasksEntry.readLaunchWithFourth",t+"prepareManaged",e+"configure"],
      e+"configure":[o+"configureManagement",e+"createEndpoint",o+"table",o+"put",e+"initialGrants",e+"activate"],
      e+"createEndpoint":[o+"createEndpoint",f+"remaining","Lemma.Kernel.Console.record"],
      e+"initialGrants":[e+"grant"],e+"grant":[c+"grantBoot"],e+"activate":[t+"activateManaged"],
      e+"retainedPrimary":[o+"table",o+"resolve",c+"requireActive",t+"lookup"],
      e+"createFault":[e+"retainedPrimary",t+"prepareManaged",e+"grant",t+"activateManaged"],
      e+"step":[e+"poll",q+"step"],e+"command":[e+"createFault","Lemma.Kernel.Development.TasksEntry.command"],
      t+"prepareManaged":[t+"prepare",c+"attach",t+"abort",t+"prepared"],
      t+"activateManaged":[t+"prepared",c+"activate",t+"activate"],t+"activate":[t+"checkedActivation"],
      t+"checkedActivation":[c+"managed",c+"requireActive"],
      t+"abort":[t+"inactiveDescriptor",t+"detachManaged","Lemma.Kernel.Loader.teardown"],
      t+"reapOne":[t+"detachManaged","Lemma.Kernel.Loader.teardown"],t+"detachManaged":[i+"detach",c+"detach"],
      c+"attach":[a+"base",o+"register",s+"initialize"],c+"header":[a+"base",c+"headerAt"],
      c+"headerAt":[o+"get",o+"registryDescriptor"],
      c+"managed":[a+"base",c+"headerAt"],c+"requireActive":[c+"header"],
      c+"lookupEntry":[c+"requireActive",o+"resolve"],c+"lookup":[c+"lookupEntry",o+"resolve",v+"rightsSubset"],
      c+"grantBoot":[c+"header",c+"grant"],c+"grant":[o+"resolve",v+"rightsValid",c+"freeSlot",o+"nextSerial",c+"publish"],
      c+"publish":[o+"reference",o+"publishSerial"],c+"grantReply":[c+"requireActive",o+"replyFields",c+"grant",o+"deliverReply"],
      c+"retireReply":[o+"replyFields",s+"pending",o+"beginReplyRevoke",o+"endpointQueue",s+"queueCancelReply",s+"invalidateReply",c+"revokeTaskStep",o+"dereference",o+"destroyReply"],
      c+"close":[c+"lookupEntry",c+"retireReply",c+"cancelEndpointReplies",c+"drop"],
      c+"revokeKey":[c+"cancelEndpointReplies",o+"beginRevoke",c+"revokeTaskStep",o+"destroy"],
      c+"revokeTaskStep":[o+"registryDescriptor",c+"header",c+"revokeEntryStep"],c+"revokeEntryStep":[c+"drop"],
      c+"drop":[c+"clearEntryStep",o+"dereference"],
      c+"cancelEndpointReplies":[c+"cancelReplyStep"],c+"cancelDescriptorReplies":[c+"cancelReplyStep"],
      c+"cancelReplyStep":[o+"resolveRevoking",c+"retireReply"],
      c+"detach":[c+"cancelDescriptorReplies",c+"cancelSenderStep",c+"ownedObjectStep",c+"detachEntryStep",s+"detach",o+"clearManagement",o+"unregister",c+"clearHeaderStep"],
      c+"ownedObjectStep":[c+"revokeKey"],c+"detachEntryStep":[c+"drop"],
      o+"table":[f+"resolvePurpose",f+"mappingCount"],o+"resolveState":[o+"table",o+"keyValid"],
      o+"createEndpoint":[o+"endpointCountStep",o+"freeObjectStep",f+"allocate",s+"queueInitialize"],
      o+"endpointQueue":[o+"resolveRevoking",s+"queue"],
      o+"replyAvailable":[o+"replyCountStep",o+"freeObjectStep"],
      o+"createReply":[s+"pending",o+"endpointQueue",o+"replyAvailable",o+"freeObjectStep"],
      o+"replyFields":[o+"resolveRevoking",s+"pending",o+"replyPhase"],
      o+"markReplyQueued":[o+"replyFields"],o+"deliverReply":[o+"replyFields",o+"registrySlot"],
      o+"destroy":[o+"endpointRepliesStep",o+"invalidateEndpointWaits",f+"release"],
      o+"destroyReply":[o+"replyFields",o+"invalidateReplyBindingStep",o+"clearObjectStep"],
      y+"dispatch":[c+"managed",y+"dispatchManaged",y+"dispatchLegacy"],
      y+"dispatchManaged":[i+"dispatch",y+"capConsole"],y+"capConsole":[c+"lookup",y+"selectedConsoleRead",y+"consoleWrite"],
      y+"selectedConsoleRead":["Lemma.Kernel.KernelInput.mode",y+"consoleRead","Lemma.Kernel.KernelInput.read"],
      i+"dispatch":[i+"send",i+"receive",i+"callBegin",i+"callWait",i+"reply",i+"cancel"],
      i+"send":[c+"lookup",i+"payload",i+"idle",i+"queueRoom",s+"prepare",i+"stage",s+"queueEnqueue",i+"publishedSend"],
      i+"callBegin":[c+"lookup",i+"payload",i+"idle",i+"queueRoom",o+"replyAvailable",i+"deadline",s+"prepare",i+"stage",o+"createReply",s+"setReply",s+"queueEnqueue",o+"markReplyQueued",s+"commitWait"],
      i+"receive":[c+"lookup",i+"destination",i+"idle",i+"beginReceive",i+"deadline"],
      i+"payload":[u+"validateRead"],i+"destination":[u+"validateWrite"],i+"deadline":["Lemma.Kernel.MachineServices.time"],
      i+"stage":[s+"stagePayload",s+"packet",i+"stamp"],s+"stagePayload":[s+"transactionRow",u+"copyFromUser"],
      i+"beginReceive":[s+"prepare",i+"receivePacket",s+"commitWait",i+"receiveResult",i+"finish",i+"clear"],
      i+"receivePacket":[i+"receiveStep"],i+"receiveStep":[i+"receiveHead"],
      i+"receiveHead":[i+"checkedTransaction",o+"endpointQueue",s+"queuePeek",i+"destination",o+"replyFields","Lemma.Kernel.MachineServices.time",c+"retireReply",c+"grantReply",i+"copyHead"],
      i+"copyHead":[s+"queueCopyToUser",s+"queuePop"],i+"receiveResult":[s+"packet",s+"complete"],
      i+"callWait":[i+"checkedTransaction",s+"setWaitBuffer",i+"poll",i+"completeWait"],
      i+"completeWait":[s+"take",u+"copyToUser",i+"finish"],i+"finish":[s+"finish"],i+"clear":[s+"abort"],
      i+"reply":[c+"lookup",i+"replyCaller",i+"payload",i+"idle",i+"stageReply"],
      i+"replyCaller":[o+"replyFields"],i+"stageReply":[s+"packet",s+"prepare",i+"stage",s+"copyBytes",i+"commitReply"],
      i+"commitReply":["Lemma.Kernel.MachineServices.time",s+"complete",c+"retireReply",i+"clear"],
      i+"cancel":[i+"checkedTransaction",c+"retireReply"],i+"poll":[s+"pending",i+"pollWaiting"],
      i+"pollWaiting":["Lemma.Kernel.MachineServices.time",i+"expireCall",i+"receivePacket",i+"receiveResult",s+"take"],
      i+"expireCall":[c+"retireReply",s+"take"],i+"waitInfo":[i+"checkedTransaction"],
      i+"detach":[c+"cancelDescriptorReplies",i+"detachEndpointStep"],i+"detachEndpointStep":[o+"endpointQueue",s+"queueCancelSender",o+"invalidateEndpointWaits"],
      s+"initialize":[a+"base",s+"zeroStep"],s+"pending":[a+"base",s+"equalWord"],
      s+"transactionRow":[s+"pending"],s+"prepare":[s+"pending",u+"validateWrite",s+"put"],
      s+"setWaitBuffer":[s+"transactionRow",u+"validateWrite",s+"put"],
      s+"queueFrame":[f+"resolvePurpose",f+"mappingCount"],s+"queue":[s+"queueFrame",s+"queueCheckStep"],
      s+"queueCheckStep":[s+"wire",s+"uniqueSerialStep"],s+"queueEnqueue":[s+"queueAvailable",s+"pending",s+"wire",s+"queue",s+"copyBytes",s+"freeSlotStep",s+"put"],
      s+"queueCopyToUser":[a+"base",u+"validateWrite",s+"queuePeek",s+"copyBytes",u+"copyToUser"],
      s+"queuePop":[s+"queue",s+"queuePeek",s+"withdrawSlot"],s+"withdrawSlot":[s+"clearStep"],
      s+"queueCancelReply":[s+"queue",s+"cancelQueueStep"],s+"queueCancelSender":[s+"queue",s+"cancelQueueStep"],
      s+"complete":[s+"transactionRow",s+"put"],s+"finish":[s+"take",s+"reset"],s+"reset":[s+"resetStep"],
      s+"invalidateReply":[s+"invalidate"],s+"invalidateEndpoint":[s+"invalidate"],s+"invalidate":[s+"pending",s+"complete"],
      q+"dispatch":[t+"capture",q+"call"],q+"call":[y+"dispatch",i+"waitInfo",p+"syscallReply",t+"block",q+"returnKernel"],
      q+"step":[t+"reap",t+"wakeDue",t+"pollIPC",t+"select"],
      t+"block":[t+"lookup",c+"requireActive",t+"increment",x+"write64"],
      t+"savedContext":[t+"lookup",a+"root",a+"satp",a+"context",p+"validateStack"],
      t+"completeBlocked":[t+"savedContext",i+"completeWait",x+"write64"],
      t+"pollIPC":[t+"pollIPCStep"],t+"pollIPCStep":[t+"lookup",i+"poll",t+"completeBlocked"],
    }
    constants={c+"headerOffset":2560,c+"entriesOffset":2624,c+"capacity":16,c+"stride":64,
       o+"capacity":16,o+"endpointCapacity":4,o+"replyCapacity":8,o+"registryCapacity":8,o+"rows":256,o+"stride":128,
       o+"maxGeneration":0x0fffffffffffffff,o+"maxSerial":0x0fffffffffffffff,
       e+"primaryKeyOffset":160,a+"activeRoot":0x80400600,t+"capacity":8,t+"managedOffset":120,t+"waitEpochOffset":128,t+"waitTransactionOffset":136,
       t+"waitKindOffset":112,t+"deadlineOffset":16,t+"stateOffset":8,t+"pcOffset":48,t+"reasonOffset":24,t+"wakeTimeOffset":104,
       t+"blocked":5,t+"running":3,t+"runnable":2,t+"dying":6,
       s+"magic":0x31435049414d454c,s+"queueMagic":0x31455551414d454c,
       s+"metadataOffset":3648,s+"metadataBytes":128,s+"packetOffset":3776,s+"payloadOffset":3840,
       s+"maximumPacket":256,s+"maximumPayload":192,s+"maxTransaction":0x0fffffffffffffff,
       s+"stateIdle":0,s+"stateReserved":1,s+"stateWaiting":2,s+"stateReady":3,
       s+"sendOperation":1,s+"receiveOperation":2,s+"callOperation":3,s+"stateOffset":24,s+"operationOffset":32,
       s+"transactionOffset":40,s+"nextTransactionOffset":48,s+"endpointOffset":56,s+"replyOffset":64,
       s+"userVAOffset":72,s+"capacityOffset":80,s+"deadlineOffset":88,s+"resultStatusOffset":96,
       s+"resultBytesOffset":104,s+"resultSenderOffset":112,s+"resultReplyOffset":120,
       s+"queueSlots":4,s+"queueHeaderBytes":128,s+"queueStride":320,s+"queueSlotSerialOffset":8,
       s+"queueSlotSenderOffset":16,s+"queueSlotTransactionOffset":24,s+"queueSlotReplyOffset":32,
       s+"queueSlotBytesOffset":40,s+"queueSlotPacketOffset":64,
       b+"messageMagic":0x31504349414d454c,b+"magicOffset":0,b+"kindOffset":8,b+"senderOffset":16,b+"requestOffset":24,b+"replyOffset":32,b+"lengthOffset":40,b+"statusOffset":48,b+"reservedOffset":56,b+"send":20,b+"receive":21,b+"callBegin":22,b+"callWait":23,b+"reply":24,b+"cancel":25,b+"headerBytes":64,b+"maximumPayload":192,b+"maximumPacket":256,
       b+"sendKind":1,b+"callKind":2,b+"replyKind":3,b+"minimumTicks":1000,b+"maximumTicks":10000000,
       v+"endpointSend":4,v+"endpointReceive":8,v+"endpointCall":16,v+"replyRight":1,v+"replyType":5,v+"endpointType":2,v+"consoleType":1,v+"managementType":3}
    if service:
        edges={caller:callees for caller,callees in edges.items() if not caller.startswith(e)}
        constants={source:value for source,value in constants.items() if not source.startswith(e)}
    if current_context:
        edges[t+'savedContext']=[t+'lookup',a+'base',x+'read64',p+'validateStackAt']
        constants[a+'userContextOffset']=2048
        constants['Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue']=16384
    required=set(constants)|set(edges)|{value for values in edges.values() for value in values}
    if current_context:
        required |= {t+'fatal',t+'failed'}
    if not required<=set(by_source):
        raise Core0Error("IPC genuine lifecycle closure missing: "+str(sorted(required-set(by_source))))
    bodies={source:_ir_definition_body(pre_ir,by_source[source]) for source in required}
    rows={re.sub(r"^_private\..*?\.[0-9]+\.","",row['source']):row for row in unit['functions']}
    for source,value in constants.items():
        if rows[source]['args']!=[] or rows[source]['effects']!=[] or re.fullmatch(r"\s*entry:\s*ret i64 "+str(value)+r"\s*",bodies[source]) is None:
            raise Core0Error("IPC genuine storage/ABI constant differs: "+source)
    byte_constants={i+'blockedStatus':254,b+'wouldBlock':12,b+'queueFull':92,b+'timeout':93,b+'canceled':94,b+'peerDied':96,b+'invalidTransaction':97,b+'bufferTooSmall':98,b+'inFlight':99,b+'alreadyCompleted':100,b+'revoked':83,b+'invalidArgument':16}
    for source,value in byte_constants.items():
        if source not in by_source or re.fullmatch(r"\s*entry:\s*ret i8 "+str(value)+r"\s*",_ir_definition_body(pre_ir,by_source[source])) is None:
            raise Core0Error('IPC genuine byte status constant differs: '+source)
    observed=[]
    for caller,callees in edges.items():
        calls=parse_definitions_and_calls(bodies[caller])[2]
        for callee in callees:
            if by_source[callee] not in calls:
                raise Core0Error("IPC genuine source edge missing: "+caller+" -> "+callee)
            observed.append([caller,callee])
    ordered=[]
    for caller,before,after in [
      (t+"prepareManaged",t+"prepare",c+"attach"),(t+"activateManaged",c+"activate",t+"activate"),
      (t+"abort",t+"detachManaged","Lemma.Kernel.Loader.teardown"),(t+"reapOne",t+"detachManaged","Lemma.Kernel.Loader.teardown"),
      (t+"detachManaged",i+"detach",c+"detach"),(c+"attach",o+"register",s+"initialize"),
      (e+"configure",e+"initialGrants",e+"activate"),(e+"createFault",e+"retainedPrimary",t+"prepareManaged"),
      (e+"createFault",e+"grant",t+"activateManaged"),(c+"publish",o+"reference",o+"publishSerial"),
      (c+"retireReply",o+"beginReplyRevoke",s+"queueCancelReply"),(c+"retireReply",s+"queueCancelReply",s+"invalidateReply"),
      (c+"retireReply",s+"invalidateReply",o+"destroyReply"),(c+"revokeKey",c+"cancelEndpointReplies",o+"beginRevoke"),
      (c+"detach",c+"cancelDescriptorReplies",c+"ownedObjectStep"),(c+"detach",s+"detach",o+"unregister"),
      (o+"createEndpoint",s+"queueInitialize",o+"put"),
      (i+"callBegin",o+"replyAvailable",s+"prepare"),(i+"callBegin",o+"createReply",s+"queueEnqueue"),
      (i+"callBegin",s+"queueEnqueue",o+"markReplyQueued"),(i+"callBegin",o+"markReplyQueued",s+"commitWait"),
      (i+"receiveHead",i+"destination",c+"grantReply"),(i+"copyHead",s+"queueCopyToUser",s+"queuePop"),
      (i+"callWait",s+"setWaitBuffer",i+"completeWait"),
      (q+"step",t+"reap",t+"pollIPC"),(q+"step",t+"wakeDue",t+"pollIPC"),(q+"step",t+"pollIPC",t+"select"),
      (q+"call",i+"waitInfo",t+"block"),(q+"call",p+"syscallReply",t+"block"),
    ]:
        if service and caller.startswith(e):
            continue
        try: ordered.append({'source':caller,**validate_call_precedes(bodies[caller],by_source[before],by_source[after])})
        except Core0Error as error: raise Core0Error(caller+' ordered '+before+' -> '+after+': '+str(error)) from error
    checked=[]
    for caller,authority,protected in [
      (i+"send",c+"lookup",i+"payload"),(i+"send",i+"payload",s+"prepare"),(i+"send",s+"prepare",s+"queueEnqueue"),
      (i+"callBegin",c+"lookup",i+"payload"),(i+"callBegin",i+"payload",s+"prepare"),
      (i+"callBegin",i+"queueRoom",s+"prepare"),(i+"callBegin",o+"replyAvailable",s+"prepare"),
      (i+"receive",c+"lookup",i+"destination"),(i+"receive",i+"destination",i+"beginReceive"),
      (i+"reply",c+"lookup",i+"replyCaller"),(i+"reply",i+"replyCaller",i+"stageReply"),(i+"reply",i+"payload",i+"stageReply"),
      (i+"receiveHead",i+"destination",c+"grantReply"),(i+"copyHead",s+"queueCopyToUser",s+"queuePop"),
      (s+"queueCopyToUser",u+"validateWrite",s+"copyBytes"),(s+"setWaitBuffer",u+"validateWrite",s+"put"),
      (s+"queueEnqueue",s+"pending",s+"copyBytes"),(s+"queueEnqueue",s+"wire",s+"copyBytes"),
      (i+"stage",s+"stagePayload",i+"stamp"),(i+"stageReply",s+"copyBytes",i+"commitReply"),
      (c+"grantReply",c+"requireActive",c+"grant"),(c+"grantReply",o+"replyFields",c+"grant"),
      (t+"block",c+"requireActive",x+"write64"),(t+"completeBlocked",t+"savedContext",x+"write64"),(o+"createReply",o+"replyAvailable",o+"put"),
    ]:
        failed=caller.rsplit('.',1)[0]+'.failed'
        checked.append({'source':caller,**validate_failed_call_gate(bodies[caller],by_source[authority],by_source[protected],by_source[failed],_ir_definition_body(pre_ir,by_source[failed]))})
    checked.append({'source':i+'commitReply',**validate_failed_call_gate(bodies[i+'commitReply'],by_source[s+'complete'],by_source[c+'retireReply'],by_source[i+'failed'],_ir_definition_body(pre_ir,by_source[i+'failed']),checked_branch_only=True)})
    checked.append({'source':i+'completeWait',**validate_failed_call_gate(bodies[i+'completeWait'],by_source[u+'copyToUser'],by_source[i+'finish'],by_source[i+'failed'],_ir_definition_body(pre_ir,by_source[i+'failed']),checked_branch_only=True)})
    for protected in (y+'dispatchManaged',y+'dispatchLegacy'):
        checked.append({'source':y+'dispatch',**validate_checked_call_gate(bodies[y+'dispatch'],by_source[c+'managed'],by_source[protected])})
    checked.append({'source':y+'dispatch',**validate_checked_call_gate(bodies[y+'dispatch'],by_source[c+'managed'],by_source[y+'dispatchManaged'],component='value',value=1)})
    for protected in (y+'selectedConsoleRead',y+'consoleWrite'):
        checked.append({'source':y+'capConsole',**validate_checked_call_gate(bodies[y+'capConsole'],by_source[c+'lookup'],by_source[protected])})
    endpoint=validate_h_endpoint_budget(bodies[o+'createEndpoint'],by_source,pre_ir=pre_ir)
    reply_budget=validate_h_endpoint_budget(bodies[o+'replyAvailable'],by_source,reply=True,pre_ir=pre_ir)
    validate_object_budget(unit,pre_ir)
    denial=validate_h_legacy_console_denial(bodies[y+'dispatchManaged'],by_source)
    # Bind syscall arguments to the actual caller descriptor and closed operations.
    var=r'%[A-Za-z0-9_.$-]+'
    for operation,args in [('send',[0,2,3,4,5]),('receive',[0,2,3,4,5,6]),('callBegin',[0,2,3,4,5,6]),('callWait',[0,2,3,4]),('reply',[0,2,3,4,5]),('cancel',[0,2])]:
        arguments=', '.join('i64 %arg'+str(arg) for arg in args)
        matches=re.findall(r'call \{ i64, i64 \} @'+re.escape(by_source[i+operation])+r'\(([^\n]*)\)',bodies[i+'dispatch'])
        if matches!=[arguments]:raise Core0Error('IPC syscall changed descriptor or closed operand mapping: '+operation)
    managed_calls=re.findall(r'call \{ i64, i64 \} @'+re.escape(by_source[i+'dispatch'])+r'\(([^\n]*)\)',bodies[y+'dispatchManaged'])
    if managed_calls!=[', '.join('i64 %arg'+str(arg) for arg in range(7))]:
        raise Core0Error('managed IPC dispatcher changed actual caller identity/operands')
    authority_constants={by_source[source]:value for source,value in constants.items()}
    for operation,kind,right in [('send',2,4),('receive',2,8),('callBegin',2,16),('reply',5,1)]:
        body=bodies[i+operation];operands=_ipc_scalar_operands(body,authority_constants)
        lookups=re.findall(r'call \{ i64, i64 \} @'+re.escape(by_source[c+'lookup'])+r'\(i64 ([^,]+), i64 ([^,]+), i64 ([^,]+), i64 ([^)]+)\)',body)
        actual=[tuple(operands.get(value,int(value) if value.isdecimal() else value) for value in row) for row in lookups]
        if actual!=[('%arg0','%arg1',kind,right)]:raise Core0Error('IPC authority lookup changed caller-local descriptor/type/rights: '+operation)
    # Exact static image selection and source-selected grants; Busy gets none.
    variable=r'%[A-Za-z0-9_.$-]+'
    grants=[]
    if not service:
        preparations=lambda body:re.findall(r'call \{ i64, i64 \} @'+re.escape(by_source[t+'prepareManaged'])+r'\(i64 ([0-9]+),',body)
        if preparations(bodies[e+'launch'])!=['0','1','2','3'] or preparations(bodies[e+'createFault'])!=['4']:
            raise Core0Error('IPC boot roles changed exact selected image preparation')
        grants_body=bodies[e+'initialGrants']
        literal_symbols={by_source[o+'consoleKey']:16,by_source[o+'managementKey']:17,by_source[v+'consoleType']:1,by_source[v+'endpointType']:2,by_source[v+'managementType']:3}
        operands={result:literal_symbols[symbol] for result,symbol in re.findall(r'('+variable+r') = call i64 @([^ (]+)\(\)',grants_body) if symbol in literal_symbols}
        grants=[tuple(operands.get(value,int(value) if value.isdecimal() else value) for value in row) for row in re.findall(
           r'call \{ i64, i64 \} @'+re.escape(by_source[e+'grant'])+r'\(i64 ([^,]+), i64 ([^,]+), i64 ([^,]+), i64 ([^)]+)\)',grants_body)]
        expected_grants=[('%arg0',16,1,34),('%arg0','%arg3',2,8),('%arg1',16,1,34),('%arg1','%arg3',2,20),('%arg1','%arg4',2,124),('%arg1',17,3,928),('%arg1','%arg5',2,4),('%arg2',16,1,34),('%arg2','%arg3',2,20),('%arg2','%arg5',2,8)]
        if grants!=expected_grants:
            raise Core0Error('IPC initial grant descriptors/keys/kinds/rights/order differ')
        if re.findall(r'call \{ i64, i64 \} @'+re.escape(by_source[t+'activateManaged'])+r'\(i64 ('+variable+r')\)',bodies[e+'activate'])!=['%arg0','%arg1','%arg2','%arg3']:
            raise Core0Error('IPC managed activation role order differs')
    # Bound every mutable completion write; no PC256 write in wakeup.
    def result(body,source,component=1):
        call=re.findall(r'('+variable+r') = call \{ i64, i64 \} @'+re.escape(by_source[source])+r'\(',body)
        values=re.findall(r'('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(call[0] if len(call)==1 else 'NO_SINGLE_CALL')+', '+str(component)+r'$',body,re.M)
        if len(call)!=1 or len(values)!=1:raise Core0Error('IPC write binding lacks one genuine checked result')
        return values[0]
    constant_symbols={by_source[source]:value for source,value in constants.items()}
    publications=[]
    completion=bodies[s+'complete'];base=result(completion,s+'transactionRow')
    publications.append({'source':s+'complete',**validate_ipc_write_inventory(completion,by_source[s+'put'],constant_symbols,
       [(('add',base,96),'%arg2'),(('add',base,104),'%arg3'),(('add',base,112),'%arg4'),(('add',base,120),'%arg5'),(('add',base,24),3)],by_source[s+'failed'],_ir_definition_body(pre_ir,by_source[s+'failed']))})
    blocked=bodies[t+'block'];record=result(blocked,t+'lookup')
    publications.append({'source':t+'block',**validate_ipc_write_inventory(blocked,by_source[x+'write64'],constant_symbols,
       [(('add',record,136),'%arg1'),(('add',record,112),'%arg2'),(('add',record,16),'%arg3'),(('add',record,48),'%arg4'),(('add',record,24),6),(('add',record,8),5)],by_source[t+'failed'],_ir_definition_body(pre_ir,by_source[t+'failed']))})
    wake=bodies[t+'completeBlocked'];context=result(wake,t+'savedContext');status=result(wake,i+'completeWait',0)
    narrow=re.findall(r'('+variable+r') = trunc i64 '+re.escape(status)+r' to i8$',wake,re.M)
    wide=re.findall(r'('+variable+r') = zext i8 '+re.escape(narrow[0] if len(narrow)==1 else 'NO_SINGLE_NARROW')+r' to i64$',wake,re.M)
    if len(wide)!=1:raise Core0Error('IPC wakeup lost exact returned status widening')
    publications.append({'source':t+'completeBlocked',**validate_ipc_write_inventory(wake,by_source[x+'write64'],constant_symbols,
       [(('add',context,80),wide[0]),(('add',context,88),result(wake,i+'completeWait')),(('add','%arg0',16),0),(('add','%arg0',112),0),(('add','%arg0',136),0),(('add','%arg0',104),'%arg4'),(('add','%arg0',8),2)],by_source[t+'failed'],_ir_definition_body(pre_ir,by_source[t+'failed']))})
    field_gates=[]
    for address,expected in [(('add',record,8),3),(('add',record,120),1)]:
        field_gates.append({'source':t+'block',**validate_ipc_read_guard(blocked,by_source[x+'read64'],constant_symbols,address,expected,by_source[x+'write64'])})
    for address,expected in [(('add','%arg0',8),5),(('add','%arg0',128),'%arg2'),(('add','%arg0',136),'%arg3'),('%arg0','%arg1')]:
        field_gates.append({'source':t+'completeBlocked',**validate_ipc_read_guard(wake,by_source[x+'read64'],constant_symbols,address,expected,by_source[x+'write64'])})
    saved=bodies[t+'savedContext'];fresh_context=None
    if current_context:
        helpers=validate_fresh_descriptor_helpers(unit,pre_ir)
        fatal=_ir_definition_body(pre_ir,by_source[t+'fatal'])
        if re.fullmatch(r'\s*entry:\s*(%[A-Za-z0-9_.$-]+) = zext i8 50 to i64\s*(%[A-Za-z0-9_.$-]+) = insertvalue \{ i64, i64 \} poison, i64 \1, 0\s*(%[A-Za-z0-9_.$-]+) = insertvalue \{ i64, i64 \} \2, i64 0, 1\s*ret \{ i64, i64 \} \3\s*',fatal) is None:
            raise Core0Error('current IPC context failure does not return fatal50/value0')
        fresh_context=validate_current_ipc_saved_context(saved,by_source,constant_symbols,_ir_definition_body(pre_ir,by_source[t+'failed']))
        fresh_context['closed_stack_helpers']=helpers
        field_gates.extend({'source':t+'savedContext',**gate} for gate in fresh_context['loaded_field_gates'])
    else:
        saved_context=result(saved,a+'context');translation=result(saved,a+'satp')
        for address,expected in [(('add',saved_context,272),translation),(saved_context,0),(('add',saved_context,264),0x200000020)]:
            field_gates.append({'source':t+'savedContext',**validate_ipc_read_guard(saved,by_source[x+'read64'],constant_symbols,address,expected,by_source[p+'validateStack'])})
        field_gates.append({'source':t+'savedContext',**validate_ipc_read_guard(saved,by_source[x+'read64'],constant_symbols,0x80400600,result(saved,a+'root'),by_source[a+'context'],equal=False)})
    wake_status=result(wake,i+'completeWait',0)
    wake_narrow=re.findall(r'('+variable+r') = trunc i64 '+re.escape(wake_status)+r' to i8$',wake,re.M)
    if len(wake_narrow)!=1:raise Core0Error('IPC wakeup lacks returned checked status')
    blocked_value=re.findall(r'('+variable+r') = call zeroext i8 @'+re.escape(by_source[i+'blockedStatus'])+r'\(\)',wake)
    for forbidden in ['255',blocked_value[0] if len(blocked_value)==1 else 'NO_STATUS254']:
        comparisons=re.findall(r'('+variable+r') = icmp eq i8 '+re.escape(wake_narrow[0])+r', '+re.escape(forbidden)+r'$',wake,re.M)
        if len(comparisons)!=1:raise Core0Error('IPC wakeup lost fatal/internal status exclusion')
        field_gates.append({'source':t+'completeBlocked','forbidden_status':forbidden,**validate_boolean_gate(wake,comparisons[0],by_source[x+'write64'],success_when_true=False)})
    bridge=validate_ipc_block_bridge(bodies[q+'call'],by_source[y+'dispatch'],by_source[i+'waitInfo'],by_source[p+'syscallReply'],by_source[t+'block'],by_source[q+'returnKernel'],by_source[i+'blockedStatus'],by_source[q+'failed'],_ir_definition_body(pre_ir,by_source[q+'failed']))
    def read_result(body,source,address):
        values=_ipc_scalar_operands(body,constant_symbols)
        calls=[call for call,operand in re.findall(r'('+variable+r') = call \{ i64, i64 \} @'+re.escape(by_source[source])+r'\(i64 ([^\n)]+)\)',body)
               if values.get(operand,int(operand) if operand.isdecimal() else operand)==address]
        found=re.findall(r'('+variable+r') = extractvalue \{ i64, i64 \} '+re.escape(calls[0] if len(calls)==1 else 'NO_CALL')+r', 1$',body,re.M)
        if len(calls)!=1 or len(found)!=1:raise Core0Error('IPC field result binding missing exact checked load')
        return found[0]
    prepare=bodies[s+'prepare'];metadata=result(prepare,s+'pending');transaction=read_result(prepare,s+'get',('add',metadata,48))
    publications.append({'source':s+'prepare',**validate_ipc_write_inventory(prepare,by_source[s+'put'],constant_symbols,
      [(('add',metadata,32),'%arg1'),(('add',metadata,40),transaction),(('add',metadata,56),'%arg2'),(('add',metadata,72),'%arg3'),(('add',metadata,80),'%arg4'),(('add',metadata,88),'%arg5'),(('add',metadata,24),1)],by_source[s+'failed'],_ir_definition_body(pre_ir,by_source[s+'failed']))})
    commit=bodies[s+'commitWait'];metadata=result(commit,s+'transactionRow')
    publications.append({'source':s+'commitWait',**validate_ipc_write_inventory(commit,by_source[s+'put'],constant_symbols,
      [(('add',metadata,48),('add','%arg1',1)),(('add',metadata,24),2)],by_source[s+'failed'],_ir_definition_body(pre_ir,by_source[s+'failed']))})
    stamp=_ir_definition_body(pre_ir,by_source[i+'stamp'])
    publications.append({'source':i+'stamp',**validate_ipc_write_inventory(stamp,by_source[i+'put'],constant_symbols,
      [(('add','%arg0',0),0x31504349414d454c),(('add','%arg0',8),'%arg1'),(('add','%arg0',16),'%arg2'),(('add','%arg0',24),'%arg3'),(('add','%arg0',32),'%arg4'),(('add','%arg0',40),'%arg5'),(('add','%arg0',48),'%arg6'),(('add','%arg0',56),0)],by_source[i+'failed'],_ir_definition_body(pre_ir,by_source[i+'failed']))})
    enqueue=bodies[s+'queueEnqueue'];metadata=result(enqueue,s+'pending');queue=result(enqueue,s+'queue');bytes=result(enqueue,s+'wire')
    transaction=read_result(enqueue,s+'get',('add',metadata,40));serial=read_result(enqueue,s+'get',('add',queue,32));count=read_result(enqueue,s+'get',('add',queue,24))
    reserved=re.findall(r'call \{ i64, i64 \} @'+re.escape(by_source[s+'put'])+r'\(i64 ('+variable+r'), i64 2\)',enqueue)
    if len(reserved)!=1:raise Core0Error('IPC queue lacks one private withdrawn slot')
    slot=reserved[0]
    publications.append({'source':s+'queueEnqueue',**validate_ipc_write_inventory(enqueue,by_source[s+'put'],constant_symbols,
      [(slot,2),(('add',slot,8),serial),(('add',slot,16),'%arg2'),(('add',slot,24),transaction),(('add',slot,32),'%arg3'),(('add',slot,40),bytes),(('add',queue,32),('add',serial,1)),(('add',queue,24),('add',count,1)),(slot,1)],by_source[s+'failed'],_ir_definition_body(pre_ir,by_source[s+'failed']))})
    for source,reader,address,expected in [(s+'prepare',s+'get',('add',result(prepare,s+'pending'),24),0),
                                          (s+'commitWait',s+'get',('add',result(commit,s+'transactionRow'),24),1),
                                          (s+'complete',s+'get',('add',result(completion,s+'transactionRow'),24),2),
                                          (s+'queueEnqueue',s+'get',('add',result(enqueue,s+'pending'),24),1)]:
        field_gates.append({'source':source,**validate_ipc_read_guard(bodies[source],by_source[reader],constant_symbols,address,expected,by_source[s+'put'])})
    checked.append({'source':s+'queueEnqueue',**validate_failed_call_gate(enqueue,by_source[s+'copyBytes'],by_source[s+'put'],by_source[s+'failed'],_ir_definition_body(pre_ir,by_source[s+'failed']),checked_branch_only=True)})
    stage=bodies[i+'stage'];packet=result(stage,s+'packet')
    stamped=re.findall(r'call \{ i64, i64 \} @'+re.escape(by_source[i+'stamp'])+r'\(([^\n]*)\)',stage)
    if stamped!=['i64 '+packet+', i64 %arg4, i64 %arg0, i64 %arg5, i64 0, i64 %arg3, i64 %arg6']:
        raise Core0Error('IPC stamped packet sender/header fields lost actual caller binding')
    # Immutable context validation has no write or syscallReply edge. Completion
    # writes exactly a0/a1 and row bookkeeping, never savedPC or SATP.
    if by_source[x+'write64'] in parse_definitions_and_calls(bodies[t+'savedContext'])[2] or by_source[p+'syscallReply'] in parse_definitions_and_calls(wake)[2]:
        raise Core0Error('IPC saved context validation/wakeup mutates PC or registers unexpectedly')
    return {'managed_policy':BUFFER_POLICY if service else IPC_POLICY,'source_call_edges':observed,'source_constants':{source:{'symbol':by_source[source],'value':value} for source,value in sorted((constants|byte_constants).items())},
      'ordered_cfg_calls':ordered,'checked_cfg_gates':checked,'state_publications':publications,'loaded_field_gates':field_gates,'blocked_bridge':bridge,'initial_grants':grants,'endpoint_budget':endpoint,'reply_budget':reply_budget,'legacy_console_denial':denial,
      'capability_header_borrow':validate_capability_header_helpers(unit,pre_ir),
      **({'current_saved_context':fresh_context} if fresh_context else {}),
      'storage':{'descriptor_metadata':3648,'descriptor_metadata_bytes':128,'packet':3776,'packet_bytes':256,'payload':3840,'payload_bytes':192,'queue_slots':4,'queue_header_bytes':128,'queue_slot_bytes':320,'reply_capacity':8},
      'limitations':['Genuine compiled source/CFG/storage binding; independent model, full ELF audit and guest execution remain separate evidence.']}


def _service_minimum_operands(body: str) -> dict[str, object]:
    """Recognize only a closed, side-effect-free unsigned minimum diamond."""
    var=r'%[A-Za-z0-9_.$-]+';label=r'[A-Za-z0-9_.$-]+'
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks);values={}
    for merge,lines in blocks.items():
        for line in lines:
            phi=re.fullmatch(r'('+var+r') = phi i64 \[ ('+var+r'), %('+label+r') \], \[ ('+var+r'), %('+label+r') \]',line)
            if phi is None:
                continue
            result,left,yes,right,no=phi.groups()
            if blocks.get(yes)!=['br label %'+merge] or blocks.get(no)!=['br label %'+merge]:
                continue
            guards=[block for block,targets in successors.items() if targets==(yes,no) and len(blocks[block])>=2
                    and re.fullmatch(r'('+var+r') = icmp ule i64 '+re.escape(left)+r', '+re.escape(right),blocks[block][-2])
                    and blocks[block][-1]=='br i1 '+blocks[block][-2].split(' = ',1)[0]+', label %'+yes+', label %'+no]
            if len(guards)==1:
                values[result]=('unsigned-min',left,right)
    return values


def validate_dynamic_copy_gate(body: str, copy: str, protected: str) -> dict:
    """Bind actual copied bytes to that call's dynamic requested count."""
    var=r'%[A-Za-z0-9_.$-]+'
    calls=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(copy)+r'\(([^\n]*)\)',body)
    if len(calls)!=1:
        raise Core0Error('input copy count gate needs one exact checked call')
    result,arguments=calls[0];parts=arguments.split(', ')
    if len(parts)!=5 or any(not part.startswith('i64 ') for part in parts):
        raise Core0Error('input copy count gate argument shape differs')
    requested=parts[-1][4:]
    if not re.fullmatch(var,requested):
        raise Core0Error('input copy must retain the dynamic requested count')
    values=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(result)+r', 1$',body,re.M)
    minimums=_service_minimum_operands(body)
    comparisons=[comparison for comparison,expected in re.findall(
        r'('+var+r') = icmp eq i64 '+re.escape(values[0] if len(values)==1 else 'NO_VALUE')+r', ('+var+r')$',body,re.M)
        if minimums.get(expected,expected)==minimums.get(requested,requested)]
    if len(values)!=1 or len(comparisons)!=1:
        raise Core0Error('input copy advancement lacks actual copied==requested binding')
    return {'actual_count':values[0],'requested_count':requested,'requested_expression':minimums.get(requested,requested),
            **validate_boolean_gate(body,comparisons[0],protected)}


def validate_server_lease_scan(body: str, *, receive: str, time: str, expire: str, dispatch: str) -> dict:
    """Successful receive needs a fresh time and completed four-row expiry scan."""
    var=r'%[A-Za-z0-9_.$-]+';label=r'[A-Za-z0-9_.$-]+'
    clocks=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(time)+r'\(\)',body)
    if len(clocks)!=2:
        raise Core0Error('Server expiry needs both timeout and post-receive time samples')
    fresh=clocks[1]
    values=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(fresh)+r', 1$',body,re.M)
    if len(values)!=1:
        raise Core0Error('Server post-receive sample lacks actual time value')
    callbacks=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(expire)+
        r'\(i32 signext ('+var+r'), i32 signext 4, i64 ('+var+r'), i64 ('+var+r'), i64 ('+var+r'), i64 '+re.escape(values[0])+r', i64 0\)',body)
    if len(callbacks)!=1:
        raise Core0Error('Server post-receive expiry lacks the exact four-row fresh-time callback')
    callback,index,accumulator,console,identity=callbacks[0]
    renamed=body.replace(fresh+' = call { i64, i64 } @'+time+'(',fresh+' = call { i64, i64 } @service_fresh_time(')
    renamed=renamed.replace(callback+' = call { i64, i64 } @'+expire+'(',callback+' = call { i64, i64 } @service_fresh_expire(')
    ordered=validate_call_precedes(renamed,receive,'service_fresh_time')
    receive_gate=validate_checked_call_gate(renamed,receive,'service_fresh_time')
    time_gate=validate_checked_call_gate(renamed,'service_fresh_time','service_fresh_expire')
    callback_status=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(callback)+r', 0$',body,re.M)
    narrow=re.findall(r'('+var+r') = trunc i64 '+re.escape(callback_status[0] if len(callback_status)==1 else 'NO_STATUS')+r' to i8$',body,re.M)
    outcomes=re.findall(r'('+var+r') = phi i8 \[ 9, %('+label+r') \], \[ '+re.escape(narrow[0] if len(narrow)==1 else 'NO_NARROW')+r', %('+label+r') \], \[ 0, %('+label+r') \]',body)
    headers=re.findall(re.escape(index)+r' = phi i32 \[ 0, %('+label+r') \], \[ ('+var+r'), %('+label+r') \]',body)
    comparisons=re.findall(r'('+var+r') = icmp eq i8 '+re.escape(outcomes[0][0] if len(outcomes)==1 else 'NO_OUTCOME')+r', 0$',body,re.M)
    if (len(narrow)!=1 or len(outcomes)!=1 or len(headers)!=1 or len(comparisons)!=1
            or re.search(re.escape(headers[0][1])+r' = add i32 '+re.escape(index)+r', 1$',body,re.M) is None
            or len(re.findall(r'icmp ult i32 '+re.escape(index)+r', 4$',body,re.M))!=1):
        raise Core0Error('Server post-receive scan lost its bounded status/completion shape')
    completed=validate_boolean_gate(body,comparisons[0],dispatch)
    # The dispatch must also remain on successful receive, even though the
    # timeout branch returns ordinary success after its separate initial scan.
    dispatch_gate=validate_checked_call_gate(body,receive,dispatch)
    return {'time_sample':fresh,'time_value':values[0],'callback':callback,'scan_rows':4,
            'receive_before_sample':ordered,'successful_receive_gate':receive_gate,
            'successful_time_gate':time_gate,'completed_scan_gate':completed,'dispatch_receive_gate':dispatch_gate}


def validate_fixed_fold(body: str, callback: str, count: int) -> dict:
    """Check one emitted zero-based callback loop with its closed iteration bound."""
    var=r'%[A-Za-z0-9_.$-]+';label=r'[A-Za-z0-9_.$-]+'
    calls=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(callback)+r'\(i32 signext ('+var+r'), i32 signext '+str(count)+r', i64 ('+var+r'),',body)
    if len(calls)!=1:
        raise Core0Error('service callback lacks one exact bounded fold: '+callback)
    result,index,accumulator=calls[0]
    headers=re.findall(re.escape(index)+r' = phi i32 \[ 0, %('+label+r') \], \[ ('+var+r'), %('+label+r') \]',body)
    continues=re.findall(r'('+var+r') = icmp ult i32 '+re.escape(index)+r', '+str(count)+r'$',body,re.M)
    if (len(headers)!=1 or len(continues)!=1 or re.search(re.escape(headers[0][1])+r' = add i32 '+re.escape(index)+r', 1$',body,re.M) is None):
        raise Core0Error('service fixed fold index or iteration bound differs')
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    preheader,next_index,latch=headers[0]
    header=[block for block,lines in blocks.items() if any(line.startswith(index+' = phi i32 ') for line in lines)]
    callback_block=[block for block,lines in blocks.items() if any(line.startswith(result+' = call ') for line in lines)]
    if len(header)!=1 or len(callback_block)!=1 or len(successors.get(header[0],()))!=2:
        raise Core0Error('service fixed fold lacks its actual loop blocks')
    actual_body,done=successors[header[0]]
    if (actual_body!=callback_block[0] or blocks[header[0]][-1]!='br i1 '+continues[0]+', label %'+actual_body+', label %'+done
            or blocks.get(preheader)!=['br label %'+header[0]]
            or blocks.get(latch)!=[next_index+' = add i32 '+index+', 1','br label %'+header[0]]
            or {block for block,targets in successors.items() if header[0] in targets}!={preheader,latch}
            or {block for block,targets in successors.items() if actual_body in targets}!={header[0]}
            or {block for block,targets in successors.items() if done in targets}!={header[0]}):
        raise Core0Error('service fixed fold has a skipped or redirected iteration edge')
    return {'callback':callback,'count':count,'index':index,'result':result,'accumulator':accumulator}


def validate_server_application_expiry(body: str, *, time: str, expire: str,
                                       create: str, existing: str, lease: str) -> dict:
    """Creation/renewal uses the same fresh clock as its completed expiry scan."""
    var=r'%[A-Za-z0-9_.$-]+';label=r'[A-Za-z0-9_.$-]+'
    clocks=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(time)+r'\(\)',body)
    times=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(clocks[0] if len(clocks)==1 else 'NO_TIME')+r', 1$',body,re.M)
    if len(clocks)!=1 or len(times)!=1:
        raise Core0Error('Server application requires one actual fresh checked time')
    now=times[0]
    fold=validate_fixed_fold(body,expire,4)
    callbacks=re.findall(r'call \{ i64, i64 \} @'+re.escape(expire)+r'\(([^\n]*)\)',body)
    if callbacks!=['i32 signext '+fold['index']+', i32 signext 4, i64 '+fold['accumulator']+', i64 %arg0, i64 %arg1, i64 '+now+', i64 0']:
        raise Core0Error('Server application scan substitutes its fresh time/identity')
    status=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(fold['result'])+r', 0$',body,re.M)
    narrow=re.findall(r'('+var+r') = trunc i64 '+re.escape(status[0] if len(status)==1 else 'NO_STATUS')+r' to i8$',body,re.M)
    outcomes=re.findall(r'('+var+r') = phi i8 \[ 9, %('+label+r') \], \[ '+re.escape(narrow[0] if len(narrow)==1 else 'NO_NARROW')+r', %('+label+r') \], \[ 0, %('+label+r') \]',body)
    comparisons=re.findall(r'('+var+r') = icmp eq i8 '+re.escape(outcomes[0][0] if len(outcomes)==1 else 'NO_OUTCOME')+r', 0$',body,re.M)
    if len(status)!=1 or len(narrow)!=1 or len(outcomes)!=1 or len(comparisons)!=1:
        raise Core0Error('Server application lacks exact successful scan completion')
    scanned=re.findall(r'('+var+r') = phi i64 \[ 0, %'+re.escape(outcomes[0][1])+r' \], \[ '+var+r', %'+re.escape(outcomes[0][2])+r' \], \[ '+re.escape(fold['accumulator'])+r', %'+re.escape(outcomes[0][3])+r' \]',body)
    scan_bounds=re.findall(r'('+var+r') = icmp ule i64 '+re.escape(scanned[0] if len(scanned)==1 else 'NO_SCANNED')+r', 4$',body,re.M)
    if len(scanned)!=1 or len(scan_bounds)!=1:
        raise Core0Error('Server application lost completed scan count bound')
    lease_values={value for value in re.findall(r'('+var+r') = call i64 @'+re.escape(lease)+r'\(\)',body)}
    deadline_values={value for value,left,right in re.findall(r'('+var+r') = add i64 ('+var+r'), ('+var+r')$',body,re.M)
                     if left==now and right in lease_values}
    gates=[]
    for protected,arity in [(create,7),(existing,9)]:
        calls=re.findall(r'call \{ i64, i64 \} @'+re.escape(protected)+r'\(([^\n]*)\)',body)
        if len(calls)!=1 or len(calls[0].split(', '))!=arity or calls[0].split(', ')[-1][4:] not in deadline_values:
            raise Core0Error('Server application renewal/create deadline lost same-time binding')
        gates.append({'protected':protected,'time_status':validate_checked_call_gate(body,time,protected),
          'time_before_scan':validate_call_precedes(body,time,expire),
          'time_status_before_scan':validate_checked_call_gate(body,time,expire),
          'completed_scan':validate_boolean_gate(body,comparisons[0],protected),
          'bounded_scan_value':validate_boolean_gate(body,scan_bounds[0],protected)})
    return {'scan_rows':4,'same_time_value':now,'fold':fold,'deadline_expression':['add',now,'leaseTicks'],
            'application_gates':gates}


def validate_service_reuse(body: str, *, grant: str, stop: str) -> dict:
    """The iterationStop hit returns the existing handle without grant effects."""
    var=r'%[A-Za-z0-9_.$-]+';label=r'[A-Za-z0-9_.$-]+'
    stopped=re.findall(r'('+var+r') = call zeroext i8 @'+re.escape(stop)+r'\(\)',body)
    conditions=re.findall(r'('+var+r') = icmp eq i8 ('+var+r'), '+re.escape(stopped[0] if len(stopped)==1 else 'NO_STOP')+r'$',body,re.M)
    if len(stopped)!=1 or len(conditions)!=1:
        raise Core0Error('discovery reuse lacks exact stopped-loop status')
    comparison,status=conditions[0];blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    branch=[block for block,lines in blocks.items() if lines[-1].startswith('br i1 '+comparison+', ')]
    if len(branch)!=1:
        raise Core0Error('discovery reuse lacks one actual status branch')
    success,failure=successors[branch[0]]
    if len(blocks[success])!=1 or not blocks[success][0].startswith('br label %'):
        raise Core0Error('discovery reuse success invokes an unexpected helper')
    merge=successors[success][0];lines=blocks[merge]
    values=re.findall(r'('+var+r') = phi i64 \[ 0, %'+label+r' \], \[ '+var+r', %'+label+r' \], \[ '+var+r', %'+label+r' \]',body)
    if len(values)!=1 or len(lines)<2 or re.search(r'phi i8 \[ 0, %'+re.escape(success)+r' \]',lines[0]) is None or re.search(r'phi i64 \[ '+re.escape(values[0])+r', %'+re.escape(success)+r' \]',lines[1]) is None:
        raise Core0Error('discovery reuse does not return the existing checked handle/status0')
    gate=validate_boolean_gate(body,comparison,grant,success_when_true=False)
    return {'reuse_branch':success,'existing_handle':values[0],'mutation_exclusion':gate}


def validate_input_read_inventory(body: str, *, get: str, put: str, copy: str,
                                  table: str, snapshot: str, failed: str,
                                  failed_body: str, constants: dict[str,int]) -> dict:
    """Exactly the copied minimum advances head/count in the validated frame."""
    var=r'%[A-Za-z0-9_.$-]+';label=r'[A-Za-z0-9_.$-]+'
    scalars=_ipc_scalar_operands(body,constants);minimums=_service_minimum_operands(body)
    def word_call(symbol,arguments):
        rows=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(symbol)+r'\(([^\n]*)\)',body)
        calls=[result for result,args in rows if args==arguments]
        values=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(calls[0] if len(calls)==1 else 'NO_CALL')+r', 1$',body,re.M)
        if len(calls)!=1 or len(values)!=1:raise Core0Error('input inventory lacks one exact checked field/call')
        return values[0]
    base=word_call(table,'')
    def field(offset):
        calls=[result for result,address in re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(get)+r'\(i64 ([^\n)]+)\)',body)
               if scalars.get(address,address)==('add',base,offset)]
        values=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(calls[0] if len(calls)==1 else 'NO_FIELD')+r', 1$',body,re.M)
        if len(calls)!=1 or len(values)!=1:raise Core0Error('input read field inventory changed')
        return values[0]
    available,head,handle=field(48),field(40),field(24)
    canonical=('unsigned-min','%arg2',available)
    def minimum(value):return minimums.get(value,value)
    copies=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(copy)+r'\(([^\n]*)\)',body)
    if len(copies)!=1:raise Core0Error('input read lost its one range copy')
    arguments=copies[0][1].split(', ')
    if (len(arguments)!=5 or arguments[:3]!=['i64 %arg0','i64 %arg1','i64 '+handle]
            or scalars.get(arguments[3][4:])!=832 or minimum(arguments[4][4:])!=canonical):
        raise Core0Error('input copy source handle/scratch/minimum inventory changed')
    snapshots=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(snapshot)+r'\(([^\n]*)\)',body)
    if len(snapshots)!=1:raise Core0Error('input read lost its one bounded snapshot')
    snapshot_arguments=snapshots[0][1].split(', ')
    loop_bound=re.findall(r'('+var+r') = icmp ult i32 ('+var+r'), ('+var+r')$',body,re.M)
    truncations={value:operand for value,operand in re.findall(r'('+var+r') = trunc i64 ('+var+r') to i32$',body,re.M)}
    if (len(snapshot_arguments)!=7 or len(loop_bound)!=1 or snapshot_arguments[1]!='i32 signext '+loop_bound[0][2]
            or snapshot_arguments[3:]!=['i64 '+base,'i64 '+head,'i64 0','i64 0']
            or minimum(truncations.get(loop_bound[0][2],''))!=canonical
            or len(re.findall(r'icmp ule i32 '+re.escape(loop_bound[0][2])+r', 256$',body,re.M))!=1):
        raise Core0Error('input snapshot budget/index/owned source differs')
    writes=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(put)+r'\(i64 ([^,\n]+), i64 ([^\n)]+)\)',body)
    if len(writes)!=2 or [scalars.get(address,address) for _,address,_ in writes]!=[('add',base,40),('add',base,48)]:
        raise Core0Error('input advancement mutable field inventory differs')
    head_value,count_value=writes[0][2],writes[1][2]
    sub=re.findall(re.escape(count_value)+r' = sub i64 ('+var+r'), ('+var+r')$',body,re.M)
    if len(sub)!=1 or sub[0][0]!=available or minimum(sub[0][1])!=canonical:
        raise Core0Error('input count subtraction does not consume exactly the copied minimum')
    phis=re.findall(re.escape(head_value)+r' = phi i64 \[ ('+var+r'), %('+label+r') \], \[ ('+var+r'), %('+label+r') \]',body)
    if len(phis)!=1:raise Core0Error('input head lacks the genuine modulo diamond')
    added,zero_block,remainder,nonzero_block=phis[0]
    additions=re.findall(re.escape(added)+r' = add i64 ('+var+r'), ('+var+r')$',body,re.M)
    remainders=re.findall(re.escape(remainder)+r' = urem i64 '+re.escape(added)+r', ('+var+r')$',body,re.M)
    if len(additions)!=1 or additions[0][0]!=head or minimum(additions[0][1])!=canonical or len(remainders)!=1 or scalars.get(remainders[0])!=512:
        raise Core0Error('input head does not wrap actual head+copied count at512')
    blocks=_structured_ir_blocks(body);successors=_structured_successors(blocks)
    conditions=re.findall(r'('+var+r') = icmp eq i64 '+re.escape(remainders[0])+r', 0$',body,re.M)
    guards=[block for block,lines in blocks.items() if lines[-1]=='br i1 '+(conditions[0] if len(conditions)==1 else 'NO_CONDITION')+', label %'+zero_block+', label %'+nonzero_block]
    merged=[block for block,lines in blocks.items() if any(line.startswith(head_value+' = phi ') for line in lines)]
    if (len(guards)!=1 or len(merged)!=1 or blocks[zero_block]!=['br label %'+merged[0]]
            or blocks[nonzero_block]!=[remainder+' = urem i64 '+added+', '+remainders[0],'br label %'+merged[0]]
            or {block for block,targets in successors.items() if zero_block in targets}!={guards[0]}
            or {block for block,targets in successors.items() if nonzero_block in targets}!={guards[0]}):
        raise Core0Error('input head modulo has an alternate entry or changed zero-divisor shape')
    renamed=body.replace(writes[0][0]+' = call { i64, i64 } @'+put+'(',writes[0][0]+' = call { i64, i64 } @service_first_advance(')
    renamed=renamed.replace(writes[1][0]+' = call { i64, i64 } @'+put+'(',writes[1][0]+' = call { i64, i64 } @service_second_advance(')
    return {'source_frame':base,'source_handle':handle,'copied_count_expression':canonical,
      'head':['urem',['add',head,canonical],512],'count':['sub',available,canonical],
      'writes':2,'successful_head_before_count':validate_failed_call_gate(renamed,'service_first_advance','service_second_advance',failed,failed_body)}


def validate_service_graph(unit: dict, pre_ir: str) -> dict:
    """Closed Buffer boot/Directory/input source and CFG artifact obligations.

    These structural checks are necessary evidence, separate from model proofs,
    compiler correctness and independently observed input/service execution.
    """
    configuration=unit.get('configuration')
    if configuration not in SERVICE_CONFIGURATIONS or unit.get('role')!='kernel':
        raise Core0Error('service graph requires the exact selected kernel unit')
    common=validate_ipc_graph(unit,pre_ir)
    rows={re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']):r for r in unit['functions']}
    by={source:r['symbol'] for source,r in rows.items()}
    e='Lemma.Kernel.ServiceEntry.';d='Lemma.Kernel.Directory.';n='Lemma.Kernel.KernelInput.'
    o='Lemma.Kernel.Objects.';c='Lemma.Kernel.Capability.';t='Lemma.Kernel.Task.';y='Lemma.Kernel.Syscall.'
    u='Lemma.Kernel.Memory.UserCopy.';a='Lemma.Kernel.Memory.AddressSpace.';f='Lemma.Kernel.Memory.Frames.'
    x='Lemma.Kernel.Memory.Access.';q='Lemma.Kernel.Scheduler.';v='Lemma.User.CapabilityABI.'
    selected=e if configuration=='service-normal' else 'Lemma.Kernel.Development.ServiceEntry.'
    edges={
      selected+('siliconBoot' if configuration=='silicon-service-development' else 'boot'):
          [e+('initializeFor' if configuration=='silicon-service-development' else 'initialize'),e+'construct'],selected+'dispatch':[q+'dispatch'],
      e+'initializeFor':['Lemma.Kernel.BootServices.bootServicesFor',o+'init',o+'serviceInitialize',n+'init'],
      e+'construct':[e+'serverBudget',d+'nextEpoch',t+'prepareManaged',e+'configure'],
      e+'serverBudget':['Lemma.Kernel.Loader.validate',x+'read64'],
      e+'configure':[e+'createEndpoint',e+'grants',d+'preflightPublish',n+'bindReader',t+'activateManaged',e+'activatePublished'],
      e+'grants':[e+'grant'],e+'grant':[c+'grantBoot'],e+'createEndpoint':[o+'createEndpoint'],
      e+'activatePublished':[t+'activateManaged',d+'publish'],
      d+'nextEpoch':[d+'epoch'],d+'epoch':[o+'serviceBinding',o+'get'],
      d+'preflightPublish':[o+'serviceBinding',d+'nextEpoch',c+'entryCount',o+'resolve'],
      d+'publish':[d+'preflightPublish',c+'requireActive',o+'publishServiceBinding'],
      d+'current':[o+'serviceBinding',c+'requireActive',o+'resolve',o+'get'],
      d+'discover':[c+'lookup',d+'current',c+'grantDiscovered',d+'epoch',c+'activeRegisteredCount',f+'remaining'],
      o+'serviceBinding':[o+'table',a+'base',o+'registrySlot',o+'resolveRevoking'],
      o+'serviceInitialize':[o+'serviceBinding',o+'put'],
      o+'publishServiceBinding':[o+'serviceBinding',a+'base',o+'registrySlot',o+'resolve',o+'put'],
      o+'withdrawService':[o+'serviceBinding',o+'put'],
      o+'beginRevoke':[o+'withdrawService',o+'put'],o+'destroy':[o+'withdrawService',o+'invalidateEndpointWaits',f+'release'],
      c+'grantDiscovered':[c+'requireActive',o+'resolve',c+'entryCount',c+'discoveredStep',c+'grant'],
      c+'discoveredStep':[o+'get',c+'lookupEntry'],c+'activeRegisteredCount':[c+'activeRegisteredStep'],
      c+'activeRegisteredStep':[o+'registryDescriptor',c+'header',o+'get'],
      y+'dispatchManaged':[d+'discover'],y+'selectedConsoleRead':[n+'mode',y+'consoleRead',n+'read'],
      n+'init':[n+'get',f+'allocate',f+'resolvePurpose',n+'put'],
      n+'table':[n+'get',f+'resolvePurpose',f+'mappingCount',n+'bodyValid'],
      n+'mode':[n+'get',n+'table'],n+'bindReader':[a+'base',n+'table',n+'get',n+'put'],
      n+'poll':[n+'table',n+'flushPending',n+'pollStep'],
      n+'pollStep':[n+'flushPending','Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep',n+'acceptByte'],
      n+'flushPending':[n+'get',n+'ringPublishStep',n+'diagnosticPublishStep',n+'put',n+'resetParser'],
      n+'ringPublishStep':[x+'read8',x+'write8'],n+'diagnosticPublishStep':[x+'read8',x+'write8'],
      n+'acceptByte':[n+'acceptHeaderByte',n+'get',x+'write8',n+'put'],
      n+'read':[u+'validateWrite',n+'table',n+'get',n+'snapshotStep',u+'copyToUser',n+'put'],
      n+'snapshotStep':[x+'read8',x+'write8'],
    }
    if configuration=='service-normal':
        edges[e+'step']=[n+'poll',q+'step']
        forbidden=[source for source in rows if source.startswith('Lemma.Kernel.Development.') or service_executable_module(source)]
        if forbidden:
            raise Core0Error('normal service reaches a development policy or User executable: '+str(forbidden))
    else:
        edges[selected+'step']=[n+'poll',selected+'diagnostic',q+'step',selected+'completeRestart']
        edges[selected+'diagnostic']=[n+'diagnosticPacket',n+'consumeDiagnostic',selected+'command']
        edges[selected+'replacement']=[selected+'stableKernel',d+'nextEpoch',t+'prepareManaged',e+'createEndpoint',e+'grant',d+'preflightPublish',e+'activatePublished']
        edges[selected+'stopServer']=[selected+'stableKernel',d+'server',t+'lookup',t+'terminate',t+'reap']
        edges[selected+'intercept']=[o+'replyFields', 'Lemma.Kernel.IPCStorage.pending',t+'lookup',c+'requireActive','Lemma.Kernel.MachineServices.time',t+'terminate',q+'returnKernel']
    if configuration!='silicon-service-development': edges[e+'initialize']=[e+'initializeFor']
    constants={o+'serviceMagic':0x31565253414d454c,o+'serviceOffset':224,o+'serviceEpochOffset':232,o+'serviceKeyOffset':240,o+'serviceOwnerOffset':248,
       n+'control':0x80400660,n+'magic':0x31504e49414d454c,n+'frameVersion':1,
       n+'ringOffset':128,n+'ringCapacity':512,n+'pendingOffset':640,n+'pendingCapacity':168,
       n+'scratchOffset':832,n+'diagnosticOffset':1088,n+'diagnosticBytes':40,
       n+'readerOffset':32,n+'headOffset':40,n+'countOffset':48,n+'stateOffset':56,n+'headerOffset':64,n+'headerCountOffset':72,
       n+'classOffset':80,n+'lengthOffset':88,n+'receivedOffset':96,n+'diagnosticReadyOffset':104,
       n+'headerState':0,n+'bodyState':1,n+'pendingState':2,d+'serviceID':1,v+'endpointCall':16,v+'directoryType':4,v+'directoryDiscover':1024}
    if configuration=='silicon-service-development':
        constants['Lemma.Platform.Silicon.Binding.boot_timer_probe_ticks']=10000
    required=set(constants)|set(edges)|{callee for callees in edges.values() for callee in callees}
    if not required<=by.keys():
        raise Core0Error('service genuine closure missing: '+str(sorted(required-by.keys())))
    bodies={source:_ir_definition_body(pre_ir,by[source]) for source in required}
    for source,value in constants.items():
        # Layout authority may be a zero-argument scalar call, never a pointer.
        body=bodies[source]
        if source==n+'control':
            layout='Lemma.Platform.LemmaVM.Layout.inputControlValue'
            if layout not in by or not re.fullmatch(r'\s*entry:\s*ret i64 '+str(value)+r'\s*',_ir_definition_body(pre_ir,by[layout])):
                raise Core0Error('input control lacks authoritative Layout value')
            if re.fullmatch(r'\s*entry:\s*%call0 = call i64 @'+re.escape(by[layout])+r'\(\)\s*ret i64 %call0\s*',body) is None:
                raise Core0Error('input control differs from Layout authority')
        elif rows[source]['args'] or rows[source]['effects'] or re.fullmatch(r'\s*entry:\s*ret i64 '+str(value)+r'\s*',body) is None:
            raise Core0Error('service storage constant differs: '+source)
    observed=[]
    for caller,callees in edges.items():
        calls=parse_definitions_and_calls(bodies[caller])[2]
        for callee in callees:
            if by[callee] not in calls:
                raise Core0Error('service source edge missing: '+caller+' -> '+callee)
            observed.append([caller,callee])
    ordered=[]
    for caller,before,after in [
      (e+'initializeFor','Lemma.Kernel.BootServices.bootServicesFor',n+'init'),(e+'initializeFor',o+'serviceInitialize',n+'init'),
      (e+'construct',e+'serverBudget',t+'prepareManaged'),(e+'configure',e+'grants',d+'preflightPublish'),
      (e+'configure',d+'preflightPublish',n+'bindReader'),(e+'configure',n+'bindReader',t+'activateManaged'),
      (e+'configure',t+'activateManaged',e+'activatePublished'),(e+'activatePublished',t+'activateManaged',d+'publish'),
      (o+'beginRevoke',o+'withdrawService',o+'put'),(o+'destroy',o+'withdrawService',o+'invalidateEndpointWaits'),
      (o+'destroy',o+'withdrawService',f+'release'),(d+'publish',d+'preflightPublish',c+'requireActive'),
      (d+'publish',c+'requireActive',o+'publishServiceBinding'),
      (n+'read',u+'validateWrite',n+'snapshotStep'),(n+'read',u+'validateWrite',u+'copyToUser'),
    ]:
        ordered.append({'source':caller,**validate_call_precedes(bodies[caller],by[before],by[after])})
    checked=[]
    for caller,authority,protected in [
      (d+'discover',c+'lookup',d+'current'),(d+'discover',d+'current',c+'grantDiscovered'),
      (d+'publish',d+'preflightPublish',o+'publishServiceBinding'),(d+'publish',c+'requireActive',o+'publishServiceBinding'),
      (c+'grantDiscovered',c+'requireActive',c+'grant'),(c+'grantDiscovered',o+'resolve',c+'grant'),
      (n+'read',u+'validateWrite',n+'snapshotStep'),(n+'read',u+'validateWrite',u+'copyToUser'),
      (n+'read',u+'copyToUser',n+'put'),(n+'bindReader',a+'base',n+'put'),
      (y+'selectedConsoleRead',n+'mode',y+'consoleRead'),(y+'selectedConsoleRead',n+'mode',n+'read'),
      (e+'configure',d+'preflightPublish',t+'activateManaged'),(e+'configure',n+'bindReader',t+'activateManaged'),
    ]:
        failure=caller.rsplit('.',1)[0]+'.failed'
        checked.append({'source':caller,**validate_failed_call_gate(bodies[caller],by[authority],by[protected],by[failure],_ir_definition_body(pre_ir,by[failure]))})
    var=r'%[A-Za-z0-9_.$-]+'
    read=bodies[n+'read']
    if re.findall(r'call \{ i64, i64 \} @'+re.escape(by[u+'validateWrite'])+r'\(([^\n]*)\)',read)!=['i64 %arg0, i64 %arg1, i64 %arg2']:
        raise Core0Error('input preflight changed complete offered range/caller')
    copy_args=re.findall(r'call \{ i64, i64 \} @'+re.escape(by[u+'copyToUser'])+r'\(([^\n]*)\)',read)
    if len(copy_args)!=1 or not copy_args[0].startswith('i64 %arg0, i64 %arg1, i64 '):
        raise Core0Error('input copy changed actual caller or destination')
    count_gate=validate_dynamic_copy_gate(read,by[u+'copyToUser'],by[n+'put'])
    # Reader is the full generation-tagged descriptor; no image/owner selector.
    input_result=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[n+'table'])+r'\(\)',read)
    base=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(input_result[0] if len(input_result)==1 else 'NO_TABLE')+r', 1$',read,re.M)
    constants_by={by[source]:value for source,value in constants.items()}
    advancement=validate_input_read_inventory(read,get=by[n+'get'],put=by[n+'put'],copy=by[u+'copyToUser'],
        table=by[n+'table'],snapshot=by[n+'snapshotStep'],failed=by[n+'failed'],
        failed_body=_ir_definition_body(pre_ir,by[n+'failed']),constants=constants_by)
    if len(base)!=1:
        raise Core0Error('input read lacks one validated owned frame')
    reader_gate=validate_ipc_read_guard(read,by[n+'get'],constants_by,('add',base[0],32),'%arg0',by[u+'copyToUser'])
    initialized=bodies[n+'init']
    allocated=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[f+'allocate'])+r'\(i64 1, i64 1\)',initialized)
    allocated_handle=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(allocated[0] if len(allocated)==1 else 'NO_ALLOCATION')+r', 1$',initialized,re.M)
    resolved=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[f+'resolvePurpose'])+r'\(i64 1, i64 '+re.escape(allocated_handle[0] if len(allocated_handle)==1 else 'NO_HANDLE')+r', i64 1\)',initialized)
    resolved_base=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(resolved[0] if len(resolved)==1 else 'NO_RESOLVE')+r', 1$',initialized,re.M)
    if len(allocated)!=1 or len(allocated_handle)!=1 or len(resolved)!=1 or len(resolved_base)!=1:
        raise Core0Error('input initialization lacks its actual owner1/purpose1 allocated frame')
    initialization=validate_ipc_write_inventory(initialized,by[n+'put'],constants_by,
        [(('add',resolved_base[0],8),1),(('add',resolved_base[0],16),'%arg0'),
         (('add',resolved_base[0],24),allocated_handle[0]),(resolved_base[0],0x31504e49414d454c),
         (0x80400660,allocated_handle[0])],by[n+'failed'],_ir_definition_body(pre_ir,by[n+'failed']))
    initialization['zero_control_before_allocation']=validate_ipc_read_guard(initialized,by[n+'get'],constants_by,0x80400660,0,by[f+'allocate'])
    initialization['resolved_before_publication']=validate_failed_call_gate(initialized,by[f+'resolvePurpose'],by[n+'put'],by[n+'failed'],_ir_definition_body(pre_ir,by[n+'failed']))
    # The only source-level getters of this authoritative control constant are
    # validation, mode, one-time initialization, and common boot clearing.
    # Indirect computed address semantics remain a separate source/ELF obligation.
    control_sources={n+'table',n+'mode',n+'init','Lemma.Kernel.BootServices.bootServicesFor'}
    control_symbols={by[n+'control'],by['Lemma.Platform.LemmaVM.Layout.inputControlValue']}
    all_bodies={match[1]:match[2] for match in re.finditer(r'(?ms)^define[^\n]*@([^( ]+)\([^\n]*\)[^\n]*\{\n(.*?)^\}',pre_ir)}
    if not set(by.values())<=all_bodies.keys():
        raise Core0Error('input control inventory cannot read every genuine definition')
    control_users={source for source,symbol in by.items() if source!=n+'control'
                   and any('@'+control+'(' in all_bodies[symbol] for control in control_symbols)}
    if control_users!=control_sources:
        raise Core0Error('input control authority has unexpected source-level users: '+str(sorted(control_users)))
    initialization['control_source_users']=sorted(control_users)
    # Every recomputed unsigned minimum has the same two immutable operands.
    # The offered length, copied count and actual available ring count cannot
    # be replaced by a constant or a smaller preflight range.
    minimums=_service_minimum_operands(read)
    requested=count_gate['requested_count']
    available_calls=[result for result,address in re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[n+'get'])+r'\(i64 ([^\n)]+)\)',read)
       if _ipc_scalar_operands(read,constants_by).get(address,address)==('add',base[0],48)]
    available_values=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(available_calls[0] if len(available_calls)==1 else 'NO_AVAILABLE')+r', 1$',read,re.M)
    if len(available_values)!=1 or minimums.get(requested)!=('unsigned-min','%arg2',available_values[0]):
        raise Core0Error('input count is not min(complete offered length, actual available bytes)')
    reuse=validate_service_reuse(bodies[c+'grantDiscovered'],grant=by[c+'grant'],stop=by['Lemma.Core0.Memory.Status.iterationStop'])
    folds={'input_poll':validate_fixed_fold(bodies[n+'poll'],by[n+'pollStep'],64),
           'discovery':validate_fixed_fold(bodies[c+'grantDiscovered'],by[c+'discoveredStep'],16),
           'active_registrations':validate_fixed_fold(bodies[c+'activeRegisteredCount'],by[c+'activeRegisteredStep'],8),
           'diagnostic_publication':validate_fixed_fold(bodies[n+'flushPending'],by[n+'diagnosticPublishStep'],40)}
    callback=bodies[c+'discoveredStep']
    entry_calls=re.findall(r'('+var+r') = call i64 @'+re.escape(by[c+'entry'])+r'\([^\n]*\)',callback)
    entry_arguments=re.findall(r'call \bi64 @'+re.escape(by[c+'entry'])+r'\(i64 %arg3, i64 ('+var+r')\)',callback)
    widened=set(re.findall(r'('+var+r') = zext i32 %arg0 to i64$',callback,re.M))
    if not entry_calls or len(entry_arguments)!=len(entry_calls) or not set(entry_arguments)<=widened:
        raise Core0Error('discovery hit lacks exact local entry geometry/index')
    callback_values=_ipc_scalar_operands(callback,constants_by)
    addresses=[callback_values.get(address,address) for address in re.findall(r'call \{ i64, i64 \} @'+re.escape(by[o+'get'])+r'\(i64 ([^\n)]+)\)',callback)]
    key_addresses=[address for address in addresses if isinstance(address,tuple) and address[0]=='add' and address[1] in entry_calls and address[2]==16]
    rights_addresses=[address for address in addresses if isinstance(address,tuple) and address[0]=='add' and address[1] in entry_calls and address[2]==24]
    if len(key_addresses)!=1 or len(rights_addresses)!=1:
        raise Core0Error('discovery hit lacks one exact key/rights read')
    hit_gates=[validate_ipc_read_guard(callback,by[o+'get'],constants_by,key_addresses[0],'%arg4',by[c+'lookupEntry']),
               validate_ipc_read_guard(callback,by[o+'get'],constants_by,rights_addresses[0],16,by[c+'lookupEntry'])]
    # Read-only hit search cannot reach serial/reference/table publication.
    mutators={by[source] for source in [c+'freeSlot',o+'nextSerial',o+'reference',c+'publish',c+'grant',o+'put',x+'write64']}
    pending=[by[c+'discoveredStep']];seen=set()
    while pending:
        symbol=pending.pop()
        if symbol in mutators:
            raise Core0Error('discovery existing-entry search reaches a grant mutation')
        if symbol not in seen:
            seen.add(symbol)
            called=parse_definitions_and_calls(_ir_definition_body(pre_ir,symbol))[2]
            pending.extend(callee for callee in called if callee in set(by.values()))
    raw_mode=validate_checked_call_gate(bodies[y+'selectedConsoleRead'],by[n+'mode'],by[y+'consoleRead'],component='value',value=0)
    legacy_control=validate_ipc_read_guard(bodies[n+'mode'],by[n+'get'],constants_by,0x80400660,0,by[n+'table'],equal=False)
    # A single primitive poll transports its exact byte value even when00.
    poll_body=bodies[n+'pollStep'];primitive='Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep'
    primitive_calls=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[primitive])+r'\(([^\n]*)\)',poll_body)
    if len(primitive_calls)!=1 or primitive_calls[0][1]!=', '.join(['i32 signext 0','i32 signext 0',*(['i64 0']*5)]):
        raise Core0Error('input poll does not use the exact single bounded receive operation')
    poll_value=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(primitive_calls[0][0])+r', 1$',poll_body,re.M)
    if len(poll_value)!=1 or re.findall(r'call \{ i64, i64 \} @'+re.escape(by[n+'acceptByte'])+r'\(([^\n]*)\)',poll_body)!=['i64 %arg3, i64 '+poll_value[0]]:
        raise Core0Error('input poll drops or substitutes its actual byte')
    # Complete publication: epoch and full owner precede key, withdrawals clear
    # key then owner and retain the epoch. All stores are successful checked calls.
    publication=bodies[o+'publishServiceBinding'];result=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[o+'serviceBinding'])+r'\(\)',publication)
    binding_base=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(result[0] if len(result)==1 else 'NO_BINDING')+r', 1$',publication,re.M)
    if len(binding_base)!=1:
        raise Core0Error('service publication lacks one checked binding base')
    publication_inventory=validate_ipc_write_inventory(publication,by[o+'put'],constants_by,
       [(('add',binding_base[0],232),'%arg2'),(('add',binding_base[0],248),'%arg0'),(('add',binding_base[0],240),'%arg1')],by[o+'failed'],_ir_definition_body(pre_ir,by[o+'failed']))
    withdrawal=bodies[o+'withdrawService'];result=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[o+'serviceBinding'])+r'\(\)',withdrawal)
    withdrawn_base=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(result[0] if len(result)==1 else 'NO_BINDING')+r', 1$',withdrawal,re.M)
    if len(withdrawn_base)!=1:
        raise Core0Error('service withdrawal lacks one checked binding base')
    withdrawal_inventory=validate_ipc_write_inventory(withdrawal,by[o+'put'],constants_by,
       [(('add',withdrawn_base[0],240),0),(('add',withdrawn_base[0],248),0)],by[o+'failed'],_ir_definition_body(pre_ir,by[o+'failed']))
    # The exact ordinary boot role indices/arguments and grant attenuation.
    preparations=re.findall(r'call \{ i64, i64 \} @'+re.escape(by[t+'prepareManaged'])+r'\(i64 ([0-9]+), i64 ([^\n)]+)\)',bodies[e+'construct'])
    if len(preparations)!=4 or [r[0] for r in preparations]!=['0','1','2','3'] or [r[1] for r in preparations[1:]]!=['1','2','3']:
        raise Core0Error('service boot images/public seed arguments differ')
    epoch_result=re.findall(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(by[d+'nextEpoch'])+r'\(\)',bodies[e+'construct'])
    epoch_value=re.findall(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(epoch_result[0] if len(epoch_result)==1 else 'NO_EPOCH')+r', 1$',bodies[e+'construct'],re.M)
    if len(epoch_value)!=1 or preparations[0][1]!=epoch_value[0]:
        raise Core0Error('Server argument is not the actual next Directory epoch')
    operands=_ipc_scalar_operands(bodies[e+'grants'],{by[o+'consoleKey']:16,by[o+'directoryKey']:18,by[v+'consoleType']:1,by[v+'directoryType']:4,by[v+'endpointType']:2})
    grants=[tuple(operands.get(value,int(value) if value.isdecimal() else value) for value in row) for row in re.findall(
       r'call \{ i64, i64 \} @'+re.escape(by[e+'grant'])+r'\(i64 ([^,]+), i64 ([^,]+), i64 ([^,]+), i64 ([^)]+)\)',bodies[e+'grants'])]
    if grants!=[('%arg0',16,1,2),('%arg0','%arg3',2,8),('%arg1',16,1,3),('%arg1',18,4,1024),('%arg2',16,1,2),('%arg2',18,4,1024)]:
        raise Core0Error('service exact role grants/attenuation/order differ')
    selected_initializer = e+('initializeFor' if configuration=='silicon-service-development' else 'initialize')
    entry_body=bodies[selected+('siliconBoot' if configuration=='silicon-service-development' else 'boot')]
    if configuration=='silicon-service-development':
        probe='Lemma.Platform.Silicon.Binding.boot_timer_probe_ticks'
        operands=_ipc_scalar_operands(entry_body,{by[probe]:10000})
        calls=re.findall(r'call \{ i64, i64 \} @'+re.escape(by[selected_initializer])+r'\(i64 ([^,]+), i64 ([^,]+), i64 ([^)]+)\)',entry_body)
        actual=[tuple(operands.get(value,int(value) if value.isdecimal() else value) for value in row) for row in calls]
        if actual!=[(2,2,10000)]:
            raise Core0Error('silicon service boot mode/delegation/probe interval differ from exact binding')
    else:
        mode_call=re.findall(r'call \{ i64, i64 \} @'+re.escape(by[selected_initializer])+r'\(i64 ([0-9]+)\)',entry_body)
        if mode_call!=['1' if configuration=='service-normal' else '2']:
            raise Core0Error('service input mode is not selected solely by exact boot root')
    return {'managed_policy':BUFFER_POLICY,'common_ipc':common,'source_call_edges':observed,
       'source_constants':{source:{'symbol':by[source],'value':value} for source,value in sorted(constants.items())},
       'ordered_cfg_calls':ordered,'checked_cfg_gates':checked,'input_copy_count_gate':count_gate,'input_reader_gate':reader_gate,
       'input_advancement':advancement,
       'input_initialization':initialization,
       'discovery_reuse':reuse,'discovery_hit_gates':hit_gates,'discovery_readonly_search':sorted(seen),
       'bounded_folds':folds,'legacy_input_mode_gate':legacy_control,'raw_console_mode_gate':raw_mode,
       'binding_publication':publication_inventory,'binding_withdrawal':withdrawal_inventory,'initial_grants':grants,
       'input':{'control':0x80400660,'ring_offset':128,'ring_bytes':512,'pending_offset':640,'pending_bytes':168,'scratch_offset':832,'diagnostic_offset':1088,'diagnostic_bytes':40,'poll_budget':64},
       'owned_page_budget':{'base_owned_task_frames':18,'base_global_task_frames':19,'server_reserved_arena_pages':4,'owner_quota':32,'server_max_text_pages':10},
       'limitations':['Necessary genuine source/CFG/byte binding; independent service/reference tests, model proofs and physical execution remain separate.']}


def validate_user_abi_data(section_text: str, data: bytes, symbol_text: str,
                           assembly: str, *, object_file: str, configuration: str = "normal") -> dict:
    """Account for the sole declarative initializer emitted by Lean startup.

    Compiled unit globals remain forbidden. This admits only the named input
    section of the startup object and its exact linked payload, not arbitrary
    writable data or additional target object symbols.
    """
    multi_file = re.fullmatch(r"users/(compute|sleeper|busy|fault|capabilities|peer|tamper|server|clienta|clientb|cli)/(startup\.o|image\.elf)", object_file)
    sim_file = (configuration in LEMMASIM_NOTEBOOK_CONFIGURATIONS and
                re.fullmatch(r"users/(store|notebook|isolation)/(startup\.o|image\.elf)", object_file) is not None)
    arithmetic_file = (configuration in ARITHMETIC_CONFIGURATIONS and
                re.fullmatch(r"users/arithmetic/(startup\.o|image\.elf)",object_file) is not None)
    if object_file not in {"user/startup.o", "user/image.elf"} and multi_file is None and not sim_file and not arithmetic_file:
        raise Core0Error("user ABI data lacks its exact startup-object ownership")
    linked = object_file.endswith("/image.elf")
    section, address, alignment = (".data", 0x20000, 4096) if linked else (".data.user_abi", 0, 8)
    rows = re.findall(r"(?m)^\s*\[\s*(\d+)\]\s+" + re.escape(section)
                      + r"\s+PROGBITS\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)\s+00\s+([A-Z]*)\s+0\s+0\s+(\d+)\s*$", section_text)
    if (len(rows) != 1 or int(rows[0][1], 16) != address or int(rows[0][2], 16) != 16
            or set(rows[0][3]) != {"W", "A"} or len(rows[0][3]) != 2 or int(rows[0][4]) != alignment
            or data != USER_ABI_INITIAL_DATA):
        raise Core0Error("user ABI initializer section/bytes/permissions/alignment differ")
    objects = [line for line in symbol_text.splitlines() if len(line.split()) >= 8
               and line.split()[0].endswith(":") and line.split()[3] == "OBJECT" and line.split()[6] != "UND"]
    expected = '.section .data.user_abi, "aw", @progbits\n.balign 8\n.quad 0\n.quad 1\n.option pop\n'
    if objects or assembly.count(expected) != 1 or len(re.findall(r"(?m)^\.section \.data", assembly)) != 1:
        raise Core0Error("user ABI initializer generated source or object-symbol closure differs")
    owner = object_file.rsplit("/", 1)[0] + "/startup.o(.data.user_abi)"
    return {"source": "Lemma.User.ABI.version", "owned_input": owner,
            "section": section, "virtual_address": address, "bytes": 16, "alignment": alignment,
            "words": [0, 1], "writable": True, "executable": False,
            "sha256": hashlib.sha256(data).hexdigest()}


def user_primitive_rows(case: str) -> list[dict]:
    if case not in {"none", *USER_ATTACKS}:
        raise Core0Error("unknown user startup case")
    rows = [{"symbol": "_user_start", "privilege": "U", "effect": "user-entry/exit"},
            {"symbol": "lemma_exec_syscall", "privilege": "U", "effect": "user-syscall"}]
    if case in USER_ATTACKS:
        symbol, effect, _ = USER_ATTACKS[case]
        rows.append({"symbol": symbol, "privilege": "U", "effect": effect})
    return rows


def _object(value: object, context: str) -> dict:
    if not isinstance(value, dict):
        raise Core0Error(f"{context} must be an object")
    return value


def _array(value: object, context: str) -> list:
    if not isinstance(value, list):
        raise Core0Error(f"{context} must be an array")
    return value


def _integer(value: object, context: str) -> int:
    if type(value) is not int or value < 0:
        raise Core0Error(f"{context} must be a nonnegative integer")
    return value


def _keys(value: dict, expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise Core0Error(f"{context} fields differ from the closed schema")


def validate_unit(value: object, role: str, *, configuration: str = "normal", image_key: str | None = None) -> dict:
    unit = _object(value, f"{role} unit")
    multi_user = configuration in MULTI_USER_CONFIGURATIONS and role == "user"
    if (image_key is not None) != multi_user:
        raise Core0Error("per-image unit selection differs from its configuration/role")
    image = image_spec(configuration, image_key) if multi_user else None
    if multi_user and image is None:
        raise Core0Error("unknown per-image user unit selection")
    keys = {"schema_version", "artifact_category", "contract_version", "configuration", "role", "roots", "functions",
            "used_execution_ops", "used_device_ops", "used_loops"}
    case_field = {"startup_case"} if multi_user and configuration in {"tasks-fault-development", *MANAGED_POLICIES} else set()
    expected_managed = managed_fields(configuration, image)
    from closed_inline import selected as inline_selected, FIELD as inline_field, catalog as inline_catalog
    from managed_records import FIELD as records_field, allowed as records_allowed, contract as records_contract
    _keys(unit, keys | ({"image_key", "image_id"} if multi_user else set()) | case_field | set(expected_managed) | ({inline_field} if inline_field in unit and inline_selected(unit) else set()) | ({records_field} if records_field in unit and records_allowed(unit) else set()), "unit")
    if any(unit.get(key) != value for key, value in expected_managed.items()):
        raise Core0Error("unit managed policy/boot role differs")
    category = ("production" if configuration in {"normal", "service-normal"} else "development") + f"-{role}-unit"
    if (unit.get("schema_version") != (2 if multi_user else 1) or type(unit.get("schema_version")) is not int
            or unit.get("artifact_category") != category or unit.get("configuration") != configuration
            or unit.get("role") != role or unit.get("contract_version") !=
                (kernel_contract(configuration) if role == "kernel" else
                 'core0-user-v0.2' if role == 'user' and records_allowed(unit) and records_field in unit else CONTRACTS[role])):
        raise Core0Error(f"{role} unit identity/version differs")
    if multi_user and (unit.get("image_key") != image_key or type(unit.get("image_id")) is not int or unit.get("image_id") != image["id"]):
        raise Core0Error("per-image user unit key/ID differs")
    if case_field and unit.get("startup_case") != image["startup_case"]:
        raise Core0Error("per-image user unit startup case differs from its closed registry")
    roots = _array(unit.get("roots"), f"{role} roots")
    expected = [(image["source"], image["args"])] if multi_user else [(source, list(args)) for source, args in configuration_roots(configuration)[role]]
    if [(row.get("source"), row.get("args")) for row in roots if isinstance(row, dict)] != expected or len(roots) != len(expected):
        raise Core0Error(f"{role} exact production roots/signatures differ")
    for index, raw in enumerate(roots, 1):
        row = _object(raw, "root")
        _keys(row, {"id", "source", "symbol", "args"}, "root")
        if type(row.get("id")) is not int or row["id"] != index:
            raise Core0Error("root identifiers differ from the exact export order")
    functions = _array(unit.get("functions"), f"{role} functions")
    if not functions:
        raise Core0Error(f"{role} function corpus is empty")
    symbols, sources = set(), set()
    for raw in functions:
        row = _object(raw, "function")
        _keys(row, {"source", "symbol", "args", "effects"}, "function")
        source, symbol = row.get("source"), row.get("symbol")
        production_identity = isinstance(source, str) and (
            source.startswith("Lemma.") or re.fullmatch(r"_private\.(Lemma(?:\.[A-Za-z0-9_]+)+)\.[0-9]+\.\1\.[A-Za-z0-9_.$]+", source) is not None)
        if not production_identity or any(token in source.lower() for token in (".test.", "examples", "mutation")):
            raise Core0Error("function lacks a production Lean source identity")
        if configuration in MANAGED_POLICIES and role == "user" and re.search(r"(?:^|\.[0-9]+\.)Lemma\.(?:Kernel|Compiler)\.", source):
            raise Core0Error("managed user source reaches privileged/compiler code")
        normalized_source = re.sub(r"^_private\..*?\.[0-9]+\.", "", source)
        if configuration in SERVICE_CONFIGURATIONS and service_executable_module(normalized_source):
            if role != "user" or not normalized_source.startswith(image["module"] + "."):
                raise Core0Error("service unit reaches another executable namespace")
        if ".Development." in source:
            allowed = (image["module"],) if multi_user else development_modules(configuration, role)
            if not any(re.search(r"(?:^|\.[0-9]+\.)" + re.escape(module) + r"\.", source) for module in allowed):
                raise Core0Error("development source escapes its exact selected module namespace")
        prefix = image["symbol_prefix"] if multi_user else "lemma_" + role + "_"
        if not isinstance(symbol, str) or not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_.$]+", symbol):
            raise Core0Error(f"function symbol lacks role prefix: {symbol}")
        if symbol in symbols or source in sources:
            raise Core0Error("duplicate function source/symbol")
        symbols.add(symbol); sources.add(source)
        if any(ty not in {"bool", "u8", "u32", "u64"} for ty in _array(row.get("args"), "function args")):
            raise Core0Error("unadmitted argument type")
        effects = _array(row.get("effects"), "function effects")
        if any(not isinstance(effect, str) for effect in effects) or len(effects) != len(set(effects)) or not set(effects) <= ROLE_EFFECTS[role]:
            raise Core0Error("function effect catalog escapes role authority")
    inline_catalog(unit)
    records_contract(unit)
    for root in roots:
        if not any(row["source"] == root["source"] and row["symbol"] == root["symbol"] and row["args"] == root["args"] for row in functions):
            raise Core0Error("root/function signature or symbol mismatch")
    seen = set()
    for raw in _array(unit.get("used_execution_ops"), "execution catalog"):
        row = _object(raw, "execution operation")
        _keys(row, {"stable_id", "source_identity", "primitive_symbol", "arguments", "returnkind"}, "execution operation")
        identity = row.get("source_identity")
        suffix = identity.rsplit(".", 1)[-1] if isinstance(identity, str) else ""
        sim_operations = {
            "deviceRead32": ("device-read32", None, 0, "word", {"kernel"}),
            "deviceWrite32": ("device-write32", None, 0, "word", {"kernel"}),
            "deviceRead64": ("device-read64", None, 0, "word", {"kernel"}),
            "deviceWrite64": ("device-write64", None, 0, "word", {"kernel"}),
        } if configuration in LEMMASIM_CONFIGURATIONS else {}
        operations = {**EXECUTION_OPERATIONS, **sim_operations}
        if suffix not in operations or identity != "Lemma.Core0.Execution.Op." + suffix:
            raise Core0Error("unknown execution operation identity")
        stable, primitive, argc, result, roles = operations[suffix]
        if (role not in roles or row.get("stable_id") != ("lemmasim." if suffix in sim_operations else "execution.") + stable or row.get("primitive_symbol") != primitive
                or row.get("arguments") != ["u64"] * argc or row.get("returnkind") != result or suffix in seen):
            raise Core0Error(f"execution operation contract/privilege differs: {suffix}")
        seen.add(suffix)
    callbacks = set()
    by_source = {row["source"]: row for row in functions}
    for raw in _array(unit.get("used_loops"), "Action loop catalog"):
        row = _object(raw, "Action loop")
        callback = row.get("callback")
        if (set(row) != {"stable_id", "callback"} or row.get("stable_id") != "action.loop" or role == "firmware"
                or not isinstance(callback, str) or callback not in by_source or by_source[callback]["args"] != []
                or callback in callbacks):
            raise Core0Error("Action loop has an unknown/duplicate/nonclosed callback or unauthorized role")
        callbacks.add(callback)
    if bool(callbacks) != any("may-diverge" in row["effects"] for row in functions):
        raise Core0Error("Action loop catalog and may-diverge effect closure disagree")
    device = _array(unit.get("used_device_ops"), "device catalog")
    if role == "user" and device:
        raise Core0Error("ordinary user code cannot have device authority")
    device_ids = set()
    expected_devices = {
        "uart.read-status": ("uartReadStatus", "uart.lsr.read8", 5, "read", None),
        "uart.read-byte": ("uartReadByte", "uart.rbr.read8", 0, "read", None),
        "uart.write-byte": ("uartWriteByte", "uart.thr.write8", 0, "write", None),
        "uart.enable-reset-fifo": ("uartEnableAndResetFifo", "uart.fcr.enable-reset", 2, "write", 7),
    }
    if role == "kernel" and unit["contract_version"] in {"core0-kernel-v0.2", "core0-kernel-v0.3", "core0-kernel-v0.4", "core0-kernel-v0.5"}:
        expected_devices["uart.enable-reset-fifo-trigger14"] = (
            "uartEnableAndResetFifo14", "uart.fcr.enable-reset-trigger14", 2, "write", 199)
    for raw in device:
        row = _object(raw, "device operation")
        _keys(row, {"stable_id", "source_identity", "lowering_id", "base", "offset", "width_bytes", "access", "fixed_value",
                    "volatile", "fence_before", "fence_after", "sites"}, "device operation")
        stable = row.get("stable_id")
        if stable not in expected_devices or stable in device_ids:
            raise Core0Error("unknown/duplicate production device operation")
        constructor, lowering, offset, access, value = expected_devices[stable]
        if (any(type(row.get(key)) is not int for key in ("base", "offset", "width_bytes"))
                or value is not None and type(row.get("fixed_value")) is not int
                or any(row.get(key) is not True for key in ("volatile", "fence_before", "fence_after"))
                or any(row.get(key) != expected for key, expected in {
            "source_identity": "Lemma.Core0.Memory.Action." + constructor,
            "lowering_id": lowering, "base": 0x10000000, "offset": offset,
            "width_bytes": 1, "access": access, "fixed_value": value,
            "volatile": True, "fence_before": True, "fence_after": True}.items())):
            raise Core0Error("compiled device operation differs from pinned UART contract")
        sites = _array(row.get("sites"), "device sites")
        if not sites or any(not isinstance(site, dict) or type(site.get("site")) is not int or site["site"] < 0 or site.get("symbol") not in symbols for site in sites):
            raise Core0Error("device site/source-function binding missing")
        for site in sites:
            _keys(site, {"site", "symbol"}, "device site")
        if stable == "uart.enable-reset-fifo-trigger14" and (
                len(sites) != 1 or not any(function["source"] == "Lemma.Platform.LemmaVM.ConsoleDevice.initialize14"
                                         and function["symbol"] == sites[0]["symbol"] and function["args"] == []
                                         for function in functions)):
            raise Core0Error("trigger14 FIFO site lacks its sole closed production initializer")
        device_ids.add(stable)
    return unit


def validate_layout(value: object, *, configuration: str = "normal", image_key: str | None = None) -> dict:
    layout = _object(value, "layout")
    image = image_spec(configuration, image_key) if image_key is not None else None
    expected_managed = managed_fields(configuration, image)
    _keys(layout, {"schema_version", "contract_version", "configuration", "startup_case", "user_startup_case", "ram_base", "ram_limit",
                   "frame_bytes", "frame_count", "task_kernel_stack_pages", "task_kernel_stack_bytes", "context", "intervals", "user"} | set(expected_managed)
          | ({"boot_clear"} if configuration in LEMMASIM_CONFIGURATIONS else set()), "layout")
    if any(layout.get(key) != value for key, value in expected_managed.items()):
        raise Core0Error("layout managed policy/boot role differs")
    selected_case = image_spec(configuration, image_key)["startup_case"] if image_key is not None else user_startup_case(configuration)
    if type(layout.get("schema_version")) is not int or layout.get("schema_version") != 1 or layout.get("contract_version") != "lemma-kernel-layout-v2" or layout.get("configuration") != configuration or layout.get("startup_case") != startup_case(configuration) or layout.get("user_startup_case") != selected_case:
        raise Core0Error("unknown kernel layout version")
    expanded = configuration in LEMMASIM_CONFIGURATIONS
    silicon = configuration.startswith("lemmasim-silicon-")
    if silicon:
        from silicon_profile import profile, configuration_profile
        binding = profile(configuration_profile(configuration))
    frame_count = binding["frame_count"] if silicon else 8192 if expanded else 512
    frame_limit = binding["frame_pool_base"] + binding["frame_pool_bytes"] if silicon else 0x84000000 if expanded else 0x82200000
    if expanded and layout.get('boot_clear') != {
            'contract_version': 'lemma-boot-clear-v1', 'base': 0x80400000,
            'limit': 0x80500000, 'stride_bytes': 8, 'phase': 'M-startup-before-boot-handoff'}:
        raise Core0Error('Lemmasim boot metadata clear interval differs')
    if (layout.get("ram_base"), layout.get("ram_limit"), layout.get("frame_bytes"), layout.get("frame_count")) != (0x80000000, 0x88000000, 4096, frame_count):
        raise Core0Error("pinned RAM/frame contract differs")
    if (type(layout.get("task_kernel_stack_pages")) is not int or type(layout.get("task_kernel_stack_bytes")) is not int
            or layout["task_kernel_stack_pages"] != 4 or layout["task_kernel_stack_bytes"] != layout["frame_bytes"] * layout["task_kernel_stack_pages"]):
        raise Core0Error("owned kernel stack construction contract differs")
    if layout.get("context") != CONTEXT_LAYOUT:
        raise Core0Error("fixed supervisor context/stack contract differs")
    expected = {"firmware": (0x80000000, 0x80010000), "firmware-private": (0x80100000, 0x80110000),
                "supervisor": (0x80200000, 0x80300000), "metadata": (0x80400000, 0x80500000),
                "supervisor-stack": (0x80500000, 0x80510000), "boot-package": (0x80600000, 0x80700000),
                "frame-pool": (0x82000000, frame_limit), "dtb-reserve": (0x87e00000, 0x88000000)}
    rows = _array(layout.get("intervals"), "layout intervals")
    observed = {}
    for raw in rows:
        row = _object(raw, "interval")
        name = row.get("name")
        if not isinstance(name, str) or name in observed:
            raise Core0Error("duplicate/invalid layout interval")
        observed[name] = (_integer(row.get("base"), "base"), _integer(row.get("limit"), "limit"))
    if observed != expected:
        raise Core0Error("authoritative reserved-region contract differs")
    user = _object(layout.get("user"), "user layout")
    if user != {"text_base": 0x1000000 if expanded else 0x10000, "text_limit": 0x1080000 if expanded else 0x1f000, "data_base": 0x20000, "data_bytes": 4096,
                "stack_base": 0x3fffa000 if expanded else 0x3fffc000, "stack_pages": 4 if expanded else 2}:
        raise Core0Error("user virtual layout differs")
    return layout


def validate_boot_metadata_clear(layout: dict, addresses: dict, segments: list[dict],
                                 raw_machine: str, ranges: dict) -> dict:
    """Independently bind reset initialization to actual ELF and instructions.

    This checks the selected fixed startup loop; it is not a whole-program boot
    proof. Historical profiles retain128B. LemmaSim clears its full reserved
    metadata before writing the hart/DTB handoff on every CPU boot.
    """
    base = 0x80400000
    limit = 0x80500000 if layout['configuration'] in LEMMASIM_CONFIGURATIONS else 0x80400080
    expected = {'__bss_start': base, '__bss_end': limit,
                '__boot_hartid': base, '__boot_dtb': base + 8}
    if any(type(addresses.get(key)) is not int or addresses.get(key) != value
           for key, value in expected.items()):
        raise Core0Error('boot metadata/BSS linked symbols differ')
    storage = [segment for segment in segments if segment['virtual_address'] < 0x80500000
               and base < segment['virtual_address'] + segment['memory_size']]
    if storage != [{'virtual_address': base, 'physical_address': base,
                    'file_size': 0, 'memory_size': limit - base, 'flags': 'RW'}]:
        raise Core0Error('boot metadata NOLOAD PT_LOAD interval differs')
    start, size = ranges.get('_start', (None, None))
    if type(start) is not int or type(size) is not int or start != 0x80000000 or size <= 0:
        raise Core0Error('boot metadata clear lacks actual startup range')
    rows = {}
    for line in raw_machine.splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s', line)
        if match and start <= int(match[1], 16) < start + size:
            pc, word = int(match[1], 16), int(match[2], 16)
            if pc in rows:
                raise Core0Error('duplicated boot instruction address')
            rows[pc] = word
    def signed(value, bits):
        return value - (1 << bits) if value & (1 << (bits - 1)) else value
    def pcrel(pc, register):
        hi, lo = rows.get(pc, 0), rows.get(pc + 4, 0)
        if hi & 0xfff != (register << 7) | 0x17 or lo & 0xfffff != (register << 15) | (register << 7) | 0x13:
            return None
        return pc + signed(hi & 0xfffff000, 32) + signed(lo >> 20, 12)
    matches = []
    for pc in rows:
        if (pcrel(pc, 5) == base and pcrel(pc + 8, 6) == limit
                and [rows.get(pc + offset) for offset in (16, 20, 24, 28)]
                    == [0x0062f863, 0x0002b023, 0x00828293, 0xff5ff06f]
                and pcrel(pc + 32, 5) == base
                and rows.get(pc + 40) == 0x0082b023
                and rows.get(pc + 44) == 0x0092b423):
            matches.append(pc)
    if len(matches) != 1:
        raise Core0Error('boot metadata clear loop bounds/store/stride/handoff instructions differ')
    return {'contract_version': 'lemma-boot-clear-v1', 'base': base, 'limit': limit,
            'bytes': limit - base, 'stride_bytes': 8, 'clear_loop_pc': matches[0] + 16,
            'handoff_store_pc': matches[0] + 40, 'scope': 'actual fixed M startup BSS clear before hart/DTB publication'}


def validate_catalog(value: object, *, configuration: str, stage: str) -> set[str]:
    validate_configuration_stage(configuration, stage)
    catalog = _object(value, "primitive catalog")
    multi = configuration in MULTI_USER_CONFIGURATIONS
    _keys(catalog, {"schema_version", "contract_version", "stage", "configuration", "startup_case", "user_startup_case", "symbols",
                    "user_images" if multi else "user_symbols"} | set(managed_fields(configuration)), "primitive catalog")
    if any(catalog.get(key) != value for key, value in managed_fields(configuration).items()):
        raise Core0Error("primitive catalog managed policy differs")
    expected_machine = MACHINE_SYMBOLS | (SUPERVISOR_SYMBOLS if stage == "supervisor" else set())
    if startup_case(configuration) == "machine-origin-probe":
        expected_machine |= {"lemma_machine_vector"}
    rows = [_object(row, "machine symbol") for row in _array(catalog.get("symbols"), "machine symbols")]
    if (type(catalog.get("schema_version")) is not int or catalog.get("schema_version") != (2 if multi else 1)
            or catalog.get("contract_version") != "lemma-execution-v1" or catalog.get("stage") != stage
            or catalog.get("configuration") != configuration or catalog.get("startup_case") != startup_case(configuration) or catalog.get("user_startup_case") != user_startup_case(configuration)
            or {row.get("symbol") for row in rows} != expected_machine or len(rows) != len(expected_machine)):
        raise Core0Error("closed platform primitive catalog differs")
    for row in rows:
        _keys(row, {"symbol", "privilege", "effect"}, "machine symbol")
        if row.get("privilege") != ("M" if row["symbol"] in M_SYMBOLS else "S") or row.get("effect") != PRIMITIVE_EFFECTS[row["symbol"]]:
            raise Core0Error("machine primitive privilege/effect differs")
    expected_users = [{"key": row["key"], "id": row["id"], "startup_case": row["startup_case"], "symbols": user_primitive_rows(row["startup_case"]),
                       **({"boot_role": row["boot_role"]} if configuration in MANAGED_POLICIES else {})}
                      for row in image_specs(configuration)] if multi else user_primitive_rows(user_startup_case(configuration))
    if (catalog.get("user_images" if multi else "user_symbols") != expected_users
            or multi and any(type(row.get("id")) is not int for row in catalog.get("user_images", []))):
        raise Core0Error("closed user primitive privilege/effect catalog differs")
    return expected_machine


def validate_user_primitive_catalog(value: object, image: dict, *, configuration: str = "tasks-development") -> dict:
    if image != image_spec(configuration, image.get("key")):
        raise Core0Error("per-image primitive authority differs from the closed selected image")
    expected = {"schema_version": 1, "contract_version": "lemma-user-execution-v1", "configuration": configuration,
                "image_key": image["key"], "image_id": image["id"], "startup_case": image["startup_case"],
                "symbols": user_primitive_rows(image["startup_case"]), **managed_fields(configuration, image)}
    catalog = _object(value, "per-image primitive catalog")
    if catalog != expected or type(catalog.get("schema_version")) is not int or type(catalog.get("image_id")) is not int:
        raise Core0Error("closed per-image user primitive catalog differs")
    return catalog


def validate_package_contract(value: object, *, configuration: str, catalog: dict | None = None) -> dict:
    notebook = configuration in LEMMASIM_CONFIGURATIONS
    image = {"id": 1, "entry": 0x1000000 if notebook else 0x10000, "text_va": 0x1000000 if notebook else 0x10000, "text_capacity": 0x80000 if notebook else 0xf000,
             "data_va": 0x20000, "data_mem_bytes": 4096, "stack_va": 0x3fffa000 if configuration in LEMMASIM_CONFIGURATIONS else 0x3fffc000, "stack_pages": 4 if configuration in LEMMASIM_CONFIGURATIONS else 2, "flags": 0}
    multi = configuration in MULTI_USER_CONFIGURATIONS
    if multi:
        selected = validate_user_image_catalog(catalog, configuration=configuration)["images"]
        images = [{**image, "key": row["key"], "id": row["id"],
                   **({"boot_role": row["boot_role"]} if configuration in MANAGED_POLICIES else {})} for row in selected]
    expected = {"schema_version": 2 if multi else 1, "configuration": configuration,
                "startup_case": startup_case(configuration), "user_startup_case": user_startup_case(configuration),
                "contract_version": "lemma-boot-package-v2" if notebook else "lemma-boot-package-v1", "magic": 0x31474b50414d454c,
                "version": 2 if notebook else 1, "image_count": len(images) if multi else 1, "header_bytes": 32, "descriptor_bytes": 96,
                "offset_encoding": "generated-label-differences", **({"images": images} if multi else {"image": image}),
                **managed_fields(configuration)}
    contract = _object(value, "boot package contract")
    if (contract != expected or any(type(contract.get(key)) is not int for key in ("schema_version", "magic", "version", "image_count", "header_bytes", "descriptor_bytes"))
            or any(type(row.get(key)) is not int for row in (contract.get("images", []) if multi else [contract.get("image", {})])
                   for key in image)):
        raise Core0Error("unknown/malformed boot package descriptor contract")
    return contract


def validate_package_payloads(package: bytes, contract: dict, payloads: list[tuple[bytes, bytes]]) -> list[dict]:
    """Bind every declared v1/v2 descriptor to separately audited bytes, in order."""
    count = contract["image_count"]
    minimum = 32 + count * 96
    if len(payloads) != count or len(package) < minimum or struct.unpack_from("<4Q", package) != (contract["magic"], contract["version"], count, len(package)):
        raise Core0Error("boot package header/count/extent differs")
    images = contract.get("images", [contract.get("image")])
    occupied, last, reports = bytearray(len(package)), minimum, []
    occupied[:minimum] = b"\1" * minimum
    for index, (image, (text, data)) in enumerate(zip(images, payloads)):
        words = struct.unpack_from("<12Q", package, 32 + index * 96)
        ident, entry, text_va, text_offset, text_bytes, data_va, data_offset, data_bytes, memory, stack_va, pages, flags = words
        if ((ident, entry, text_va, data_va, memory, stack_va, pages, flags) !=
                (image["id"], image["entry"], image["text_va"], image["data_va"], image["data_mem_bytes"], image["stack_va"], image["stack_pages"], image["flags"])
                or not 0 < len(text) <= image["text_capacity"] or len(data) > memory
                or text_bytes != len(text) or data_bytes != len(data)
                or text_offset < last or text_offset % 8 or data_offset < text_offset + text_bytes or data_offset % 8
                or data_offset + data_bytes > len(package)):
            raise Core0Error("boot package descriptor/source image extents differ")
        for begin, raw in ((text_offset, text), (data_offset, data)):
            end = begin + len(raw)
            if end > len(package) or any(occupied[begin:end]) or package[begin:end] != raw:
                raise Core0Error("boot package image payload is overlapping, missing or changed")
            occupied[begin:end] = b"\1" * len(raw)
        last = data_offset + data_bytes
        reports.append({"id": ident, "key": image.get("key"), "text_offset": text_offset, "text_bytes": text_bytes,
                        "data_offset": data_offset, "data_bytes": data_bytes,
                        "text_sha256": hashlib.sha256(text).hexdigest(), "data_sha256": hashlib.sha256(data).hexdigest()})
    if any(byte for byte, used in zip(package, occupied) if not used):
        raise Core0Error("unaccounted nonzero boot package bytes outside audited payloads")
    if len(package) != last:
        raise Core0Error("boot package has an unexpected trailing extent")
    return reports


def validate_startup_case(text: str, ranges: dict[str, tuple[int, int]], case: str) -> dict:
    if case not in {"normal", "machine-origin-probe"} or "_start" not in ranges:
        raise Core0Error("unknown/missing startup case function")
    begin, size = ranges["_start"]
    pcs = [int(match[1], 16) for line in text.splitlines()
           if (match := re.match(r"\s*([0-9a-f]+):\s+ecall\s*$", line)) and begin <= int(match[1], 16) < begin + size]
    if len(pcs) != (1 if case == "machine-origin-probe" else 0):
        raise Core0Error("startup ECALL inventory differs from the exact generated case")
    return {"case": case, "start_ecall_pcs": pcs}


def _assembly_function(text: str, symbol: str) -> list[str]:
    bodies = re.findall(r"(?ms)^" + re.escape(symbol) + r":\n(.*?)^\.size " + re.escape(symbol) + r",[^\n]*$", text)
    if len(bodies) != 1:
        raise Core0Error(f"generated boundary @{symbol} is missing/duplicated")
    return [line.strip() for line in bodies[0].splitlines() if line.strip() and not line.strip().startswith("#")]


def _raw_function(text: str, ranges: dict[str, tuple[int, int]], symbol: str) -> bytes:
    if symbol not in ranges:
        raise Core0Error(f"machine boundary @{symbol} is missing")
    begin, size = ranges[symbol]
    words = {}
    for line in text.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+\S+", line)
        if match and begin <= (address := int(match[1], 16)) < begin + size:
            if address in words:
                raise Core0Error("machine boundary contains duplicate instruction bytes")
            words[address] = int(match[2], 16)
    if set(words) != set(range(begin, begin + size, 4)):
        raise Core0Error("machine boundary raw instruction byte coverage differs")
    return b"".join(struct.pack("<I", words[address]) for address in sorted(words))


def validate_enter_user_machine(raw: bytes) -> dict:
    if len(raw) != 91 * 4 or hashlib.sha256(raw).hexdigest() != ENTER_USER_SHA256:
        raise Core0Error("actual caller context save/U restore machine bytes differ")
    words = struct.unpack("<91I", raw)
    stores = sum(word & 0x7f == 0x23 for word in words)
    loads = sum(word & 0x7f == 0x03 for word in words)
    if stores != 38 or loads != 37 or words[-1] != 0x10200073:
        raise Core0Error("actual context load/store/return inventory differs")
    return {"instructions": 91, "stores": stores, "loads": loads, "sha256": hashlib.sha256(raw).hexdigest()}


def validate_context_abi(assembly: str, raw_machine: str, ranges: dict[str, tuple[int, int]],
                         user_assembly: str, user_root: str, user_case: str = "none") -> dict:
    restore = ["ld t0, 272(sp)", "csrw satp, t0", "sfence.vma zero, zero", "ld t0, 256(sp)",
               "csrw sepc, t0", "ld t0, 264(sp)", "csrw sstatus, t0"]
    restore += [f"ld {register}, {index * 8}(sp)" for index, register in enumerate(GPR_NAMES) if index and register not in {"sp", "t0"}]
    restore += ["ld t0, 280(sp)", "csrw sscratch, t0", "ld t0, 40(sp)", "ld sp, 16(sp)", "sret"]
    expected = ["addi sp, sp, -16", "sd t0, 0(sp)", "sd t1, 8(sp)", "li t0, 2152726528", "sd zero, 0(t0)"]
    expected += [f"sd {register}, {index * 8}(t0)" for index, register in enumerate(GPR_NAMES) if index and register not in {"sp", "t0", "t1"}]
    expected += ["addi t1, sp, 16", "sd t1, 16(t0)", "ld t1, 0(sp)", "sd t1, 40(t0)", "ld t1, 8(sp)",
                 "sd t1, 48(t0)", "sd ra, 256(t0)", "li t1, 8589934848", "sd t1, 264(t0)",
                 "csrr t1, satp", "sd t1, 272(t0)", "sd zero, 280(t0)", "addi sp, sp, 16", "mv sp, a0", *restore]
    if _assembly_function(assembly, "lemma_exec_enter_user") != expected:
        raise Core0Error("generated caller context save/U restore differs from the closed ABI")
    raw = _raw_function(raw_machine, ranges, "lemma_exec_enter_user")
    validate_enter_user_machine(raw)
    if "lemma_supervisor_vector" in ranges:
        vector = _assembly_function(assembly, "lemma_supervisor_vector")
        if vector[-len(restore):] != restore or hashlib.sha256(_raw_function(raw_machine, ranges, "lemma_supervisor_vector")[-41 * 4:]).hexdigest() != SUPERVISOR_RESTORE_SHA256:
            raise Core0Error("supervisor vector does not share the complete trusted restore ABI")
    validate_user_entry_source(user_assembly, user_root, user_case)
    return {"layout": CONTEXT_LAYOUT, "kernel_resume_status": 0x200000100, "saved_gpr_slots": 32,
            "fixed_frame_stores": 36, "temporary_spill_stores": 2, "shared_restore_loads": 35,
            "total_enter_loads": 37, "enter_machine_instructions": 91, "shared_restore_machine_instructions": 41,
            "enter_machine_sha256": hashlib.sha256(raw).hexdigest(), "restore_machine_sha256": SUPERVISOR_RESTORE_SHA256,
            "original_sp_and_t0_t1_preserved": True, "caller_satp_readback_saved": True,
            "kernel_resume_sie": 0, "kernel_resume_scratch": 0, "initial_user_argument": "a0:u64"}


def validate_user_entry_source(assembly: str, root: str, case: str) -> None:
    if case not in {"none", *USER_ATTACKS}:
        raise Core0Error("unknown user startup ABI case")
    prefix = [f"call {root}"] if case == "none" else ["mv gp, zero", "mv tp, zero", f"call {root}",
              "bnez a0, .Luser_exit", f"call {USER_ATTACKS[case][0]}", ".Luser_exit:"]
    expected = [*prefix, *(f"li a{register}, 0" for register in range(1, 7)), "li a7, 6",
                "ecall", ".Luser_exit_returned:", "j .Luser_exit_returned"]
    if _assembly_function(assembly, "_user_start") != expected:
        raise Core0Error("user startup does not forward its initial word to the exact Action root")


def validate_user_syscall_bridge(assembly: str, raw_machine: str, ranges: dict[str, tuple[int, int]]) -> dict:
    symbol = "lemma_exec_syscall"
    expected = ["mv a7, a0", "mv a0, a1", "mv a1, a2", "mv a2, a3", "mv a3, a4", "mv a4, a5", "ecall", "ret"]
    packed = struct.pack("<8I", *USER_SYSCALL_WORDS)
    if _assembly_function(assembly, symbol) != expected or _raw_function(raw_machine, ranges, symbol) != packed:
        raise Core0Error("user syscall register transport/ECALL/return differs from the declared ABI")
    base, size = ranges[symbol]
    return {"symbol": symbol, "base": base, "bytes": size, "ecall_pc": base + 24,
            "number_register": "a7", "argument_registers": ["a0", "a1", "a2", "a3", "a4"],
            "result_registers": ["a0:status", "a1:value"], "raw_sha256": hashlib.sha256(packed).hexdigest()}


def validate_instruction_selection(case: str, *, configuration: str, image_key: str | None, unit: dict) -> None:
    """Only an exact selected genuine Entry root can reach a K startup site."""
    expected = (USER_INSTRUCTION_CONFIGURATIONS.get(configuration) if image_key is None else
                SERVICE_INSTRUCTION_CONFIGURATIONS.get(configuration) if image_key == "fault" else None)
    if case not in INSTRUCTION_CASES or expected != case:
        raise Core0Error("instruction startup authority differs from its exact configuration/image")
    validate_unit(unit, "user", configuration=configuration, image_key=image_key)
    if [(row["source"], row["args"]) for row in unit["roots"]] != [("Lemma.User.Entry.main", ["u64"])]:
        raise Core0Error("instruction probe lacks the genuine initial-data/BSS Entry precondition")

def validate_architecture_diagnostics(unit: dict, pre_ir: str) -> dict:
    """Bind diagnostic words to the validated original frame, not a literal.

    This is a narrow genuine source/CFG obligation. Actual U origin, opcode,
    trap contents, termination and continuing peers require guest evidence.
    """
    configuration = unit.get("configuration")
    managed = configuration in SERVICE_INSTRUCTION_CONFIGURATIONS
    if configuration not in { *USER_INSTRUCTION_CONFIGURATIONS, *SERVICE_INSTRUCTION_CONFIGURATIONS } or unit.get("role") != "kernel":
        raise Core0Error("architecture diagnostics require one exact selected kernel configuration")
    by = {re.sub(r"^_private\..*?\.[0-9]+\.", "", row["source"]): row["symbol"] for row in unit["functions"]}
    p, q, t, x, c = "Lemma.Kernel.Process.", "Lemma.Kernel.Scheduler.", "Lemma.Kernel.Task.", "Lemma.Kernel.Memory.Access.", "Lemma.Kernel.Console."
    required = {p + "validateFrame", x + "read64", c + "record"}
    required |= ({q + "dispatch", q + "reportFault", q + "failed", q + "finish", q + "returnKernel", t + "capture", t + "failed",
                  ("Lemma.Kernel.Memory.AddressSpace.base" if any(re.sub(r"^_private\..*?\.[0-9]+\.","",r["source"])==t+"contextAt" for r in unit["functions"]) else "Lemma.Kernel.Memory.AddressSpace.context")} if managed else
                 {p + "dispatch", p + "userTrap", p + "failed", p + "finish"})
    if not required <= by.keys(): raise Core0Error("architecture diagnostic genuine source closure is incomplete")
    body = {source: _ir_definition_body(pre_ir, by[source]) for source in required}
    variable = r"%[-A-Za-z0-9_.$]+"
    def status_load(source, frame):
        offsets = re.findall(r"(" + variable + r") = add i64 " + re.escape(frame) + r", 264$", body[source], re.M)
        if len(offsets) != 1: raise Core0Error("diagnostic status is not read from the original hardware frame+264")
        calls = re.findall(r"(" + variable + r") = call \{ i64, i64 \} @" + re.escape(by[x + "read64"]) + r"\(i64 " + re.escape(offsets[0]) + r"\)", body[source])
        values = re.findall(r"(" + variable + r") = extractvalue \{ i64, i64 \} " + re.escape(calls[0] if len(calls) == 1 else "NO_STATUS_LOAD") + r", 1$", body[source], re.M)
        if len(calls) != 1 or len(values) != 1: raise Core0Error("hardware status load/result binding is missing or duplicated")
        return values[0]
    if managed:
        dispatch, report, failed = q + "dispatch", q + "reportFault", q + "failed"
        gates = [{"source": dispatch, **validate_failed_call_gate(body[dispatch], by[t + "capture"], by[report], by[failed], body[failed])}]
        capture_body = _ir_definition_body(pre_ir, by[t + "capture"])
        task_failed = by.get(t + "failed")
        context = by.get("Lemma.Kernel.Memory.AddressSpace.base" if t+"contextAt" in by else "Lemma.Kernel.Memory.AddressSpace.context")
        if task_failed is None or context is None: raise Core0Error("capture ownership proof source closure is incomplete")
        gates.append({"source": t + "capture", **validate_failed_call_gate(capture_body, by[p + "validateFrame"], context, task_failed, _ir_definition_body(pre_ir, task_failed))})
        calls = re.findall(r"call \{ i64, i64 \} @" + re.escape(by[report]) + r"\(([^)]+)\)", body[dispatch])
        if len(calls) != 2 or any(re.fullmatch(r"i64 " + variable + r", i64 %arg0, i64 %arg1, i64 %arg2, i64 " + variable, args) is None for args in calls):
            raise Core0Error("managed fault paths substitute the original frame/cause/stval")
        raw_status = status_load(report, "%arg1")
        expected_d4 = "i64 212, i64 %arg2, i64 %arg4, i64 %arg3, i64 " + raw_status
        if re.findall(r"call \{ i64, i64 \} @" + re.escape(by[c + "record"]) + r"\(([^)]+)\)", body[report]) != [expected_d4]:
            raise Core0Error("managed D4 substitutes sanitized or fabricated hardware trap fields")
        if re.findall(r"call \{ i64, i64 \} @" + re.escape(by[q + "finish"]) + r"\(([^)]+)\)", body[report]) != ["i64 %arg0, i64 %arg2, i64 44, i64 %arg4, i64 %arg3"]:
            raise Core0Error("managed diagnostic does not terminate the same task with code44")
        gates.extend([{"source": report, **validate_failed_call_gate(body[report], by[x + "read64"], by[c + "record"], by[failed], body[failed])},
                      {"source": report, **validate_failed_call_gate(body[report], by[c + "record"], by[q + "finish"], by[failed], body[failed])}])
        ordered = validate_call_precedes(body[report], by[c + "record"], by[q + "finish"])
        finish = body[q + "finish"]
        comparisons = re.findall(r"(" + variable + r") = icmp eq i64 %arg1, 8$", finish, re.M)
        branches = re.findall(r"br i1 " + re.escape(comparisons[0] if len(comparisons) == 1 else "NO_CAUSE") + r", label %(\S+), label %(\S+)", finish)
        phis = re.findall(r"(" + variable + r") = phi i64 \[ 4, %([^ ]+) \], \[ 5, %([^ ]+) \]", finish)
        if len(branches) != 1 or len(phis) != 1 or branches[0] != phis[0][1:] or not re.search(
            r"call \{ i64, i64 \} @" + re.escape(by[q + "returnKernel"]) + r"\(i64 %arg0, i64 " + re.escape(phis[0][0]) + r", i64 %arg3\)", finish):
            raise Core0Error("managed code44 return reason is not cause8->4 / otherfault->5")
    else:
        dispatch, trap, failed = p + "dispatch", p + "userTrap", p + "failed"
        gates = [{"source": dispatch, **validate_failed_call_gate(body[dispatch], by[p + "validateFrame"], by[x + "read64"], by[failed], body[failed])}]
        raw_status = status_load(dispatch, "%arg0")
        arguments = re.findall(r"call \{ i64, i64 \} @" + re.escape(by[trap]) + r"\(([^)]+)\)", body[dispatch])
        if len(arguments) != 1 or re.fullmatch(r"i64 " + variable + r", i64 %arg0, i64 %arg1, i64 %arg2, i64 " + variable + r", i64 " + re.escape(raw_status) + r", i64 " + variable, arguments[0]) is None:
            raise Core0Error("single-process dispatch does not forward its actual saved hardware status")
        d4_args = "i64 212, i64 %arg2, i64 %arg4, i64 %arg3, i64 %arg5"
        finish_args = "i64 %arg0, i64 %arg2, i64 44, i64 %arg4, i64 %arg5, i64 %arg6"
        if len(re.findall(r"call \{ i64, i64 \} @" + re.escape(by[c + "record"]) + r"\(" + re.escape(d4_args) + r"\)", body[trap])) != 2:
            raise Core0Error("halfword and hardware faults lack actual D4 PC/stval/status diagnostics")
        if len(re.findall(r"call \{ i64, i64 \} @" + re.escape(by[p + "finish"]) + r"\(" + re.escape(finish_args) + r"\)", body[trap])) != 2:
            raise Core0Error("halfword and hardware faults lack same-instance termination44")
        ordered = validate_call_precedes(body[trap], by[c + "record"], by[p + "finish"],
                    before_arguments=re.escape(d4_args), after_arguments=re.escape(finish_args))
    return {"raw_status_offset": 264, "diagnostic_tag": 212, "diagnostic_words": ["cause", "pc", "stval", "original_hardware_status"],
            "termination_code": 44, "halfword_ecall_return_reason": 4 if managed else None,
            "hardware_fault_return_reason": 5 if managed else None,
            "source_functions": {source: by[source] for source in sorted(required)}, "ownership_gates": gates,
            "diagnostic_before_termination": ordered,
            "limitations": ["Necessary genuine source/CFG binding; hardware trap, containment and service continuation require actual guest evidence."]}


def _attack_source(case: str) -> list[str]:
    return {"supervisor-csr": ["csrr a0, sstatus", "ret"],
            "execute-data": ["li t0, 131072", "jalr zero, 0(t0)"],
            "execute-kernel": ["li t0, 2149580800", "jalr zero, 0(t0)"],
            "execute-misaligned": ["li t0, 65538", "jalr zero, 0(t0)"],
            "halfword-ecall": ["la t0, .Llemma_user_halfword_ecall_pair", "addi t0, t0, 2", "jalr zero, 0(t0)",
                               ".Llemma_user_halfword_ecall_pair:", "addi zero, t1, 7", ".word 0x00000000"],
            "return-supervisor": ["sret"], "return-machine": ["mret"]}[case]


def validate_user_attack_machine(raw_machine: str, ranges: dict[str, tuple[int, int]],
                                 assembly: str, case: str, *, raw_bytes: bytes | None = None,
                                 configuration: str | None = None, image_key: str | None = None,
                                 unit: dict | None = None) -> dict:
    attacks = {symbol for symbol in ranges if symbol.startswith("lemma_user_attack_")}
    if case == "none":
        if attacks or ".text.user_adversarial" in assembly:
            raise Core0Error("ordinary user artifact contains quarantined attack code")
        return {"case": "none", "privileged_instruction_exceptions": []}
    if case not in USER_ATTACKS:
        raise Core0Error("unknown quarantined user attack")
    if case in INSTRUCTION_CASES:
        validate_instruction_selection(case, configuration=configuration, image_key=image_key, unit=unit)
    symbol, effect, words = USER_ATTACKS[case]
    packed = struct.pack(f"<{len(words)}I", *words)
    actual = raw_bytes if case == "halfword-ecall" else _raw_function(raw_machine, ranges, symbol)
    if attacks != {symbol} or actual != packed or ranges.get(symbol, (None, None))[1] != len(packed):
        raise Core0Error("quarantined user attack symbol/opcode/size inventory differs")
    if _assembly_function(assembly, symbol) != _attack_source(case) or len(re.findall(r'(?m)^\.section \.text\.user_adversarial,\s*"ax",\s*@progbits$', assembly)) != 1:
        raise Core0Error("quarantined user attack generated source/section differs")
    base, size = ranges[symbol]
    if base % 4 or size % 4:
        raise Core0Error("quarantined function envelope is not word aligned")
    if case == "execute-misaligned":
        if ranges.get("_user_start", (None, None))[0] != 0x10000 or _raw_function(raw_machine, ranges, "_user_start")[:4] != struct.pack("<I", 0x00000193):
            raise Core0Error("illegal-halfword fixture lacks its exact audited startup word/target")
    if case in INSTRUCTION_CASES:
        offset, opcode = INSTRUCTION_CASES[case]
        if struct.unpack_from("<I", actual, offset)[0] != opcode:
            raise Core0Error("instruction site is not the exact linked four-byte opcode")
        site = {"pc": base + offset, "offset": offset, "instruction_bits": 32, "opcode": opcode}
        return {"case": case, "symbol": symbol, "effect": effect, "base": base, "bytes": size,
                "raw_sha256": hashlib.sha256(actual).hexdigest(), "fault_pc": site["pc"],
                "instruction_site": site,
                "privileged_instruction_exceptions": [site["pc"]] if case != "halfword-ecall" else [],
                **({"overlapping_words": {"offset": 16, "bytes": 8, "words": [0x00730013, 0],
                                           "instruction_pair_offset": 2}} if case == "halfword-ecall" else {})}
    return {"case": case, "symbol": symbol, "effect": effect, "base": base, "bytes": size,
            "raw_sha256": hashlib.sha256(packed).hexdigest(),
            "fault_pc": {"supervisor-csr": base, "execute-data": 0x20000,
                         "execute-kernel": 0x80200000, "execute-misaligned": 0x10002}[case],
            "privileged_instruction_exceptions": [base] if case == "supervisor-csr" else []}


def validate_user_attack_object(section_text: str, symbol_text: str, raw: bytes, assembly: str,
                                *, configuration: str, image_key: str | None, unit: dict | None = None,
                                relocation_text: str = "") -> dict:
    """The same object scanner covers singleton and selected managed probes."""
    image = image_spec(configuration, image_key) if image_key is not None else None
    case = image["startup_case"] if image is not None else user_startup_case(configuration)
    attacks = {symbol for symbol in defined_function_symbols(symbol_text) if symbol.startswith("lemma_user_attack_")}
    sections = re.findall(r"(?m)^.*\.text\.user_adversarial\s+.*$", section_text)
    if case == "none":
        if sections or attacks or raw or ".text.user_adversarial" in assembly:
            raise Core0Error("ordinary selected user startup object contains quarantined code")
        return {"case": "none", "privileged_instruction_exceptions": []}
    if case in INSTRUCTION_CASES:
        validate_instruction_selection(case, configuration=configuration, image_key=image_key, unit=unit)
    elif image_key is not None and (configuration, image_key, case) != ("tasks-fault-development", "fault", "supervisor-csr"):
        raise Core0Error("unknown per-image privileged instruction authority")
    symbol, effect, words = USER_ATTACKS[case]
    # LLVM's assembler resolves this same-section local LA in startup.o.
    # Its exact AUIPC(0)/ADDI(16) pair is already relocation-free; accepting
    # unresolved placeholders or foreign relocations would change authority.
    expected_raw = struct.pack(f"<{len(words)}I", *words)
    section = re.fullmatch(r"\s*\[\s*(\d+)\]\s+\.text\.user_adversarial\s+PROGBITS\s+0+\s+[0-9a-f]+\s+([0-9a-f]+)\s+00\s+AX\s+0\s+0\s+4\s*", sections[0]) if len(sections) == 1 else None
    rows = [line.split() for line in symbol_text.splitlines() if line.split() and line.split()[-1] == symbol]
    if (section is None or int(section[2], 16) != len(expected_raw) or attacks != {symbol} or len(rows) != 1 or len(rows[0]) != 8
            or rows[0][1:] != ["0000000000000000", str(len(expected_raw)), "FUNC", "GLOBAL", "DEFAULT", section[1], symbol]
            or raw != expected_raw or _assembly_function(assembly, symbol) != _attack_source(case)
            or len(re.findall(r'(?m)^\.section \.text\.user_adversarial,\s*"ax",\s*@progbits$', assembly)) != 1):
        raise Core0Error("startup object attack section/symbol/bytes/source inventory differs")
    relocations = re.findall(r"(?ms)^Relocation section ['\"]\.rela\.text\.user_adversarial['\"][^\n]*\n(.*?)(?=^Relocation section |\Z)", relocation_text)
    relocation_rows = [line.split() for block in relocations for line in block.splitlines() if re.match(r"\s*[0-9a-f]+\s+[0-9a-f]+\s+R_", line)]
    evidence = None
    if case == "halfword-ecall":
        if relocations or relocation_rows:
            raise Core0Error("halfword same-section local pair has unexpected relocations")
        mapping = [row for line in symbol_text.splitlines() if len(row := line.split()) == 8
                   and row[3:7] == ["NOTYPE", "LOCAL", "DEFAULT", section[1]]]
        if sorted((int(row[1], 16), row[7]) for row in mapping) != [(0, "$x"), (20, "$d")]:
            raise Core0Error("halfword object instruction/fixed-zero mapping differs")
        evidence = {"kind": "assembler-resolved-local-pair", "pc_relative_start": 0,
                    "pair_offset": 16, "halfword_offset": 2, "relocations": []}
    elif relocation_rows:
        raise Core0Error("fixed attack instruction object has unexpected relocations")
    owner = image["directory"] + "/startup.o" if image is not None else "user/startup.o"
    record = {"case": case, "symbol": symbol, "effect": effect, "bytes": len(raw),
              "section": ".text.user_adversarial", "object": owner,
              "raw_sha256": hashlib.sha256(raw).hexdigest(), "privileged_instruction_exceptions": [0] if case == "supervisor-csr" else []}
    if case in INSTRUCTION_CASES:
        offset, opcode = INSTRUCTION_CASES[case]
        if struct.unpack_from("<I", raw, offset)[0] != opcode:
            raise Core0Error("object instruction site differs from its declared four-byte opcode")
        record.update(base=0, instruction_site={"pc": offset, "offset": offset, "instruction_bits": 32, "opcode": opcode},
                      privileged_instruction_exceptions=[offset] if case != "halfword-ecall" else [])
        if evidence is not None: record["local_pair_resolution"] = evidence
    return record


def validate_image_attack_object(section_text: str, symbol_text: str, raw: bytes, assembly: str,
                                *, configuration: str, image_key: str, unit: dict | None = None,
                                relocation_text: str = "") -> dict:
    return validate_user_attack_object(section_text, symbol_text, raw, assembly,
                                      configuration=configuration, image_key=image_key, unit=unit,
                                      relocation_text=relocation_text)


def _validate_readonly_pmp_lookup(ir: str, unit: dict, *, optimized: bool) -> tuple[set[int], list[dict]]:
    """Admit only LLVM's observed immutable lookup for the fixed PMP policy.

    The closed three-block body proves the table index is below four before
    its sole load. No other global, pointer derivation, use, or load is admitted.
    """
    lines = ir.splitlines()
    globals_ = [line.strip() for line in lines if re.match(r"^\s*@", line)]
    if not globals_:
        return set(), []
    source = "Lemma.Kernel.MachineServices.expectedPmp"
    rows = [row for row in unit["functions"] if row["source"] == source]
    if not optimized or unit["role"] != "kernel" or len(rows) != 1 or rows[0]["args"] != ["u64"] or rows[0]["effects"]:
        raise Core0Error("IR global lacks the exact pure kernel PMP source authority")
    symbol = rows[0]["symbol"]
    table = "switch.table." + symbol
    values = [0x20001fff, 0x20041fff, 0x20ffffff, 0x0400001f]
    expected_global = f"@{table} = private unnamed_addr constant [4 x i64] [" + ", ".join(f"i64 {value}" for value in values) + "], align 8"
    if globals_ != [expected_global] or len(re.findall(r"@" + re.escape(table) + r"(?![A-Za-z0-9_.$-])", ir)) != 2:
        raise Core0Error("readonly PMP table global/content/use inventory differs")
    from audit_memory import parse_ir_functions, _parse_blocks
    functions = parse_ir_functions(ir)
    function = functions.get(symbol)
    if function is None or not re.search(r"\bi64 @" + re.escape(symbol) + r"\(i64 %arg0\)", function.header):
        raise Core0Error("readonly PMP lookup LLVM signature differs")
    load = "%switch.load = load i64, ptr %switch.gep, align 8"
    expected_blocks = {
        "entry": ["%0 = icmp ult i64 %arg0, 4", "br i1 %0, label %switch.lookup, label %if.merge.2"],
        "switch.lookup": [f"%switch.gep = getelementptr inbounds nuw [4 x i64], ptr @{table}, i64 0, i64 %arg0",
                          load, "br label %if.merge.2"],
        "if.merge.2": ["%if.result7 = phi i64 [ %switch.load, %switch.lookup ], [ 262655, %entry ]", "ret i64 %if.result7"],
    }
    blocks = _parse_blocks("\n".join(line.split(";", 1)[0] for line in function.body.splitlines()), symbol)
    if blocks != expected_blocks:
        raise Core0Error("readonly PMP lookup lacks its exact dominating bound guard/body")
    owners = _line_functions(lines)
    load_sites = {index for index, line in enumerate(lines) if line.strip() == load and owners[index] == symbol}
    if len(load_sites) != 1:
        raise Core0Error("readonly PMP lookup load inventory differs")
    return load_sites, [{"source": source, "function": symbol, "global": table, "values": values,
                         "element_bits": 64, "alignment_bytes": 8, "index_bound": 4, "default": 262655,
                         "guarded_loads": 1, "readonly": True}]


def validate_readonly_pmp_lookup(ir: str, unit: dict, *, optimized: bool) -> tuple[set[int], list[dict]]:
    """Preserve PMP admission; add only the two observed managed-policy lookups."""
    if optimized and unit.get("configuration") in LEMMASIM_CONFIGURATIONS:
        from lemmasim_readonly import validate_lookup
        sim_sites, sim_tables, removed = validate_lookup(ir, unit)
        filtered = "\n".join("" if line.strip() in removed else line for line in ir.splitlines())
        # Re-enter the unchanged historical policy with its closed admission.
        old_unit = {**unit, "configuration": "normal"}
        old_sites, old_tables = validate_readonly_pmp_lookup(filtered, old_unit, optimized=optimized)
        return sim_sites | old_sites, [*old_tables, *sim_tables]
    if unit.get("role") != "kernel" or not optimized:
        return _validate_readonly_pmp_lookup(ir,unit,optimized=optimized)
    lines=ir.splitlines();globals_=[line.strip() for line in lines if re.match(r"^\s*@",line)]
    if not globals_:
        return _validate_readonly_pmp_lookup(ir,unit,optimized=optimized)
    by_source={re.sub(r"^_private\..*?\.[0-9]+\.","",row["source"]):row for row in unit["functions"]}
    specs=[("Lemma.Kernel.Objects.replyLimitFor",[8,8,7],["u64"],[]),
           ("Lemma.User.CapabilityABI.typeMask",[35,124,928,1056,1],["u64"],[]),
           ("Lemma.Kernel.Objects.initStep",[1,3,4],["u32","u32","u64","u64","u64","u64","u64"],["checked-access","physical-write"])]
    accepted_globals=[];sites=set();observed=[];owners=_line_functions(lines)
    from audit_memory import parse_ir_functions,_parse_blocks
    functions=parse_ir_functions(ir)
    for source,values,args,effects in specs:
        row=by_source.get(source)
        if row is None:
            continue
        if row["args"]!=args or row["effects"]!=effects:
            raise Core0Error("H readonly lookup lacks its exact source/signature/effects")
        symbol=row["symbol"];table="switch.table."+symbol;count=len(values)
        expected=f"@{table} = private unnamed_addr constant [{count} x i64] ["+", ".join(f"i64 {value}" for value in values)+"], align 8"
        if globals_.count(expected)!=1 or len(re.findall(r"@"+re.escape(table)+r"(?![A-Za-z0-9_.$-])",ir))!=2:
            raise Core0Error("H readonly lookup exact global/content/use inventory differs")
        function=functions.get(symbol)
        types={"u32":"i32","u64":"i64"}
        if function is None or re.findall(r"\b(i1|i8|i32|i64)\b",re.search(r"@"+re.escape(symbol)+r"\(([^\n]*)\)",function.header).group(1))!=[types[t] for t in args]:
            raise Core0Error("H readonly lookup LLVM argument signature differs")
        body="\n".join(line.split(";",1)[0].rstrip() for line in function.body.splitlines())
        blocks=_parse_blocks(body,symbol);load="%switch.load = load i64, ptr %switch.gep, align 8"
        if source=="Lemma.Kernel.Objects.replyLimitFor":
            expected_blocks={"entry":["%switch.tableidx = add i64 %arg0, -1","%0 = icmp ult i64 %switch.tableidx, 3","br i1 %0, label %switch.lookup, label %if.merge.2"],
                "switch.lookup":[f"%switch.gep = getelementptr inbounds nuw [3 x i64], ptr @{table}, i64 0, i64 %switch.tableidx",load,"br label %if.merge.2"],
                "if.merge.2":["%if.result8 = phi i64 [ 0, %entry ], [ %switch.load, %switch.lookup ]","ret i64 %if.result8"]}
            if blocks!=expected_blocks:raise Core0Error("Objects-v3 optimized reply quota lacks exact version1..3 bound/default/load")
        elif source=="Lemma.User.CapabilityABI.typeMask":
            expected_blocks={"entry":["%switch.tableidx = add i64 %arg0, -1","%0 = icmp ult i64 %switch.tableidx, 5","br i1 %0, label %switch.lookup, label %if.merge.2"],
                             "switch.lookup":[f"%switch.gep = getelementptr inbounds nuw [5 x i64], ptr @{table}, i64 0, i64 %switch.tableidx",load,"br label %if.merge.2"],
                             "if.merge.2":["%if.result19 = phi i64 [ %switch.load, %switch.lookup ], [ 0, %entry ]","ret i64 %if.result19"]}
            if blocks!=expected_blocks or not re.search(r"\bi64 @"+re.escape(symbol)+r"\(i64 %arg0\)",function.header):
                raise Core0Error("H type-mask lookup lacks exact subtraction/bound guard/default/body")
        else:
            put=by_source.get("Lemma.Kernel.Objects.put",{}).get("symbol")
            if put is None or not re.search(r"define \{ i64, i64 \} @"+re.escape(symbol),function.header):
                raise Core0Error("H pinned-kind lookup lacks checked initialization source")
            if blocks.get("action.if.else.1")!=["%bin15 = add i64 %call1, 16","%0 = icmp ult i32 %arg0, 3","br i1 %0, label %switch.lookup, label %if.merge.5"] or blocks.get("switch.lookup")!=["%1 = zext nneg i32 %arg0 to i64",f"%switch.gep = getelementptr inbounds nuw [3 x i64], ptr @{table}, i64 0, i64 %1",load,"br label %if.merge.5"]:
                raise Core0Error("H pinned-kind lookup lacks exact bounded index/load block")
            merge=blocks.get("if.merge.5",[])
            if len(merge)<2 or merge[:2]!=["%if.result27 = phi i64 [ 0, %action.if.else.1 ], [ %switch.load, %switch.lookup ]",f"%action.call.result28 = call {{ i64, i64 }} @{put}(i64 %bin15, i64 %if.result27)"] or len(re.findall(r"%if\.result27(?![A-Za-z0-9_.$-])",body))!=2:
                raise Core0Error("H pinned-kind result escapes its sole object-kind publication")
            successors=_structured_successors(_structured_ir_blocks(body))
            without_guard={block:tuple(target for target in targets if (block,target)!=("action.if.else.1","switch.lookup")) for block,targets in successors.items()}
            if _structured_reachable(without_guard,"entry","switch.lookup") or _structured_reachable(successors,"if.merge.5","switch.lookup"):
                raise Core0Error("H pinned-kind lookup has a bound-guard bypass")
        located={i for i,line in enumerate(lines) if line.strip()==load and owners[i]==symbol}
        if len(located)!=1 or len(re.findall(r"%switch\.gep(?![A-Za-z0-9_.$-])",body))!=2 or len(re.findall(r"%switch\.load(?![A-Za-z0-9_.$-])",body))!=2:
            raise Core0Error("H readonly pointer/load use inventory differs")
        sites|=located;accepted_globals.append(expected)
        observed.append({"source":row["source"],"function":symbol,"global":table,"values":values,"element_bits":64,"alignment_bytes":8,"index_bound":count,"default":0,"guarded_loads":1,"readonly":True})
    filtered="\n".join("" if line.strip() in accepted_globals else line for line in lines)
    pmp_sites,pmp=_validate_readonly_pmp_lookup(filtered,unit,optimized=True)
    return sites|pmp_sites,[*pmp,*observed]


def validate_pmp_constant_section(section_text: str, raw: bytes, *, object_file: str, tables: list[dict]) -> dict:
    values = [0x20001fff, 0x20041fff, 0x20ffffff, 0x0400001f]
    if (object_file != "kernel/program.o" or len(tables) != 1
            or tables[0].get("source") != "Lemma.Kernel.MachineServices.expectedPmp"
            or tables[0].get("values") != values or tables[0].get("readonly") is not True):
        raise Core0Error("32-byte constant section lacks its exact kernel PMP IR provenance")
    section_rows = re.findall(r"(?m)^.*\.rodata\.cst32\s+.*$", section_text)
    expected = r"\s*\[\s*\d+\]\s+\.rodata\.cst32\s+PROGBITS\s+[0-9a-f]+\s+[0-9a-f]+\s+000020\s+20\s+AM\s+0\s+0\s+8\s*"
    if len(section_rows) != 1 or not re.fullmatch(expected, section_rows[0]) or raw != struct.pack("<4Q", *values):
        raise Core0Error("PMP constant section size/flags/alignment/little-endian bytes differ")
    return {"object": object_file, "section": ".rodata.cst32", "bytes": 32, "flags": "AM", "alignment": 8,
            "source": tables[0]["source"], "values": values}


def validate_h_readonly_sections(section_text: str, symbol_text: str, relocation_text: str,
                                 constants: bytes, rodata: bytes, *, object_file: str, tables: list[dict],
                                 configuration: str = "capabilities-development") -> dict:
    """Exact current object inventory for genuinely reachable kernel helpers.

    The additive Reply ABI makes the shared mask five words. Historical H
    four-word outputs retain their old auditor/source binding; this scanner
    admits only the current five-word source contract.
    """
    configuration_roots(configuration)
    pmp=[0x20001fff,0x20041fff,0x20ffffff,0x0400001f];masks=[35,124,928,1056,1];kinds=[1,3,4]
    sources=["Lemma.Kernel.MachineServices.expectedPmp","Lemma.Kernel.Objects.replyLimitFor","Lemma.User.CapabilityABI.typeMask","Lemma.Kernel.Objects.initStep"]
    canonical={source:values for source,values in zip(sources,[pmp,[8,8,7],masks,kinds])}
    actual_sources=[re.sub(r"^_private\..*?\.[0-9]+\.","",row.get("source","")) for row in tables]
    if object_file!="kernel/program.o" or not 1<=len(tables)<=4 or actual_sources!=[source for source in sources if source in actual_sources] or len(set(actual_sources))!=len(actual_sources) or actual_sources[0]!=sources[0]:
        raise Core0Error("immutable tables lack their exact reachable kernel object inventory")
    if any(source not in canonical or row.get("values")!=canonical[source] or row.get("readonly") is not True for row,source in zip(tables,actual_sources)):
        raise Core0Error("object immutable-table source/content provenance differs")
    def section(name,size,entry_size,flags):
        rows=re.findall(r"(?m)^\s*\[\s*(\d+)\]\s+"+re.escape(name)+r"\s+PROGBITS\s+0+\s+[0-9a-f]+\s+([0-9a-f]+)\s+"+entry_size+r"\s+"+flags+r"\s+0\s+0\s+8\s*$",section_text)
        if len(rows)!=1 or int(rows[0][1],16)!=size:
            raise Core0Error("immutable-table section size/flags/alignment differs")
        return rows[0][0]
    cst_section=section(".rodata.cst32",32,"20","AM")
    ro_section=section(".rodata",len(rodata),"00","A") if any(source!=sources[0] for source in actual_sources) else None
    if constants!=struct.pack("<4Q",*pmp):
        raise Core0Error("PMP immutable bytes differ")
    rows=[line.split() for line in symbol_text.splitlines() if len(line.split())==8 and line.split()[3]=="OBJECT" and line.split()[6]!="UND"]
    expected_names={".L"+row["global"] for row in tables}
    if {row[-1] for row in rows}!=expected_names or len(rows)!=len(tables):
        raise Core0Error("immutable object-symbol inventory differs")
    observed=[];extents=[]
    for table,source in zip(tables,actual_sources):
        values=canonical[source];is_pmp=source==sources[0]
        row=next(row for row in rows if row[-1]==".L"+table["global"])
        offset,size=int(row[1],16),int(row[2]);section_id=cst_section if is_pmp else ro_section
        section_name=".rodata.cst32" if is_pmp else ".rodata"
        raw=constants if is_pmp else rodata
        if row[4:7]!=["LOCAL","DEFAULT",section_id] or size!=len(values)*8 or offset%8 or offset+size>len(raw) or raw[offset:offset+size]!=struct.pack("<"+str(len(values))+"Q",*values) or is_pmp and offset!=0:
            raise Core0Error("immutable table symbol extent/ownership/bytes differs")
        if any(previous_section==section_id and offset<previous_end and previous_start<offset+size for previous_section,previous_start,previous_end in extents):
            raise Core0Error("immutable table symbol extents overlap")
        extents.append((section_id,offset,offset+size))
        current=None
        for line in relocation_text.splitlines():
            header=re.search(r"Relocation section '([^']+)'",line)
            if header:current=header[1]
            relocation=re.match(r"\s*([0-9a-f]+)\s+[0-9a-f]+\s+(R_RISCV_[A-Z0-9_]+)\s",line)
            if relocation and current==".rela"+section_name and int(relocation[1],16)<offset+size and offset<int(relocation[1],16)+(8 if relocation[2].endswith("64") else 4):
                raise Core0Error("immutable table literal bytes contain a link relocation")
        observed.append({"source":table["source"],"symbol":row[-1],"section":section_name,"offset":offset,"bytes":size,"values":values,"sha256":hashlib.sha256(raw[offset:offset+size]).hexdigest(),"relocations":[]})
    return {"object":object_file,"configuration":configuration,"readonly_tables":observed,
            "constant_section_bytes":32,"constant_section_sha256":hashlib.sha256(constants).hexdigest()}


# Closed observed LLVM RV64 switch lowering, admitted by genuine source identity.
# The counts are backend artifact facts, not a new Core0 source-language feature.
BACKEND_JUMP_TABLES = {
    'Lemma.Kernel.Syscall.memoryStatus': ('kernel', 77, ['u8'], [], [0,33,37,38,71,72,73,74,76]),
    'Lemma.Kernel.BootInfo.tokenStep': ('kernel', 9, ['u32','u32',*(['u64']*5)], ['checked-access','physical-read','physical-write'], [1,2,3,4,9]),
    'Lemma.Kernel.IPC.dispatch': ('kernel', 6, ['u64']*7, ['checked-access','io-order','machine-state','physical-read','physical-write','firmware-call'], list(range(20,26))),
    'Lemma.Kernel.Syscall.dispatchLegacy': ('kernel', 8, ['u64']*7, ['checked-access','mmio-read','mmio-write','io-order','machine-state','interrupt-state','physical-read','physical-write','firmware-call','address-space','wait-state'], [1,2,3,4,5,7,8]),
    'Lemma.Kernel.Syscall.dispatchManaged': ('kernel', 18, ['u64']*7, ['checked-access','mmio-read','mmio-write','io-order','machine-state','interrupt-state','physical-read','physical-write','firmware-call','address-space','wait-state'], [2,*range(9,20)]),
    'Lemma.Platform.RiscV.Firmware.call': ('firmware', 5, ['u64']*3, ['checked-access','mmio-read','mmio-write','io-order','machine-state','timer-state','interrupt-state','physical-read','physical-write'], list(range(1,6))),
    'Lemma.Kernel.Development.FramesEntry.operation': ('kernel', 22, ['u64']*5, ['checked-access','io-order','machine-state','physical-read','physical-write','address-space','instruction-sync'], [*range(7),*range(8,22)]),
    'Lemma.Kernel.Development.ServiceEntry.command': ('kernel', 17, ['u64']*5, ['checked-access','mmio-read','mmio-write','io-order','machine-state','physical-read','physical-write','address-space','instruction-sync'], [49,50,51,64,65]),
    'Lemma.Services.Buffer.Protocol.requestShape': ('user', 6, ['u64']*6, [], list(range(1,7))),
    'Lemma.Services.Buffer.Server.existing': ('user', 5, ['u64']*9, ['checked-access','io-order','virtual-read','virtual-write','user-syscall','privilege-transition'], list(range(2,7))),
}
BACKEND_JUMP_TABLE_CONFIGURATIONS = {
    'Lemma.Kernel.Development.FramesEntry.operation': {'frames-development'},
    'Lemma.Kernel.Development.ServiceEntry.command': set(SERVICE_CONFIGURATIONS) - {'service-normal'},
    'Lemma.Services.Buffer.Protocol.requestShape': set(SERVICE_CONFIGURATIONS),
    'Lemma.Services.Buffer.Server.existing': set(SERVICE_CONFIGURATIONS),
}
BACKEND_JUMP_TABLE_USER_IMAGES = {
    'Lemma.Services.Buffer.Protocol.requestShape': {'server'},
    'Lemma.Services.Buffer.Server.existing': {'server'},
}
LEMMASIM_BACKEND_JUMP_TABLES = {
    # Pure descriptor identity selection for the five exact declared bindings.
    'Lemma.Platform.LemmaSim.Descriptor.expectedBinding': ('kernel',5,['u64','u64'],[],list(range(1,6))),
    'Lemma.Platform.LemmaSim.DeviceService.surface': ('kernel',5,['u64']*6,['checked-access','mmio-read','mmio-write','io-order','physical-read','physical-write'],list(range(5))),
    'Lemma.Kernel.IPC.dispatchWithLimit': ('kernel',6,['u64']*8,['checked-access','io-order','machine-state','physical-read','physical-write','firmware-call'],list(range(20,26))),
    'Lemma.Kernel.Syscall.dispatchManagedWithIPCLimit': ('kernel',18,['u64']*8,['checked-access','mmio-read','mmio-write','io-order','machine-state','interrupt-state','physical-read','physical-write','firmware-call','address-space','wait-state'],[2,*range(9,20)]),
    # The maintained discovery parser contains the additive Power and manual
    # BLE literal inventories. Legacy bindings still reject
    # undeclared device roles; this is exact literal provenance, not an MMIO
    # authority extension. Older immutable artifacts retain their prior audit.
    'Lemma.Platform.LemmaSim.DescriptorDTB.literalWord': ('kernel',75,['u64','u64'],[],[*range(2,20),*range(32,56),*range(64,77)]),
    'Lemma.Platform.LemmaSim.DescriptorDTB.leafProperty': ('kernel',15,['u64']*4,['checked-access','physical-read','physical-write'],[36,45,47,48,49,50]),
    'Lemma.Platform.LemmaSim.DescriptorDTB.tokenStep': ('kernel',9,['u32','u32',*(['u64']*5)],['checked-access','physical-read','physical-write'],[1,2,3,4,9]),
    'Lemma.Services.Store.Protocol.shape': ('user',10,['u64']*7,[],list(range(1,11))),
    'Lemma.Services.Store.Engine.complete': ('user',81,['u64','u8'],['checked-access','virtual-read','virtual-write'],[*range(1,6),*range(16,22),*range(32,41),*range(64,70),80,81]),
    'Lemma.Services.Store.Server.application': ('user',9,['u64']*3,['checked-access','io-order','virtual-read','virtual-write','user-syscall','privilege-transition'],[2,3,4,5,6,7,9,10]),
    'Lemma.Applications.Notebook.toolbar': ('user',9,['u64'],['checked-access','io-order','virtual-read','virtual-write','user-syscall','privilege-transition'],list(range(9))),
    'Lemma.Applications.Notebook.pumpSave': ('user',6,[],['checked-access','io-order','virtual-read','virtual-write','user-syscall','privilege-transition'],[1,2,3,4,6]),
    'Lemma.Ink.Surface.glyph': ('user',9,['u64'],[],list(range(9))),
    'Lemma.Applications.Notebook.statusCharacter': ('user',9,['u64']*5,[],[10,11,13,14,15,17,18]),
    # Original course presentation is genuinely compiled scalar Lean. These
    # exact pure owners/domains gain no memory, syscall or checker authority.
    'Lemma.Courses.Arithmetic.character': ('user',33,['u64','u64'],[],list(range(33))),
    'Lemma.Courses.Arithmetic.answerCharacter': ('user',25,['u64','u64'],[],[2,3,7,8,13,14,19,20,25,26]),
    'Lemma.Courses.Arithmetic.panelCharacter': ('user',8,['u64']*5,[],list(range(8))),
    # The v2 learner-event validator performs checked reads only. This is its
    # exact kind2..6 dispatch; kind1 follows its separately checked attempt
    # reference path. It cannot gain write/syscall or another image authority.
    'Lemma.Documents.Mathematics.validateEventStep': ('user',5,['u32','u32',*(['u64']*5)],['checked-access','virtual-read'],[2,3,4,5,6]),
}
LEMMASIM_JUMP_TABLE_USER_IMAGES = {
    'Lemma.Services.Store.Protocol.shape': {'store','notebook','isolation'},
    'Lemma.Services.Store.Engine.complete': {'store'},
    'Lemma.Services.Store.Server.application': {'store'},
    'Lemma.Applications.Notebook.toolbar': {'notebook'},
    'Lemma.Applications.Notebook.pumpSave': {'notebook'},
    'Lemma.Ink.Surface.glyph': {'notebook'},
    'Lemma.Applications.Notebook.statusCharacter': {'notebook'},
    'Lemma.Courses.Arithmetic.character': {'notebook'},
    'Lemma.Courses.Arithmetic.answerCharacter': {'notebook'},
    'Lemma.Courses.Arithmetic.panelCharacter': {'notebook'},
    'Lemma.Documents.Mathematics.validateEventStep': {'notebook'},
}


def _jump_switch_default(optimized_body: str, assembly: str, symbol: str,
                         targets: list[str], cases: list[int]) -> dict:
    """Bind the diagnostic switch's unlisted slot to the genuine default block."""
    switches = re.findall(r'switch i64 %arg0, label %([A-Za-z0-9_.$-]+) \[([^]]+)\]', optimized_body, re.S)
    selected = [(default, block) for default, block in switches
                if sorted(int(value) for value in re.findall(r'i64 (-?\d+), label', block)) == cases]
    if len(selected) != 1:
        raise Core0Error('diagnostic jump table lacks one exact command/default switch')
    default, _ = selected[0]
    owner = re.search(r'(?m)^'+re.escape(symbol)+r':[^\n]*\n(.*?)^\s*\.size\s+'+re.escape(symbol)+r',', assembly, re.S)
    labels = re.findall(r'(?m)^(\.LBB\d+_\d+):[^\n]*# %'+re.escape(default)+r'\s*$', owner[1]) if owner else []
    holes = [value for value in range(min(cases), max(cases)+1) if value not in cases]
    if len(labels) != 1 or any(targets[value-min(cases)] != labels[0] for value in holes):
        raise Core0Error('diagnostic jump table hole does not target its genuine default block')
    from audit_memory import _parse_blocks
    blocks = _parse_blocks('\n'.join(line.split(';', 1)[0] for line in optimized_body.splitlines()), symbol)
    status = [line for line in blocks.get(default, []) if ' = phi i64 ' in line and re.search(r'\[ 17, %entry \]', line)]
    value = [line for line in blocks.get(default, []) if ' = phi i64 ' in line and re.search(r'\[ 0, %entry \]', line)]
    if len(status) != 1 or len(value) != 1:
        raise Core0Error('diagnostic switch default lacks checked unsupported17/value0 provenance')
    lines = blocks[default]
    word = r'(%[A-Za-z0-9_.$-]+)'
    status_word = re.match(word+r' = phi i64 ', status[0])[1]
    value_word = re.match(word+r' = phi i64 ', value[0])[1]
    if len(lines) != 6 or lines[:2] != [status[0], value[0]]:
        raise Core0Error('diagnostic switch default lacks its exact checked aggregate return')
    masked = re.fullmatch(word+r' = and i64 '+re.escape(status_word)+r', 255', lines[2])
    partial = (re.fullmatch(word+r' = insertvalue \{ i64, i64 \} poison, i64 '+re.escape(masked[1])+r', 0', lines[3])
               if masked else None)
    complete = (re.fullmatch(word+r' = insertvalue \{ i64, i64 \} '+re.escape(partial[1])+r', i64 '+re.escape(value_word)+r', 1', lines[4])
                if partial else None)
    if complete is None or lines[5] != 'ret { i64, i64 } '+complete[1]:
        raise Core0Error('diagnostic switch default PHIs do not reach the checked return')
    return {'holes': holes, 'llvm_default': default, 'machine_default': labels[0],
            'default_status': 17, 'default_value': 0}


def _jump_service_default(optimized_ir: str, assembly: str, symbol: str,
                          targets: list[str], cases: list[int], unit: dict) -> dict:
    """Sparse development commands acknowledge17/0 on the genuine default."""
    body=_ir_definition_body(optimized_ir,symbol);var=r'%[A-Za-z0-9_.$-]+'
    switches=re.findall(r'switch i64 %arg0, label %([A-Za-z0-9_.$-]+) \[([^]]+)\]',body,re.S)
    if len(switches)!=1 or sorted(int(v) for v in re.findall(r'i64 (-?\d+), label',switches[0][1]))!=cases:
        raise Core0Error('service command default lacks one exact genuine switch')
    default=switches[0][0]
    owner=re.search(r'(?m)^'+re.escape(symbol)+r':[^\n]*\n(.*?)^\s*\.size\s+'+re.escape(symbol)+r',',assembly,re.S)
    labels=re.findall(r'(?m)^(\.LBB\d+_\d+):[^\n]*# %'+re.escape(default)+r'\s*$',owner[1]) if owner else []
    holes=[v for v in range(min(cases),max(cases)+1) if v not in cases]
    if len(labels)!=1 or any(targets[v-min(cases)]!=labels[0] for v in holes):
        raise Core0Error('service command holes do not reach the exact default block')
    sources={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row for row in unit['functions']}
    ack=sources.get('Lemma.Kernel.Development.ServiceEntry.acknowledge')
    if ack is None or ack['args']!=['u64','u8','u64','u64']:
        raise Core0Error('service command default lacks exact static acknowledgement source')
    blocks=_structured_ir_blocks('\n'.join(line.split(';',1)[0] for line in body.splitlines()))
    lines=blocks.get(default,[])
    call=re.fullmatch(r'('+var+r') = call \{ i64, i64 \} @'+re.escape(ack['symbol'])+r'\(i64 %arg0, i8 zeroext 17, i64 0, i64 %arg1\)',lines[0]) if len(lines)==4 else None
    if call is None:
        raise Core0Error('service unknown command changes actual number/status17/value0/subject')
    status=re.fullmatch(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(call[1])+r', 0',lines[1])
    value=re.fullmatch(r'('+var+r') = extractvalue \{ i64, i64 \} '+re.escape(call[1])+r', 1',lines[2])
    merge=re.fullmatch(r'br label %([A-Za-z0-9_.$-]+)',lines[3])
    if status is None or value is None or merge is None:
        raise Core0Error('service default loses its actual checked acknowledgement result')
    returned=blocks.get(merge[1],[])
    status_phi=re.match(r'('+var+r') = phi i64 ',returned[0]) if len(returned)==6 else None
    value_phi=re.match(r'('+var+r') = phi i64 ',returned[1]) if len(returned)==6 else None
    if (status_phi is None or value_phi is None or '[ '+status[1]+', %'+default+' ]' not in returned[0]
            or '[ '+value[1]+', %'+default+' ]' not in returned[1]):
        raise Core0Error('service default checked words do not reach the return PHIs')
    masked=re.fullmatch(r'('+var+r') = and i64 '+re.escape(status_phi[1])+r', 255',returned[2])
    partial=re.fullmatch(r'('+var+r') = insertvalue \{ i64, i64 \} poison, i64 '+re.escape(masked[1] if masked else 'NO_MASK')+r', 0',returned[3])
    complete=re.fullmatch(r'('+var+r') = insertvalue \{ i64, i64 \} '+re.escape(partial[1] if partial else 'NO_PARTIAL')+r', i64 '+re.escape(value_phi[1])+r', 1',returned[4])
    if complete is None or returned[5]!='ret { i64, i64 } '+complete[1]:
        raise Core0Error('service default checked words do not reach the exact aggregate return')
    return {'holes':holes,'llvm_default':default,'machine_default':labels[0],
            'acknowledgement_source':ack['source'],'acknowledged_status':17,'acknowledged_value':0,
            'actual_command_operand':'%arg0','actual_subject_operand':'%arg1'}


def _object_symbols(text: str) -> dict[int, dict]:
    result = {}
    for line in text.splitlines():
        row = re.fullmatch(r'\s*(\d+):\s+([0-9a-f]+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*?)\s*', line)
        if row:
            index = int(row[1])
            if index in result:
                raise Core0Error('duplicate object symbol index')
            result[index] = dict(index=index, value=int(row[2],16), size=int(row[3]), type=row[4],
                                 binding=row[5], visibility=row[6], section=row[7], name=row[8])
    if not result:
        raise Core0Error('empty/unparseable object symbol table')
    return result


def _object_relocations(text: str, symbols: dict[int, dict]) -> list[dict]:
    result = []; section = None
    for line in text.splitlines():
        header = re.search(r"Relocation section '([^']+)'",line)
        if header:
            section = header[1]
        elif re.search(r'\bR_RISCV_',line):
            row = re.fullmatch(r'\s*([0-9a-f]+)\s+([0-9a-f]+)\s+(R_RISCV_[A-Z0-9_]+)\s+([0-9a-f]+)\s+(\S+)\s+\+\s+(-?(?:0x)?[0-9a-f]+)\s*',line)
            if row is None or section is None:
                raise Core0Error('unparseable object relocation')
            index = int(row[2],16)>>32; symbol = symbols.get(index)
            if symbol is None or symbol['name']!=row[5] or symbol['value']!=int(row[4],16):
                raise Core0Error('object relocation symbol index/name/value disagree')
            result.append(dict(section=section,offset=int(row[1],16),type=row[3],symbol=symbol,addend=int(row[6],16)))
    return result


def _jump_assembly_function(assembly: str, symbol: str) -> tuple[list[tuple[str,list[str]]],dict[str,int]]:
    match = re.search(r'(?m)^'+re.escape(symbol)+r':[^\n]*\n(.*?)^\s*\.size\s+'+re.escape(symbol)+r',',assembly,re.S)
    if match is None:
        raise Core0Error('companion assembly lacks owning function')
    instructions=[];labels={symbol:0}
    for raw in match[1].splitlines():
        line=raw.split('#',1)[0].strip()
        if not line: continue
        label=re.fullmatch(r'([.$A-Za-z0-9_]+):',line)
        if label:
            if label[1] in labels: raise Core0Error('duplicate companion code label')
            labels[label[1]]=len(instructions)
        elif not line.startswith('.'):
            parts=line.split(None,1)
            instructions.append((parts[0],parts[1].replace(' ','').split(',') if len(parts)>1 else []))
    return instructions,labels


def _jump_status_default(optimized_body: str, assembly: str, symbol: str,
                         targets: list[str], cases: list[int]) -> dict:
    """Check the authored footer's two sparse slots independently in IR/code."""
    switches=re.findall(r'switch i64 %arg1, label %([A-Za-z0-9_.$-]+) \[([^]]+)\]',optimized_body,re.S)
    selected=[(default,block) for default,block in switches
              if sorted(int(value) for value in re.findall(r'i64 (-?\d+), label',block))==cases]
    if cases!=[10,11,13,14,15,17,18] or len(targets)!=9 or len(selected)!=1:
        raise Core0Error('notebook footer lacks its exact index/default switch')
    from audit_memory import _parse_blocks
    blocks=_parse_blocks('\n'.join(line.split(';',1)[0] for line in optimized_body.splitlines()),symbol)
    default,_=selected[0]
    lines=blocks.get(default,[])
    branch=re.fullmatch(r'br label %([A-Za-z0-9_.$-]+)',lines[0]) if len(lines)==1 else None
    returned=blocks.get(branch[1],[]) if branch else []
    phi=(re.fullmatch(r'(%[A-Za-z0-9_.$-]+) = phi i64 (.+)',returned[0])
         if len(returned)==2 else None)
    if (phi is None or returned[1]!='ret i64 '+phi[1]
        or len(re.findall(r'\[ 32, %'+re.escape(default)+r' \]',phi[2]))!=1):
        raise Core0Error('notebook footer default does not return the authored space32')
    code,labels=_jump_assembly_function(assembly,symbol)
    holes=[12,16]
    machine_default=targets[2]
    if targets[6]!=machine_default or machine_default not in labels:
        raise Core0Error('notebook footer holes do not share one local default')
    at=labels[machine_default]
    if code[at:at+2]!=[('li',['a0','32']),('ret',[])]:
        raise Core0Error('notebook footer machine default does not return space32')
    return {'holes':holes,'llvm_default':default,'machine_default':machine_default,'default_value':32}


def _jump_save_default(optimized_body: str, assembly: str, symbol: str,
                       targets: list[str], cases: list[int]) -> dict:
    """Bind the notebook phase5 hole to its checked error234 return, not a phase."""
    switches=re.findall(r'switch i64 (%[A-Za-z0-9_.$-]+), label %([A-Za-z0-9_.$-]+) \[([^]]+)\]',optimized_body,re.S)
    selected=[(value,default,block) for value,default,block in switches
              if sorted(int(case) for case in re.findall(r'i64 (-?\d+), label',block))==cases]
    if cases!=[1,2,3,4,6] or len(targets)!=6 or len(selected)!=1:
        raise Core0Error('notebook Save lacks its exact phase/default switch')
    value,default,_=selected[0]
    waits=[block for operand,_default,block in switches if operand==value
           and sorted(int(case) for case in re.findall(r'i64 (-?\d+), label',block))==[0,5]]
    if len(waits)!=1:
        raise Core0Error('notebook Save phase0/5 wait split differs')
    from audit_memory import _parse_blocks
    blocks=_parse_blocks('\n'.join(line.split(';',1)[0] for line in optimized_body.splitlines()),symbol)
    owners=[label for label,lines in blocks.items() if any(line.startswith('switch i64 '+value+', label %'+default+' [') for line in lines)]
    returned=blocks.get(default,[])
    phi=re.fullmatch(r'(%[A-Za-z0-9_.$-]+) = phi i64 (.+)',returned[0]) if len(returned)==5 else None
    if (len(owners)!=1 or phi is None or
        len(re.findall(r'\[ 234, %'+re.escape(owners[0])+r' \]',phi[2]))!=1):
        raise Core0Error('notebook Save default lacks its checked error234 PHI')
    masked=re.fullmatch(r'(%[A-Za-z0-9_.$-]+) = and i64 '+re.escape(phi[1])+r', 255',returned[1])
    partial=re.fullmatch(r'(%[A-Za-z0-9_.$-]+) = insertvalue \{ i64, i64 \} poison, i64 '+re.escape(masked[1] if masked else 'NO_MASK')+r', 0',returned[2])
    complete=re.fullmatch(r'(%[A-Za-z0-9_.$-]+) = insertvalue \{ i64, i64 \} '+re.escape(partial[1] if partial else 'NO_PARTIAL')+r', i64 0, 1',returned[3])
    if complete is None or returned[4]!='ret { i64, i64 } '+complete[1]:
        raise Core0Error('notebook Save default changes its checked return words')
    code,labels=_jump_assembly_function(assembly,symbol)
    hole=targets[4]
    marked=[label for label in re.findall(r'(?m)^(\.LBB\d+_\d+):[^\n]*# %'+re.escape(default)+r'\s*$',assembly)
            if label in labels]
    if hole not in marked or hole not in labels:
        raise Core0Error('notebook Save phase5 is not the actual local default block')
    at=labels[hole]
    epilogue=[('andi',['a0','s0','255']),('li',['a1','0'])]
    epilogue += [('ld',[register,str(offset)+'(sp)']) for register,offset in
                 [('ra',56),('s0',48),('s1',40),('s2',32),('s3',24),('s4',16),('s5',8),('s6',0)]]
    epilogue += [('addi',['sp','sp','64']),('ret',[])]
    uses=[i for i,(op,args) in enumerate(code) if op=='auipc' and len(args)==2 and args[1].startswith('%pcrel_hi(.LJTI')]
    if (code[at:at+len(epilogue)]!=epilogue or len(uses)!=1 or uses[0]<5 or
        code[uses[0]-5:uses[0]]!=[('addi',['s3','s3','-1']),('li',['a0','5']),
          ('li',['s0','234']),('bltu',['a0','s3',hole]),('slli',['s3','s3','3'])]):
        raise Core0Error('notebook Save default error/frame or phase guard differs')
    return {'holes':[5],'llvm_default':default,'machine_default':hole,
            'default_status':234,'default_value':0,'wait_split_phases':[0,5]}


def validate_dtb_pair_body(ir: str, unit: dict, symbol: str) -> str:
    source='Lemma.Platform.LemmaSim.DescriptorDTB.leafProperty'
    names={row['symbol']:re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']) for row in unit['functions']}
    if (unit.get('role')!='kernel' or unit.get('configuration') not in LEMMASIM_CONFIGURATIONS
        or names.get(symbol)!=source):raise Core0Error('DTB paired body escapes exact kernel owner')
    body=_ir_definition_body(ir,symbol)
    rebound=re.sub(r'@([^ (]+)',lambda m:'@'+names.get(m[1],m[1]),body)
    normalized=' '.join(' '.join(line.split(';',1)[0].strip() for line in rebound.splitlines()).split())
    digest=hashlib.sha256(normalized.encode()).hexdigest()
    if digest!='b259ebe10adb20c25ef1dc0e83cdc915789c742220633112f38267596185af1c':
        raise Core0Error('DTB paired owner differs from exact checked property/role body')
    return digest


def _jump_leaf_pair(assembly: str, symbol: str, source: str | None,
                    configuration: str | None) -> dict[int,list[str]]:
    """Closed DTB property/role pair, with distinct CFG edges per transfer."""
    if source!='Lemma.Platform.LemmaSim.DescriptorDTB.leafProperty' or configuration not in LEMMASIM_CONFIGURATIONS:
        raise Core0Error('paired table escapes the exact LemmaSim DTB owner')
    code,labels=_jump_assembly_function(assembly,symbol)
    uses=[(i,re.fullmatch(r'%pcrel_hi\((\.LJTI[0-9]+_[0-9]+)\)',args[1]))
          for i,(op,args) in enumerate(code) if op=='auipc' and len(args)==2 and args[1].startswith('%pcrel_hi(.LJTI')]
    if len(uses)!=2 or any(match is None for _,match in uses):raise Core0Error('DTB pair has an extra or unparseable table use')
    names=[match[1] for _,match in uses]
    group=re.fullmatch(r'\.LJTI([0-9]+)_0',names[0])
    if group is None or names[1]!='.LJTI'+group[1]+'_1':raise Core0Error('DTB pair table labels/order differ')
    result={};defaults=[]
    for (use,_),name,count,minimum,holes in zip(uses,names,(15,9),(36,1),([1,2,3,4,5,6,7,8,10],[2,3,4,6])):
        declaration=re.search(r'(?m)^'+re.escape(name)+r':\n((?:\s*\.quad\s+\.LBB[0-9]+_[0-9]+\s*\n)+)',assembly)
        targets=re.findall(r'\.quad\s+(\.LBB[0-9]+_[0-9]+)',declaration[1]) if declaration else []
        if len(targets)!=count or any(label not in labels for label in targets):raise Core0Error('DTB pair local target count differs')
        if use+4>=len(code) or code[use+3][0]!='ld' or code[use+4]!=('jr',[code[use+3][1][0]]):
            raise Core0Error('DTB pair transfer is not the exact loaded target')
        index=code[use+3][1][0];base=code[use][1][0]
        guard=code[use-2] if use>=5 else ('invalid',[])
        if (use<5 or guard[0]!='bltu' or len(guard[1])!=3 or guard[1][1]!=index
            or code[use-5][0]!='addi' or code[use-5][1][0]!=index
            or code[use-5][1][2]!=str(-minimum)
            or code[use-4]!=('li',[guard[1][0],str(count-1)])
            or code[use-3][0]!='li' or code[use-3][1][1]!='0'
            or code[use-3][1][0] in {index,guard[1][0]}
            or code[use-1]!=('slli',[index,index,'3']) or base==index
            or code[use+2]!=('add',[index,index,base])
            or code[use+3]!=('ld',[index,'0('+index+')'])):
            raise Core0Error('DTB paired guard/index/load differs from its closed path')
        result[use+4]=targets
        denied=[i for i in range(max(0,use-4),use) if code[i][0]=='bltu']
        if len(denied)!=1:raise Core0Error('DTB pair lacks its local unsigned guard')
        default=code[denied[0]][1][-1]
        if any(targets[index]!=default for index in holes):raise Core0Error('DTB pair hole does not target its checked default')
        defaults.append(default)
    if defaults[0]!=defaults[1] or set(result)!={i for i,(op,_args) in enumerate(code) if op=='jr'}:
        raise Core0Error('DTB pair has a foreign transfer or divergent checked default')
    return result


def _jump_assembly_guard(assembly: str, symbol: str, table: str, targets: list[str], count: int, minimum: int,
                         *, source: str | None = None, configuration: str | None = None, image_key: str | None = None) -> dict:
    """Check the actual closed unsigned guard/scale/load/JR path and its CFG."""
    code,labels=_jump_assembly_function(assembly,symbol)
    uses=[i for i,(op,args) in enumerate(code) if op=='auipc' and len(args)==2 and args[1]=='%pcrel_hi('+table+')']
    if len(uses)!=1:
        raise Core0Error('jump table lacks one owning PC-relative address use')
    use=uses[0];base=code[use][1][0]
    if use==0 or code[use-1][0]!='slli' or len(code[use-1][1])!=3 or code[use-1][1][2]!='3':
        raise Core0Error('jump table index lacks exact eight-byte scaling')
    index=code[use-1][1][1];scaled=code[use-1][1][0]
    if base==scaled: raise Core0Error('jump table address overwrites its scaled index')
    if len(code)<=use+4 or code[use+1][0]!='addi' or code[use+1][1][:2]!=[base,base] or not re.fullmatch(r'%pcrel_lo\(\.Lpcrel_hi\d+\)',code[use+1][1][2]):
        raise Core0Error('jump table address lacks its matched PC-relative low half')
    low_label=code[use+1][1][2][len('%pcrel_lo('):-1]
    if labels.get(low_label)!=use:
        raise Core0Error('jump table PC-relative low label points elsewhere')
    address=code[use+2][1][0]
    if code[use+2][0]!='add' or sorted(code[use+2][1][1:])!=sorted([scaled,base]):
        raise Core0Error('jump table address does not add the scaled index')
    load=code[use+3];target=load[1][0]
    if load[0]!='ld' or load[1][1]!='0('+address+')':
        raise Core0Error('jump table target lacks one 64-bit table load')
    jumps=[i for i,(op,args) in enumerate(code) if op=='jr']
    paired = _jump_leaf_pair(assembly,symbol,source,configuration) if len(jumps)==2 else {}
    own_jumps=[i for i in jumps if use+4<=i<=use+6 and code[i]==('jr',[target])]
    if (len(own_jumps)!=1 or (len(jumps)!=1 and not paired)
        or (paired and paired.get(own_jumps[0])!=targets)):
        raise Core0Error('jump table has an unknown or unbound indirect transfer')
    jump=own_jumps[0]
    reload = None
    literal = None
    mask = None
    if jump==use+5:
        intervening=code[use+4]
        if intervening[0]=='li' and intervening[1][0]!=target:
            pass
        elif (source=='Lemma.Courses.Arithmetic.panelCharacter'
              and configuration in LEMMASIM_NOTEBOOK_CONFIGURATIONS and image_key=='notebook'
              and count==8 and minimum==0 and index==scaled==address=='a0' and base==target=='a5'
              and code[:2]==[('addi',['sp','sp','-16']),('sd',['ra','8(sp)'])]
              and intervening==('andi',['a0','a4','7'])):
            # Only the course's pure row switch hoists its admitted display
            # outcome mask here. The loaded a5 target remains untouched.
            mask={'instruction':'andi a0,a4,7','value_register':'a0',
                  'preserved_target_register':'a5'}
        elif (source=='Lemma.Services.Buffer.Server.existing' and configuration in SERVICE_CONFIGURATIONS and image_key=='server'
              and count==5 and minimum==2 and index==scaled==address==target=='a0' and base=='a2'
              and code[0]==('addi',['sp','sp','-112']) and intervening==('ld',['a2','112(sp)'])
              and code[use-4]==('addi',['a0','s3','-2']) and code[use-3]==('li',['a2','4'])
              and code[use-2][0]=='bltu' and code[use-2][1][:2]==['a2','a0']):
            # Nine scalar arguments: this exact fixed-frame load recovers the
            # ninth incoming argument at the original SP. It cannot change a0,
            # the bounded/scaled index or loaded branch target.
            reload={'instruction':'ld a2,112(sp)','fixed_frame_bytes':112,'incoming_argument':8,
                    'loaded_register':'a2','preserved_target_register':'a0'}
        else:
            raise Core0Error('jump table target is overwritten or has an unknown intervening instruction before transfer')
    elif jump==use+6:
        if (source=='Lemma.Ink.Surface.glyph' and configuration in LEMMASIM_NOTEBOOK_CONFIGURATIONS
            and image_key=='notebook' and count==9 and minimum==0
            and index==scaled==address=='a0' and base==target=='a1'
            and code[:2]==[('addi',['sp','sp','-16']),('sd',['ra','8(sp)'])]
            and code[use+4:jump]==[('lui',['a0','3']),('addiw',['a0','a0','-1566'])]):
            # This exact authored arrow is the preloaded return value for its
            # local merge block. The two instructions preserve the loaded a1
            # branch target; no other source, image, literal or register shape
            # gains a two-instruction exception.
            literal={'instructions':['lui a0,3','addiw a0,a0,-1566'],
                     'value':0x29e2,'loaded_register':'a0','preserved_target_register':'a1'}
        else:
            raise Core0Error('jump table target is overwritten or has an unknown intervening instruction before transfer')
    guards=[]
    hoisted=None
    for i in range(max(0,use-8),use-1):
        op,args=code[i]
        if op=='bltu' and len(args)==3 and args[1]==index:
            prior=[j for j in range(max(0,i-3),i) if code[j]==('li',[args[0],str(count-1)])]
            if len(prior)==1 and all(code[j][1][:1]!=[args[0]] for j in range(prior[0]+1,i)):
                guards.append(i)
            elif (source=='Lemma.Applications.Notebook.statusCharacter'
                  and configuration in LEMMASIM_NOTEBOOK_CONFIGURATIONS and image_key=='notebook'
                  and count==9 and minimum==10 and index==scaled==target=='a1' and base==address=='a0'
                  and code[0]==('li',['a5','8']) and args[:2]==['a5','a1']
                  and code[1][0]=='bltu' and code[1][1][:2]==['a5','a1']
                  and labels.get(code[1][1][-1])==i-1
                  and code[i-1]==('addi',['a1','a1','-10'])
                  and all(operation in {'li','beq','bnez','bgeu','slli','auipc','addi','j'}
                          and words[:1]!=['a5'] for operation,words in code[2:i])):
                # Only this pure notebook footer reuses its entry index bound
                # after the exact local normalization. The entry branch, one
                # preserved definition and normalizing target are all bound.
                guards.append(i)
                hoisted={'instruction':'li a5,8','definition_instruction':0,
                         'preserved_register':'a5','normalized_index_register':'a1'}
    if len(guards)!=1: raise Core0Error('jump table lacks the exact unsigned index bound')
    guard=guards[0]
    # Every instruction between the guard and scale preserves the bounded index.
    if any(args[:1]==[index] for _op,args in code[guard+1:use-1]):
        raise Core0Error('jump table bounded index is overwritten')
    if minimum:
        normalizations=[i for i in range(max(0,guard-5),guard) if code[i][0]=='addi' and len(code[i][1])==3 and code[i][1][0]==index and code[i][1][2]==str(-minimum)]
        if len(normalizations)!=1 or any(args[:1]==[index] for _op,args in code[normalizations[0]+1:guard]):
            raise Core0Error('jump table lacks exact subtraction index normalization')
    successors={}
    conditional={'beq','bne','blt','bge','bltu','bgeu','beqz','bnez','blez','bgez','bltz','bgtz','bgt','ble','bgtu','bleu'}
    for i,(op,args) in enumerate(code):
        following=[i+1] if i+1<len(code) else []
        if op in conditional:
            if args[-1] not in labels or labels[args[-1]]>=len(code): raise Core0Error('jump guard has nonlocal/noninstruction branch target')
            successors[i]=[labels[args[-1]],*following]
        elif op=='j':
            if args!=args[-1:] or args[0] not in labels or labels[args[0]]>=len(code): raise Core0Error('jump function has nonlocal/noninstruction branch')
            successors[i]=[labels[args[0]]]
        elif op=='jr':
            selected_targets=paired.get(i,targets)
            if any(label not in labels for label in selected_targets): raise Core0Error('jump table contains a foreign assembly block')
            successors[i]=list({labels[label] for label in selected_targets})
        elif op in {'ret','tail'}: successors[i]=[]
        else: successors[i]=following
    def reaches(graph,start,finish):
        seen=set();pending=[start]
        while pending:
            point=pending.pop()
            if point==finish:return True
            if point not in seen:seen.add(point);pending.extend(graph.get(point,[]))
        return False
    denied={i:list(edges) for i,edges in successors.items()};denied[guard]=[labels[code[guard][1][-1]]]
    if any(reaches(denied,0,point) for point in (use-1,use,use+3,jump)) or not reaches(successors,0,jump):
        raise Core0Error('jump table load/transfer can bypass the unsigned guard')
    return dict(bound=count,minimum=minimum,unsigned=True,scale_bytes=8,load_bytes=8,guard_dominates_load=True,one_indirect_transfer=not bool(paired),
                **({'closed_dtb_pair_transfers':2,'each_transfer_uses_own_targets':True} if paired else {}),
                **({'target_preserving_reload':reload} if reload is not None else {}),
                **({'target_preserving_literal':literal} if literal is not None else {}),
                **({'target_preserving_mask':mask} if mask is not None else {}),
                **({'hoisted_entry_bound':hoisted} if hoisted is not None else {}))


def validate_backend_jump_tables(section_text: str, symbol_text: str, relocation_text: str,
                                  rodata: bytes, *, unit: dict, optimized_ir: str, optimization: str,
                                  readonly_tables: list[dict], assembly: str='', companion_symbols: str='',
                                  companion_relocations: str='', text: bytes=b'', companion_text: bytes=b'') -> dict:
    """Exact byte/relocation/source/guard provenance; not a compiler correctness proof."""
    symbols=_object_symbols(symbol_text);relocations=_object_relocations(relocation_text,symbols)
    sections={m[1]:m[2] for m in re.finditer(r'(?m)^\s*\[\s*(\d+)\]\s+(\S+)\s+',section_text)}
    functions={s['name']:s for s in symbols.values() if s['type']=='FUNC' and s['section']!='UND'}
    tables=[s for s in symbols.values() if s['name'].startswith('.LJTI')]
    literal=[r for r in readonly_tables if r['section']=='.rodata']
    literal_contracts={'Lemma.Kernel.Objects.replyLimitFor':[8,8,7],'Lemma.User.CapabilityABI.typeMask':[35,124,928,1056,1], 'Lemma.Kernel.Objects.initStep':[1,3,4]}
    sim_literals = unit.get('configuration') in LEMMASIM_CONFIGURATIONS
    if sim_literals:
        from lemmasim_readonly import canonical_specs, ble_specs, BLE_CONFIGURATIONS
        extra = ble_specs() if unit.get("configuration") in BLE_CONFIGURATIONS else canonical_specs()
        modern = ble_specs()
        def admitted_literal(row):
            source=re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])
            if source in literal_contracts:
                return unit['role']=='kernel' and literal_contracts[source]==row['values']
            spec=extra.get(source)
            return spec is not None and spec[0]==unit['role'] and row['values'] in [[0 if value is None else value for value in values] for values in (*spec[3],*modern[source][3])]
        valid_literals=all(admitted_literal(row) for row in literal)
    else:
        valid_literals=unit['role']=='kernel' and all(literal_contracts.get(re.sub(r'^_private\..*?\.[0-9]+\.','',r['source']))==r['values'] for r in literal)
    if literal and not valid_literals:
        raise Core0Error('readonly literal provenance escapes the exact kernel contracts')
    observed=[];extents=[];used_relocations=set()
    section_id=next((index for index,name in sections.items() if name=='.rodata'),None)
    if section_id is not None:
        row=re.search(r'(?m)^\s*\[\s*'+section_id+r'\]\s+\.rodata\s+PROGBITS\s+0+\s+[0-9a-f]+\s+([0-9a-f]+)\s+00\s+A\s+0\s+0\s+8\s*$',section_text)
        if row is None or int(row[1],16)!=len(rodata): raise Core0Error('jump table section bytes/readonly flags/alignment differ')
    elif rodata or tables or literal: raise Core0Error('jump table data lacks its declared readonly section')
    if tables:
        if optimization!='O2' or unit['role'] not in {'kernel','firmware','user'} or not text or text!=companion_text:
            raise Core0Error('jump tables lack exact O2 companion code bytes/role provenance')
        companion=_object_symbols(companion_symbols);named={s['name']:s for s in companion.values() if s['name']}
        other_relocations=_object_relocations(companion_relocations,companion)
        # The companion is not linked. Reassemble retained labels to bind block PCs;
        # code bytes and all code/data relocation semantics must match the real object.
        def canonical(rows,section_names=None):
            return sorted((r['section'],r['offset'],r['type'],r['symbol']['value'],
                           (sections.get(r['symbol']['section'],r['symbol']['section']) if section_names is None else section_names.get(r['symbol']['section'],r['symbol']['section'])),
                           r['symbol']['binding'],r['symbol']['name'] if r['symbol']['binding']!='LOCAL' else '',r['addend'])
                          for r in rows if r['section'] in {'.rela.text','.rela.rodata'})
        # Both MC paths retain the same allocated section numbers; permit no hidden relocation semantic difference.
        if canonical(relocations)!=canonical(other_relocations): raise Core0Error('companion code/table relocation semantics differ from actual object')
        definitions=re.findall(r'(?m)^(\.LJTI\d+_\d+):',assembly)
        if set(definitions)!={s['name'] for s in tables} or len(definitions)!=len(tables):
            raise Core0Error('actual and companion jump-table label inventories differ')
        by_symbol={r['symbol']:r for r in unit['functions']}
        for table in sorted(tables,key=lambda s:s['value']):
            name=table['name'];match=re.fullmatch(r'\.LJTI(\d+)_([01])',name)
            if match is None or table['type']!='NOTYPE' or table['binding']!='LOCAL' or table['section']!=section_id or table['size']!=0 or table['value']%8:
                raise Core0Error('backend table label is not one local aligned readonly extent')
            declaration=re.search(r'(?m)^'+re.escape(name)+r':\n((?:\s*\.quad\s+\.LBB\d+_\d+\s*\n)+)',assembly)
            if declaration is None:raise Core0Error('backend table lacks a closed companion local-block list')
            targets=re.findall(r'\.quad\s+(\.LBB\d+_\d+)',declaration[1]);size=len(targets)*8;start=table['value']
            references=[r for r in relocations if r['symbol']['index']==table['index']]
            if len(references)!=1 or references[0]['section']!='.rela.text' or references[0]['type']!='R_RISCV_PCREL_HI20' or references[0]['addend']!=0:
                raise Core0Error('backend jump table lacks one exact owning text address relocation')
            owners=[f for f in functions.values() if sections.get(f['section'])=='.text' and f['value']<=references[0]['offset']<f['value']+f['size']]
            if len(owners)!=1:raise Core0Error('backend jump table reference has no unique compiled function owner')
            owner=owners[0]
            if owner['value']%4 or owner['size']%4 or references[0]['offset']%4:
                raise Core0Error('jump table owner/address reference has invalid instruction alignment')
            source_row=by_symbol.get(owner['name']);source=re.sub(r'^_private\..*?\.[0-9]+\.','',source_row.get('source','') if source_row else '')
            sim_source=unit.get('configuration') in LEMMASIM_CONFIGURATIONS and source in LEMMASIM_BACKEND_JUMP_TABLES
            spec=(LEMMASIM_BACKEND_JUMP_TABLES if sim_source else BACKEND_JUMP_TABLES).get(source)
            owner_tables=[candidate['name'] for candidate in tables
                          if candidate['name'].startswith('.LJTI'+match[1]+'_')]
            paired_leaf=(sim_source and source=='Lemma.Platform.LemmaSim.DescriptorDTB.leafProperty'
                         and sorted(owner_tables)==['.LJTI'+match[1]+'_0','.LJTI'+match[1]+'_1'])
            if match[2]!='0' and not paired_leaf:raise Core0Error('second table escapes closed DTB pair')
            if paired_leaf:
                validate_dtb_pair_body(optimized_ir,unit,owner['name'])
                if match[2]=='1':spec=('kernel',9,['u64']*4,['checked-access','physical-read','physical-write'],[1,2,6,8,9])
            if (sim_source and source=='Lemma.Platform.LemmaSim.DescriptorDTB.literalWord'
                    and len(targets)==74 and unit.get('configuration') not in BLE_CONFIGURATIONS):
                # Exact historical Power literal domain; immutable old units
                # and fixtures retain this version. The selected BLE probe
                # requires the new domain including its five literal codes.
                spec=('kernel',74,['u64','u64'],[],[*range(2,19),*range(32,53),*range(64,76)])
            if spec is None or (unit['role'],len(targets),source_row['args'],source_row['effects'])!=spec[:4]:
                raise Core0Error('unknown backend table owner/count/source signature/effects: '+repr(dict(
                    table=name, source=source, role=unit['role'], count=len(targets),
                    args=source_row.get('args') if source_row else None,
                    effects=source_row.get('effects') if source_row else None,
                    configuration=unit.get('configuration'))))
            if source in BACKEND_JUMP_TABLE_CONFIGURATIONS and unit.get('configuration') not in BACKEND_JUMP_TABLE_CONFIGURATIONS[source]:
                raise Core0Error('diagnostic backend table escapes its exact selected configuration: '+source)
            image_authority=LEMMASIM_JUMP_TABLE_USER_IMAGES if sim_source else BACKEND_JUMP_TABLE_USER_IMAGES
            if unit['role']=='user' and (source not in image_authority or unit.get('image_key') not in image_authority[source]):
                raise Core0Error('User backend table escapes its exact selected image: '+source)
            switch_sets=[sorted(int(value) for value in re.findall(r'i\d+ (-?\d+), label',block)) for block in re.findall(r'switch i\d+ [^\n]+\[([^]]+)\]',_ir_definition_body(optimized_ir,owner['name']),re.S)]
            if switch_sets.count(spec[4])!=1 or max(spec[4])-min(spec[4])+1!=len(targets):raise Core0Error('backend table lacks its exact genuine LLVM switch domain')
            default = (_jump_switch_default(_ir_definition_body(optimized_ir,owner['name']), assembly,
                                           owner['name'], targets, spec[4])
                       if source == 'Lemma.Kernel.Development.FramesEntry.operation' else
                       _jump_service_default(optimized_ir,assembly,owner['name'],targets,spec[4],unit)
                       if source == 'Lemma.Kernel.Development.ServiceEntry.command' else
                       _jump_status_default(_ir_definition_body(optimized_ir,owner['name']),assembly,
                                            owner['name'],targets,spec[4])
                       if source == 'Lemma.Applications.Notebook.statusCharacter' else
                       _jump_save_default(_ir_definition_body(optimized_ir,owner['name']),assembly,
                                          owner['name'],targets,spec[4])
                       if source == 'Lemma.Applications.Notebook.pumpSave' else None)
            if named.get(name,{}).get('value')!=start or named.get(owner['name'],{}).get('value')!=owner['value'] or named[owner['name']]['size']!=owner['size']:
                raise Core0Error('companion table/function extents differ from actual object')
            rows=[r for r in relocations if r['section']=='.rela.rodata' and start<=r['offset']<start+size]
            if len(rows)!=len(targets) or sorted(r['offset'] for r in rows)!=list(range(start,start+size,8)) or rodata[start:start+size]!=b'\0'*size:
                raise Core0Error('backend table bytes/entry relocation coverage differ')
            entries=[]
            for row,label in zip(sorted(rows,key=lambda r:r['offset']),targets):
                target=row['symbol'];companion_target=named.get(label)
                if (row['type']!='R_RISCV_64' or row['addend']!=0 or target['type']!='NOTYPE' or target['binding']!='LOCAL' or target['visibility']!='DEFAULT' or target['section']!=owner['section'] or target['size']!=0
                        or target['value']%4 or not owner['value']<=target['value']<owner['value']+owner['size'] or companion_target is None or companion_target['value']!=target['value']
                        or not label.startswith('.LBB'+match[1]+'_')):
                    raise Core0Error('backend table entry escapes its exact local code owner/block/alignment')
                used_relocations.add(id(row));entries.append(dict(offset=row['offset'],target_offset=target['value'],target_label=label,symbol_index=target['index']))
            guard=_jump_assembly_guard(assembly,owner['name'],name,targets,len(targets),min(spec[4]),
                                       source=source,configuration=unit.get('configuration'),image_key=unit.get('image_key'))
            observed.append(dict(source=source_row['source'],function=owner['name'],symbol=name,offset=start,bytes=size,entries=entries,guard=guard,reference_pc=references[0]['offset'],function_base=owner['value'],function_bytes=owner['size'],
                                 **({'switch_default': default} if default is not None else {})))
            extents.append((start,start+size,'jump-table'))
    for row in literal:
        start=row['offset'];end=start+row['bytes']
        if rodata[start:end]!=struct.pack('<'+str(len(row['values']))+'Q',*row['values']):raise Core0Error('declared literal extent bytes differ')
        extents.append((start,end,'literal-table'))
    position=0;alignment=[]
    for start,end,kind in sorted(extents):
        if start<position or end>len(rodata) or end<=start:raise Core0Error('readonly data extents overlap/escape their section')
        gap=rodata[position:start]
        if len(gap)>7 or any(gap):raise Core0Error('unaccounted readonly data bytes outside exact tables/alignment')
        if gap:alignment.append(dict(offset=position,bytes=len(gap)))
        position=end
    if len(rodata)-position>7 or any(rodata[position:]):raise Core0Error('unaccounted trailing readonly data bytes')
    if position<len(rodata):alignment.append(dict(offset=position,bytes=len(rodata)-position))
    for row in relocations:
        if row['section']=='.rela.rodata' and id(row) not in used_relocations:raise Core0Error('unknown readonly-data relocation')
        if row['type']=='R_RISCV_64' and id(row) not in used_relocations:
            target=row['symbol']
            if row['section']!='.rela.stack_sizes' or row['addend']!=0 or target['type']!='NOTYPE' or target['binding']!='LOCAL' or target['visibility']!='DEFAULT' or target['size']!=0 or not any(target['section']==f['section'] and target['value']==f['value'] for f in functions.values()):
                raise Core0Error('absolute relocation is neither exact local jump entry nor compiled stack metadata')
    return dict(role=unit['role'],jump_tables=observed,jump_table_bytes=sum(r['bytes'] for r in observed),rodata_bytes=len(rodata),rodata_sha256=hashlib.sha256(rodata).hexdigest(),literal_bytes=sum(r['bytes'] for r in literal),zero_alignment=alignment,
                limitations='Necessary LLVM/object/relocation/guard provenance checks, not a compiler correctness proof or runtime measurement.')


def inspect_backend_jump_tables(inspect, directory: Path, *, object_file: str, section_text: str,
                                symbol_text: str, relocation_text: str, unit: dict, optimization: str,
                                readonly_tables: list[dict]) -> dict:
    """Generate an audit-only companion with the identical pinned LLVM settings."""
    prefix=object_file.removesuffix('.o');raw_file=prefix+'-audit-rodata.bin'
    rodata=b''
    if '.rodata' in alloc_section_names(section_text):
        inspect('llvm-objcopy',['-O','binary','--only-section=.rodata',object_file,raw_file],prefix.replace('/','-')+'-jump-rodata')
        rodata=(directory/raw_file).read_bytes()
    assembly='';symbols='';relocations='';text=b'';companion_text=b'';companion_files={}
    if '.LJTI' in symbol_text:
        asm_file=prefix+'-audit-companion.s';companion_file=prefix+'-audit-companion.o'
        args=[('-filetype=asm' if arg=='-filetype=obj' else arg) for arg in LLC_ARGUMENTS]
        inspect('llc',[*args,'-stack-size-section','-'+optimization,prefix+'.opt.ll','-o',asm_file],prefix.replace('/','-')+'-jump-llc')
        inspect('llvm-mc',['-triple=riscv64-unknown-elf','-mattr=+m,+zicsr,+zifencei,-a,-f,-d,-c,-v,-relax','-filetype=obj','-save-temp-labels',asm_file,'-o',companion_file],prefix.replace('/','-')+'-jump-mc')
        assembly=(directory/asm_file).read_text()
        symbols=inspect('llvm-readelf',['-s','--wide',companion_file],prefix.replace('/','-')+'-jump-companion-symbols')
        relocations=inspect('llvm-readelf',['-r',companion_file],prefix.replace('/','-')+'-jump-companion-relocations')
        for obj,raw in ((object_file,prefix+'-audit-text.bin'),(companion_file,prefix+'-audit-companion-text.bin')):
            inspect('llvm-objcopy',['-O','binary','--only-section=.text',obj,raw],raw.replace('/','-'))
        text=(directory/(prefix+'-audit-text.bin')).read_bytes();companion_text=(directory/(prefix+'-audit-companion-text.bin')).read_bytes()
        companion_files=dict(assembly_sha256=sha256(directory/asm_file),object_sha256=sha256(directory/companion_file),code_sha256=hashlib.sha256(text).hexdigest())
    report=validate_backend_jump_tables(section_text,symbol_text,relocation_text,rodata,unit=unit,optimized_ir=(directory/(prefix+'.opt.ll')).read_text(),optimization=optimization,readonly_tables=readonly_tables,
                                        assembly=assembly,companion_symbols=symbols,companion_relocations=relocations,text=text,companion_text=companion_text)
    return {**report,**companion_files}


def _kernel_access_op(line: str, unit: dict, *, optimized: bool = False) -> str | None:
    """Keep the new closed FCR byte outside every legacy device recognizer."""
    ordinary = _access_op(line, optimized=optimized)
    if ordinary is not None:
        return ordinary
    if unit.get("role") != "kernel" or not (unit.get("contract_version") == "core0-kernel-v0.2" or
            unit.get("configuration") in LEMMASIM_CONFIGURATIONS and unit.get("contract_version") == kernel_contract(unit.get("configuration"))):
        return None
    value = r"(?:199|-57)" if optimized else "199"
    store = re.fullmatch(r"store volatile i8 " + value +
                         r", ptr inttoptr \(i64 268435458 to ptr\), align ([0-9]+)", line.strip())
    if store and _valid_access_alignment(0x10000002, int(store[1]), optimized=optimized):
        return "uart.fcr.enable-reset-trigger14"
    return None


def validate_kernel_uart_initialize(ir: str, unit: dict, *, optimized: bool) -> None:
    """Bind the closed FIFO site to the first boot service and one direct call."""
    operations = [row for row in unit["used_device_ops"] if row["stable_id"] == "uart.enable-reset-fifo-trigger14"]
    if not operations:
        return
    by_source = {row["source"]: row["symbol"] for row in unit["functions"]}
    initialize = by_source.get("Lemma.Platform.LemmaVM.ConsoleDevice.initialize14")
    factored_boot = by_source.get("Lemma.Kernel.BootServices.bootServicesFor")
    boot = factored_boot or by_source.get("Lemma.Kernel.Entry.bootServices")
    if unit.get("configuration") in LEMMASIM_CONFIGURATIONS:
        normalized = {re.sub(r"^_private\..*?\.[0-9]+\.", "", source): symbol for source,symbol in by_source.items()}
        boot = normalized.get("Lemma.Platform.Silicon.Development.BLELink.boot") if unit["configuration"] in BLE_CONFIGURATIONS else normalized.get("Lemma.Platform.Silicon.Development.PowerSafety.boot") if unit["configuration"]=="lemmasim-silicon-power-safety-probe" else normalized.get("Lemma.Platform.LemmaSim.NotebookKernel.siliconPowerProbe") if unit["configuration"] == "lemmasim-silicon-power-probe" else normalized.get("Lemma.Platform.LemmaSim.NotebookKernel.bootSelected") if unit["configuration"] in LEMMASIM_NOTEBOOK_CONFIGURATIONS else normalized.get("Lemma.Platform.LemmaSim.Entry.initializeBinding")
    if initialize is None or boot is None:
        raise Core0Error("trigger14 FIFO lacks its exact initializer/boot source closure")
    if not optimized:
        body = _ir_definition_body(ir, boot)
        calls = re.findall(r"(?m)^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:tail )?call\s+[^\n]*?@([-A-Za-z0-9_.$]+)\(", body)
        if factored_boot is not None:
            control = by_source.get("Lemma.Platform.LemmaVM.Layout.inputControlValue")
            write = by_source.get("Lemma.Kernel.Memory.Access.write64")
            if (control is None or write is None or calls[:3] != [control, write, initialize]
                    or re.fullmatch(r"\s*entry:\s*ret i64 " + str(0x80400660) + r"\s*", _ir_definition_body(ir, control)) is None):
                raise Core0Error("factored boot lacks its exact initial input-control clear and FIFO sequence")
            addresses = re.findall(r"(%[A-Za-z0-9_.$-]+) = call i64 @" + re.escape(control) + r"\(\)", body)
            writes = re.findall(r"call \{ i64, i64 \} @" + re.escape(write) + r"\(i64 ([^,\n]+), i64 ([^\n)]+)\)", body)
            if len(addresses) != 1 or writes != [(addresses[0], "0")]:
                raise Core0Error("boot input-control clear changed address/value or added a write")
            validate_checked_call_gate(body, write, initialize)
        elif not calls or calls[0] != initialize:
            raise Core0Error("boot services do not initialize the FIFO before their first effect")
        if calls.count(initialize) != 1:
            raise Core0Error("boot services do not initialize the FIFO exactly once")
        total = len(re.findall(r"(?m)^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:tail )?call\s+[^\n]*?@" + re.escape(initialize) + r"\(", ir))
        if total != 1:
            raise Core0Error("compiled boot closure contains an additional FIFO reset")


def validate_ir(ir: str, unit: dict, *, optimized: bool, optimization: str | None = None) -> dict:
    if optimization is not None and optimization not in OPT_PASSES:
        raise Core0Error("IR audit optimization level differs from closed pipeline")
    ble_header = validate_ble_header_intrinsic(ir,unit,optimized=optimized,optimization=optimization)
    definitions, declarations, calls = parse_definitions_and_calls(ir)
    functions = {row["symbol"] for row in unit["functions"]}
    primitives = {row["primitive_symbol"] for row in unit["used_execution_ops"] if row["primitive_symbol"] is not None}
    if unit["role"] != "user":
        primitives.add("core0_io_fence")
    intrinsic = optimizer_intrinsics(unit) if optimized else set()
    if (not definitions or (definitions != functions if not optimized else not definitions <= functions)
            or not declarations <= primitives | intrinsic or not calls <= functions | primitives | intrinsic):
        raise Core0Error("LLVM definitions/declarations/calls escape the closed unit catalog")
    if re.search(r"\basm\b|\binvoke\b|\bcallbr\b|\bblockaddress\b|\bcomdat\b|\bthread_local\b", ir):
        raise Core0Error("unsupported LLVM control/runtime construct")
    for line in ir.splitlines():
        call_instruction = re.match(r"^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:(?:tail|musttail|notail)\s+)?call\b", line)
        if call_instruction and not re.search(r"@[-A-Za-z0-9_.$]+\(", line):
            raise Core0Error("indirect or unparseable LLVM call")
    if 'target triple = "riscv64-unknown-unknown-elf"' not in ir:
        raise Core0Error("LLVM target triple differs")
    if not optimized:
        types = {"bool": "i1", "u8": "i8", "u32": "i32", "u64": "i64"}
        for row in unit["functions"]:
            matches = re.findall(r"(?m)^define\s+[^\n]*@" + re.escape(row["symbol"]) + r"\(([^\n]*)\)", ir)
            if len(matches) != 1 or re.findall(r"\b(i1|i8|i32|i64)\b", matches[0]) != [types[ty] for ty in row["args"]]:
                raise Core0Error("source manifest/LLVM function argument signature differs")
        by_source = {row["source"]: row["symbol"] for row in unit["functions"]}
        for loop in unit["used_loops"]:
            callback = re.escape(by_source[loop["callback"]])
            if not re.search(r"(?m)^define \{ i64, i64 \} @" + callback + r"\(\)", ir) or not re.search(r"\bcall \{ i64, i64 \} @" + callback + r"\(\)", ir):
                raise Core0Error("Action loop callback is not a closed direct checked-Action call in LLVM")
    for operation in unit["used_execution_ops"]:
        symbol = operation["primitive_symbol"]
        if symbol is None or symbol not in declarations:
            continue
        expected_result = "{ i64, i64 }" if operation["returnkind"] == "checked" else "i64"
        expected_args = ", ".join("i64" for _ in operation["arguments"])
        expected = "declare " + expected_result + " @" + symbol + "(" + expected_args + ")"
        if not _primitive_declaration_matches(ir, expected):
            raise Core0Error("LLVM execution primitive calling convention differs")
    if "core0_io_fence" in declarations and not _primitive_declaration_matches(ir, "declare void @core0_io_fence()"):
        raise Core0Error("LLVM IO fence calling convention differs")
    from closed_inline import validate as validate_closed_inline
    inline_report = validate_closed_inline(ir, unit, optimized=optimized)
    from managed_records import validate as validate_managed_records
    records_report = validate_managed_records(ir, unit, optimized=optimized)
    validate_kernel_uart_initialize(ir, unit, optimized=optimized)
    lines = ir.splitlines()
    # A post-pipeline O0 file still contains the untransformed genuine bodies.
    # Preserve historical validators and classify only new LemmaSim lowering
    # by the actual recorded optimization command, not its filename.
    sim_transformed = optimized and optimization != "O0"
    readonly_load_sites, readonly_tables = validate_readonly_pmp_lookup(ir, unit,
        optimized=sim_transformed if unit.get('configuration') in LEMMASIM_CONFIGURATIONS else optimized)
    from lemmasim_readonly import validate_devices
    sim_device_sites, sim_devices = validate_devices(ir, unit, sim_transformed)
    line_functions = _line_functions(lines)
    expected_sites = {(site["site"], site["symbol"], operation["lowering_id"])
                      for operation in unit["used_device_ops"] for site in operation["sites"]}
    observed_sites = set()
    actual_device_operations = []
    memory_operations = {row["source_identity"].rsplit(".", 1)[-1] for row in unit["used_execution_ops"]
                         if row["primitive_symbol"] is None}
    memory_access_counts = {"read8": 0, "read64": 0, "write8": 0, "write64": 0}
    for index, line in enumerate(lines):
        marker = SITE_MARKER.fullmatch(line)
        if marker and not optimized:
            if index + 3 >= len(lines) or FENCE_CALL.fullmatch(lines[index+1]) is None or FENCE_CALL.fullmatch(lines[index+3]) is None:
                raise Core0Error("compiled UART site lacks its contiguous IO fence pair")
            operation = _kernel_access_op(lines[index+2], unit)
            site = (int(marker[1]), line_functions[index], marker[2])
            if operation != marker[2] or site in observed_sites:
                raise Core0Error("compiled UART site is duplicated or its access differs")
            observed_sites.add(site)
        address = DIRECT_ADDRESS.search(line)
        if address and 0x10000000 <= int(address[1]) < 0x10000100 and ("load " in line or line.lstrip().startswith("store ")):
            operation = _kernel_access_op(line, unit, optimized=optimized)
            if (operation is None or index == 0 or index + 1 >= len(lines) or
                    FENCE_CALL.fullmatch(lines[index-1]) is None or FENCE_CALL.fullmatch(lines[index+1]) is None):
                raise Core0Error("UART IR access width/address/volatility/fences differ")
            if unit["role"] == "user":
                raise Core0Error("U-mode unit has physical MMIO")
            actual_device_operations.append(operation)
        elif re.match(r"^\s*(?:%[-A-Za-z0-9_.$]+\s*=\s*)?(?:load|store)\b", line):
            if index in readonly_load_sites or index in sim_device_sites:
                continue
            match = re.search(r"\b(load|store) volatile i(8|64)\b", line)
            if not match:
                raise Core0Error("unknown/nonvolatile target RAM access type")
            direction = "Read" if match[1] == "load" else "Write"
            operation_name = ("virtual" if unit["role"] == "user" else "physical") + direction + match[2]
            if operation_name not in memory_operations:
                raise Core0Error("target RAM access lacks its exact source execution-operation authority")
            memory_access_counts[direction.lower() + match[2]] += 1
    if not optimized and observed_sites != expected_sites:
        raise Core0Error("source/device site catalog disagrees with emitted LLVM")
    from collections import Counter
    if Counter(actual_device_operations) != Counter(op for _, _, op in expected_sites):
        raise Core0Error("LLVM removed/duplicated/unaccounted compiled UART operation")
    return {"definitions": sorted(definitions), "calls": sorted(calls), "declarations": sorted(declarations),
            "optimizer_intrinsics": sorted(declarations & intrinsic), "device_operations": actual_device_operations,
            "memory_access_counts": memory_access_counts, "readonly_optimizer_tables": readonly_tables,
            "checked_inline": inline_report, "managed_records": records_report,
            **({"ble_header_intrinsic":ble_header} if ble_header else {}),
            **({"lemmasim_device_lowering":sim_devices} if unit.get("configuration") in LEMMASIM_CONFIGURATIONS else {})}


def _primitive_declaration_matches(ir: str, expected: str) -> bool:
    """Keep the generated primitive ABI and its opaque side effects exact.

    The exporter marks these boundaries nounwind. LLVM may intern that single
    attribute and add local_unnamed_addr; memory/purity or alternate calling
    convention annotations are not admitted at this boundary.
    """
    declarations = re.findall(r"(?m)^" + re.escape(expected) + r"(?: local_unnamed_addr)? (nounwind|#[0-9]+)$", ir)
    if len(declarations) != 1:
        return False
    attribute = declarations[0]
    if attribute == "nounwind":
        return True
    groups = re.findall(r"(?m)^attributes " + re.escape(attribute) + r" = \{([^\n]*)\}$", ir)
    return len(groups) == 1 and groups[0].strip() == "nounwind"


def function_ranges(symbol_text: str) -> dict[str, tuple[int, int]]:
    ranges = {}
    for line in symbol_text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[0].endswith(":") and fields[3] == "FUNC" and fields[6] != "UND":
            name, address, size = fields[7], int(fields[1], 16), int(fields[2], 0)
            if name in ranges or size <= 0 or size % 4 or address % 4:
                raise Core0Error("duplicate/empty/unaligned integer function range")
            ranges[name] = (address, size)
    ordered = sorted(ranges.values())
    if not ordered or any(left + size > right for (left, size), (right, _) in zip(ordered, ordered[1:])):
        raise Core0Error("empty/overlapping executable function range corpus")
    return ranges


def validate_machine(text: str, *, user: bool = False,
                     ranges: dict[str, tuple[int, int]] | None = None, user_csr_pc: int | None = None,
                     user_attack: dict | None = None, configuration: str = "normal") -> None:
    if user_csr_pc is not None and (not user or type(user_csr_pc) is not int):
        raise Core0Error("CSR exception lacks exact user instruction address")
    return_site, zero_window = None, None
    if user_attack is not None:
        if not user or ranges is None or user_attack.get("case") not in INSTRUCTION_CASES:
            raise Core0Error("instruction exception lacks a selected proved user function")
        case = user_attack["case"]
        symbol, effect, words = USER_ATTACKS[case]
        base, size = ranges.get(symbol, (None, None))
        offset, opcode = INSTRUCTION_CASES[case]
        if (type(base) is not int or base % 4 or size != 4 * len(words) or
                any(user_attack.get(key) != value for key, value in {
                    "symbol": symbol, "effect": effect, "base": base, "bytes": size,
                    "raw_sha256": hashlib.sha256(struct.pack(f"<{len(words)}I", *words)).hexdigest(),
                    "fault_pc": base + offset,
                    "instruction_site": {"pc": base + offset, "offset": offset, "instruction_bits": 32, "opcode": opcode}}.items())):
            raise Core0Error("instruction exception is not bound to its exact audited function/site/bytes")
        if case == "halfword-ecall": zero_window = (base + 20, base + 24)
        else: return_site = (base, "sret" if case == "return-supervisor" else "mret")
    found = 0
    expected = None if ranges is None else {address for begin, size in ranges.values() for address in range(begin, begin+size, 4)}
    observed = set()
    zero_sites = set()
    if zero_window is not None: expected.remove(zero_window[0])
    for line in text.splitlines():
        match = re.match(r"\s*([0-9a-f]+):\s+(\S+)\s*(.*)", line)
        if not match:
            continue
        address = int(match[1], 16)
        if ranges is not None and not any(begin <= address < begin+size for begin, size in ranges.values()):
            continue  # source-bound object constant pools are not FUNC bytes
        instruction, operands = match[2], match[3]
        if zero_window is not None and zero_window[0] <= address < zero_window[1]:
            # Pinned LLVM prints the proven fixed-zero word as two unknown
            # halfwords. This exception is only formatting of these exact
            # extracted zero bytes inside the selected24-byte function.
            if address in zero_sites or address not in {zero_window[0], zero_window[0] + 2} or instruction != "<unknown>" or operands.strip():
                raise Core0Error("halfword fixed zero window disassembly differs")
            zero_sites.add(address)
            continue
        if address in observed or expected is not None and address not in expected:
            raise Core0Error("duplicate/unaligned instruction inside a function range")
        observed.add(address)
        found += 1
        if instruction not in INTEGER_INSTRUCTIONS:
            raise Core0Error(f"unknown/noninteger/compressed machine instruction: {instruction}")
        allowed_csr = address == user_csr_pc and instruction == "csrr" and operands.replace(" ", "") == "a0,sstatus"
        allowed_return = return_site == (address, instruction) and not operands.strip()
        if user and (instruction.startswith("csr") and not allowed_csr or
                     instruction in {"mret", "sret", "wfi", "sfence.vma"} and not allowed_return):
            raise Core0Error("ordinary user image contains privileged machine instructions")
        if instruction.startswith("csr"):
            names = re.findall(r"\b(?:[ms][a-z][a-z0-9]+|satp|pmp[a-z0-9]+)\b", operands)
            allowed = KNOWN_CSRS | ({"pmpaddr5", "pmpaddr6", "pmpaddr7"} if configuration in LEMMASIM_CONFIGURATIONS else set())
            if not names or not set(names) <= allowed:
                raise Core0Error("unknown CSR in platform code")
    if not found:
        raise Core0Error("empty machine instruction corpus")
    if expected is not None and observed != expected:
        raise Core0Error("disassembly does not cover every four-byte function instruction")
    if zero_window is not None and zero_sites != {zero_window[0], zero_window[0] + 2}:
        raise Core0Error("halfword fixed zero word lacks complete disassembly coverage")



def _artifact_inspector(root: Path, directory: Path, timeout: float, logs: list[dict]):
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise Core0Error("artifact inspection timeout must be finite and positive")
    tools = require_tools(("llvm-readelf", "llvm-nm", "llvm-objdump", "llvm-objcopy", "llc", "llvm-mc"))
    pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
    store = pin.get("tools", {}).get("llvm", {}).get("store_path")
    if pin.get("status") != "pinned" or not isinstance(store, str) or any(not path.startswith(store + "/") for path in tools.values()):
        raise Core0Error("artifact inspection tools differ from the immutable LLVM output")
    def inspect(name: str, args: list[str], label: str) -> str:
        actual = [tools[name], *(["--elf-output-style=GNU"] if name == "llvm-readelf" else []), *args]
        result = run_bounded(actual, cwd=directory, timeout_seconds=timeout)
        logs.append({"argv": actual, "cwd": str(directory), "returncode": result.returncode})
        text = (result.stdout + result.stderr).decode(errors="strict")
        (directory / ("audit-" + label + ".txt")).write_text(text)
        if result.returncode:
            raise Core0Error(f"artifact inspection failed: {label}: {text}")
        return text
    return inspect


def inspect_linked_elf(inspect, *, name: str, image: str, expected: set[str], layout: dict,
                       user: bool, assembly: str, user_case: str = "none",
                       output_dir: Path | None = None, unit: dict | None = None) -> tuple[dict, str, str, dict]:
    """One linked-code scanner shared by each boot and separately linked user ELF."""
    header = inspect("llvm-readelf", ["-h", image], name + "-header")
    if not all(token in header for token in ("ELF64", "little endian", "RISC-V")) or not re.search(r"Flags:\s+0x0(?:\s|$)", header):
        raise Core0Error("ELF ISA/class/endianness/float/compressed flags differ")
    attributes = inspect("llvm-readelf", ["-A", image], name + "-attributes")
    arch = re.search(r"rv64i[0-9p]+(?:_[a-z0-9p]+)+", attributes)
    if not arch or arch[0] != "rv64i2p1_m2p0_zicsr2p0_zifencei2p0_zmmul1p0":
        raise Core0Error("ELF architecture attribute differs from integer-only profile")
    if inspect("llvm-nm", ["--undefined-only", image], name + "undefined").strip():
        raise Core0Error("final ELF contains undefined symbols")
    if relocation_types(inspect("llvm-readelf", ["-r", image], name + "-relocations")):
        raise Core0Error("final ELF contains runtime relocations")
    symbol_text = inspect("llvm-readelf", ["-s", "--wide", image], name + "-symbols")
    symbols = defined_function_symbols(symbol_text)
    if symbols != expected:
        raise Core0Error(f"{name} executable symbol provenance differs: missing {sorted(expected-symbols)}; unexpected {sorted(symbols-expected)}")
    addresses = numeric_symbols(inspect("llvm-nm", ["--defined-only", image], name + "-addresses"))
    segments = parse_load_segments(inspect("llvm-readelf", ["-l", "--wide", image], name + "-segments"))
    text_base, text_limit = layout["user"]["text_base"], layout["user"]["text_limit"]
    intervals = [(row["base"], row["limit"]) for row in layout["intervals"]] if not user else [(text_base, text_limit), (0x20000, 0x21000)]
    if not segments:
        raise Core0Error("ELF load segment corpus is empty")
    if user and (len(segments) != 2 or segments[0]["virtual_address"] != text_base or segments[0]["flags"] != "RE"
                 or segments[0]["memory_size"] != segments[0]["file_size"]
                 or segments[1]["virtual_address"] != 0x20000 or segments[1]["flags"] != "RW"
                 or segments[1]["file_size"] != 16 or segments[1]["memory_size"] != 4096):
        raise Core0Error("user ELF text RX/data RW initialized/BSS segment contract differs")
    for segment in segments:
        begin, size = segment["virtual_address"], segment["memory_size"]
        if (size == 0 or segment["file_size"] > size or "W" in segment["flags"] and "E" in segment["flags"]
                or not any(lo <= begin and begin + size <= hi for lo, hi in intervals) or segment["physical_address"] != begin):
            raise Core0Error("ELF PT_LOAD permissions or declared range differs")
    entry = re.search(r"Entry point address:\s*(0x[0-9a-fA-F]+)", header)
    required = text_base if user else 0x80000000
    if not entry or int(entry[1], 16) != required:
        raise Core0Error("ELF entry point differs")
    for symbol in symbols:
        privilege = "U" if user else ("M" if symbol.startswith("lemma_firmware_") or symbol in M_SYMBOLS else "S")
        low, high = ((text_base, text_limit) if user else (0x80000000, 0x80010000) if privilege == "M" else (0x80200000, 0x80300000))
        if symbol not in addresses or not low <= addresses[symbol] < high:
            raise Core0Error(f"{symbol} lies outside its source privilege range")
    machine = inspect("llvm-objdump", ["-d", "--no-show-raw-insn", image], name + "-disassembly")
    ranges = function_ranges(symbol_text)
    raw_machine = inspect("llvm-objdump", ["-d", image], name + "-raw-disassembly")
    attack_bytes = None
    if user and user_case == "halfword-ecall":
        if output_dir is None:
            raise Core0Error("halfword linked instruction audit lacks actual ELF byte extraction")
        binary = "audit-" + name + "-code.bin"
        inspect("llvm-objcopy", ["-O", "binary", "--only-section=.text", image, binary], name + "-code-extract")
        text = (output_dir / binary).read_bytes()
        base, size = ranges.get(USER_ATTACKS[user_case][0], (None, None))
        if type(base) is not int or base < 0x10000 or base + size > 0x10000 + len(text):
            raise Core0Error("halfword function exceeds its independently extracted ELF code bytes")
        attack_bytes = text[base - 0x10000: base - 0x10000 + size]
    attack = validate_user_attack_machine(raw_machine, ranges, assembly, user_case, raw_bytes=attack_bytes,
                                         configuration=layout["configuration"], image_key=unit.get("image_key") if unit else None,
                                         unit=unit) if user else None
    validate_machine(machine, user=user, ranges=ranges, user_csr_pc=attack["base"] if user and user_case == "supervisor-csr" else None,
                     user_attack=attack if user and user_case in INSTRUCTION_CASES else None, configuration=layout["configuration"])
    record = {"entry": required, "segments": segments, "function_symbols": sorted(symbols),
              "function_ranges": {symbol: {"base": address, "bytes": size} for symbol, (address, size) in ranges.items()}}
    if not user:
        record['boot_metadata_clear'] = validate_boot_metadata_clear(layout, addresses, segments, raw_machine, ranges)
    if user:
        begin, size = ranges["_user_start"]
        pcs = [int(match[1], 16) for line in machine.splitlines()
               if (match := re.match(r"\s*([0-9a-f]+):\s+ecall\s*$", line)) and begin <= int(match[1], 16) < begin + size]
        if len(pcs) != 1:
            raise Core0Error("user startup lacks its exact single exit ECALL")
        record.update(exit_ecall_pc=pcs[0], syscall_bridge=validate_user_syscall_bridge(assembly, raw_machine, ranges),
                      quarantined_startup=attack)
    return record, symbol_text, raw_machine, ranges


def audit_user_image(*, root: Path, output_dir: Path, catalog: dict, image_key: str,
                     optimization: str, timeout_seconds: float = 60) -> dict:
    """Reusable actual unit/object/ELF/stack audit for full and standalone images.

    The caller binds the registry, source snapshot and construction commands.
    This scanner independently checks every selected image's actual bytes.
    """
    image = selected_user_image(catalog, image_key)
    configuration, user_case = catalog["configuration"], image["startup_case"]
    if optimization not in OPT_PASSES or output_dir.name != image_key or output_dir.parent.name != "users":
        raise Core0Error("per-image audit path/optimization differs")
    logs = []
    inspect = _artifact_inspector(root, output_dir, timeout_seconds, logs)
    layout = validate_layout(load_json(output_dir / "layout.json"), configuration=configuration, image_key=image_key)
    validate_user_primitive_catalog(load_json(output_dir / "primitive-catalog.json"), image, configuration=configuration)
    unit = validate_unit(load_json(output_dir / "unit.json"), "user", configuration=configuration, image_key=image_key)
    ir = {kind: validate_ir((output_dir / file).read_text(), unit, optimized=kind == "optimized", optimization=optimization)
          for kind, file in (("pre", "program.ll"), ("optimized", "program.opt.ll"))}
    assembly = (output_dir / "startup.S").read_text()
    validate_user_entry_source(assembly, unit["roots"][0]["symbol"], user_case)
    primitive_symbols = {row["symbol"] for row in user_primitive_rows(user_case)}
    object_functions = {"startup.o": primitive_symbols, "program.o": set(ir["optimized"]["definitions"])}
    allowed_relocations = {"R_RISCV_BRANCH", "R_RISCV_JAL", "R_RISCV_PCREL_HI20", "R_RISCV_PCREL_LO12_I", "R_RISCV_PCREL_LO12_S",
                           "R_RISCV_CALL", "R_RISCV_CALL_PLT", "R_RISCV_64", "R_RISCV_32", "R_RISCV_ADD64", "R_RISCV_SUB64"}
    initializer, attack_object = None, None
    backend_objects = []
    for obj, expected in object_functions.items():
        symbols = inspect("llvm-readelf", ["-s", "--wide", obj], obj + "-symbols")
        relocation_text = inspect("llvm-readelf", ["-r", obj], obj + "-relocations")
        if defined_function_symbols(symbols) != expected or not relocation_types(relocation_text) <= allowed_relocations:
            raise Core0Error("user object executable source/relocation closure differs")
        section_text = inspect("llvm-readelf", ["-S", "--wide", obj], obj + "-sections")
        sections = alloc_section_names(section_text)
        allowed = ({".text", ".text.user_start", ".text.user_boundary", ".data.user_abi"}
                   | ({".text.user_adversarial"} if user_case != "none" else set())) if obj == "startup.o" else {".text", ".rodata", ".rodata.cst8", ".data", ".bss"}
        if not sections <= allowed:
            raise Core0Error("unaccounted allocated per-image user object section")
        if ".rodata.cst8" in sections:
            constant = re.search(r"(?m)^\s*\[\s*\d+\]\s+\.rodata\.cst8\s+PROGBITS\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)\s+08\s+AM\s+0\s+0\s+8\s*$", section_text)
            if not constant or int(constant[1], 16) == 0 or int(constant[1], 16) % 8:
                raise Core0Error("user constant pool flags/entry size/alignment differ")
        if obj == "program.o":
            literal_tables = []
            if configuration in LEMMASIM_CONFIGURATIONS:
                from lemmasim_readonly import validate_object
                section_bytes={}
                for name in (".rodata", ".rodata.cst32"):
                    if name in sections:
                        filename="audit-" + name.removeprefix(".") + "-literals.bin"
                        inspect("llvm-objcopy", ["-O", "binary", "--only-section="+name, obj, filename], "literal-"+name)
                        section_bytes[name]=(output_dir/filename).read_bytes()
                literal_tables=validate_object(section_text,symbols,relocation_text,section_bytes,
                    ir["optimized"]["readonly_optimizer_tables"],image["directory"]+"/"+obj)["readonly_tables"]
            backend_objects.append(inspect_backend_jump_tables(inspect, output_dir, object_file=obj,
                                  section_text=section_text, symbol_text=symbols, relocation_text=relocation_text,
                                  unit=unit, optimization=optimization, readonly_tables=literal_tables))
        if obj == "startup.o":
            attack_bytes = b""
            if user_case != "none":
                inspect("llvm-objcopy", ["-O", "binary", "--only-section=.text.user_adversarial", obj, "audit-attack-object.bin"], "attack-object-extract")
                attack_bytes = (output_dir / "audit-attack-object.bin").read_bytes()
            attack_object = validate_image_attack_object(section_text, symbols, attack_bytes, assembly,
                                                        configuration=configuration, image_key=image_key, unit=unit,
                                                        relocation_text=relocation_text)
            inspect("llvm-objcopy", ["-O", "binary", "--only-section=.data.user_abi", obj, "audit-abi-object.bin"], "abi-object-extract")
            initializer = validate_user_abi_data(section_text, (output_dir / "audit-abi-object.bin").read_bytes(), symbols, assembly,
                                                object_file=image["directory"] + "/startup.o", configuration=configuration)
    expected_objects = {image["directory"] + "/" + obj for obj in ("startup.o", "program.o")}
    linked_objects = set(re.findall(r"([^\s()]+\.o)(?=[:(\s])", (output_dir / "image.map").read_text()))
    if linked_objects != expected_objects:
        raise Core0Error("per-image actual link map escapes its two declared objects")
    for symbol in primitive_symbols:
        if machine_frame(assembly, symbol):
            raise Core0Error("user entry/syscall consumes undeclared stack")
    frames = parse_stack_sizes(inspect("llvm-readelf", ["--stack-sizes", "program.o"], "stack-sizes"))
    if set(frames) != object_functions["program.o"]:
        raise Core0Error("per-image stack metadata differs from object code closure")
    validate_compiled_stack(inspect("llvm-objdump", ["-d", "--no-show-raw-insn", "program.o"], "stack-disassembly"), frames)
    primitives = {row["primitive_symbol"]: machine_frame(assembly, row["primitive_symbol"])
                  for row in unit["used_execution_ops"] if row["primitive_symbol"] is not None}
    undefined = {line.split()[-1] for line in inspect("llvm-nm", ["--undefined-only", "program.o"], "stack-undefined").splitlines() if line.split()}
    if not undefined <= set(primitives):
        raise Core0Error("per-image object contains an unaccounted stack/runtime symbol")
    post = (output_dir / "program.opt.ll").read_text()
    _defs, _decls, calls = parse_definitions_and_calls(post)
    primitives.update({symbol: 0 for symbol in calls & optimizer_intrinsics(unit)})
    graph = weighted_stack_graph(post, frames, primitives)
    capacities = {"machine": 65536, "boot": 61440, "kernel-trap": layout["task_kernel_stack_bytes"], "user": layout["user"]["stack_pages"] * layout["frame_bytes"]}
    graph.update(entries=validate_stack_entries(unit, graph, capacities=capacities, vector_bytes=288),
                 function_bytes=dict(sorted(frames.items())), object_undefined_symbols=sorted(undefined), maximum_compiled_frame_bytes=max(frames.values()))
    if configuration in LEMMASIM_CONFIGURATIONS and any(row['margin_bytes'] * 4 < row['capacity_bytes'] for row in graph['entries']):
        raise Core0Error('Lemmasim compiled User stack has less than 25percent headroom')
    lease_scan = None
    if configuration in SERVICE_CONFIGURATIONS and image_key == 'server':
        source_symbols={re.sub(r'^_private\..*?\.[0-9]+\.','',row['source']):row['symbol'] for row in unit['functions']}
        expected=['Lemma.Services.Buffer.Server.step','Lemma.User.IPC.receive','Lemma.User.Syscall.time',
                  'Lemma.Services.Buffer.Server.expireStep','Lemma.Services.Buffer.Server.dispatch',
                  'Lemma.Services.Buffer.Server.application','Lemma.Services.Buffer.Server.create',
                  'Lemma.Services.Buffer.Server.existing','Lemma.Services.Buffer.Protocol.leaseTicks']
        if not set(expected)<=source_symbols.keys():
            raise Core0Error('Server lease scan source closure is incomplete')
        lease_scan=validate_server_lease_scan(_ir_definition_body((output_dir/'program.ll').read_text(),source_symbols[expected[0]]),
            receive=source_symbols[expected[1]],time=source_symbols[expected[2]],expire=source_symbols[expected[3]],dispatch=source_symbols[expected[4]])
        if re.fullmatch(r'\s*entry:\s*ret i64 100000000\s*',_ir_definition_body((output_dir/'program.ll').read_text(),source_symbols[expected[8]])) is None:
            raise Core0Error('Server application leaseTicks contract differs')
        lease_scan['application']=validate_server_application_expiry(
            _ir_definition_body((output_dir/'program.ll').read_text(),source_symbols[expected[5]]),
            time=source_symbols[expected[2]],expire=source_symbols[expected[3]],create=source_symbols[expected[6]],
            existing=source_symbols[expected[7]],lease=source_symbols[expected[8]])
    elf, symbols, raw, ranges = inspect_linked_elf(inspect, name="user", image="image.elf", expected=primitive_symbols | set(ir["optimized"]["definitions"]),
                                                  layout=layout, user=True, assembly=assembly, user_case=user_case,
                                                  output_dir=output_dir, unit=unit)
    for section, target in ((".text", "text.bin"), (".data", "data.bin")):
        actual = "audit-extracted-" + target
        inspect("llvm-objcopy", ["-O", "binary", "--only-section=" + section, "image.elf", actual], target + "-extract")
        if (output_dir / actual).read_bytes() != (output_dir / target).read_bytes():
            raise Core0Error("per-image packaged payload differs from its independently extracted ELF section")
    text, data = (output_dir / "text.bin").read_bytes(), (output_dir / "data.bin").read_bytes()
    if not 0 < len(text) <= layout["user"]["text_limit"] - layout["user"]["text_base"] or len(data) != 16:
        raise Core0Error("per-image user text/initialized-data extent differs")
    service_quota = None
    if configuration in SERVICE_CONFIGURATIONS:
        text_pages = (len(text) + 4095) // 4096
        arena_pages = 4 if image_key == "server" else 0
        if 18 + text_pages + arena_pages > 32:
            raise Core0Error("service image exceeds owned-page quota with its reserved backing pages")
        service_quota = {"base_owned_task_frames":18,"base_global_task_frames":19,
                         "text_pages":text_pages,"reserved_arena_pages":arena_pages,"owner_quota":32}
    linked_sections=inspect("llvm-readelf", ["-S", "--wide", "image.elf"], "user-sections")
    initializer_symbols=symbols
    if configuration in LEMMASIM_CONFIGURATIONS:
        from lemmasim_readonly import validate_linked_literals
        elf['readonly_literals']=validate_linked_literals(linked_sections,symbols,text,layout['user']['text_base'],literal_tables)
        initializer_symbols='\n'.join(line for line in symbols.splitlines() if not (len(line.split())==8 and line.split()[3]=='OBJECT' and line.split()[6]!='UND'))
    initialized = validate_user_abi_data(linked_sections, data, initializer_symbols, assembly,
                                         object_file=image["directory"] + "/image.elf", configuration=configuration)
    if initializer is None or initialized["sha256"] != initializer["sha256"]:
        raise Core0Error("per-image linked initializer differs from its declared startup object")
    elf["initialized_data"] = initialized
    return {"image_key": image_key, "image_id": image["id"], "unit_ir": ir, "elf": elf, "stack_bounds": graph, **managed_fields(configuration,image),
            "image_sha256": sha256(output_dir / "image.elf"), "text_sha256": sha256(output_dir / "text.bin"),
            "data_sha256": sha256(output_dir / "data.bin"), "commands": logs, "backend_readonly_objects": backend_objects,
            **({"owned_page_budget": service_quota} if service_quota is not None else {}),
            **({'server_lease_scan':lease_scan} if lease_scan is not None else {}),
            **({"startup_case": user_case, "object_quarantined_startup": attack_object} if configuration == "tasks-fault-development" or configuration in SERVICE_INSTRUCTION_CONFIGURATIONS else {})}


def validate_multi_commands(rows: object, *, root: Path, output_dir: Path, images: list[dict],
                            optimization: str, roles: dict, standalone: bool, configuration: str = "tasks-development") -> None:
    rows = _array(rows, "multi-image construction commands")
    if not rows or any(not isinstance(row, dict) or type(row.get("returncode")) is not int or row["returncode"] != 0
                       or not isinstance(row.get("argv"), list) or not row["argv"]
                       or any(not isinstance(arg, str) for arg in row["argv"]) or not isinstance(row.get("cwd"), str)
                       for row in rows):
        raise Core0Error("multi-image command corpus is empty, malformed or failed")
    base = str(output_dir.relative_to(root))
    def compile_unit(directory):
        return [("opt", ["-S", f"-passes={OPT_PASSES[optimization]}", "program.ll", "-o", "program.opt.ll"], base + "/" + directory),
                ("llc", [*LLC_ARGUMENTS, "-stack-size-section", f"-{optimization}", "program.opt.ll", "-o", "program.o"], base + "/" + directory)]
    expected = [item for role in roles for item in compile_unit(role)]
    expected += [item for image in images for item in compile_unit(image["directory"])]
    for image in images:
        d = image["directory"]
        expected += [("clang", [*STARTUP_ARGUMENTS, d + "/startup.S", "-o", d + "/startup.o"], base),
                     ("ld.lld", ["-m", "elf64lriscv", "--no-relax", "-T", d + "/link.ld", "-Map=" + d + "/image.map", d + "/startup.o", d + "/program.o", "-o", d + "/image.elf"], base),
                     ("llvm-objcopy", ["-O", "binary", "--only-section=.text", d + "/image.elf", d + "/text.bin"], base),
                     ("llvm-objcopy", ["-O", "binary", "--only-section=.data", d + "/image.elf", d + "/data.bin"], base)]
    if not standalone:
        expected += [("clang", [*STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"], base),
                     ("clang", [*STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"], base),
                     ("ld.lld", ["-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"], base)]
    def tool_name(path):
        name = Path(path).name
        return "clang" if name == "clang-20" else name
    actual = [(tool_name(row["argv"][0]), row["argv"][1:], row["cwd"]) for row in rows
              if tool_name(row["argv"][0]) in {"opt", "llc", "clang", "ld.lld", "llvm-objcopy"} and row["argv"][1:] != ["--version"]]
    if actual != expected:
        raise Core0Error("multi-image actual tool/arguments/working-directory closure differs")
    pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
    stores = {name: pin["tools"]["llvm"]["store_path"] for name in ("opt", "llc", "llvm-objcopy")}
    stores.update({"clang": pin["tools"]["llvm"]["outputs"]["clang_unwrapped"]["store_path"], "ld.lld": pin["tools"]["lld"]["store_path"],
                   "lean": pin["tools"]["lean"]["store_path"], "lake": pin["tools"]["lean"]["store_path"]})
    for row in rows:
        name = tool_name(row["argv"][0])
        if name in stores and not row["argv"][0].startswith(stores[name] + "/"):
            raise Core0Error("multi-image compiler executable differs from its pinned store")
    source_path = pin["tools"]["lean"]["source_path"]
    nix = [row["argv"][1:] for row in rows if Path(row["argv"][0]).name == "nix"]
    if nix != [["build", "--no-link", "--print-out-paths", "--impure", "--expr", LEAN_SOURCE_EXPRESSION], ["path-info", "--json", source_path]]:
        raise Core0Error("multi-image immutable Lean source realization commands differ")
    consumers = {"CatalogExport.lean": "import Lemma.Compiler.KernelExport\n\n#lemma_export_user_catalog\n"}
    for image in images:
        consumers[image["directory"] + "/Export.lean"] = (f'import {image["module"]}\nimport Lemma.Compiler.KernelExport\n\n'
                                                          f'#lemma_export_user_image "{image["key"]}" [{image["source"]}]\n')
    if standalone:
        consumers["UserFilesExport.lean"] = f'import Lemma.Compiler.KernelExport\n\n#lemma_export_user_files "{images[0]["key"]}"\n'
    else:
        consumers["BootExport.lean"] = "import Lemma.Compiler.KernelExport\n\n#lemma_export_boot_files\n"
        for role, module in configuration_modules(configuration).items():
            consumers[role + "/Export.lean"] = (f'import {module}\nimport Lemma.Compiler.KernelExport\n\n#lemma_export_unit "{role}" ['
                                                + ", ".join(source for source, _ in roles[role]) + "]\n")
    for path, contents in consumers.items():
        if (output_dir / path).read_text() != contents:
            raise Core0Error("genuine Lean export consumer differs from its exact selected roots")
    exports = [row for row in rows if Path(row["argv"][0]).name == "lake" and row["argv"][1:3] == ["env", "lean"]]
    expected_exports = [base + "/CatalogExport.lean", *(base + "/" + role + "/Export.lean" for role in roles),
                        *(base + "/" + image["directory"] + "/Export.lean" for image in images),
                        base + ("/UserFilesExport.lean" if standalone else "/BootExport.lean")]
    if [row["argv"][3:] for row in exports] != [[path] for path in expected_exports] or any(row["cwd"] != "." for row in exports):
        raise Core0Error("genuine Lean elaboration invocation/working-directory evidence differs")


def audit_standalone_user(*, root: Path, output_dir: Path, timeout_seconds: float = 60) -> dict:
    try:
        relative = output_dir.resolve().relative_to((root / "build/user").resolve())
    except ValueError as error:
        raise Core0Error("independent user audit must stay inside build/user") from error
    if not relative.parts:
        raise Core0Error("refusing to audit the whole build/user evidence root")
    result_path = output_dir / "audit.json"
    invalidate_output_file(result_path, root)
    invalidate_output_file(output_dir / "audit-failure.json", root)
    logs = []
    try:
        build = _object(load_json(output_dir / "user-build.json"), "independent user build")
        provenance = _object(load_json(output_dir / "user-provenance.json"), "independent user provenance")
        catalog = validate_user_image_catalog(load_json(output_dir / "user-image-catalog.json"))
        image = selected_user_image(catalog, provenance.get("image_key"))
        configuration = catalog["configuration"]
        key, directory = image["key"], image["directory"]
        validate_standalone_managed_provenance(build, provenance, configuration=configuration, image=image)
        identity = {"schema_version": 2, "artifact_category": user_artifact_category(configuration), "configuration": configuration,
                    "image_key": key, "image_id": image["id"], "stage": "supervisor", "startup_case": "normal", "user_startup_case": image["startup_case"],
                    **managed_fields(configuration, image)}
        if (any(build.get(field) != value or provenance.get(field) != value for field, value in identity.items())
                or type(build.get("schema_version")) is not int or type(provenance.get("schema_version")) is not int
                or type(build.get("image_id")) is not int or type(provenance.get("image_id")) is not int
                or build.get("status") != "BUILT" or build.get("provenance_sha256") != sha256(output_dir / "user-provenance.json")):
            raise Core0Error("independent user build/provenance identity differs")
        optimization = provenance.get("optimization")
        if optimization not in OPT_PASSES or build.get("optimization") != optimization:
            raise Core0Error("independent user optimization differs")
        source_snapshot = source_inputs(root)
        if provenance.get("source_inputs") != source_snapshot:
            raise Core0Error("independent user complete source inventory is missing/stale")
        closure = user_module_closure(root, image, configuration)
        if configuration in MANAGED_POLICIES and any(path.startswith(("Lemma/Kernel/", "Lemma/Compiler/")) for path in closure):
            raise Core0Error("managed user target dependency closure contains privileged/compiler code")
        if (any("/Development/" in path and path != image["module"].replace(".", "/") + ".lean" for path in closure)
                or provenance.get("target_module_closures") != {"users": {key: closure}}):
            raise Core0Error("independent user selected source dependency closure differs")
        generated = ["user-image-catalog.json", *(directory + "/" + name for name in ("startup.S", "link.ld", "layout.json", "primitive-catalog.json"))]
        if (provenance.get("generated_by_lean") != generated
                or provenance.get("linked_inputs") != {"users": {key: [directory + "/startup.o", directory + "/program.o"]}}
                or provenance.get("unit_contracts") != {"users": {key: validate_unit(load_json(output_dir / directory / 'unit.json'), 'user', configuration=configuration, image_key=key)['contract_version']}}):
            raise Core0Error("independent user selected generated/linked/contract inventory differs")
        artifacts = _object(provenance.get("artifacts"), "independent user artifacts")
        mandatory = set(generated) | {"CatalogExport.lean", "UserFilesExport.lean"} | {directory + "/" + name for name in
                    (*UNIT_FILES, "Export.lean", "program.opt.ll", "program.o", "startup.o", "image.elf", "image.map", "text.bin", "data.bin")}
        if build.get("artifacts") != artifacts or not mandatory <= set(artifacts):
            raise Core0Error("independent user mandatory artifact inventory differs")
        for name, digest in artifacts.items():
            path = output_dir / name
            if (not path.resolve().is_relative_to(output_dir.resolve()) or not path.is_file() or sha256(path) != digest
                    or name.endswith((".o", ".elf")) and name not in {directory + "/startup.o", directory + "/program.o", directory + "/image.elf"}):
                raise Core0Error("independent user artifact is stale, foreign or escapes selected output")
        pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
        realization = _object(provenance.get("lean_source_realization"), "independent Lean source realization")
        expected = validate_lean_source_realization(pin["tools"]["lean"], str(realization.get("source_path")) + "\n",
                    {str(realization.get("source_path")): {"narHash": realization.get("narHash"), "narSize": realization.get("narSize")}})
        uint_source = Path(expected["source_path"]) / "src/Init/Data/UInt/Basic.lean"
        expected.update(uint_source=str(uint_source), uint_source_sha256=LEAN_UINT_SOURCE_SHA256)
        if realization != expected or build.get("lean_source_realization") != expected or not uint_source.is_file() or sha256(uint_source) != LEAN_UINT_SOURCE_SHA256:
            raise Core0Error("independent user immutable Lean source evidence differs")
        validate_multi_commands(provenance.get("commands"), root=root, output_dir=output_dir, images=[image], optimization=optimization, roles={}, standalone=True, configuration=configuration)
        observed = audit_user_image(root=root, output_dir=output_dir / directory, catalog=catalog, image_key=key,
                                    optimization=optimization, timeout_seconds=timeout_seconds)
        logs.extend(observed["commands"])
        if source_inputs(root) != source_snapshot:
            raise Core0Error("independent user source changed during audit")
        record = {**identity, "status": "PASS", "optimization": optimization, "source_commit": provenance["source_commit"],
                  "dirty_paths": provenance["dirty_paths"], "source_inputs": source_snapshot, "lean_source_realization": realization,
                  "user_image_catalog_sha256": sha256(output_dir / "user-image-catalog.json"), "provenance_sha256": sha256(output_dir / "user-provenance.json"),
                  **observed, "limitations": ["Independent user artifact/source audit; no kernel was built and no target execution is established."]}
        write_json(result_path, record)
        return record
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        write_json(output_dir / "audit-failure.json", {"schema_version": 2, "status": "FAIL", "error": str(error), "commands": logs})
        raise

def audit(*, root: Path, output_dir: Path, timeout_seconds: float = 60) -> dict:
    try:
        output_relative = output_dir.resolve().relative_to((root / "build/kernel").resolve())
    except ValueError as error:
        raise Core0Error("kernel audit output must be an ignored build/kernel subdirectory") from error
    if not output_relative.parts:
        raise Core0Error("refusing to audit/write the whole build/kernel root")
    result_path = output_dir / "audit.json"
    invalidate_output_file(result_path, root)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        write_json(output_dir / "audit-failure.json", {"schema_version": 1, "status": "FAIL", "error": "audit timeout must be finite and positive", "commands": []})
        raise Core0Error("audit timeout must be finite and positive")
    logs = []
    try:
        tools = require_tools(("llvm-readelf", "llvm-nm", "llvm-objdump", "llvm-objcopy", "llc", "llvm-mc"))
    except Core0Error as error:
        write_json(output_dir / "audit-failure.json", {"schema_version": 1, "status": "FAIL", "error": str(error), "commands": logs})
        raise

    def inspect(name: str, args: list[str], label: str) -> str:
        # require_tools resolves Nix's llvm-readelf symlink to llvm-readobj.
        # Set the GNU table format explicitly rather than relying on argv[0].
        actual = [tools[name], *(["--elf-output-style=GNU"] if name == "llvm-readelf" else []), *args]
        result = run_bounded(actual, cwd=output_dir, timeout_seconds=timeout_seconds)
        logs.append({"argv": actual, "returncode": result.returncode})
        text = (result.stdout + result.stderr).decode(errors="strict")
        (output_dir / ("audit-" + label + ".txt")).write_text(text)
        if result.returncode != 0:
            raise Core0Error(f"artifact inspection failed: {label}: {text}")
        return text

    try:
        build = _object(load_json(output_dir / "build.json"), "build report")
        provenance = _object(load_json(output_dir / "provenance.json"), "provenance")
        configuration = provenance.get("configuration")
        multi = configuration in MULTI_USER_CONFIGURATIONS
        catalog = validate_user_image_catalog(load_json(output_dir / "user-image-catalog.json"), configuration=configuration) if multi else None
        images = catalog["images"] if multi else []
        roles = configuration_roots(configuration)
        category = artifact_category(configuration)
        if (type(build.get("schema_version")) is not int or type(provenance.get("schema_version")) is not int
                or build.get("schema_version") != (2 if multi else 1) or provenance.get("schema_version") != (2 if multi else 1)):
            raise Core0Error("build/provenance schema differs from selected configuration")
        pin = _object(load_json(root / "tooling/toolchain-lock.json"), "toolchain lock")
        llvm_store = pin.get("tools", {}).get("llvm", {}).get("store_path")
        if pin.get("status") != "pinned" or not isinstance(llvm_store, str) or any(not path.startswith(llvm_store + "/") for path in tools.values()):
            raise Core0Error("artifact inspection tools differ from the immutable LLVM store output")
        realization = _object(provenance.get("lean_source_realization"), "Lean source realization")
        lean_pin = _object(pin.get("tools", {}).get("lean"), "locked Lean input")
        expected_realization = validate_lean_source_realization(
            lean_pin, str(realization.get("source_path")) + "\n",
            {str(realization.get("source_path")): {"narHash": realization.get("narHash"), "narSize": realization.get("narSize")}})
        uint_source = Path(expected_realization["source_path"]) / "src/Init/Data/UInt/Basic.lean"
        expected_realization.update(uint_source=str(uint_source), uint_source_sha256=LEAN_UINT_SOURCE_SHA256)
        if (realization != expected_realization or build.get("lean_source_realization") != realization
                or not uint_source.is_file() or sha256(uint_source) != LEAN_UINT_SOURCE_SHA256):
            raise Core0Error("realized Lean audit input is missing, stale or differs from its immutable source")
        if build.get("status") != "BUILT" or build.get("artifact_category") != category or build.get("configuration") != configuration or provenance.get("artifact_category") != category or build.get("provenance_sha256") != sha256(output_dir / "provenance.json"):
            raise Core0Error("build/provenance identity missing or stale")
        stage, optimization = provenance.get("stage"), provenance.get("optimization")
        if stage not in {"bootstrap-m", "supervisor"} or optimization not in OPT_PASSES or build.get("stage") != stage or build.get("optimization") != optimization:
            raise Core0Error("build execution stage/profile differs")
        validate_configuration_stage(configuration, stage)
        case, user_case = startup_case(configuration), user_startup_case(configuration)
        validate_image_case_provenance(build, provenance, configuration=configuration, images=images)
        validate_managed_provenance(build, provenance, configuration=configuration, images=images)
        if build.get("startup_case") != case or provenance.get("startup_case") != case or build.get("user_startup_case") != user_case or provenance.get("user_startup_case") != user_case:
            raise Core0Error("build/provenance generated startup case differs")
        generated = (["startup.S", "link.ld", "layout.json", "primitive-catalog.json", "boot-package.S", "package-contract.json", "user-image-catalog.json"]
                     + [image["directory"] + "/" + name for image in images for name in ("startup.S", "link.ld", "layout.json", "primitive-catalog.json")]) if multi else list(BOOT_FILES)
        linked = {"boot": list(BOOT_OBJECTS), **({"users": {image["key"]: [image["directory"] + "/startup.o", image["directory"] + "/program.o"] for image in images}} if multi else {"user": list(USER_OBJECTS)})}
        contracts = {role: kernel_contract(configuration) if role == "kernel" else CONTRACTS[role] for role in roles}
        if multi:
            contracts["users"] = {image["key"]: validate_unit(load_json(output_dir / image['directory'] / 'unit.json'), 'user', configuration=configuration, image_key=image['key'])['contract_version'] for image in images}
        if provenance.get("unit_contracts") != contracts:
            raise Core0Error("exact selected per-unit contract inventory differs")
        if provenance.get("generated_by_lean") != generated or provenance.get("linked_inputs") != linked:
            raise Core0Error("unexpected code-generation or linked-object closure")
        artifacts = _object(provenance.get("artifacts"), "artifact hashes")
        for name, digest in artifacts.items():
            path = output_dir / name
            if path.resolve().parent != output_dir.resolve() and output_dir.resolve() not in path.resolve().parents:
                raise Core0Error("artifact path escapes output")
            if not isinstance(digest, str) or not path.is_file() or sha256(path) != digest:
                raise Core0Error(f"missing/stale artifact: {name}")
        mandatory = set(generated) | set(BOOT_OBJECTS) | {"image.elf", "image.map", "platform.dtb", "platform.dts"}
        mandatory |= {role + "/" + name for role in roles for name in (*UNIT_FILES, "program.opt.ll")}
        if multi:
            mandatory |= {image["directory"] + "/" + name for image in images for name in
                          (*UNIT_FILES, "Export.lean", "program.opt.ll", "program.o", "startup.o", "image.elf", "image.map", "text.bin", "data.bin")}
        else:
            mandatory |= set(USER_OBJECTS) | {"user/image.elf", "user/image.map", "user-text.bin", "user-data.bin"}
        if not mandatory <= set(artifacts):
            raise Core0Error("mandatory artifact hash inventory is incomplete")
        source_hashes = _object(provenance.get("source_inputs"), "source input hashes")
        if source_hashes != source_inputs(root):
            raise Core0Error("complete current compiler/production source hash inventory differs")
        for name, digest in source_hashes.items():
            path = root / name
            if not path.is_file() or sha256(path) != digest:
                raise Core0Error(f"current source differs from built input: {name}")
        for role, module in configuration_modules(configuration).items():
            allowed = development_modules(configuration, role)
            closure = module_closure(root, module, allow_development=bool(allowed), development_modules=allowed,
                                     selected_executable_module="" if configuration in SERVICE_CONFIGURATIONS else None)
            if any("/Development/" in path and path not in {selected.replace(".", "/") + ".lean" for selected in allowed} for path in closure):
                raise Core0Error("dependency imports another configuration's development module")
            if closure != provenance.get("target_module_closures", {}).get(role):
                raise Core0Error("production import closure missing/stale")
        if multi:
            expected_users = {image["key"]: user_module_closure(root, image, configuration) for image in images}
            if configuration in MANAGED_POLICIES and any(path.startswith(("Lemma/Kernel/", "Lemma/Compiler/")) for closure in expected_users.values() for path in closure):
                raise Core0Error("managed user target dependency closure contains privileged/compiler code")
            if any("/Development/" in path and path != image["module"].replace(".", "/") + ".lean"
                   for image in images for path in expected_users[image["key"]]):
                raise Core0Error("per-image dependency imports another development module")
            if provenance.get("target_module_closures") != {**{role: module_closure(root, module, allow_development=development_role(configuration, role), development_modules=development_modules(configuration, role), selected_executable_module="" if configuration in SERVICE_CONFIGURATIONS else None) for role, module in configuration_modules(configuration).items()}, "users": expected_users}:
                raise Core0Error("exact full per-image source dependency inventory differs")
        command_rows = _array(provenance.get("commands"), "build commands")
        if not command_rows or any(not isinstance(row, dict) or row.get("returncode") != 0 for row in command_rows):
            raise Core0Error("build command corpus empty, malformed or failed")
        lake_commands = [row["argv"][0] for row in command_rows if isinstance(row.get("argv"), list)
                         and row["argv"] and Path(row["argv"][0]).name == "lake"]
        if not lake_commands or any(not path.startswith(lean_pin["store_path"] + "/") for path in lake_commands):
            raise Core0Error("genuine Lean elaboration must use the immutable pinned Lake executable")
        nix_commands = [row["argv"][1:] for row in command_rows if isinstance(row.get("argv"), list)
                        and row["argv"] and Path(row["argv"][0]).name == "nix"]
        if nix_commands != [["build", "--no-link", "--print-out-paths", "--impure", "--expr", LEAN_SOURCE_EXPRESSION],
                            ["path-info", "--json", lean_pin["source_path"]]]:
            raise Core0Error("Lean source realization command evidence is missing or differs")
        compile_commands = [row["argv"][1:] for row in command_rows if isinstance(row.get("argv"), list)
                            and row["argv"] and Path(row["argv"][0]).name in {"llc", "opt", "ld.lld", "clang", "clang-20", "llvm-objcopy"}
                            and row["argv"][1:] != ["--version"]]
        expected_commands = []
        for _role in roles:
            expected_commands += [["-S", f"-passes={OPT_PASSES[optimization]}", "program.ll", "-o", "program.opt.ll"],
                                  [*LLC_ARGUMENTS, "-stack-size-section", f"-{optimization}", "program.opt.ll", "-o", "program.o"]]
        if multi:
            for image in images:
                expected_commands += [["-S", f"-passes={OPT_PASSES[optimization]}", "program.ll", "-o", "program.opt.ll"],
                                      [*LLC_ARGUMENTS, "-stack-size-section", f"-{optimization}", "program.opt.ll", "-o", "program.o"]]
            for image in images:
                d = image["directory"]
                expected_commands += [[*STARTUP_ARGUMENTS, d + "/startup.S", "-o", d + "/startup.o"],
                                      ["-m", "elf64lriscv", "--no-relax", "-T", d + "/link.ld", "-Map=" + d + "/image.map", d + "/startup.o", d + "/program.o", "-o", d + "/image.elf"],
                                      ["-O", "binary", "--only-section=.text", d + "/image.elf", d + "/text.bin"],
                                      ["-O", "binary", "--only-section=.data", d + "/image.elf", d + "/data.bin"]]
            expected_commands += [[*STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"],
                                  [*STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"],
                                  ["-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"]]
        else:
            expected_commands += [[*STARTUP_ARGUMENTS, "user-startup.S", "-o", "user/startup.o"],
                              ["-m", "elf64lriscv", "--no-relax", "-T", "user-link.ld", "-Map=user/image.map", *USER_OBJECTS, "-o", "user/image.elf"],
                              ["-O", "binary", "--only-section=.text", "user/image.elf", "user-text.bin"],
                              ["-O", "binary", "--only-section=.data", "user/image.elf", "user-data.bin"],
                              [*STARTUP_ARGUMENTS, "boot-package.S", "-o", "boot-package.o"],
                              [*STARTUP_ARGUMENTS, "startup.S", "-o", "startup.o"],
                              ["-m", "elf64lriscv", "--no-relax", "-T", "link.ld", "-Map=image.map", *BOOT_OBJECTS, "-o", "image.elf"]]
        if multi:
            validate_multi_commands(command_rows, root=root, output_dir=output_dir, images=images, optimization=optimization, roles=roles, standalone=False, configuration=configuration)
        if compile_commands != expected_commands:
            raise Core0Error("actual compiler/link command closure differs")
        for map_file, allowed in ((("image.map", BOOT_OBJECTS),) if multi else (("image.map", BOOT_OBJECTS), ("user/image.map", USER_OBJECTS))):
            objects = set(re.findall(r"([^\s()]+\.o)(?=[:(\s])", (output_dir / map_file).read_text()))
            if objects != set(allowed):
                raise Core0Error(f"actual linked input map differs: {map_file}: {sorted(objects)}")
        units = {role: validate_unit(load_json(output_dir / role / "unit.json"), role, configuration=configuration) for role in roles}
        layout = validate_layout(load_json(output_dir / "layout.json"), configuration=configuration)
        expected_machine = validate_catalog(load_json(output_dir / "primitive-catalog.json"), configuration=configuration, stage=stage)
        if configuration in SILICON_CONFIGURATIONS:
            from silicon_profile import configuration_profile, validate_evidence
            validate_evidence(sha256(output_dir / "platform.dtb"), (output_dir / "platform.dts").read_text(), configuration_profile(configuration))
        else:
            validate_platform_evidence(sha256(output_dir / "platform.dtb"), (output_dir / "platform.dts").read_text())
        ir = {role: {kind: validate_ir((output_dir / role / filename).read_text(), unit, optimized=kind == "optimized", optimization=optimization)
                     for kind, filename in (("pre", "program.ll"), ("optimized", "program.opt.ll"))} for role, unit in units.items()}
        task_stack = validate_owned_task_stack(layout, units["kernel"], (output_dir / "kernel/program.ll").read_text())
        object_budget = validate_object_budget(units['kernel'], (output_dir/'kernel/program.ll').read_text())
        # Canonical notebooks use their own device/boot authority closure,
        # rather than the historical IPC-development graph. Every kernel unit
        # that reaches managed dispatch must still audit this local borrow.
        capability_header_borrow = (validate_capability_header_helpers(units['kernel'], (output_dir/'kernel/program.ll').read_text())
            if any(re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])=='Lemma.Kernel.Capability.managed'
                   for row in units['kernel']['functions']) else None)
        task_capture_borrow = (validate_task_capture_borrow(units['kernel'], (output_dir/'kernel/program.ll').read_text())
            if any(re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])=='Lemma.Kernel.Task.capture'
                   for row in units['kernel']['functions']) else None)
        surface_read_page_borrow = (validate_surface_read_page_borrow(units['kernel'], (output_dir/'kernel/program.ll').read_text())
            if any(re.sub(r'^_private\..*?\.[0-9]+\.','',row['source'])=='Lemma.Platform.LemmaSim.DeviceService.surface'
                   for row in units['kernel']['functions']) else None)
        managed_capabilities = (validate_managed_capability_graph(units["kernel"], (output_dir / "kernel/program.ll").read_text())
                                if configuration == "capabilities-development" else None)
        managed_ipc = (validate_ipc_graph(units["kernel"], (output_dir / "kernel/program.ll").read_text())
                       if configuration == "ipc-development" else None)
        managed_service = (validate_service_graph(units["kernel"], (output_dir / "kernel/program.ll").read_text())
                           if configuration in SERVICE_CONFIGURATIONS else None)
        object_functions = {
            "startup.o": expected_machine, "boot-package.o": set(),
            **({} if multi else {"user/startup.o": {row["symbol"] for row in user_primitive_rows(user_case)}}),
            **{role + "/program.o": set(ir[role]["optimized"]["definitions"]) for role in roles},
        }
        allowed_relocations = {"R_RISCV_BRANCH", "R_RISCV_JAL", "R_RISCV_PCREL_HI20", "R_RISCV_PCREL_LO12_I", "R_RISCV_PCREL_LO12_S",
                               "R_RISCV_CALL", "R_RISCV_CALL_PLT", "R_RISCV_64", "R_RISCV_32", "R_RISCV_ADD64", "R_RISCV_SUB64"}
        readonly_objects = []
        backend_objects = []
        architecture = (validate_architecture_diagnostics(units["kernel"], (output_dir / "kernel/program.ll").read_text())
                        if configuration in {*USER_INSTRUCTION_CONFIGURATIONS, *SERVICE_INSTRUCTION_CONFIGURATIONS} else None)
        user_abi_object, user_attack_object = None, None
        for object_file, expected_functions in object_functions.items():
            label = object_file.replace("/", "-")
            object_symbols = inspect("llvm-readelf", ["-s", "--wide", object_file], label + "-symbols")
            if defined_function_symbols(object_symbols) != expected_functions:
                raise Core0Error(f"object executable source closure differs: {object_file}")
            object_relocation_text = inspect("llvm-readelf", ["-r", object_file], label + "-relocations")
            relocs = relocation_types(object_relocation_text)
            if not relocs <= allowed_relocations:
                raise Core0Error(f"unknown/relaxed relocation in {object_file}: {sorted(relocs-allowed_relocations)}")
            object_section_text = inspect("llvm-readelf", ["-S", "--wide", object_file], label + "-sections")
            sections = alloc_section_names(object_section_text)
            if object_file == "user/startup.o" and (".text.user_adversarial" in sections) != (user_case != "none"):
                raise Core0Error("user attack case/object section presence differs")
            allowed_sections = ({".boot_package"} if object_file == "boot-package.o" else
                                {".text", ".text.firmware", ".text.platform"} if object_file == "startup.o" else
                                {".text", ".text.user_start", ".text.user_boundary", ".data.user_abi"} | ({".text.user_adversarial"} if user_case != "none" else set()) if object_file == "user/startup.o" else
                                {".text", ".rodata", ".rodata.cst8", ".data", ".bss"})
            if object_file == "user/startup.o":
                attack_bytes = b""
                if user_case != "none":
                    inspect("llvm-objcopy", ["-O", "binary", "--only-section=.text.user_adversarial", object_file,
                                            "audit-user-attack-object.bin"], "user-attack-object-extract")
                    attack_bytes = (output_dir / "audit-user-attack-object.bin").read_bytes()
                user_attack_object = validate_user_attack_object(object_section_text, object_symbols, attack_bytes,
                    (output_dir / "user-startup.S").read_text(), configuration=configuration, image_key=None,
                    unit=units["user"], relocation_text=object_relocation_text)
                if ".data.user_abi" not in sections:
                    raise Core0Error("user startup lacks its sole declared initialized-data section")
                inspect("llvm-objcopy", ["-O", "binary", "--only-section=.data.user_abi", object_file, "audit-user-abi-object.bin"], "user-abi-object-extract")
                user_abi_object = validate_user_abi_data(
                    (output_dir / ("audit-" + label + "-sections.txt")).read_text(),
                    (output_dir / "audit-user-abi-object.bin").read_bytes(), object_symbols,
                    (output_dir / "user-startup.S").read_text(), object_file=object_file)
            literal_tables = []
            tables = ir["kernel"]["optimized"]["readonly_optimizer_tables"] if object_file == "kernel/program.o" else []
            if object_file == "kernel/program.o" and bool(tables) != (".rodata.cst32" in sections):
                raise Core0Error("kernel PMP IR table/object constant section presence differs")
            if object_file == "kernel/program.o" and configuration in LEMMASIM_CONFIGURATIONS:
                from lemmasim_readonly import validate_object
                section_bytes={}
                for name in (".rodata", ".rodata.cst32"):
                    if name in sections:
                        filename="audit-kernel-" + name.removeprefix(".") + "-literals.bin"
                        inspect("llvm-objcopy", ["-O", "binary", "--only-section="+name, object_file, filename], "kernel-literal-"+name)
                        section_bytes[name]=(output_dir/filename).read_bytes()
                table_report=validate_object(object_section_text,object_symbols,object_relocation_text,
                    section_bytes,tables,object_file)
                readonly_objects.append(table_report)
                literal_tables=table_report["readonly_tables"]
                allowed_sections.add(".rodata.cst32")
            elif ".rodata.cst32" in sections:
                inspect("llvm-objcopy", ["-O", "binary", "--only-section=.rodata.cst32", object_file, "audit-kernel-pmp-table.bin"], "pmp-table-extract")
                if len(tables) > 1:
                    inspect("llvm-objcopy", ["-O", "binary", "--only-section=.rodata", object_file, "audit-kernel-h-rodata.bin"], "h-rodata-extract")
                    table_report = validate_h_readonly_sections(
                        (output_dir / ("audit-" + label + "-sections.txt")).read_text(), object_symbols,
                        (output_dir / ("audit-" + label + "-relocations.txt")).read_text(),
                        (output_dir / "audit-kernel-pmp-table.bin").read_bytes(),
                        (output_dir / "audit-kernel-h-rodata.bin").read_bytes(), object_file=object_file, tables=tables, configuration=configuration)
                else:
                    table_report = validate_pmp_constant_section(
                        (output_dir / ("audit-" + label + "-sections.txt")).read_text(),
                        (output_dir / "audit-kernel-pmp-table.bin").read_bytes(), object_file=object_file, tables=tables)
                    table_report["sha256"] = sha256(output_dir / "audit-kernel-pmp-table.bin")
                readonly_objects.append(table_report)
                literal_tables = table_report.get("readonly_tables", [])
                allowed_sections.add(".rodata.cst32")
            if object_file.endswith("/program.o"):
                object_role = object_file.split("/", 1)[0]
                backend_objects.append(inspect_backend_jump_tables(inspect, output_dir, object_file=object_file,
                                      section_text=object_section_text, symbol_text=object_symbols,
                                      relocation_text=object_relocation_text, unit=units[object_role],
                                      optimization=optimization, readonly_tables=literal_tables))
            if ".rodata.cst8" in sections:
                section_text = (output_dir / ("audit-" + label + "-sections.txt")).read_text()
                constant = re.search(r"(?m)^\s*\[\s*\d+\]\s+\.rodata\.cst8\s+PROGBITS\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)\s+08\s+AM\s+0\s+0\s+8\s*$", section_text)
                if not constant or int(constant[1], 16) == 0 or int(constant[1], 16) % 8:
                    raise Core0Error("integer constant pool has unexpected flags/entry size/alignment")
            # Clang may create an empty default .text section before selecting
            # the generated DATA-only package section. It must contain no bytes.
            if object_file == "boot-package.o" and ".text" in sections:
                section_text = (output_dir / ("audit-" + label + "-sections.txt")).read_text()
                match = re.search(r"\[\s*\d+\]\s+\.text\s+\S+\s+[0-9a-f]+\s+[0-9a-f]+\s+([0-9a-f]+)", section_text)
                if not match or int(match[1], 16) != 0:
                    raise Core0Error("boot package object has executable text bytes")
                sections.remove(".text")
            if not sections <= allowed_sections or object_file == "boot-package.o" and sections != {".boot_package"}:
                raise Core0Error(f"unaccounted allocated object section in {object_file}: {sorted(sections)}")
        intervals = {row["name"]: row for row in layout["intervals"]}
        capacities = {"machine": intervals["firmware-private"]["limit"] - intervals["firmware-private"]["base"],
                      "boot": intervals["supervisor-stack"]["limit"] - layout["context"]["boot_stack_floor"],
                      "kernel-trap": layout["task_kernel_stack_bytes"] - 32, "user": layout["user"]["stack_pages"] * layout["frame_bytes"]}
        if capacities != {"machine": 65536, "boot": 61440, "kernel-trap": 16352, "user": 16384 if configuration in LEMMASIM_CONFIGURATIONS else 8192}:
            raise Core0Error("authoritative stack capacities differ")
        startup = (output_dir / "startup.S").read_text()
        user_source = output_dir / (images[0]["directory"] + "/startup.S" if multi else "user-startup.S")
        user_startup = user_source.read_text()
        user_audits = {image["key"]: audit_user_image(root=root, output_dir=output_dir / image["directory"], catalog=catalog,
                                                   image_key=image["key"], optimization=optimization, timeout_seconds=timeout_seconds)
                       for image in images}
        for value in user_audits.values():
            logs.extend(value["commands"])
        for vector in ("lemma_machine_vector", "lemma_supervisor_vector"):
            if vector in expected_machine and machine_frame(startup, vector) != layout["context"]["bytes"]:
                raise Core0Error("typed vector stack allocation differs from the context layout")
        if machine_frame(user_startup, "_user_start") or machine_frame(user_startup, "lemma_exec_syscall"):
            raise Core0Error("user entry/syscall bridge consumes undeclared stack")
        stacks = {}
        for role, unit in units.items():
            object_file = role + "/program.o"
            frames = parse_stack_sizes(inspect("llvm-readelf", ["--stack-sizes", object_file], role + "-stack-sizes"))
            if set(frames) != object_functions[object_file]:
                raise Core0Error("stack metadata differs from the actual executable object closure")
            validate_compiled_stack(inspect("llvm-objdump", ["-d", "--no-show-raw-insn", object_file], role + "-stack-disassembly"), frames)
            primitive_source = user_startup if role == "user" else startup
            primitives = {row["primitive_symbol"]: machine_frame(primitive_source, row["primitive_symbol"])
                          for row in unit["used_execution_ops"] if row["primitive_symbol"] is not None}
            if unit["used_device_ops"] or configuration in LEMMASIM_CONFIGURATIONS and any(row["stable_id"].startswith("lemmasim.device-") for row in unit["used_execution_ops"]):
                primitives["core0_io_fence"] = machine_frame(primitive_source, "core0_io_fence")
            undefined = {line.split()[-1] for line in inspect("llvm-nm", ["--undefined-only", object_file], role + "-stack-undefined").splitlines() if line.split()}
            if not undefined <= set(primitives):
                raise Core0Error(f"object has an unaccounted external stack/runtime symbol: {sorted(undefined - set(primitives))}")
            post_ir = (output_dir / role / "program.opt.ll").read_text()
            _definitions, _declarations, called = parse_definitions_and_calls(post_ir)
            for intrinsic in called & optimizer_intrinsics(unit):
                primitives[intrinsic] = 0
            graph = weighted_stack_graph(post_ir, frames, primitives)
            graph.update(entries=validate_stack_entries(unit, graph, capacities=capacities, vector_bytes=288),
                         function_bytes=dict(sorted(frames.items())), object_undefined_symbols=sorted(undefined),
                         maximum_compiled_frame_bytes=max(frames.values()))
            if any(row['margin_bytes'] * 4 < row['capacity_bytes'] for row in graph['entries']):
                raise Core0Error('current compiled privileged stack has less than 25percent headroom')
            stacks[role] = graph
        inspections = {}
        specs = [("boot", "image.elf", expected_machine | {row["symbol"] for role in ("firmware", "kernel") for row in units[role]["functions"]}, False)]
        if not multi:
            specs.append(("user", "user/image.elf", {row["symbol"] for row in user_primitive_rows(user_case)} | set(ir["user"]["optimized"]["definitions"]), True))
        for name, image_file, expected, user in specs:
            info, symbol_text, raw_machine, ranges = inspect_linked_elf(inspect, name=name, image=image_file, expected=expected,
                                                                      layout=layout, user=user, assembly=user_startup, user_case=user_case,
                                                                      output_dir=output_dir, unit=units.get("user") if user else None)
            inspections[name] = info
            if not user:
                machine = (output_dir / "audit-boot-disassembly.txt").read_text()
                info["startup"] = validate_startup_case(machine, ranges, case)
                root_symbol = (load_json(output_dir / images[0]["directory"] / "unit.json")["roots"][0]["symbol"] if multi else units["user"]["roots"][0]["symbol"])
                info["context_abi"] = validate_context_abi(startup, raw_machine, ranges, user_startup, root_symbol, user_case)
            else:
                initialized = validate_user_abi_data(inspect("llvm-readelf", ["-S", "--wide", image_file], "user-sections"),
                                                     (output_dir / "user-data.bin").read_bytes(), symbol_text, user_startup, object_file=image_file)
                if user_abi_object is None or initialized["sha256"] != user_abi_object["sha256"]:
                    raise Core0Error("linked user initializer differs from its accounted startup object")
                info["initialized_data"] = initialized
                if user_case in INSTRUCTION_CASES:
                    info["object_quarantined_startup"] = user_attack_object
        if multi:
            inspections["users"] = {key: value["elf"] for key, value in user_audits.items()}
        package_contract = validate_package_contract(load_json(output_dir / "package-contract.json"), configuration=configuration, catalog=catalog)
        inspect("llvm-objcopy", ["-O", "binary", "--only-section=.boot_package", "image.elf", "audit-package.bin"], "package-extract")
        if multi:
            payloads = [((output_dir / image["directory"] / "text.bin").read_bytes(), (output_dir / image["directory"] / "data.bin").read_bytes()) for image in images]
            package_images = validate_package_payloads((output_dir / "audit-package.bin").read_bytes(), package_contract, payloads)
        else:
            payloads = [((output_dir / "user-text.bin").read_bytes(), (output_dir / "user-data.bin").read_bytes())]
            validate_package_payloads((output_dir / "audit-package.bin").read_bytes(), package_contract, payloads)
        record = {"schema_version": 2 if multi else 1, "status": "PASS", "artifact_category": category, "configuration": configuration, "startup_case": case, "user_startup_case": user_case,
                  "stage": stage, "optimization": optimization, "source_commit": provenance["source_commit"],
                  "dirty_paths": provenance["dirty_paths"], "image_sha256": sha256(output_dir / "image.elf"),
                  "lean_source_realization": realization,
                  "boot_package_sha256": sha256(output_dir / "audit-package.bin"),
                  "unit_ir": ir, "readonly_optimizer_object_sections": readonly_objects, "backend_readonly_objects": backend_objects, "elf": inspections, "commands": logs,
                  "stack_bounds": {"capacities": capacities, "roles": stacks, "dynamic_stack": False},
                  "task_kernel_stack": task_stack,
                  "object_budget": object_budget,
                  **({"capability_header_borrow":capability_header_borrow} if capability_header_borrow is not None else {}),
                  **({"task_capture_borrow":task_capture_borrow} if task_capture_borrow is not None else {}),
                  **({"surface_read_page_borrow":surface_read_page_borrow} if surface_read_page_borrow is not None else {}),
                  **({"architecture_diagnostics": architecture} if architecture is not None else {}),
                  "limitations": ["Artifact/source closure audit, not S/U execution or compiler-correctness proof.",
                                   ("bootstrap-m invokes maintained kernel code in M mode; separately linked user bytes are not yet a running task."
                                    if stage == "bootstrap-m" else "Supervisor artifact audit does not establish a running isolated user task.")]}
        if multi:
            record["user_images"] = {image["key"]: {"id": image["id"], "module": image["module"], "source": image["source"],
                                    **{key: user_audits[image["key"]][key] for key in ("image_sha256", "text_sha256", "data_sha256", "stack_bounds")},
                                    "text_bytes": (output_dir / image["directory"] / "text.bin").stat().st_size,
                                    "data_bytes": (output_dir / image["directory"] / "data.bin").stat().st_size,
                                    **managed_fields(configuration,image),
                                    **({"startup_case": image["startup_case"], "object_quarantined_startup": user_audits[image["key"]]["object_quarantined_startup"]}
                                       if configuration == "tasks-fault-development" or configuration in SERVICE_INSTRUCTION_CONFIGURATIONS else {})} for image in images}
            record["unit_ir"]["users"] = {key: value["unit_ir"] for key, value in user_audits.items()}
            record["stack_bounds"]["roles"]["users"] = {key: value["stack_bounds"] for key, value in user_audits.items()}
            record["package_images"] = package_images
            record["user_image_catalog_sha256"] = sha256(output_dir / "user-image-catalog.json")
            if configuration == "tasks-fault-development" or configuration in SERVICE_INSTRUCTION_CONFIGURATIONS:
                record["user_startup_cases"] = {image["key"]: image["startup_case"] for image in images}
            if configuration in MANAGED_POLICIES:
                record.update(managed_policy=MANAGED_POLICIES[configuration], boot_roles={image["key"]: image["boot_role"] for image in images})
                record.update({'managed_capabilities':managed_capabilities} if configuration=='capabilities-development' else
                              {'notebook_authority_observations':'NOT_ESTABLISHED_BY_ARTIFACT_AUDIT'} if configuration in LEMMASIM_CONFIGURATIONS else
                              {'managed_service':managed_service} if configuration in SERVICE_CONFIGURATIONS else {'managed_ipc':managed_ipc})
        else:
            record["user_image_sha256"] = sha256(output_dir / "user/image.elf")
        if source_inputs(root) != source_hashes:
            raise Core0Error("compiler/production source changed during artifact audit")
        write_json(result_path, record)
        return record
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        write_json(output_dir / "audit-failure.json", {"schema_version": 1, "status": "FAIL", "error": str(error), "commands": logs})
        raise


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--timeout", type=float, default=60)
    ns = parser.parse_args()
    root = repo_root()
    try:
        directory = (root / ns.output_dir).resolve()
        if (directory / "user-build.json").exists():
            if (directory / "build.json").exists():
                raise Core0Error("ambiguous boot/independent-user build category")
            record = audit_standalone_user(root=root, output_dir=directory, timeout_seconds=ns.timeout)
        else:
            record = audit(root=root, output_dir=directory, timeout_seconds=ns.timeout)
    except (Core0Error, OSError, ValueError, KeyError, TypeError) as error:
        print(f"KERNEL AUDIT FAIL: {error}", file=sys.stderr)
        return 1
    print(f"KERNEL AUDIT PASS: {record['stage']}, {record['optimization']}; source {record['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
