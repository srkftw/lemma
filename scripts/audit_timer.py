#!/usr/bin/env python3
"""Independent fail-closed checks for the Gate 8 machine-timer profile."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

import audit_device
import audit_memory
import audit_trap
from core0_common import Core0Error


CONTRACT_VERSION = "core0-v0.7"
ARTIFACT_CATEGORY = "test-timer-suite"
TEST_ABI = "lemma-timer-test-v1"
SOURCE_IDENTITY = "Lemma Gate 8 machine timer and interrupt conformance"
FOREGROUND_SOURCE = "Lemma.Examples.Foundation.Timer.foreground"
DISPATCH_SOURCE = "Lemma.Examples.Foundation.Timer.dispatch"
MUTATION_ENVIRONMENT = "LEMMA_TIMER_MUTATION"

TIMER_EXTERNALS = {
    "core0_timer_read_time",
    "core0_timer_set_compare",
    "core0_timer_read_pending",
    "core0_irq_save_disable",
    "core0_irq_restore",
    "core0_timer_set_interrupt",
    "core0_timer_probe",
}
TRAP_EXTERNALS = set(audit_trap.TRAP_EXTERNALS)
TIMER_STARTUP_FUNCTIONS = set(audit_trap.TRAP_STARTUP_FUNCTIONS) | TIMER_EXTERNALS

# These hashes bind every final linked instruction in each of the seven timer
# leaves (including the full asynchronous register probe), rather than trusting
# startup.S or checking only the memory/CSR subsequences.  The startup object is
# optimization-independent; the sole permitted alternate body is the declared
# disable-timer-arming test mutant.
TIMER_MACHINE_BODY_SHA256 = {
    "core0_irq_restore": "0d0c3e199cf7209c315be260164d60f2adad9fd292af48c34963f3327f5f9076",
    "core0_irq_save_disable": "81cd1fa8037c20efdc2cef7fd36a766ab69f7545f43fd7c1cc263a0692104c45",
    "core0_timer_probe": "407fc011546a4ddcced3cf3e0c9fd26c4b192e92b2af7f226653268da9703ebd",
    "core0_timer_read_pending": "93c428991f4d9b1013d72ec835989801b2620191d796b7d364faaece4f341bc2",
    "core0_timer_read_time": "e103c9cb31268a2fe7a1170b1f72dfb2efb062716d320aeac8416adcd7cdc382",
    "core0_timer_set_compare": "56104ada535d927c3c48e5c5994e8f1e36b6b96fdd6c9f9a08215ce14ccac12f",
    "core0_timer_set_interrupt": "828d70fc99140850c90fe9444a9a9770c73b09e081d651e8e612c64395d02e0f",
}
DISABLE_ARMING_MACHINE_BODY_SHA256 = (
    "9aea8f20d9852e9bd3be60fcbea49403feca9cf055ef6cd8e5284d8bc7eb2659"
)
TIMER_START_MACHINE_BODY_SHA256 = {
    # Pinned O0 and O2 differ only in resolved program/BSS PC-relative values.
    "O0": "9a46933e45b7e67131862fb81f3eae09a6f23d80570d98195ea21c3f9e7c1653",
    "O2": "c28069c5eb66e5c6bfaad03ecbbf3f740d447d345ad671cdc08751b2c36a9407",
}


TRAP_CONTRACT: dict[str, object] = {
    "schema_version": 1,
    "profile": "m-mode-timer-trap-v1",
    "privileged_spec": "RISC-V Privileged Architecture 20240411; Machine ISA 1.13",
    "privileged_spec_sha256":
        "538f3b17e1990ffabde30a6b96aaa2a0111afb63c174a6ef02b55a7aeb0e701d",
    "frame_bytes": 288,
    "call_alignment": 16,
    "outgoing_argument_bytes": 16,
    "integer_registers": 31,
    "hart_count": 1,
    "nested": False,
    "cpu_extensions_disabled": ["Smrnmi", "Smdbltrp"],
    "qemu_feature_normalization": {
        "source": "target/riscv/tcg/tcg-cpu.c",
        "sha256": "562e89fd688a921f9d48d718c60af73b51a7effaf5ec0577b67d0b177d99a7b9",
        "lines": "1630-1646",
    },
    "latch": "mscratch=trap-stack-top in foreground; zero during dispatch",
    "csr_snapshots": ["mstatus", "mepc", "mcause", "mtval", "mie"],
    "dispatcher_arguments": [
        "cause", "pc", "mstatus", "tval", "mie", "ecall-site", "ecall-resume",
        "breakpoint-site", "breakpoint-resume",
    ],
    "authorized_sync_sites": [
        {"cause": 11, "site": "__trap_ecall_site", "resume": "__trap_ecall_resume",
         "instruction_bytes": 4},
        {"cause": 3, "site": "__trap_breakpoint_site",
         "resume": "__trap_breakpoint_resume", "instruction_bytes": 4},
    ],
    "timer_interrupt": {
        "cause": "0x8000000000000007",
        "resume": "interrupted-pc-unchanged-after-compiled-policy",
        "entry_mstatus": "MPIE=1,MIE=0,MPRV=0,MPP=M",
        "entry_mie": "MTIE-only",
    },
    "fatal_status": 18,
    "double_fault_status": 19,
    "context_mismatch_status": 20,
    "missing_interrupt_status": 21,
    "invalid_deadline_status": 22,
    "premises": [
        "fixed aligned RAM frame/stack accesses do not fault",
        "single hart; no NMI; non-nested software latch",
        "timer return preserves the interrupted PC; synchronous return uses only approved sites",
        "compiled code uses neither gp nor tp; no relaxation; no floating/vector state",
    ],
}

TIMER_CONTRACT: dict[str, object] = {
    "schema_version": 1,
    "profile": "qemu-virt-machine-timer-v1",
    "qemu_version": "11.1.1",
    "qemu_revision": "c3d48b7d1e89604920e5b81b91140c2ad39a1943",
    "qemu_source_archive_sha256":
        "079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482",
    "hart_count": 1,
    "timebase_frequency_hz": 10000000,
    "mtime": {"address": "0x000000000200bff8", "width_bits": 64,
              "alignment": 8, "access": "read"},
    "mtimecmp": {"address": "0x0000000002004000", "width_bits": 64,
                 "alignment": 8, "access": "write",
                 "boot_value": "0xffffffffffffffff"},
    "interrupt": {"cause": 7, "class": "machine-timer", "mip_bit": 7,
                  "mie_bit": 7, "global_mstatus_bit": 3,
                  "controller": "CPU-local ACLINT MTIMER presented by the QEMU virt CLINT node; not PLIC"},
    "maximum_period": 1000000,
    "maximum_goal": 512,
    "deadline_domain": "0..0x7fffffffffffffff with checked nonwrapping addition",
    "event_ring": {"region": "events", "capacity": 16, "record_bytes": 32,
                   "fields": ["sequence", "time", "pc", "cause"],
                   "overflow": "counted-drop"},
    "synchronization":
        "single-hart global-MIE save/disable/restore critical sections with checked volatile RAM and full fences",
    "qemu_sources": [
        {"path": "hw/riscv/virt.c",
         "sha256": "ab1ef03005e1a94c25f6a8c7e1ddb7c44393802a7db13410c5c97603a1ea4920",
         "lines": "85-90,600-602,623-633,1384-1392"},
        {"path": "include/hw/intc/riscv_aclint.h",
         "sha256": "6bd7dac8694d4d8012f1036c00d6b1e9e746d3d7635fc0380d100026e01f7d39",
         "lines": "74-80"},
        {"path": "hw/intc/riscv_aclint.c",
         "sha256": "0b2ba0e01c110141df685e16b1ce98383646f95ec426c92b23ab3313a6cb1b89",
         "lines": "51-60,63-119,125-130,138-167,192-202,266-277,323-336,374-419"},
        {"path": "target/riscv/tcg/cpu_helper.c",
         "sha256": "172bd47c98c1ea9da48e95e3add0f3b3ac923a4e8a743ab3b785b098f90e4416",
         "lines": "351-372,553-590,2310-2347"},
        {"path": "target/riscv/tcg/csr.c",
         "sha256": "631294ef82387021c1a40d2125b636b4097a9350a2bc50d299ff38d5aa856360",
         "lines": "1814-1819,2292-2308,3776-3813"},
    ],
}

TIMER_ABI: dict[str, object] = {
    "schema_version": 1,
    "contract_version": CONTRACT_VERSION,
    "name": TEST_ABI,
    "byte_order": "little-endian",
    "ready": "LEMMA_DEVICE/1\nREADY\n",
    "runtime_fixture_address": "0x0000000081000000",
    "runtime_fixture_bytes": 32,
    "runtime_fields": ["seed:u64@0", "goal:u64@8", "period:u64@16", "scenario:u64@24"],
    "maximum_goal": 512,
    "maximum_period": 1000000,
    "response_bytes": 24,
    "response_magic": "LMS6",
    "response_version": 1,
    "fixed_stat_frames": 24,
    "stat_ids": list(range(0x8101, 0x8119)),
    "stat_fields": [
        "checksum", "completed-outer-quanta", "hardware-irq-count", "ring-head",
        "ring-tail", "ring-overflow", "skipped-periods", "spurious-entries",
        "maximum-catch-up-steps", "context-mask", "pending-witness",
        "shutdown-count-before", "shutdown-count-after", "guard-mask",
        "last-consumed-sequence", "last-consumed-time", "last-isr-time", "deadline",
        "real-read-time", "real-pending", "last-ring-sequence", "last-ring-time",
        "last-ring-pc", "last-ring-cause",
    ],
    "ring_dump": {"base_id": 0x8200, "maximum_records": 16,
                  "frames_per_record": 4, "maximum_frames": 64,
                  "fields": ["sequence", "time", "pc", "cause"],
                  "record_id": "0x8200 + slot*4 + field-index"},
    "maximum_total_frames": 88,
    "failure": {"id": 0x81FF, "context_status": 20,
                "context_value": "register/canary mask", "missing_interrupt_status": 21,
                "missing_interrupt_value": "observed hardware IRQ count"},
    "invalid_deadline_status": 22,
    "scenarios": {"0": "overflow", "1": "masked-pending", "2": "forced-catch-up",
                  "3": "shutdown", "4": "interleaved-ring"},
}


def _timer_op(
    stable_id: str,
    source: str,
    symbol: str,
    source_arguments: list[str],
    machine_arguments: list[str],
    result_meaning: str,
    state_operation: str,
    effects: list[str],
    *,
    mmio: dict[str, object] | None = None,
    canonical_bool: bool = False,
    requires_mie_disabled: bool = False,
) -> dict[str, object]:
    return {
        "stable_id": stable_id,
        "source_identity": source,
        "llvm_symbol": symbol,
        "source_arguments": source_arguments,
        "machine_arguments": machine_arguments,
        "result": "u64",
        "result_meaning": result_meaning,
        "state_operation": state_operation,
        "mmio": mmio,
        "canonical_bool_argument": canonical_bool,
        "requires_global_mie_disabled": requires_mie_disabled,
        "fence_before": True,
        "fence_after": True,
        "effects": effects,
    }


def _mmio(address: str, access: str) -> dict[str, object]:
    return {"address": address, "width_bits": 64, "alignment": 8,
            "access": access, "volatile": True, "fence_before": True,
            "fence_after": True}


TIMER_OPS = [
    _timer_op("timer.read-time", "Lemma.Core0.Memory.Action.timerReadTime",
              "core0_timer_read_time", [], [], "time", "read-mtime",
              ["mmio-read", "io-order", "machine-state", "timer-state"],
              mmio=_mmio("0x000000000200bff8", "read")),
    _timer_op("timer.set-compare", "Lemma.Core0.Memory.Action.timerSetCompare",
              "core0_timer_set_compare", ["u64"], ["u64"], "zero", "write-mtimecmp",
              ["mmio-write", "io-order", "machine-state", "timer-state"],
              mmio=_mmio("0x0000000002004000", "write")),
    _timer_op("timer.read-pending", "Lemma.Core0.Memory.Action.timerReadPending",
              "core0_timer_read_pending", [], [], "pending-bit", "read-mip-mtip",
              ["io-order", "machine-state", "timer-state", "interrupt-state"]),
    _timer_op("irq.save-disable", "Lemma.Core0.Memory.Action.irqSaveDisable",
              "core0_irq_save_disable", [], [], "previous-global-mie",
              "save-disable-mstatus-mie",
              ["io-order", "machine-state", "interrupt-state"]),
    _timer_op("irq.restore", "Lemma.Core0.Memory.Action.irqRestore",
              "core0_irq_restore", ["bool"], ["u64"], "zero",
              "restore-mstatus-mie-only",
              ["io-order", "machine-state", "interrupt-state"], canonical_bool=True),
    _timer_op("timer.set-interrupt", "Lemma.Core0.Memory.Action.timerSetInterrupt",
              "core0_timer_set_interrupt", ["bool"], ["u64"], "zero",
              "set-mie-mtie-only",
              ["io-order", "machine-state", "timer-state", "interrupt-state"],
              canonical_bool=True),
    _timer_op("timer.probe", "Lemma.Core0.Memory.Action.timerProbe",
              "core0_timer_probe", [], [], "probe-mask",
              "quarantined-real-interrupt-context-probe",
              ["io-order", "machine-state", "timer-state", "interrupt-state"],
              requires_mie_disabled=True),
]
# Reachability order is part of the frozen checked-source closure, independently
# of the declaration catalog's constructor order.
_TIMER_OP_BY_ID = {str(item["stable_id"]): item for item in TIMER_OPS}
TIMER_OPS = [
    _TIMER_OP_BY_ID[stable_id]
    for stable_id in (
        "timer.set-interrupt", "timer.set-compare", "timer.read-time",
        "irq.save-disable", "timer.probe", "irq.restore", "timer.read-pending",
    )
]

MACHINE_PRIMITIVES = [
    {"identity": "timer-startup", "effect": "machine-state/timer-state",
     "implementation": "Lemma.Machine.TimerPrimitives.startup"},
    {"identity": "trap-entry-return", "effect": "machine-state/interrupt-state",
     "implementation": "Lemma.Machine.TrapPrimitives.vector"},
    {"identity": "trap-register-probes", "effect": "sync-trap/context-check",
     "implementation": "Lemma.Machine.TrapPrimitives.ecallProbe/breakpointProbe"},
    {"identity": "trap-fatal-fixtures", "effect": "sync-trap",
     "implementation": "Lemma.Machine.TrapPrimitives.unexpectedEcall/illegalInstruction"},
    {"identity": "trap-fatal-finishers", "effect": "vm-termination-mmio",
     "implementation": "Lemma.Machine.TrapPrimitives.fatalDispatch/doubleFault"},
    {"identity": "timer-mmio", "effect": "ordered-64-bit-mmio",
     "implementation": "Lemma.Machine.TimerPrimitives.readTime/setCompare"},
    {"identity": "timer-csr", "effect": "interrupt-state",
     "implementation": "Lemma.Machine.TimerPrimitives.readPending/saveDisable/restore/setInterrupt"},
    {"identity": "timer-register-probe", "effect": "real-interrupt/context-check",
     "implementation": "Lemma.Machine.TimerPrimitives.probe"},
    {"identity": "io-fence", "effect": "ordered-mmio",
     "implementation": "Lemma.Machine.Primitives.ioFence"},
    {"identity": "status-test-harness", "effect": "action-abi/status-coded-vm-termination",
     "implementation": "Lemma.Machine.DeviceHarness.main"},
]


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise Core0Error(f"{context} is not an object")
    return value


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise Core0Error(f"{context} is not an array")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise Core0Error(
            f"{context} keys differ: missing={sorted(expected - set(value))!r}, "
            f"unexpected={sorted(set(value) - expected)!r}"
        )


def _hex64(value: object, context: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{16}", value) is None:
        raise Core0Error(f"{context} is not a canonical 64-bit hexadecimal identity")
    return value


def _body_calls(body: str, prefix: str) -> list[str]:
    return list(dict.fromkeys(re.findall(rf"\({re.escape(prefix)} ([A-Za-z0-9_.]+)", body)))


EFFECT_ORDER = (
    "checked-access", "fixed-ram-read", "fixed-ram-write", "mmio-read", "mmio-write",
    "io-order", "sync-trap", "machine-state", "timer-state", "interrupt-state",
)

SCALAR_FUNCTIONS = (
    ("Lemma.Core0.Memory.RegionId.input", (), "u8"),
    ("Lemma.Examples.Foundation.Device.Support.readyLength", (), "u32"),
    ("Lemma.Examples.Foundation.Device.Support.readyByte", ("u32",), "u8"),
    ("Lemma.Core0.Memory.Status.ok", (), "u8"),
    ("Lemma.Examples.Foundation.Device.Support.pollBudget", (), "u32"),
    ("Lemma.Core0.Memory.Status.iterationStop", (), "u8"),
    ("Lemma.Core0.Memory.Status.txTimeout", (), "u8"),
    ("Lemma.Core0.Device.UART.lsrErrorMask", (), "u8"),
    ("Lemma.Core0.Device.UART.lsrThrEmpty", (), "u8"),
    ("Lemma.Core0.Memory.Status.lineError", (), "u8"),
    ("Lemma.Core0.Memory.Status.invalidLength", (), "u8"),
    ("Lemma.Examples.Foundation.Timer.invalidDeadline", (), "u8"),
    ("Lemma.Core0.Memory.Status.malformedFrame", (), "u8"),
    ("Lemma.Examples.Foundation.Timer.maximumTime", (), "u64"),
    ("Lemma.Examples.Foundation.Timer.initialDeadline", ("u64", "u64"), "u64"),
    ("Lemma.Core0.Memory.RegionId.events", (), "u8"),
    ("Lemma.Examples.Foundation.Timer.witnessedPending", ("u8", "u64"), "bool"),
    ("Lemma.Examples.Foundation.Timer.missingEvent", (), "u8"),
    ("Lemma.Core0.Memory.Status.contextMismatch", (), "u8"),
    ("Lemma.Examples.Foundation.Timer.shutdownQuanta", ("u64",), "u32"),
    ("Lemma.Examples.Foundation.Timer.ringDrained", ("u64", "u64", "u64", "u64"), "bool"),
    ("Lemma.Examples.Foundation.Timer.validGuards", ("u64", "u64"), "bool"),
    ("Lemma.Examples.Foundation.Timer.ringCapacity", (), "u64"),
    ("Lemma.Examples.Foundation.Timer.validRing", ("u64", "u64"), "bool"),
    ("Lemma.Examples.Foundation.Timer.validPc", ("u64",), "bool"),
    ("Lemma.Examples.Foundation.Timer.timerCause", (), "u64"),
    ("Lemma.Examples.Foundation.Timer.validRecord", ("u64", "u64", "u64", "u64", "u64", "u64"), "bool"),
    ("Lemma.Examples.Foundation.Timer.retainedRecords", ("u64",), "u64"),
    ("Lemma.Core0.Device.UART.lsrTransmitterEmpty", (), "u8"),
    ("Lemma.Examples.Foundation.Device.Support.responseByte", ("u32", "u8", "u64", "u64"), "u8"),
    ("Lemma.Core0.Memory.RegionId.output", (), "u8"),
    ("Lemma.Examples.Foundation.Timer.workQuantum", (), "u32"),
    ("Lemma.Examples.Foundation.Trap.mix", ("u32", "u64"), "u64"),
    ("Lemma.Examples.Foundation.Timer.shouldConsume", ("u64", "u32"), "bool"),
    ("Lemma.Examples.Foundation.Timer.timerPolicy", ("u64", "u64", "u64", "u64", "u64"), "bool"),
    ("Lemma.Examples.Foundation.Timer.validInterruptEnable", ("u64",), "bool"),
    ("Lemma.Examples.Foundation.Timer.syncResume", ("u64",) * 9, "u64"),
    ("Lemma.Core0.Memory.Status.budgetExceeded", (), "u8"),
    ("Lemma.Core0.Memory.Status.unexpectedTrap", (), "u8"),
    ("Lemma.Examples.Foundation.Timer.validPeriodTime", ("u64", "u64"), "bool"),
)

ACTION_FUNCTIONS = (
    ("Lemma.Examples.Foundation.Device.Support.transmitPollStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Device.Support.sendByte", ("u8",)),
    ("Lemma.Examples.Foundation.Device.Support.readyStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Device.Support.sendReady", ()),
    ("Lemma.Examples.Foundation.Timer.writeWord", ("u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.clearStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.initializeState", ("u64",)),
    ("Lemma.Examples.Foundation.Timer.readWord", ("u64",)),
    ("Lemma.Examples.Foundation.Timer.checkGuards", ()),
    ("Lemma.Examples.Foundation.Timer.consumeOne", ()),
    ("Lemma.Examples.Foundation.Timer.drainStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.validateRing", ()),
    ("Lemma.Examples.Foundation.Device.Support.drainPollStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Device.Support.drain", ()),
    ("Lemma.Examples.Foundation.Device.Support.responseStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Device.Support.sendResponse", ("u8", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.dumpStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.statValue", ("u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.statStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.emitStats", ("u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.failure", ("u8", "u64")),
    ("Lemma.Examples.Foundation.Timer.mixStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.controlStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.finish", ("u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.restoreResult", ("u64", "u8", "u64")),
    ("Lemma.Examples.Foundation.Timer.consumeCritical", ()),
    ("Lemma.Examples.Foundation.Timer.workBody", ("u32", "u64")),
    ("Lemma.Examples.Foundation.Timer.workStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.runWork", ("u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.pendingStep", ("u32", "u32", "u64", "u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.pendingAndProbe", ("u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.arm", ("u64", "u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.selectScenario", ("u64", "u64", "u64", "u64")),
    (FOREGROUND_SOURCE, ()),
    ("Lemma.Examples.Foundation.Timer.increment", ("u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.enqueue", ("u64", "u64", "u64")),
    ("Lemma.Examples.Foundation.Timer.rearm", ("u64",)),
    ("Lemma.Examples.Foundation.Timer.interrupt", ("u64",)),
    ("Lemma.Examples.Foundation.Trap.fatalDiagnostic", ("u64", "u64", "u64", "u64", "u64")),
    (DISPATCH_SOURCE, ("u64",) * 9),
)

PRIMITIVE_CONTRACTS = (
    ("u8.eq", ("u8", "u8"), "bool", ("Eq",)),
    ("u32.eq", ("u32", "u32"), "bool", ("Eq",)),
    ("u64.add", ("u64", "u64"), "u64", ("UInt64.add",)),
    ("u8.to-u64.zext", ("u8",), "u64", ("UInt8.toUInt64",)),
    ("u64.to-u8.trunc", ("u64",), "u8", ("UInt64.toUInt8",)),
    ("u8.and", ("u8", "u8"), "u8", ("UInt8.land",)),
    ("u64.eq", ("u64", "u64"), "bool", ("Eq",)),
    ("u64.ult", ("u64", "u64"), "bool", ("UInt64.lt",)),
    ("u64.sub", ("u64", "u64"), "u64", ("UInt64.sub",)),
    ("u64.ule", ("u64", "u64"), "bool", ("UInt64.le",)),
    ("u32.to-u64.zext", ("u32",), "u64", ("UInt32.toUInt64",)),
    ("u64.mul", ("u64", "u64"), "u64", ("UInt64.mul",)),
    ("bool.eq", ("bool", "bool"), "bool", ("Eq",)),
    ("u64.to-u32.trunc", ("u64",), "u32", ("UInt64.toUInt32",)),
    ("u64.and", ("u64", "u64"), "u64", ("UInt64.land",)),
    ("u64.urem", ("u64", "u64"), "u64", ("UInt64.mod",)),
    ("u8.or", ("u8", "u8"), "u8", ("UInt8.lor",)),
    ("u64.lshr", ("u64", "u64"), "u64", ("UInt64.shiftRight",)),
    ("u64.xor", ("u64", "u64"), "u64", ("UInt64.xor",)),
    ("u64.shl", ("u64", "u64"), "u64", ("UInt64.shiftLeft",)),
    ("u32.mul", ("u32", "u32"), "u32", ("UInt32.mul",)),
    ("u32.add", ("u32", "u32"), "u32", ("UInt32.add",)),
    ("u32.and", ("u32", "u32"), "u32", ("UInt32.land",)),
    ("u64.udiv", ("u64", "u64"), "u64", ("UInt64.div",)),
)

ITERATIONS = (
    (21, "Lemma.Examples.Foundation.Device.Support.readyStep"),
    (1000000, "Lemma.Examples.Foundation.Device.Support.transmitPollStep"),
    (16, "Lemma.Examples.Foundation.Timer.clearStep"),
    (1024, "Lemma.Examples.Foundation.Timer.pendingStep"),
    (1000000, "Lemma.Examples.Foundation.Timer.workStep"),
    (1000000, "Lemma.Examples.Foundation.Timer.controlStep"),
    (512, "Lemma.Examples.Foundation.Timer.controlStep"),
    (16, "Lemma.Examples.Foundation.Timer.drainStep"),
    (64, "Lemma.Examples.Foundation.Timer.dumpStep"),
    (24, "Lemma.Examples.Foundation.Timer.statStep"),
    (1000000, "Lemma.Examples.Foundation.Device.Support.drainPollStep"),
    (24, "Lemma.Examples.Foundation.Device.Support.responseStep"),
    (128, "Lemma.Examples.Foundation.Timer.mixStep"),
)


def _body_direct_effects(body: str) -> list[str]:
    present = set(audit_trap._body_direct_effects(body))
    op_effects = {
        str(item["stable_id"]): set(str(effect) for effect in item["effects"])
        for item in TIMER_OPS
    }
    for stable_id in re.findall(r"\(action\.timer ([a-z0-9.-]+) ", body):
        if stable_id not in op_effects:
            raise Core0Error(f"timer Action body contains unknown operation {stable_id!r}")
        present.update(op_effects[stable_id])
    return [effect for effect in EFFECT_ORDER if effect in present]


INTERRUPT_SOURCE = "Lemma.Examples.Foundation.Timer.interrupt"
INTERRUPT_ACTION_CLOSURE = {
    INTERRUPT_SOURCE,
    "Lemma.Examples.Foundation.Timer.readWord",
    "Lemma.Examples.Foundation.Timer.writeWord",
    "Lemma.Examples.Foundation.Timer.enqueue",
    "Lemma.Examples.Foundation.Timer.increment",
    "Lemma.Examples.Foundation.Timer.rearm",
}


def _validate_timer_role_closure(
    dependency_graph: Mapping[str, set[str]]
) -> dict[str, object]:
    def reachable(root: str) -> set[str]:
        if root not in dependency_graph:
            raise Core0Error(f"timer role graph omits {root}")
        seen: set[str] = set()
        pending = [root]
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            if current not in dependency_graph:
                raise Core0Error(f"timer role graph references unknown Action {current}")
            seen.add(current)
            pending.extend(sorted(dependency_graph[current] - seen))
        return seen

    callers = {
        source for source, dependencies in dependency_graph.items()
        if INTERRUPT_SOURCE in dependencies
    }
    if callers != {DISPATCH_SOURCE}:
        raise Core0Error(
            "timer interrupt must have the dispatcher as its sole direct caller: "
            + repr(sorted(callers))
        )
    interrupt_closure = reachable(INTERRUPT_SOURCE)
    if interrupt_closure != INTERRUPT_ACTION_CLOSURE:
        raise Core0Error(
            "timer interrupt Action closure differs from the short deferred-work ISR: "
            + repr(sorted(interrupt_closure))
        )
    foreground_closure = reachable(FOREGROUND_SOURCE)
    if foreground_closure & {DISPATCH_SOURCE, INTERRUPT_SOURCE}:
        raise Core0Error("timer foreground can manually reach interrupt/dispatcher policy")
    dispatcher_closure = reachable(DISPATCH_SOURCE)
    if INTERRUPT_SOURCE not in dispatcher_closure:
        raise Core0Error("timer dispatcher does not reach the interrupt policy")
    return {
        "interrupt_direct_caller": DISPATCH_SOURCE,
        "interrupt_action_closure": sorted(interrupt_closure),
        "foreground_excludes_interrupt_policy": True,
    }


def _validate_function_closure(manifest: Mapping[str, object]) -> dict[str, object]:
    scalars = _list(manifest.get("scalar_functions"), "timer scalar functions")
    actions = _list(manifest.get("action_functions"), "timer Action functions")
    if len(scalars) != len(SCALAR_FUNCTIONS) or len(actions) != len(ACTION_FUNCTIONS):
        raise Core0Error("timer function closure has the wrong cardinality")
    scalar_sources: set[str] = set()
    for index, (raw, expected) in enumerate(zip(scalars, SCALAR_FUNCTIONS)):
        function = _mapping(raw, f"timer scalar function {index}")
        _exact_keys(function, {"source", "llvm", "signature", "dependencies", "body", "noinline"},
                    f"timer scalar function {index}")
        source, body = function.get("source"), function.get("body")
        if (not isinstance(source, str) or not source or source in scalar_sources
                or function.get("llvm") != f"core0_scalar_{index}"
                or function.get("noinline") is not True or not isinstance(body, str)):
            raise Core0Error("timer scalar source/LLVM/preservation closure differs")
        signature = _mapping(function.get("signature"), f"timer scalar signature {source}")
        args, result = signature.get("args"), signature.get("result")
        if (not isinstance(args, list) or any(arg not in {"bool", "u8", "u32", "u64"} for arg in args)
                or result not in {"bool", "u8", "u32", "u64"}):
            raise Core0Error(f"timer scalar signature is outside Core0 for {source}")
        expected_source, expected_args, expected_result = expected
        if (source != expected_source or args != list(expected_args)
                or result != expected_result):
            raise Core0Error(f"timer scalar source/signature closure differs at index {index}")
        scalar_sources.add(source)
    for raw in scalars:
        function = _mapping(raw, "timer scalar function")
        body = str(function["body"])
        dependencies = function.get("dependencies")
        if dependencies != _body_calls(body, "call") or any(
            dependency not in scalar_sources for dependency in _list(dependencies, "scalar dependencies")
        ):
            raise Core0Error(f"timer scalar dependency metadata is stale for {function['source']}")

    action_sources: set[str] = set()
    action_by_source: dict[str, Mapping[str, object]] = {}
    for index, (raw, expected) in enumerate(zip(actions, ACTION_FUNCTIONS)):
        function = _mapping(raw, f"timer Action function {index}")
        _exact_keys(function, {"source", "llvm", "signature", "scalar_dependencies",
                    "action_dependencies", "direct_effects", "transitive_effects", "body", "noinline"},
                    f"timer Action function {index}")
        source, body = function.get("source"), function.get("body")
        if (not isinstance(source, str) or not source or source in action_sources
                or function.get("llvm") != f"core0_action_{index}"
                or function.get("noinline") is not True
                or not isinstance(body, str) or not body.startswith("(action.")):
            raise Core0Error("timer Action source/LLVM/preservation closure differs")
        signature = _mapping(function.get("signature"), f"timer Action signature {source}")
        args = signature.get("args")
        if not isinstance(args, list) or any(arg not in {"bool", "u8", "u32", "u64"} for arg in args):
            raise Core0Error(f"timer Action signature is outside Core0 for {source}")
        expected_source, expected_args = expected
        if source != expected_source or args != list(expected_args):
            raise Core0Error(f"timer Action source/signature closure differs at index {index}")
        action_sources.add(source)
        action_by_source[source] = function
    for source, function in action_by_source.items():
        body = str(function["body"])
        action_dependencies = _list(function.get("action_dependencies"), "Action dependencies")
        body_action_dependencies = set(_body_calls(body, "action.call")) | set(
            re.findall(r"\bcallback=([A-Za-z0-9_.]+)", body)
        )
        if (len(action_dependencies) != len(set(action_dependencies))
                or set(action_dependencies) != body_action_dependencies
                or any(dependency not in action_sources for dependency in action_dependencies)):
            raise Core0Error(f"timer Action dependency metadata is stale for {source}")
        scalar_dependencies = _list(function.get("scalar_dependencies"), "Action scalar dependencies")
        if (len(scalar_dependencies) != len(set(scalar_dependencies))
                or set(scalar_dependencies) != set(_body_calls(body, "call"))
                or any(dependency not in scalar_sources for dependency in scalar_dependencies)):
            raise Core0Error(f"timer Action scalar dependency metadata is stale for {source}")
        for field in ("direct_effects", "transitive_effects"):
            effects = _list(function.get(field), f"{source} {field}")
            if len(effects) != len(set(effects)) or any(
                effect not in {
                    "checked-access", "fixed-ram-read", "fixed-ram-write", "mmio-read",
                    "mmio-write", "io-order", "sync-trap", "machine-state",
                    "timer-state", "interrupt-state",
                }
                for effect in effects
            ):
                raise Core0Error(f"timer Action {field} is outside the closed effect set")
        if function.get("direct_effects") != _body_direct_effects(body):
            raise Core0Error(f"timer Action direct effects are stale for {source}")
        transitive = _list(function.get("transitive_effects"), f"{source} transitive effects")
        computed = set(_list(function.get("direct_effects"), f"{source} direct effects"))
        for dependency in action_dependencies:
            computed.update(_list(
                action_by_source[dependency].get("transitive_effects"), "callee effects"
            ))
        if transitive != [effect for effect in EFFECT_ORDER if effect in computed]:
            raise Core0Error(f"timer Action transitive effects are stale for {source}")
    role_closure = _validate_timer_role_closure({
        source: set(_list(function.get("action_dependencies"), "Action dependencies"))
        for source, function in action_by_source.items()
    })
    return {
        "scalar_functions": len(scalars),
        "action_functions": len(actions),
        "foreground_symbol": str(action_by_source.get(FOREGROUND_SOURCE, {}).get("llvm", "")),
        "dispatcher_symbol": str(action_by_source.get(DISPATCH_SOURCE, {}).get("llvm", "")),
        "interrupt_role_closure": role_closure,
    }


def validate_timer_suite_manifest(value: object) -> dict[str, object]:
    manifest = _mapping(value, "timer-suite manifest")
    _exact_keys(
        manifest,
        set(audit_device.TOP_LEVEL_KEYS)
        | {"trap_contract", "timer_contract", "used_trap_ops", "used_timer_ops", "timer_mutation"},
        "timer-suite manifest",
    )
    for field, expected in (
        ("schema_version", 1), ("artifact_category", ARTIFACT_CATEGORY),
        ("contract_version", CONTRACT_VERSION), ("test_abi", TEST_ABI),
    ):
        if manifest.get(field) != expected:
            raise Core0Error(f"timer-suite manifest {field} differs")
    identities = {field: _hex64(manifest.get(field), f"timer-suite {field}")
                  for field in ("suite_id", "source_seed", "runtime_seed")}
    if identities != {"suite_id": "7d18a8491d0038c1", "source_seed": "4c454d4d41383038",
                     "runtime_seed": "52554e54494d4538"}:
        raise Core0Error("timer-suite fixed identities differ")
    if manifest.get("checked_result") != audit_device.CHECKED_RESULT:
        raise Core0Error("timer-suite checked-result ABI differs")
    audit_device._validate_memory_boundary(manifest.get("memory_contract"))
    audit_device.validate_device_contract(_mapping(manifest.get("device_contract"), "device contract"))
    if manifest.get("trap_contract") != TRAP_CONTRACT:
        raise Core0Error("timer trap contract differs from the closed v0.7 contract")
    if manifest.get("timer_contract") != TIMER_CONTRACT:
        raise Core0Error("machine-timer contract differs from its pinned QEMU contract")
    function_counts = _validate_function_closure(manifest)
    foreground_symbol = function_counts["foreground_symbol"]
    dispatcher_symbol = function_counts["dispatcher_symbol"]
    if not re.fullmatch(r"core0_action_[0-9]+", str(foreground_symbol)) or not re.fullmatch(
        r"core0_action_[0-9]+", str(dispatcher_symbol)
    ):
        raise Core0Error("timer checked roots are absent from the Action function closure")
    expected_roots = [
        {"root_id": 1, "source": FOREGROUND_SOURCE, "llvm": foreground_symbol,
         "signature": {"args": []}},
        {"root_id": 2, "source": DISPATCH_SOURCE, "llvm": dispatcher_symbol,
         "signature": {"args": ["u64"] * 9}},
    ]
    if manifest.get("roots") != expected_roots:
        raise Core0Error("timer-suite root closure differs")
    if manifest.get("used_timer_ops") != TIMER_OPS:
        raise Core0Error("timer operation identity/signature/effect closure differs")
    expected_memory = [
        audit_memory.MEMORY_OPS[stable_id]
        for stable_id in ("ram.read64", "ram.write64", "ram.write8")
    ]
    if manifest.get("used_memory_ops") != expected_memory:
        raise Core0Error("timer memory-operation closure differs")
    expected_device = [
        audit_device.DEVICE_OPS[stable_id]
        for stable_id in ("uart.enable-reset-fifo", "uart.write-byte", "uart.read-status")
    ]
    if manifest.get("used_device_ops") != expected_device:
        raise Core0Error("timer UART operation closure differs")
    expected_primitives = [
        {"stable_id": stable_id, "signature": {"args": list(args), "result": result},
         "lean_identities": list(identities), "effect": "pure"}
        for stable_id, args, result, identities in PRIMITIVE_CONTRACTS
    ]
    if manifest.get("used_primitives") != expected_primitives:
        raise Core0Error("timer scalar primitive identity/signature closure differs")
    observed_iterations: list[tuple[int, str]] = []
    for raw in _list(manifest.get("action_iterations"), "timer Action iterations"):
        iteration = _mapping(raw, "timer Action iteration")
        fixed = {
            "stable_id": "action.u64.bounded-fold",
            "source_identity": "Lemma.Core0.Memory.Action.boundedFoldU64",
            "maximum_budget": 1000000,
            "counter": {"type": "u32", "order": "ascending-zero-based"},
            "accumulator": "u64", "contexts": 4,
            "outcome": "checked-result-v1",
            "exhaustion": {"status": 9, "value": "initial", "callbacks": 0},
        }
        if any(iteration.get(field) != expected for field, expected in fixed.items()):
            raise Core0Error("timer bounded-iteration contract differs")
        budget, callback = iteration.get("static_budget"), iteration.get("callback")
        if isinstance(budget, bool) or not isinstance(budget, int) or not isinstance(callback, str):
            raise Core0Error("timer bounded-iteration selector is malformed")
        observed_iterations.append((budget, callback))
    if tuple(observed_iterations) != ITERATIONS:
        raise Core0Error("timer bounded-iteration site closure differs")
    trap_catalog = {
        stable_id: {"stable_id": stable_id, "llvm_symbol": symbol,
                    "source_identity": source, "effects": ["sync-trap", "machine-state"],
                    "arguments": [], "result": "u64-context-mask"}
        for stable_id, symbol, source in audit_trap.TRAP_OPS
    }
    used_traps = _list(manifest.get("used_trap_ops"), "used trap operations")
    if (len(used_traps) != len({str(_mapping(item, "used trap operation").get("stable_id")) for item in used_traps})
            or any(trap_catalog.get(str(_mapping(item, "used trap operation").get("stable_id"))) != item
                   for item in used_traps)):
        raise Core0Error("timer suite uses an unknown or duplicate synchronous-trap operation")
    if manifest.get("machine_primitives") != MACHINE_PRIMITIVES:
        raise Core0Error("timer machine-primitive closure differs")
    mutation = _mapping(manifest.get("timer_mutation"), "timer mutation")
    _exact_keys(mutation, {"identity", "production_selectable", "transform_stage",
                           "match_count", "expected_delta"}, "timer mutation")
    identity = mutation.get("identity")
    expected = {
        "none": ("none", 0, None),
        "restore-s3-from-s4": ("structured-machine-restore", 1,
            {"function": "core0_trap_vector", "before": "ld s3, 144(sp)",
             "after": "ld s3, 152(sp)"}),
        "disable-timer-arming": ("structured-machine-timer-arming", 1,
            {"function": "core0_timer_set_compare", "before": "sd a0, 0(t0)",
             "after": "sd t1, 0(t0)"}),
    }.get(identity)
    if expected is None or mutation != {
        "identity": identity, "production_selectable": False,
        "transform_stage": expected[0], "match_count": expected[1],
        "expected_delta": expected[2],
    }:
        raise Core0Error("timer mutation is outside the exact test-only quarantine")
    return dict(manifest)


def validate_timer_test_abi(value: object, manifest: Mapping[str, object]) -> dict[str, object]:
    abi = _mapping(value, "timer test ABI")
    if dict(abi) != TIMER_ABI:
        raise Core0Error("timer test ABI differs from lemma-timer-test-v1")
    if manifest.get("contract_version") != abi.get("contract_version") or manifest.get("test_abi") != abi.get("name"):
        raise Core0Error("timer test ABI does not match the suite manifest")
    return dict(abi)


def validate_timer_manifest_companions(
    manifest: Mapping[str, object], normalized: str, symbols: str
) -> None:
    if not normalized.endswith("\n") or normalized.splitlines()[0] != f"contract={CONTRACT_VERSION}":
        raise Core0Error("timer normalized companion has the wrong contract or boundary")
    lines = normalized.splitlines()
    roots = _list(manifest.get("roots"), "timer roots")
    expected_roots = [
        f"root={root['root_id']};source={root['source']};signature="
        + ('{"args":[]}' if index == 0 else '{"args":["u64","u64","u64","u64","u64","u64","u64","u64","u64"]}')
        for index, root in enumerate(roots)
    ]
    if [line for line in lines if line.startswith("root=")] != expected_roots:
        raise Core0Error("timer normalized root closure differs")
    symbol_lines: list[str] = []
    for kind in ("scalar_functions", "action_functions"):
        for raw in _list(manifest.get(kind), kind):
            function = _mapping(raw, kind)
            symbol_lines.append(f"source={function['source']};llvm={function['llvm']}")
            if kind == "scalar_functions":
                expected = f"scalar={function['source']};body={function['body']}"
            else:
                direct = "[" + ",".join(function["direct_effects"]) + "]"
                transitive = "[" + ",".join(function["transitive_effects"]) + "]"
                expected = (f"action={function['source']};direct={direct};"
                            f"transitive={transitive};body={function['body']}")
            if lines.count(expected) != 1:
                raise Core0Error(f"timer normalized body/effects drifted for {function['source']}")
    if symbols.splitlines() != symbol_lines:
        raise Core0Error("timer symbols companion differs from the source/LLVM closure")
    for prefix, field in (
        ("memory-op=", "used_memory_ops"), ("device-op=", "used_device_ops"),
        ("trap-op=", "used_trap_ops"), ("timer-op=", "used_timer_ops"),
    ):
        expected = Counter(prefix + str(_mapping(item, field)["stable_id"])
                           for item in _list(manifest.get(field), field))
        if Counter(line for line in lines if line.startswith(prefix)) != expected:
            raise Core0Error(f"timer normalized {prefix[:-1]} closure differs")


def validate_timer_export_configuration(
    value: object, manifest: Mapping[str, object], root: Path
) -> dict[str, object]:
    configuration = _mapping(value, "timer-suite exporter configuration")
    _exact_keys(configuration, {"driver", "generation_command", "environment"},
                "timer-suite exporter configuration")
    driver = "examples/foundation/TimerBuild.lean"
    expected_command = ["lake", "env", "lean", str((root / driver).resolve())]
    environment = _mapping(configuration.get("environment"), "timer-suite exporter environment")
    _exact_keys(environment, {MUTATION_ENVIRONMENT}, "timer-suite exporter environment")
    identity = _mapping(manifest.get("timer_mutation"), "timer mutation").get("identity")
    expected_value = {"none": "0", "restore-s3-from-s4": "1",
                      "disable-timer-arming": "2"}.get(identity)
    if (configuration.get("driver") != driver
            or configuration.get("generation_command") != expected_command
            or environment.get(MUTATION_ENVIRONMENT) != expected_value):
        raise Core0Error("timer exporter configuration is not bound to its mutation profile")
    return dict(configuration)


def _memory_proof_view(pre_ir: str) -> str:
    """Erase only independently audited later-gate leaves from Gate 5's IR view."""
    result: list[str] = []
    timer_symbols = "|".join(re.escape(name) for name in sorted(TIMER_EXTERNALS | TRAP_EXTERNALS))
    for line in pre_ir.splitlines():
        if "call void @core0_io_fence()" in line:
            result.append("")
            continue
        machine_call = re.match(
            rf"^(\s*)(%[A-Za-z0-9_.$-]+) = call i64 @(?:{timer_symbols})\(.*$", line
        )
        if machine_call is not None:
            result.append(f"{machine_call.group(1)}{machine_call.group(2)} = add i64 0, 0")
            continue
        scalar_call = re.match(
            r"^(\s*)(%[A-Za-z0-9_.$-]+) = call "
            r"(?:(?:zeroext|signext) )?i(1|8|32|64) @core0_scalar_[0-9]+\(.*$",
            line,
        )
        if scalar_call is not None:
            bits = scalar_call.group(3)
            result.append(
                f"{scalar_call.group(1)}{scalar_call.group(2)} = add i{bits} 0, 0"
            )
            continue
        if "inttoptr (i64 268435" in line:
            load = re.match(r"^(\s*)(%[A-Za-z0-9_.$-]+) = load volatile i8,", line)
            result.append(
                f"{load.group(1)}{load.group(2)} = add i8 0, 0" if load is not None else ""
            )
            continue
        result.append(line)
    return "\n".join(result) + "\n"


def _validate_timer_uart_ir(pre_ir: str, post_ir: str) -> dict[str, object]:
    expected = (
        "uart.lsr.read8", "uart.thr.write8", "uart.lsr.read8", "uart.fcr.enable-reset",
    )
    findings: dict[str, object] = {}
    for label, ir in (("pre", pre_ir), ("post", post_ir)):
        lines = ir.splitlines()
        functions = audit_device._line_functions(lines)
        operations: list[str] = []
        access_indices: set[int] = set()
        if label == "pre":
            for index, line in enumerate(lines):
                marker = audit_device.SITE_MARKER.fullmatch(line)
                if marker is None:
                    continue
                following = audit_device._nonblank_after(lines, index, 3)
                if len(following) != 3:
                    raise Core0Error("timer UART source site is truncated")
                (before_i, before), (access_i, access), (after_i, after) = following
                if (before_i, access_i, after_i) != (index + 1, index + 2, index + 3):
                    raise Core0Error("timer UART fence/access bracket is not contiguous")
                if (audit_device.FENCE_CALL.fullmatch(before) is None
                        or audit_device.FENCE_CALL.fullmatch(after) is None):
                    raise Core0Error("timer UART source site lacks immediate fences")
                operation = audit_device._access_op(access)
                if operation != marker.group(2) or functions[index] != functions[access_i]:
                    raise Core0Error("timer UART source marker differs from its physical access")
                operations.append(operation)
                access_indices.add(access_i)
            if "lemma.uart-site=" not in ir:
                raise Core0Error("timer pre-optimization IR lacks UART source markers")
        else:
            for index in audit_device._direct_physical_access_indices(lines):
                address = audit_device.DIRECT_ADDRESS.search(lines[index])
                if (address is None
                        or not audit_device.UART_BASE <= int(address.group(1))
                        < audit_device.UART_BASE + audit_device.UART_SPAN):
                    continue
                operation = audit_device._access_op(lines[index], optimized=True)
                if operation is None:
                    raise Core0Error("optimized timer UART access is not volatile i8 align 1")
                if (index == 0 or index + 1 >= len(lines)
                        or audit_device.FENCE_CALL.fullmatch(lines[index - 1]) is None
                        or audit_device.FENCE_CALL.fullmatch(lines[index + 1]) is None):
                    raise Core0Error("optimized timer UART access lacks immediate fences")
                operations.append(operation)
                access_indices.add(index)
            if "lemma.uart-site=" in ir:
                raise Core0Error("optimized timer IR retained source-only UART markers")
        if tuple(operations) != expected:
            raise Core0Error(f"{label} timer UART operation sequence differs")
        audit_device._validate_constant_pointers(lines, functions, access_indices)
        findings[label] = {
            "operations": operations,
            "accesses": len(operations),
            "functions": sorted({functions[index] for index in access_indices}),
        }
    return findings


def validate_timer_ir(
    manifest: Mapping[str, object], pre_ir: str, post_ir: str, optimization: str
) -> dict[str, object]:
    """Bind checked source timer sites to both LLVM stages and legacy RAM/UART audits."""
    memory = audit_memory.validate_memory_pre_ir(
        manifest, _memory_proof_view(pre_ir), require_volatile=True
    )
    uart = _validate_timer_uart_ir(pre_ir, post_ir)
    for address in (33603576, 33570816):
        if f"inttoptr (i64 {address}" in pre_ir or f"inttoptr (i64 {address}" in post_ir:
            raise Core0Error("compiled timer program contains direct machine-timer MMIO")
    parsed_pre = audit_memory.parse_ir_functions(pre_ir)
    parsed_post = audit_memory.parse_ir_functions(post_ir)
    if "llvm.umin.i64" in pre_ir:
        raise Core0Error("unoptimized timer IR unexpectedly contains llvm.umin.i64")
    retained_post = parsed_post.get("core0_scalar_27")
    if retained_post is None:
        raise Core0Error("timer IR omits the retained-record bound helper")
    expected_umin_calls = 1 if optimization == "O2" else 0
    umin_calls = len(re.findall(r"\bcall i64 @llvm\.umin\.i64\(", post_ir))
    retained_umin_calls = len(re.findall(
        r"\bcall i64 @llvm\.umin\.i64\(i64 %arg0, i64 16\)",
        retained_post.body,
    ))
    umin_declarations = len(re.findall(
        r"^declare i64 @llvm\.umin\.i64\(i64, i64\)", post_ir, re.MULTILINE
    ))
    if (
        umin_calls != expected_umin_calls
        or retained_umin_calls != expected_umin_calls
        or umin_declarations != expected_umin_calls
    ):
        raise Core0Error(
            "timer optimized minimum intrinsic differs from the exact retained-record bound"
        )
    symbol_by_stable = {
        str(item["stable_id"]): str(item["llvm_symbol"]) for item in TIMER_OPS
    }
    source_counts: Counter[str] = Counter()
    pre_counts: Counter[str] = Counter()
    post_counts: Counter[str] = Counter()
    for raw in _list(manifest.get("action_functions"), "timer Action functions"):
        function = _mapping(raw, "timer Action function")
        source, llvm, body = str(function["source"]), str(function["llvm"]), str(function["body"])
        pre_function, post_function = parsed_pre.get(llvm), parsed_post.get(llvm)
        if pre_function is None or post_function is None:
            raise Core0Error(f"timer pre/post optimization IR omits @{llvm}")
        for stable_id, symbol in symbol_by_stable.items():
            source_count = body.count(f"(action.timer {stable_id} ")
            pre_count = len(re.findall(rf"\bcall i64 @{re.escape(symbol)}\(", pre_function.body))
            post_count = len(re.findall(rf"\bcall i64 @{re.escape(symbol)}\(", post_function.body))
            if source_count != pre_count:
                raise Core0Error(
                    f"timer source/pre-lowering call count differs for {source}/{stable_id}"
                )
            # O2 legally tail-merges the two mutually exclusive set-compare
            # sites in rearm into one call fed by a phi.  Pin that sole closed
            # transformation rather than weakening post-IR call accounting.
            expected_post_count = (
                1
                if (
                    optimization == "O2"
                    and llvm == "core0_action_36"
                    and stable_id == "timer.set-compare"
                    and source_count == 2
                )
                else source_count
            )
            if post_count != expected_post_count:
                raise Core0Error(
                    f"timer post-lowering call count differs for {source}/{stable_id}: "
                    f"{post_count} != {expected_post_count}"
                )
            source_counts[stable_id] += source_count
            pre_counts[symbol] += pre_count
            post_counts[symbol] += post_count
    if set(source_counts) != set(symbol_by_stable) or any(count <= 0 for count in source_counts.values()):
        raise Core0Error(f"timer source operation site closure differs: {dict(source_counts)!r}")
    post_merge: dict[str, object] | None = None
    if optimization == "O2":
        rearm_post = parsed_post["core0_action_36"].body
        merge = re.findall(
            r"(%[A-Za-z0-9_.]+) = phi i64 "
            r"\[ (%[A-Za-z0-9_.]+), %action\.if\.then\.18 \], "
            r"\[ (%[A-Za-z0-9_.]+), %action\.if\.else\.10 \]\s+"
            r"%[A-Za-z0-9_.]+ = call i64 @core0_timer_set_compare\(i64 \1\)",
            rearm_post,
        )
        if len(merge) != 1:
            raise Core0Error(
                "optimized timer rearm does not retain the exact two-input set-compare tail merge"
            )
        post_merge = {
            "function": "core0_action_36",
            "source_sites": 2,
            "machine_calls": 1,
            "selector": "two-input phi from the mutually exclusive deadline branches",
        }
    declaration_contract = {
        "core0_timer_read_time": "declare i64 @core0_timer_read_time()",
        "core0_timer_set_compare": "declare i64 @core0_timer_set_compare(i64)",
        "core0_timer_read_pending": "declare i64 @core0_timer_read_pending()",
        "core0_irq_save_disable": "declare i64 @core0_irq_save_disable()",
        "core0_irq_restore": "declare i64 @core0_irq_restore(i64)",
        "core0_timer_set_interrupt": "declare i64 @core0_timer_set_interrupt(i64)",
        "core0_timer_probe": "declare i64 @core0_timer_probe()",
    }
    for label, ir in (("pre", pre_ir), ("post", post_ir)):
        for symbol, declaration in declaration_contract.items():
            if ir.count(declaration) != 1:
                raise Core0Error(f"{label} timer primitive declaration differs for @{symbol}")
    zext_results = re.findall(
        r"^\s*(%[A-Za-z0-9_.$-]+) = zext i1 (?:%[A-Za-z0-9_.$-]+|[01]) to i64$",
        pre_ir,
        re.MULTILINE,
    )
    bool_call_arguments = re.findall(
        r"\bcall i64 @core0_(?:irq_restore|timer_set_interrupt)\(i64 (%[A-Za-z0-9_.$-]+)\)",
        pre_ir,
    )
    if (len(bool_call_arguments) != 6 or Counter(bool_call_arguments) != Counter(zext_results)
            or re.search(r"sext i1 .* to i64", pre_ir)):
        raise Core0Error("timer Bool arguments are not exact canonical i1-to-i64 zero extensions")
    return {
        "optimization": optimization,
        "memory": memory,
        "uart": uart,
        "timer_calls": {
            "source": dict(sorted(source_counts.items())),
            "pre_optimization": dict(sorted(pre_counts.items())),
            "post_optimization": dict(sorted(post_counts.items())),
        },
        "post_optimization_tail_merge": post_merge,
        "optimizer_intrinsics": {
            "llvm.umin.i64": expected_umin_calls,
            "function": "core0_scalar_27" if expected_umin_calls else None,
            "upper_bound": 16 if expected_umin_calls else None,
        },
        "machine_timer_mmio_in_program": 0,
        "bool_machine_arguments": {
            "calls": len(bool_call_arguments),
            "lowering": "canonical i1-to-i64 zext",
        },
    }


def _asm_body(assembly: str, name: str) -> str:
    return audit_trap._asm_body(assembly, name)


def _asm_instructions(assembly: str, name: str) -> list[str]:
    return audit_trap._asm_instructions(_asm_body(assembly, name))


def _timer_probe_expected(layout: Mapping[str, object]) -> list[str]:
    registers = audit_trap.REGISTERS
    caller = (
        ("ra", 0), ("sp", 8), ("gp", 16), ("tp", 24), ("s0", 32),
        ("s1", 40), ("s2", 48), ("s3", 56), ("s4", 64), ("s5", 72),
        ("s6", 80), ("s7", 88), ("s8", 96), ("s9", 104),
        ("s10", 112), ("s11", 120),
    )
    probe_sp = int(str(layout.get("trap_probe_sp")), 0)
    sentinel = {
        register: (
            65536 if register == "t0"
            else probe_sp if register == "sp"
            else 0x3753000000000000 | (number << 16) | number
        )
        for number, register in enumerate(registers, 1)
    }
    instructions = ["la t0, __trap_probe_context"]
    instructions.extend(f"sd {register}, {offset}(t0)" for register, offset in caller)
    instructions.extend(f"li {register}, {sentinel[register]}" for register in registers)
    instructions.extend([
        "fence iorw, iorw", "csrsi mstatus, 8", "addi t0, t0, -1",
        "bnez t0, __timer_probe_loop", "csrci mstatus, 8", "fence iorw, iorw",
    ])
    instructions.extend(
        f"sd {register}, {(number - 1) * 8}(sp)"
        for number, register in enumerate(registers, 1)
    )
    instructions.append("li a0, 0")
    for number, register in enumerate(registers, 1):
        expected = 0 if register == "t0" else sentinel[register]
        instructions.extend([
            f"ld t0, {(number - 1) * 8}(sp)", f"li t1, {expected}",
            f"beq t0, t1, .Ltimer_probe_x{number}_ok", f"li t2, {1 << (number - 1)}",
            "or a0, a0, t2",
        ])
    for index, raw in enumerate(_list(layout.get("trap_canaries"), "trap canaries")):
        canary = _mapping(raw, "trap canary")
        address = int(str(canary["address"]), 0)
        for word in range(2):
            value = int(str(canary[f"word{word}"]), 0)
            instructions.extend([
                f"li t0, {address + word * 8}", "ld t1, 0(t0)", f"li t2, {value}",
                f"beq t1, t2, .Ltimer_probe_canary{index}_{word}_ok",
                f"li t2, {1 << (31 + index)}", "or a0, a0, t2",
            ])
    instructions.append("la t0, __trap_probe_context")
    instructions.extend(
        f"ld {register}, {offset}(t0)" for register, offset in caller if register != "sp"
    )
    instructions.extend(["ld sp, 8(t0)", "ret"])
    return instructions


_COMMON_TRAP_FUNCTION_ORDER = (
    "_start", "core0_io_fence", "core0_trap_vector",
    "core0_trap_fatal_dispatch", "core0_trap_double_fault",
    "core0_trap_ecall", "core0_trap_breakpoint",
    "core0_trap_unexpected_ecall", "core0_trap_illegal_instruction",
)


def _common_trap_assembly(assembly: str, dispatcher: str) -> str:
    start = _asm_instructions(assembly, "_start")
    parking = [
        "fence iorw, iorw", "li t0, 33570816", "li t1, 18446744073709551615",
        "sd t1, 0(t0)", "fence iorw, iorw",
    ]
    matches = [index for index in range(len(start) - len(parking) + 1)
               if start[index:index + len(parking)] == parking]
    if len(matches) != 1:
        raise Core0Error("timer startup compare-parking sequence is not uniquely removable")
    start_body = _asm_body(assembly, "_start")
    parking_text = "".join(f"  {instruction}\n" for instruction in parking)
    if start_body.count(parking_text) != 1:
        raise Core0Error("timer startup compare-parking source block is not contiguous")
    bodies = {name: _asm_body(assembly, name) for name in _COMMON_TRAP_FUNCTION_ORDER}
    bodies["_start"] = start_body.replace(parking_text, "", 1)
    bodies["core0_trap_vector"] = bodies["core0_trap_vector"].replace(
        dispatcher, audit_trap.DISPATCH_SYMBOL
    )
    lines = [".option push", ".option norelax", ".option norvc",
             '.section .text.start, "ax", @progbits']
    for name in _COMMON_TRAP_FUNCTION_ORDER:
        lines.extend([
            ".balign 4", f".globl {name}", f".type {name}, @function", f"{name}:",
            bodies[name].rstrip("\n"), f".size {name}, . - {name}",
        ])
    lines.extend([".option pop", '.section .note.GNU-stack, "", @progbits', ""])
    return "\n".join(lines)


def validate_timer_startup_assembly(
    assembly: str, manifest: Mapping[str, object], layout: Mapping[str, object]
) -> dict[str, object]:
    """Require the exact structured timer/trap source assembly, including mutations."""
    if (assembly.count(".option norelax") != 1 or assembly.count(".option norvc") != 1
            or ".note.GNU-stack" not in assembly):
        raise Core0Error("timer startup lacks no-relax/no-RVC/non-executable-stack policy")
    globals_seen = set(re.findall(r"^\.globl ([A-Za-z0-9_.$]+)$", assembly, re.MULTILINE))
    if globals_seen != TIMER_STARTUP_FUNCTIONS:
        raise Core0Error("timer startup global-function closure differs")
    mutation = _mapping(manifest.get("timer_mutation"), "timer mutation").get("identity")
    if mutation not in {"none", "restore-s3-from-s4", "disable-timer-arming"}:
        raise Core0Error("timer startup mutation identity is malformed")
    dispatcher = str(_list(manifest.get("roots"), "timer roots")[1]["llvm"])
    expected_vector = audit_trap._expected_trap_vector(
        "restore-s3-from-s4" if mutation == "restore-s3-from-s4" else "none"
    )
    expected_vector = [
        instruction.replace(audit_trap.DISPATCH_SYMBOL, dispatcher)
        for instruction in expected_vector
    ]
    vector = _asm_instructions(assembly, "core0_trap_vector")
    if vector != expected_vector:
        raise Core0Error("timer trap vector differs from the exact full-context/CSR/latch sequence")

    start = _asm_instructions(assembly, "_start")
    parking = [
        "fence iorw, iorw", "li t0, 33570816", "li t1, 18446744073709551615",
        "sd t1, 0(t0)", "fence iorw, iorw", "call core0_main",
    ]
    matches = [index for index in range(len(start) - len(parking) + 1)
               if start[index:index + len(parking)] == parking]
    if (len(matches) != 1
            or start[matches[0] + len(parking):]
            != ["wfi", "j .Ltrap_boot_halt"]):
        raise Core0Error("timer startup does not park mtimecmp exactly once immediately before entry")

    common_assembly = _common_trap_assembly(assembly, dispatcher)
    audit_trap.validate_trap_startup_assembly(
        common_assembly,
        {"restore_mutation": {
            "identity": "restore-s3-from-s4" if mutation == "restore-s3-from-s4" else "none"
        }},
        layout,
    )

    expected_leaves = {
        "core0_io_fence": ["fence iorw, iorw", "ret"],
        "core0_timer_read_time": ["fence iorw, iorw", "li t0, 33603576",
                                  "ld a0, 0(t0)", "fence iorw, iorw", "ret"],
        "core0_timer_set_compare": [
            "fence iorw, iorw", "li t0, 33570816", "li t1, 18446744073709551615",
            f"sd {'t1' if mutation == 'disable-timer-arming' else 'a0'}, 0(t0)",
            "fence iorw, iorw", "li a0, 0", "ret",
        ],
        "core0_timer_read_pending": ["fence iorw, iorw", "csrr a0, mip",
                                     "srli a0, a0, 7", "andi a0, a0, 1",
                                     "fence iorw, iorw", "ret"],
        "core0_irq_save_disable": ["fence iorw, iorw", "csrrci a0, mstatus, 8",
                                   "andi a0, a0, 8", "srli a0, a0, 3",
                                   "fence iorw, iorw", "ret"],
        "core0_irq_restore": ["fence iorw, iorw", "beqz a0, .Ltimer_restore_clear",
                              "csrsi mstatus, 8", "j .Ltimer_restore_done",
                              "csrci mstatus, 8", "fence iorw, iorw", "li a0, 0", "ret"],
        "core0_timer_set_interrupt": [
            "fence iorw, iorw", "li t0, 128", "beqz a0, .Ltimer_interrupt_clear",
            "csrs mie, t0", "j .Ltimer_interrupt_done", "csrc mie, t0",
            "fence iorw, iorw", "li a0, 0", "ret",
        ],
    }
    for name, expected in expected_leaves.items():
        if _asm_instructions(assembly, name) != expected:
            raise Core0Error(f"timer structured primitive {name} differs")
    probe = _asm_instructions(assembly, "core0_timer_probe")
    if probe != _timer_probe_expected(layout):
        raise Core0Error("timer asynchronous probe phase/register/canary sequence differs")
    audit_trap.validate_stackless_fatal_body(
        "core0_trap_fatal_dispatch", 18,
        _asm_instructions(assembly, "core0_trap_fatal_dispatch"),
    )
    audit_trap.validate_stackless_fatal_body(
        "core0_trap_double_fault", 19,
        _asm_instructions(assembly, "core0_trap_double_fault"),
    )
    return {
        "mutation": mutation,
        "startup_compare_parked": True,
        "timer_functions": 7,
        "timer_mmio_width_bits": 64,
        "timer_probe_iterations": 65536,
        "probe_registers": 31,
        "csr_roles": ["mstatus.MIE", "mie.MTIE", "mip.MTIP"],
        "synchronous_trap_substrate": "exact core0-v0.6 structured sequence",
    }


def _instruction_rows(disassembly: str) -> list[tuple[int, str, str]]:
    return [
        (int(address, 16), mnemonic, operands.strip())
        for address, mnemonic, operands in re.findall(
            r"^[ \t]*([0-9a-f]+):[ \t]+([a-z][a-z0-9.<>]*)[ \t]*([^\n]*?)[ \t]*$",
            disassembly,
            re.MULTILINE,
        )
    ]


def _function_rows(
    rows: Sequence[tuple[int, str, str]],
    symbol_addresses: Mapping[str, int],
    name: str,
    all_function_names: set[str],
    program_functions: set[str],
) -> list[tuple[int, str, str]]:
    start = symbol_addresses.get(name)
    if isinstance(start, bool) or not isinstance(start, int):
        raise Core0Error(f"timer machine function {name} is missing")
    later = [
        address for symbol, address in symbol_addresses.items()
        if address > start and (symbol in all_function_names or symbol in program_functions)
    ]
    stop = min(later) if later else start + 0x100000
    return [row for row in rows if start <= row[0] < stop]


def _integer(text: str) -> int:
    sign = -1 if text.startswith("-") else 1
    raw = text[1:] if sign < 0 else text
    return sign * int(raw, 0)


_MEMORY = re.compile(
    r"^(sd|ld)\s+([a-z][a-z0-9]*),\s*(-?(?:0x[0-9a-f]+|[0-9]+))\(([a-z][a-z0-9]*)\)$"
)


def _memory_sequence(instructions: Sequence[str]) -> list[tuple[str, str, int, str]]:
    result: list[tuple[str, str, int, str]] = []
    for instruction in instructions:
        match = _MEMORY.fullmatch(instruction)
        if match is not None:
            result.append((match.group(1), match.group(2), _integer(match.group(3)), match.group(4)))
    return result


def _machine_memory(rows: Sequence[tuple[int, str, str]]) -> list[tuple[str, str, int, str]]:
    return _memory_sequence([f"{mnemonic} {operands}" for _address, mnemonic, operands in rows])


def _canonical_privileged(instruction: str) -> str:
    compact = re.sub(r"\s+", "", instruction)
    return re.sub(
        r"(?<![A-Za-z_.])(?:0x[0-9a-f]+|[0-9]+)",
        lambda match: str(int(match.group(0), 0)),
        compact,
    )


def _is_privileged_mnemonic(mnemonic: str) -> bool:
    """Recognize the closed privileged/system namespace, including aliases."""
    return (
        mnemonic.startswith(("csr", "sfence", "hfence", "sinval", "hinval"))
        or mnemonic in {
            "ecall", "ebreak", "mret", "sret", "uret", "mnret", "dret", "wfi",
            "unimp",
        }
    )


def _validate_disassembly_inventory(
    disassembly: str, symbol_addresses: Mapping[str, int]
) -> None:
    """Reject unparsed machine rows and close the single illegal fixture site."""
    rows = re.findall(
        r"^[ \t]*([0-9a-f]+):[ \t]+(\S+)(?:[ \t]+(.*?))?[ \t]*$",
        disassembly,
        re.MULTILINE,
    )
    if not rows:
        raise Core0Error("timer disassembly contains no instruction rows")
    malformed = [
        (address, mnemonic, operands)
        for address, mnemonic, operands in rows
        if mnemonic != "<unknown>" and re.fullmatch(r"[a-z][a-z0-9.]*", mnemonic) is None
    ]
    if malformed:
        raise Core0Error(f"timer disassembly contains unparsed instruction rows: {malformed!r}")
    unknown = [int(address, 16) for address, mnemonic, _operands in rows if mnemonic == "<unknown>"]
    expected = symbol_addresses.get("__trap_illegal_instruction_site")
    if isinstance(expected, bool) or not isinstance(expected, int) or unknown != [expected]:
        raise Core0Error(
            "timer image must contain exactly one unknown instruction at the declared "
            f"illegal fixture site: {unknown!r}"
        )


def _compiled_program_bodies(
    disassembly: str,
    program_functions: set[str],
    symbol_addresses: Mapping[str, int],
) -> dict[str, str]:
    """Return address-bounded bodies, including rows after local-symbol headers."""
    header_counts = Counter(
        re.findall(r"^[0-9a-f]+ <([A-Za-z0-9_.$]+)>:$", disassembly, re.MULTILINE)
    )
    bad_headers = {
        name: header_counts[name]
        for name in sorted(program_functions)
        if header_counts[name] != 1
    }
    starts: list[tuple[int, str]] = []
    for name in sorted(program_functions):
        address = symbol_addresses.get(name)
        if isinstance(address, bool) or not isinstance(address, int):
            bad_headers[name] = 0
        else:
            starts.append((address, name))
    if bad_headers:
        raise Core0Error(
            "timer disassembly does not contain exactly one body for every compiled "
            f"function: {bad_headers!r}"
        )
    if len({address for address, _name in starts}) != len(starts):
        raise Core0Error("timer compiled functions do not have unique machine addresses")
    starts.sort()
    rows = _instruction_rows(disassembly)
    if not rows:
        raise Core0Error("timer disassembly contains no parsed machine instructions")
    result: dict[str, str] = {}
    image_stop = max(address for address, _mnemonic, _operands in rows) + 4
    for index, (start, name) in enumerate(starts):
        stop = starts[index + 1][0] if index + 1 < len(starts) else image_stop
        body_rows = [row for row in rows if start <= row[0] < stop]
        if not body_rows or body_rows[0][0] != start:
            raise Core0Error(f"timer compiled function {name} has an empty/unbounded body")
        result[name] = "".join(
            f"{address:x}: {mnemonic} {operands}".rstrip() + "\n"
            for address, mnemonic, operands in body_rows
        )
    return result


def _validate_compiled_program_bodies(
    disassembly: str,
    program_functions: set[str],
    symbol_addresses: Mapping[str, int],
) -> dict[str, str]:
    bodies = _compiled_program_bodies(disassembly, program_functions, symbol_addresses)
    audit_trap.validate_compiled_register_reservation(bodies)
    unexpected = sorted(
        (name, mnemonic, operands)
        for name, body in bodies.items()
        for mnemonic, operands in re.findall(
            r"^[ \t]*[0-9a-f]+:[ \t]+([a-z][a-z0-9.]*)[ \t]*(.*?)$",
            body,
            re.MULTILINE,
        )
        if _is_privileged_mnemonic(mnemonic)
    )
    if unexpected:
        raise Core0Error(
            "compiled timer program contains privileged/system instructions: "
            + repr(unexpected)
        )
    return bodies


def _machine_body_sha256(rows: Sequence[tuple[int, str, str]]) -> str:
    canonical = "".join(
        f"{mnemonic} {operands}".rstrip() + "\n"
        for _address, mnemonic, operands in rows
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_timer_machine_body_hashes(
    by_function: Mapping[str, Sequence[tuple[int, str, str]]], mutation: str
) -> dict[str, str]:
    expected = dict(TIMER_MACHINE_BODY_SHA256)
    if mutation == "disable-timer-arming":
        expected["core0_timer_set_compare"] = DISABLE_ARMING_MACHINE_BODY_SHA256
    elif mutation not in {"none", "restore-s3-from-s4"}:
        raise Core0Error(f"unknown timer machine mutation identity: {mutation}")
    observed = {
        name: _machine_body_sha256(by_function[name])
        for name in sorted(TIMER_EXTERNALS)
        if name in by_function
    }
    if set(observed) != TIMER_EXTERNALS or observed != expected:
        raise Core0Error(
            "timer final machine primitive bodies differ from the exact closed inventory: "
            + repr(observed)
        )
    return observed


def _validate_timer_mmio_machine_closure(
    by_function: Mapping[str, Sequence[tuple[int, str, str]]]
) -> dict[str, object]:
    """Infer every statically materialized CLINT access in the final image."""
    clint_start, clint_stop = 0x02000000, 0x02010000
    mask64 = (1 << 64) - 1
    memory = re.compile(
        r"^(lb|lbu|lh|lhu|lw|lwu|ld|sb|sh|sw|sd)\s+"
        r"([a-z][a-z0-9]*),\s*(-?(?:0x[0-9a-f]+|[0-9]+))"
        r"\(([a-z][a-z0-9]*)\)$"
    )
    caller_saved = {"ra", *(f"a{i}" for i in range(8)), *(f"t{i}" for i in range(7))}
    nonwriting = {
        "beq", "bne", "blt", "bge", "bltu", "bgeu", "beqz", "bnez",
        "blez", "bgez", "bltz", "bgtz", "j", "jr", "ret", "fence", "nop",
        "ecall", "ebreak", "mret", "wfi",
    }
    records: list[dict[str, object]] = []

    def in_clint(value: int) -> bool:
        return clint_start <= (value & mask64) < clint_stop

    for function, rows in sorted(
        by_function.items(), key=lambda item: item[1][0][0] if item[1] else -1
    ):
        known: dict[str, tuple[int, bool]] = {}
        compiled_function = (
            function == "core0_main"
            or function.startswith("core0_action_")
            or function.startswith("core0_scalar_")
        )

        def value(register: str) -> tuple[int, bool] | None:
            return (0, False) if register == "zero" else known.get(register)

        def assign(register: str, raw: int, derived: bool = False) -> None:
            if register != "zero":
                normalized = raw & mask64
                known[register] = (normalized, derived or in_clint(normalized))

        for address, mnemonic, operands in rows:
            instruction = f"{mnemonic} {operands}".rstrip()
            memory_match = memory.fullmatch(instruction)
            if memory_match is not None:
                operation, target, offset_text, base_register = memory_match.groups()
                base = value(base_register)
                if base is not None:
                    target_address = (base[0] + _integer(offset_text)) & mask64
                    if base[1] or in_clint(target_address):
                        if not in_clint(target_address):
                            raise Core0Error(
                                "timer MMIO pointer escapes the pinned CLINT aperture"
                            )
                        records.append({
                            "function": function,
                            "instruction": operation,
                            "address": f"0x{target_address:08x}",
                            "machine_address": f"0x{address:x}",
                            "width_bits": {
                                "lb": 8, "lbu": 8, "sb": 8,
                                "lh": 16, "lhu": 16, "sh": 16,
                                "lw": 32, "lwu": 32, "sw": 32,
                                "ld": 64, "sd": 64,
                            }[operation],
                        })
                stored = value(target) if operation.startswith("s") else None
                if (
                    stored is not None
                    and stored[1]
                    and (base is None or not base[1])
                ):
                    raise Core0Error(
                        "timer MMIO pointer escapes through an untracked machine store"
                    )
                if operation.startswith("l"):
                    known.pop(target, None)
                continue
            parts = [part.strip() for part in operands.split(",")] if operands else []
            if mnemonic in {"jal", "jalr", "call", "tail"}:
                if compiled_function and any(derived for _value, derived in known.values()):
                    raise Core0Error(
                        "compiled timer MMIO pointer is live across a machine call"
                    )
                for register in caller_saved:
                    known.pop(register, None)
                continue
            if (
                compiled_function
                and mnemonic in nonwriting
                and mnemonic not in {"fence", "nop"}
                and any(derived for _value, derived in known.values())
            ):
                raise Core0Error(
                    "compiled timer MMIO pointer is live across a control-flow boundary"
                )
            if mnemonic in nonwriting or not parts:
                continue
            destination = parts[0]
            if mnemonic in {"lui", "li"} and len(parts) == 2:
                immediate = _integer(parts[1])
                if mnemonic == "lui":
                    immediate = (immediate & ((1 << 20) - 1)) << 12
                    if immediate & (1 << 31):
                        immediate -= 1 << 32
                assign(destination, immediate)
                continue
            if mnemonic == "auipc" and len(parts) == 2:
                assign(destination, address + (_integer(parts[1]) << 12))
                continue
            if mnemonic == "mv" and len(parts) == 2:
                source = value(parts[1])
                if source is None:
                    known.pop(destination, None)
                else:
                    assign(destination, source[0], source[1])
                continue
            if mnemonic in {"addi", "addiw", "ori", "xori", "andi"} and len(parts) == 3:
                source = value(parts[1])
                if source is None:
                    known.pop(destination, None)
                else:
                    immediate = _integer(parts[2])
                    if mnemonic in {"addi", "addiw"}:
                        result = source[0] + immediate
                    elif mnemonic == "ori":
                        result = source[0] | immediate
                    elif mnemonic == "xori":
                        result = source[0] ^ immediate
                    else:
                        result = source[0] & immediate
                    if mnemonic == "addiw":
                        result &= 0xFFFFFFFF
                        if result & (1 << 31):
                            result -= 1 << 32
                    assign(destination, result, source[1])
                continue
            if mnemonic in {"slli", "srli"} and len(parts) == 3:
                source = value(parts[1])
                if source is None:
                    known.pop(destination, None)
                else:
                    amount = _integer(parts[2])
                    result = source[0] << amount if mnemonic == "slli" else source[0] >> amount
                    assign(destination, result, source[1])
                continue
            if mnemonic in {"add", "sub", "or", "xor", "and"} and len(parts) == 3:
                left, right = value(parts[1]), value(parts[2])
                if left is not None and right is not None:
                    if mnemonic == "add":
                        result = left[0] + right[0]
                    elif mnemonic == "sub":
                        result = left[0] - right[0]
                    elif mnemonic == "or":
                        result = left[0] | right[0]
                    elif mnemonic == "xor":
                        result = left[0] ^ right[0]
                    else:
                        result = left[0] & right[0]
                    assign(destination, result, left[1] or right[1])
                    continue
            if any(value(register) is not None and value(register)[1] for register in parts[1:]):
                raise Core0Error(
                    f"timer MMIO pointer has unsupported machine transform `{instruction}`"
                )
            known.pop(destination, None)

    observed = sorted(
        (str(record["function"]), str(record["instruction"]), str(record["address"]))
        for record in records
    )
    expected = sorted((
        ("_start", "sd", "0x02004000"),
        ("core0_timer_read_time", "ld", "0x0200bff8"),
        ("core0_timer_set_compare", "sd", "0x02004000"),
    ))
    if observed != expected or any(record["width_bits"] != 64 for record in records):
        raise Core0Error(
            "final timer MMIO access inventory differs from the exact three 64-bit sites: "
            + repr(observed)
        )
    return {
        "access_count": 3,
        "width_bits": 64,
        "compiled_program_accesses": 0,
        "all_inferred_accesses_are_approved": True,
        "scope": "bounded per-function straight-line constant/alias inference; not a CFG proof",
        "accesses": records,
    }


def validate_timer_machine_disassembly(
    disassembly: str,
    symbol_addresses: Mapping[str, int],
    program_functions: set[str],
    startup_assembly: str,
    manifest: Mapping[str, object],
    optimization: str,
    *,
    expected_start_body_sha256: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Bind critical startup.S memory/CSR phases to the final linked RV64 image."""
    dispatcher = str(_list(manifest.get("roots"), "timer roots")[1]["llvm"])
    mutation = str(_mapping(manifest.get("timer_mutation"), "timer mutation")["identity"])
    _validate_disassembly_inventory(disassembly, symbol_addresses)
    compiled_bodies = _validate_compiled_program_bodies(
        disassembly, program_functions, symbol_addresses
    )
    # Validate original names and bodies before the compatibility projection
    # used by the Gate 7 common trap checker.  In particular, Timer.failure is
    # core0_action_20 while the Timer dispatcher is core0_action_39, so blindly
    # renaming the latter to Gate 7's action_20 would otherwise hide one body.
    common_assembly = _common_trap_assembly(startup_assembly, dispatcher)
    collision_alias = "core0_timer_gate7_original_action_20"
    if (
        collision_alias in disassembly
        or collision_alias in symbol_addresses
        or collision_alias in program_functions
        or audit_trap.DISPATCH_SYMBOL not in program_functions
        or dispatcher not in program_functions
    ):
        raise Core0Error("timer compatibility symbol projection is not collision-free")
    symbol_token = r"(?<![A-Za-z0-9_.$]){}(?![A-Za-z0-9_.$])"
    compatibility_disassembly = re.sub(
        symbol_token.format(re.escape(audit_trap.DISPATCH_SYMBOL)),
        collision_alias,
        disassembly,
    )
    compatibility_disassembly = re.sub(
        symbol_token.format(re.escape(dispatcher)),
        audit_trap.DISPATCH_SYMBOL,
        compatibility_disassembly,
    )
    compatibility_symbols = dict(symbol_addresses)
    original_collision_address = compatibility_symbols.pop(audit_trap.DISPATCH_SYMBOL)
    compatibility_symbols[collision_alias] = original_collision_address
    compatibility_symbols[audit_trap.DISPATCH_SYMBOL] = compatibility_symbols.pop(dispatcher)
    compatibility_program = set(program_functions)
    compatibility_program.remove(audit_trap.DISPATCH_SYMBOL)
    compatibility_program.remove(dispatcher)
    compatibility_program.add(collision_alias)
    compatibility_program.add(audit_trap.DISPATCH_SYMBOL)
    # Bound the last common primitive before the seven timer functions without
    # hiding those functions from the timer-specific audit below.
    boundary = "core0_main"
    if boundary not in compatibility_program:
        raise Core0Error("timer compiled program lacks the machine harness boundary")
    compatibility_symbols[boundary] = symbol_addresses["core0_timer_read_time"]
    common = audit_trap.validate_trap_machine_disassembly(
        compatibility_disassembly,
        compatibility_symbols,
        compatibility_program,
        common_assembly,
    )

    rows = _instruction_rows(disassembly)
    by_function = {
        name: _function_rows(
            rows, symbol_addresses, name, TIMER_STARTUP_FUNCTIONS, program_functions
        )
        for name in TIMER_STARTUP_FUNCTIONS
    }
    if any(not rows_for_function for rows_for_function in by_function.values()):
        raise Core0Error("timer machine function inventory contains an empty body")
    all_machine_functions = TIMER_STARTUP_FUNCTIONS | program_functions
    all_by_function = {
        name: _function_rows(
            rows, symbol_addresses, name, all_machine_functions, program_functions
        )
        for name in all_machine_functions
    }
    if any(not function_rows for function_rows in all_by_function.values()):
        raise Core0Error("timer final machine function closure contains an empty body")
    timer_mmio_machine = _validate_timer_mmio_machine_closure(all_by_function)
    observed_body_hashes = _validate_timer_machine_body_hashes(by_function, mutation)
    start_body_sha256 = _machine_body_sha256(by_function["_start"])
    start_hashes = (
        TIMER_START_MACHINE_BODY_SHA256
        if expected_start_body_sha256 is None
        else expected_start_body_sha256
    )
    if (
        optimization not in start_hashes
        or start_body_sha256 != start_hashes[optimization]
    ):
        raise Core0Error(
            f"timer _start final machine body differs from the exact {optimization} inventory"
        )
    slot_counts: dict[str, int] = {}
    for name in sorted(TIMER_STARTUP_FUNCTIONS):
        expected_memory = _memory_sequence(_asm_instructions(startup_assembly, name))
        observed_memory = _machine_memory(by_function[name])
        if observed_memory != expected_memory:
            raise Core0Error(f"{name} machine memory-access slots/order differ from startup.S")
        slot_counts[name] = len(observed_memory)

    csr_counts: dict[str, int] = {}
    for name in sorted(TIMER_STARTUP_FUNCTIONS):
        expected = [
            _canonical_privileged(instruction)
            for instruction in _asm_instructions(startup_assembly, name)
            if _is_privileged_mnemonic(instruction.split(None, 1)[0])
        ]
        observed = [
            _canonical_privileged(f"{mnemonic} {operands}".rstrip())
            for _address, mnemonic, operands in by_function[name]
            if _is_privileged_mnemonic(mnemonic)
        ]
        if expected != observed:
            raise Core0Error(f"{name} machine privileged/CSR sequence differs from startup.S")
        csr_counts[name] = len(observed)

    def instruction_pairs(name: str) -> list[tuple[str, str]]:
        return [(mnemonic, operands) for _address, mnemonic, operands in by_function[name]]

    read_time = instruction_pairs("core0_timer_read_time")
    if read_time != [
        ("fence", ""), ("lui", "t0, 0x200c"), ("addiw", "t0, t0, -0x8"),
        ("ld", "a0, 0x0(t0)"), ("fence", ""), ("ret", ""),
    ]:
        raise Core0Error("timer read machine body/address/width/fence sequence differs")
    set_compare = instruction_pairs("core0_timer_set_compare")
    expected_store = "t1, 0x0(t0)" if mutation == "disable-timer-arming" else "a0, 0x0(t0)"
    if set_compare != [
        ("fence", ""), ("lui", "t0, 0x2004"), ("li", "t1, -0x1"),
        ("sd", expected_store), ("fence", ""), ("li", "a0, 0x0"), ("ret", ""),
    ]:
        raise Core0Error("timer compare machine body/address/width/fence sequence differs")

    probe_rows = by_function["core0_timer_probe"]
    loop = symbol_addresses.get("__timer_probe_loop")
    snapshot = symbol_addresses.get("__timer_probe_snapshot")
    probe_memory_rows = [row for row in probe_rows if _MEMORY.fullmatch(f"{row[1]} {row[2]}")]
    if (not isinstance(loop, int) or not isinstance(snapshot, int)
            or len(probe_memory_rows) != slot_counts["core0_timer_probe"]
            or len(probe_memory_rows) < 47
            or any(row[0] >= loop for row in probe_memory_rows[:16])
            or probe_memory_rows[16][0] != snapshot
            or any(row[0] < snapshot for row in probe_memory_rows[16:])):
        raise Core0Error("timer probe machine save/enable/loop/disable/snapshot phase order differs")
    probe_privileged = [
        (address, mnemonic, operands)
        for address, mnemonic, operands in probe_rows
        if _is_privileged_mnemonic(mnemonic)
    ]
    if ([mnemonic for _address, mnemonic, _operands in probe_privileged]
            != ["csrsi", "csrci"]
            or not probe_privileged[0][0] < loop < probe_privileged[1][0] < snapshot):
        raise Core0Error("timer probe enables MIE outside its bounded interrupt window")
    loop_rows = [row for row in probe_rows if loop <= row[0] < snapshot]
    if [(mnemonic, operands) for _address, mnemonic, operands in loop_rows] != [
        ("addi", "t0, t0, -0x1"),
        ("bnez", f"t0, 0x{loop:x} <__timer_probe_loop>"),
        ("csrci", "mstatus, 0x8"),
        ("fence", ""),
    ]:
        raise Core0Error("timer probe machine wait loop is not the exact bounded counter loop")

    fence_counts = {
        name: sum(mnemonic == "fence" for _address, mnemonic, _operands in function_rows)
        for name, function_rows in by_function.items()
    }
    expected_timer_fences = {
        "core0_timer_read_time": 2, "core0_timer_set_compare": 2,
        "core0_timer_read_pending": 2, "core0_irq_save_disable": 2,
        "core0_irq_restore": 2, "core0_timer_set_interrupt": 2,
        "core0_timer_probe": 2,
    }
    if any(fence_counts.get(name) != count for name, count in expected_timer_fences.items()):
        raise Core0Error("timer machine primitive fence inventory differs")
    return {
        **common,
        "compiled_functions": len(program_functions - {"core0_main"}),
        "compiled_privileged_instructions": 0,
        "mutation": mutation,
        "startup_functions": len(TIMER_STARTUP_FUNCTIONS),
        "timer_functions": 7,
        "timer_mmio_accesses": timer_mmio_machine["access_count"],
        "timer_mmio_width_bits": timer_mmio_machine["width_bits"],
        "timer_mmio_machine": timer_mmio_machine,
        "timer_fence_operations": sum(expected_timer_fences.values()),
        "timer_machine_body_sha256": observed_body_hashes,
        "timer_start_machine_body_sha256": start_body_sha256,
        "machine_slot_sequences": dict(sorted(slot_counts.items())),
        "machine_csr_by_function": {
            name: count for name, count in sorted(csr_counts.items()) if count
        },
        "machine_csr_operations": sum(csr_counts.values()),
        "timer_probe": {
            "iterations": 65536,
            "caller_saves": 16,
            "snapshot_registers": 31,
            "memory_slots": slot_counts["core0_timer_probe"],
            "mie_window": "after sentinels, bounded counter only, before snapshots",
        },
    }
