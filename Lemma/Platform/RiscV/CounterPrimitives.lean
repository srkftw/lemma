import Lemma.Machine.Primitives
import Lemma.Machine.Layout
import Lemma.Core0.Execution
import Lemma.Platform.RiscV.ExecutionPrimitives

/-! Closed hardware boundary for core0-firmware-v0.2. No caller-selected CSR,
privilege policy or qualification algorithm is generated here. -/
namespace Lemma.Platform.RiscV.CounterPrimitives
open Lemma.Machine.Primitives
open Lemma.Core0.Execution

/-- The fixed operation/CSR pair is authoritative; write helpers return zero
only after the actual CSRRW instruction has executed normally in M-mode. -/
def accesses : Array (Op × CSR × Bool) := #[
  (.readMisa, .misa, false),
  (.readMachineCycle, .mcycle, false), (.writeMachineCycle, .mcycle, true),
  (.readMachineRetired, .minstret, false), (.writeMachineRetired, .minstret, true),
  (.readMachineInhibit, .mcountinhibit, false), (.writeMachineInhibit, .mcountinhibit, true),
  (.readMachineCounterEnable, .mcounteren, false), (.writeMachineCounterEnable, .mcounteren, true)]

private def ins (i : Instruction) : Line := .instruction i

def functions : Array (String × Array Line) := accesses.map fun (operation, csr, write) =>
  let symbol := operation.primitiveSymbol?.getD "invalid-counter-operation"
  (symbol, #[.label symbol] ++
    (if write then #[ins (.csrWrite csr .a0), ins (.loadImmediate .a0 0)]
     else #[ins (.csrRead .a0 csr)]) ++ #[ins .return])

/-- Only a calling convention and diagnostic finisher disposition. The checked
Lean root is solely responsible for the result records and success decision. -/
def startup (entry : String) : Array Line := #[
  .label "_start", ins (.csrWrite .mie .zero), ins .maskMachineInterruptEnable,
  ins (.csrWrite .satp .zero), ins .translationFenceAll,
  ins (.loadAddress .sp "__stack_top"), ins (.move .gp .zero), ins (.move .tp .zero),
  ins (.loadAddress .t0 "__bss_start"), ins (.loadAddress .t1 "__bss_end"),
  .label ".Lcounter_clear_bss", ins (.branchGeUnsigned .t0 .t1 ".Lcounter_call"),
  ins (.storeDouble .zero .t0 0), ins (.addImmediate .t0 .t0 8),
  ins (.jump ".Lcounter_clear_bss"),
  .label ".Lcounter_call", ins (.call entry),
  ins (.branchNeZero .a0 ".Lcounter_failure"),
  ins (.loadImmediate .t1 0x5555), ins (.jump ".Lcounter_finish"),
  .label ".Lcounter_failure", ins (.loadImmediate .t1 0x13333),
  .label ".Lcounter_finish", ins (.loadImmediate .t0 0x00100000),
  ins .fenceIO, ins (.storeWord .t1 .t0 0), ins .fenceIO,
  .label ".Lcounter_halt", ins .waitForInterrupt, ins (.jump ".Lcounter_halt")]

private def renderFunction (name : String) (lines : Array Line) : List String :=
  [".balign 4", s!".globl {name}", s!".type {name}, @function"] ++
  lines.toList.map Line.render ++ [s!".size {name}, . - {name}"]

def render (entry : String) : Except String String := do
  unless !entry.isEmpty && entry.toList.all (fun c => c.isAlphanum || c == '_') do
    throw "counter startup requires an exact compiled entry symbol"
  unless accesses.size == 9 && accesses.all (fun (op, _, write) =>
      op.admits .firmware_v0_2 && !op.admits .firmware_v0_1 &&
      op.primitiveSymbol?.isSome && op.argumentCount == (if write then 1 else 0)) do
    throw "invalid closed counter operation catalog"
  pure <| String.intercalate "\n" <| [
    ".option push", ".option norelax", ".option norvc", ".section .text.start, \"ax\", @progbits"] ++
    renderFunction "_start" (startup entry) ++
    (functions ++ #[("lemma_exec_read_time", ExecutionPrimitives.readTime)]).toList.flatMap
      (fun (name, lines) => renderFunction name lines) ++
    [".option pop", ".section .note.GNU-stack, \"\", @progbits", ""]

/-- Inherit the pinned 128MiB RAM; the diagnostic image/stack remain in existing
firmware/private envelopes. No host-initialized input or application state. -/
def layout : Lemma.Machine.Layout := { Lemma.Machine.core0Layout with
  image := ⟨"firmware", 0x80000000, 0x10000, 0x1000, .loaded⟩
  stack := ⟨"firmware-private-stack", 0x80100000, 0x10000, 16, .noLoad⟩ }

end Lemma.Platform.RiscV.CounterPrimitives
