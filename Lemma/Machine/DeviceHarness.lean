import Lemma.Compiler.CFGLower
import Lemma.Compiler.Test.DeviceABI
import Lemma.Machine.DeviceLayout

/-!
Minimal machine harness for the compiled `core0-v0.5` device session.

UART initialization, polling, framing, validation, dispatch, response encoding,
and transmitter drain all remain in the elaborated Lean root.  This glue only
crosses the no-argument action ABI and writes a status-coded value to QEMU's
SiFive test finisher.  In particular, it contains no UART register access.
-/

namespace Lemma.Machine.DeviceHarness

open Lemma.Compiler
open Lemma.Compiler.LLVM

private def value (name : String) : Operand := .local name
private def int32 (n : Nat) : Operand := .int .i32 n
private def int64 (n : Nat) : Operand := .int .i64 n

private def entryBlock (root : LoweredActionRoot) : Block := {
  label := "entry"
  instructions := #[
    .abiCall (some "session.outcome") .checkedResult none root.llvm #[],
    .extractResultStatus "session.status" (value "session.outcome"),
    .extractResultValue "session.value" (value "session.outcome"),
    .icmp "session.ok" .eq .i64 (value "session.status") (int64 0),
    .branch (value "session.ok") "success" "failure"
  ]
}

private def successBlock (layout : DeviceLayout) : Block := {
  label := "success"
  instructions := #[
    .ptrFromInt "success.finisher" layout.memory.machine.testFinisherBase,
    .call none .void "core0_io_fence" #[],
    .store .i32 (int32 0x5555) (value "success.finisher") 4 true,
    .call none .void "core0_io_fence" #[],
    .jump "halt"
  ]
}

private def failureBlock (layout : DeviceLayout) : Block := {
  label := "failure"
  instructions := #[
    .trunc "failure.status.i32" .i64 (value "session.status") .i32,
    .bin "failure.status.shifted" .shl .i32
      (value "failure.status.i32") (int32 16),
    .bin "failure.code" .or .i32
      (value "failure.status.shifted") (int32 0x3333),
    .ptrFromInt "failure.finisher" layout.memory.machine.testFinisherBase,
    .call none .void "core0_io_fence" #[],
    .store .i32 (value "failure.code") (value "failure.finisher") 4 true,
    .call none .void "core0_io_fence" #[],
    .jump "halt"
  ]
}

private def haltBlock : Block := {
  label := "halt"
  instructions := #[.jump "halt"]
}

def main (layout : DeviceLayout) (root : LoweredActionRoot) : Function := {
  name := "core0_main"
  returnType := .void
  parameters := #[]
  attributes := #["noreturn", "nounwind"]
  blocks := #[entryBlock root, successBlock layout, failureBlock layout, haltBlock]
}

def functions (layout : DeviceLayout) (root : LoweredActionRoot) : Array Function :=
  #[main layout root]

def declarations : Array Declaration := #[
  { name := "core0_io_fence", returnType := .void, parameters := #[] }
]

end Lemma.Machine.DeviceHarness
