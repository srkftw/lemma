import Lemma.Platform.RiscV.CounterPrimitives

/-! Fixed CSR and privilege/context transport for core0-counter-su-v0.1.
This module performs no permission expectation, corpus selection or verdict.
The lower entry and trap dispatcher are exact genuinely compiled source symbols.
Historical CounterPrimitives and its emitted bodies remain unchanged. -/
namespace Lemma.Platform.RiscV.CounterSuPrimitives
open Lemma.Machine.Primitives
open Lemma.Core0.Execution

def contextBase : Nat := 0x80108000
def trapStackTop : Nat := 0x8010a000
def lowerStackTop : Nat := 0x8010c000

def accesses : Array (Op × CSR × Bool) := CounterPrimitives.accesses ++ #[
  (.readCounterCycle, .cycle, false), (.readCounterTime, .time, false),
  (.readCounterRetired, .instret, false),
  (.readSupervisorCounterEnable, .scounteren, false), (.writeSupervisorCounterEnable, .scounteren, true),
  (.attemptWriteCounterCycle, .cycle, true), (.attemptWriteCounterTime, .time, true),
  (.attemptWriteCounterRetired, .instret, true)]

private def ins (i : Instruction) : Line := .instruction i

/-- A read initializes the ordinary ABI result register before its fixed actual
CSR access. If the diagnostic trap policy skips that instruction, its zero value
is defined but the captured illegal trap remains mandatory evidence. -/
def functions : Array (String × Array Line) := accesses.map fun (op, csr, write) =>
  let symbol := op.primitiveSymbol?.getD "invalid-counter-su-operation"
  (symbol, #[.label symbol] ++
    (if write then #[.label (symbol ++ "_access"), ins (.csrWrite csr .a0), ins (.loadImmediate .a0 0)]
     else #[ins (.loadImmediate .a0 0), .label (symbol ++ "_access"), ins (.csrRead .a0 csr)]) ++ #[ins .return])

/-- Suspend an M ABI caller, preserving every architectural GPR and its return
PC/status/interrupt enables in fixed private storage. The fixed lower privilege
selection is part of the operation, never a caller-supplied CSR or code address. -/
private def enter (name : String) (mode : Nat) : Array Line := #[
  .label name, ins (.addImmediate .sp .sp (-16)),
  ins (.storeDouble .t0 .sp 0), ins (.storeDouble .t1 .sp 8),
  ins (.loadImmediate .t0 contextBase), ins (.storeDouble .zero .t0 0)
] ++ (Register.all.extract 1 32 |>.filter fun r => r != .sp && r != .t0 && r != .t1).map
  (fun r => ins (.storeDouble r .t0 (Int.ofNat (r.number*8)))) ++ #[
  ins (.loadDouble .t1 .sp 0), ins (.storeDouble .t1 .t0 40),
  ins (.loadDouble .t1 .sp 8), ins (.storeDouble .t1 .t0 48),
  ins (.addImmediate .t1 .sp 16), ins (.storeDouble .t1 .t0 16),
  ins (.loadAddress .t1 "lemma_counter_su_resume"), ins (.storeDouble .t1 .t0 256),
  ins (.csrRead .t1 .mstatus), ins (.loadImmediate .t2 0x1800),
  ins (.orRegisters .t1 .t1 .t2), ins (.storeDouble .t1 .t0 264),
  ins (.csrRead .t1 .mie), ins (.storeDouble .t1 .t0 272),
  ins (.loadImmediate .t1 trapStackTop), ins (.storeDouble .t1 .t0 280),
  ins (.loadImmediate .t1 0x1800), ins (.csrClear .mstatus .t1),
  ins (.loadImmediate .t1 (mode*0x800)), ins (.csrSet .mstatus .t1),
  ins (.loadImmediate .sp lowerStackTop),
  ins (.loadAddress .t0 "lemma_counter_su_lower"), ins (.csrWrite .mepc .t0),
  ins .machineReturn]

def transitions : Array (String × Array Line) := #[
  ("lemma_exec_counter_enter_supervisor", enter "lemma_exec_counter_enter_supervisor" 1),
  ("lemma_exec_counter_enter_user", enter "lemma_exec_counter_enter_user" 0),
  ("lemma_counter_su_resume", #[.label "lemma_counter_su_resume", ins .return])]

private def fatal (name : String) (value : Nat) : Array Line := #[
  .label name, ins (.loadImmediate .t0 0x00100000), ins (.loadImmediate .t1 value),
  ins .fenceIO, ins (.storeWord .t1 .t0 0), ins .fenceIO,
  .label (name ++ "_halt"), ins .waitForInterrupt, ins (.jump (name ++ "_halt"))]

def startup (main : String) : Array Line := #[
  .label "_start", ins (.csrWrite .mie .zero), ins .maskMachineInterruptEnable,
  ins (.csrWrite .medeleg .zero), ins (.csrWrite .mideleg .zero),
  ins (.csrWrite .satp .zero), ins .translationFenceAll,
  ins (.loadAddress .t0 "lemma_machine_vector"), ins (.csrWrite .mtvec .t0),
  ins (.loadImmediate .t0 trapStackTop), ins (.csrWrite .mscratch .t0),
  ins (.loadImmediate .t0 0x20001fff), ins (.csrWrite .pmpaddr0 .t0),
  ins (.loadImmediate .t0 0x20041fff), ins (.csrWrite .pmpaddr1 .t0),
  ins (.loadImmediate .t0 0x1b1d), ins (.csrWrite .pmpcfg0 .t0),
  ins (.loadAddress .sp "__stack_top"), ins (.move .gp .zero), ins (.move .tp .zero),
  ins (.loadAddress .t0 "__bss_start"), ins (.loadAddress .t1 "__bss_end"),
  .label ".Lcounter_su_clear_bss", ins (.branchGeUnsigned .t0 .t1 ".Lcounter_su_call"),
  ins (.storeDouble .zero .t0 0), ins (.addImmediate .t0 .t0 8), ins (.jump ".Lcounter_su_clear_bss"),
  .label ".Lcounter_su_call", ins (.call main),
  ins (.branchNeZero .a0 "lemma_counter_su_failure"),
  ins (.loadImmediate .t1 0x5555), ins (.loadImmediate .t0 0x00100000),
  ins .fenceIO, ins (.storeWord .t1 .t0 0), ins .fenceIO,
  .label ".Lcounter_su_park", ins .waitForInterrupt, ins (.jump ".Lcounter_su_park")]

private def renderFunction (name : String) (body : Array Line) : List String :=
  [".balign 4", s!".globl {name}", s!".type {name}, @function"] ++
    body.toList.map Line.render ++ [s!".size {name}, . - {name}"]
private def validSymbol (name : String) : Bool :=
  !name.isEmpty && name.toList.all (fun c => c.isAlphanum || c == '_')

def render (main probe trap : String) : Except String String := do
  unless #[main, probe, trap].all validSymbol && accesses.size == 17 do
    throw "counter-su requires exact compiled main/probe/trap symbols and closed CSR inventory"
  let config : Lemma.Platform.RiscV.ExecutionPrimitives.Configuration := {
    stage := .bootstrapM, kernelMain := main, firmwareDispatcher := trap }
  let bodies := #[("_start", startup main)] ++ functions ++ transitions ++ #[
    ("lemma_counter_su_lower", #[.label "lemma_counter_su_lower", ins (.call probe),
      .label "lemma_counter_su_ecall", ins .environmentCall, ins (.jump "lemma_counter_su_failure")]),
    ("lemma_machine_vector", Lemma.Platform.RiscV.ExecutionPrimitives.machineVector config),
    ("lemma_machine_fatal", fatal "lemma_machine_fatal" 0x33333),
    ("lemma_machine_double_fault", fatal "lemma_machine_double_fault" 0x23333),
    ("lemma_counter_su_failure", fatal "lemma_counter_su_failure" 0x13333),
    ("lemma_exec_read_time", Lemma.Platform.RiscV.ExecutionPrimitives.readTime)]
  pure <| String.intercalate "\n" <| [
    ".option push", ".option norelax", ".option norvc", ".section .text.start, \"ax\", @progbits"] ++
    bodies.toList.flatMap (fun (name, body) => renderFunction name body) ++
    [".option pop", ".section .note.GNU-stack, \"\", @progbits", ""]

def layout : Lemma.Machine.Layout := CounterPrimitives.layout
end Lemma.Platform.RiscV.CounterSuPrimitives
