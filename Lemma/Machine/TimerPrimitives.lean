import Lemma.Machine.TrapPrimitives

/-!
Closed RV64 machine-timer and interrupt-control primitives. Addresses are the
aligned 64-bit MTIME/MTIMECMP registers of the pinned one-hart QEMU virt CLINT.
All timer/interrupt boundary operations use full `fence iorw, iorw`. They do not
implement a deadline policy, ISR, event queue, or source-level foreground work.

The bounded, non-reentrant asynchronous sentinel probe requires global MIE off,
MTIE on, and a compare already armed/due. It enables MIE only after initializing
all integer sentinels and disables it before snapshotting. A missing interrupt
still terminates normally; compiled source, not this primitive, must require an
observed hardware event. The trap substrate retains its fixed-RAM/no-NMI and
single-hart/non-nesting premises.
-/

namespace Lemma.Machine.TimerPrimitives

open Lemma.Machine.Primitives
open Lemma.Machine (trapLayout)

inductive Mutation where
  | none
  | restoreS3FromS4
  | disableArming
  deriving Repr, BEq, Inhabited

def Mutation.stableId : Mutation → String
  | .none => "none"
  | .restoreS3FromS4 => "restore-s3-from-s4"
  | .disableArming => "disable-timer-arming"

structure Configuration where
  dispatcher : String
  mutation : Mutation := .none
  deriving Repr, BEq

def mtimeAddress : Nat := 0x0200bff8
def mtimecmpAddress : Nat := 0x02004000
def parkedCompare : Nat := 0xffffffffffffffff
def probeIterations : Nat := 65536

private def ins (instruction : Instruction) : Line := .instruction instruction
private def label (name : String) : Line := .label name
private def asOffset (value : Nat) : Int := Int.ofNat value

/-- Insert typed timer parking instructions, not assembly-text replacement. -/
def startup : Array Line := TrapPrimitives.startup.flatMap fun line =>
  if line == ins (.call "core0_main") then #[
    ins .fenceIO,
    ins (.loadImmediate .t0 mtimecmpAddress),
    ins (.loadImmediate .t1 parkedCompare),
    ins (.storeDouble .t1 .t0 0),
    ins .fenceIO,
    line
  ] else #[line]

def readTime : Array Line := #[
  label "core0_timer_read_time",
  ins .fenceIO,
  ins (.loadImmediate .t0 mtimeAddress),
  ins (.loadDouble .a0 .t0 0),
  ins .fenceIO,
  ins .return
]

/-- The test-only arming mutation changes exactly the store's source register. -/
def setCompare (mutation : Mutation) : Array Line := #[
  label "core0_timer_set_compare",
  ins .fenceIO,
  ins (.loadImmediate .t0 mtimecmpAddress),
  ins (.loadImmediate .t1 parkedCompare),
  ins (.storeDouble (if mutation == .disableArming then .t1 else .a0) .t0 0),
  ins .fenceIO,
  ins (.loadImmediate .a0 0),
  ins .return
]

def readPending : Array Line := #[
  label "core0_timer_read_pending",
  ins .fenceIO,
  ins (.csrRead .a0 .mip),
  ins (.shiftRightImmediate .a0 .a0 7),
  ins (.andImmediate .a0 .a0 1),
  ins .fenceIO,
  ins .return
]

/-- Atomically capture and clear only mstatus.MIE; return its old canonical bit. -/
def saveDisable : Array Line := #[
  label "core0_irq_save_disable",
  ins .fenceIO,
  ins (.csrReadClearImmediate .a0 .mstatus 8),
  ins (.andImmediate .a0 .a0 8),
  ins (.shiftRightImmediate .a0 .a0 3),
  ins .fenceIO,
  ins .return
]

/-- The source frontend guarantees a0 is the i64 transport of a canonical Bool. -/
def restore : Array Line := #[
  label "core0_irq_restore",
  ins .fenceIO,
  ins (.branchEqZero .a0 ".Ltimer_restore_clear"),
  ins (.csrSetImmediate .mstatus 8),
  ins (.jump ".Ltimer_restore_done"),
  label ".Ltimer_restore_clear",
  ins (.csrClearImmediate .mstatus 8),
  label ".Ltimer_restore_done",
  ins .fenceIO,
  ins (.loadImmediate .a0 0),
  ins .return
]

/-- Change only mie.MTIE, without enabling global MIE or any other interrupt. -/
def setInterrupt : Array Line := #[
  label "core0_timer_set_interrupt",
  ins .fenceIO,
  ins (.loadImmediate .t0 0x80),
  ins (.branchEqZero .a0 ".Ltimer_interrupt_clear"),
  ins (.csrSet .mie .t0),
  ins (.jump ".Ltimer_interrupt_done"),
  label ".Ltimer_interrupt_clear",
  ins (.csrClear .mie .t0),
  label ".Ltimer_interrupt_done",
  ins .fenceIO,
  ins (.loadImmediate .a0 0),
  ins .return
]

private def callerRegisters : Array Register := #[
  .ra, .sp, .gp, .tp, .s0, .s1, .s2, .s3, .s4, .s5, .s6, .s7, .s8, .s9, .s10, .s11
]

private def saveCaller : Array Line := #[ins (.loadAddress .t0 "__trap_probe_context")] ++
  callerRegisters.mapIdx (fun index register =>
    ins (.storeDouble register .t0 (asOffset (index * 8))))

private def restoreCaller : Array Line := #[ins (.loadAddress .t0 "__trap_probe_context")] ++
  (callerRegisters.mapIdx fun index register => (index, register)).filterMap
    (fun (index, register) =>
      if register == .sp then none
      else some (ins (.loadDouble register .t0 (asOffset (index * 8))))) ++ #[
        ins (.loadDouble .sp .t0 8),
        ins .return
      ]

private def expectedSnapshot (register : Register) : Nat :=
  if register == .t0 then 0 else TrapPrimitives.sentinelValue register

private def compareSnapshot : Array Line :=
  TrapPrimitives.preservedRegisters.flatMap fun register =>
    let next := s!".Ltimer_probe_x{register.number}_ok"
    #[
      ins (.loadDouble .t0 .sp (asOffset (TrapPrimitives.frameOffset register))),
      ins (.loadImmediate .t1 (expectedSnapshot register)),
      ins (.branchEq .t0 .t1 next),
      ins (.loadImmediate .t2 (2 ^ (register.number - 1))),
      ins (.orRegisters .a0 .a0 .t2),
      label next
    ]

private def compareCanaries : Array Line :=
  (trapLayout.canaries.mapIdx fun index canary => (index, canary)).flatMap fun (index, canary) =>
    (#[0, 1] : Array Nat).flatMap fun word =>
      let next := s!".Ltimer_probe_canary{index}_{word}_ok"
      #[
        ins (.loadImmediate .t0 (canary.address + word * 8)),
        ins (.loadDouble .t1 .t0 0),
        ins (.loadImmediate .t2 (canary.value + word)),
        ins (.branchEq .t1 .t2 next),
        ins (.loadImmediate .t2 (2 ^ (31 + index))),
        ins (.orRegisters .a0 .a0 .t2),
        label next
      ]

/-- A real asynchronous trap may interrupt any instruction in the bounded loop.
No ISR call, synthetic event, WFI, memory polling, or wait-for-event loop occurs. -/
def probe : Array Line := #[label "core0_timer_probe"] ++ saveCaller ++
  TrapPrimitives.preservedRegisters.map (fun register =>
    ins (.loadImmediate register
      (if register == .t0 then probeIterations else TrapPrimitives.sentinelValue register))) ++ #[
    ins .fenceIO,
    ins (.csrSetImmediate .mstatus 8),
    label "__timer_probe_loop",
    ins (.addImmediate .t0 .t0 (-1)),
    ins (.branchNeZero .t0 "__timer_probe_loop"),
    ins (.csrClearImmediate .mstatus 8),
    ins .fenceIO,
    label "__timer_probe_snapshot"
  ] ++ TrapPrimitives.preservedRegisters.map (fun register =>
    ins (.storeDouble register .sp (asOffset (TrapPrimitives.frameOffset register)))) ++ #[
      ins (.loadImmediate .a0 0)
    ] ++ compareSnapshot ++ compareCanaries ++ restoreCaller

private def renderFunction (symbol : String) (lines : Array Line) : List String :=
  [".balign 4", s!".globl {symbol}", s!".type {symbol}, @function"] ++
    lines.toList.map Line.render ++ [s!".size {symbol}, . - {symbol}"]

def renderStartup (config : Configuration) : Except String String := do
  trapLayout.validate
  let trapConfig : TrapPrimitives.Configuration := {
    dispatcher := config.dispatcher
    mutation := if config.mutation == .restoreS3FromS4 then .restoreS3FromS4 else .none
  }
  -- Reuse the established validation, but never splice its rendered string.
  let _ ← TrapPrimitives.renderStartup trapConfig
  pure <| String.intercalate "\n" <|
    [".option push", ".option norelax", ".option norvc",
      ".section .text.start, \"ax\", @progbits"] ++
    renderFunction "_start" startup ++
    renderFunction "core0_io_fence" Primitives.ioFence ++
    renderFunction "core0_trap_vector" (TrapPrimitives.vector trapConfig) ++
    renderFunction "core0_trap_fatal_dispatch" TrapPrimitives.fatalDispatch ++
    renderFunction "core0_trap_double_fault" TrapPrimitives.doubleFault ++
    renderFunction "core0_trap_ecall" TrapPrimitives.ecallProbe ++
    renderFunction "core0_trap_breakpoint" TrapPrimitives.breakpointProbe ++
    renderFunction "core0_trap_unexpected_ecall" TrapPrimitives.unexpectedEcall ++
    renderFunction "core0_trap_illegal_instruction" TrapPrimitives.illegalInstruction ++
    renderFunction "core0_timer_read_time" readTime ++
    renderFunction "core0_timer_set_compare" (setCompare config.mutation) ++
    renderFunction "core0_timer_read_pending" readPending ++
    renderFunction "core0_irq_save_disable" saveDisable ++
    renderFunction "core0_irq_restore" restore ++
    renderFunction "core0_timer_set_interrupt" setInterrupt ++
    renderFunction "core0_timer_probe" probe ++
    [".option pop", ".section .note.GNU-stack, \"\", @progbits", ""]

end Lemma.Machine.TimerPrimitives
