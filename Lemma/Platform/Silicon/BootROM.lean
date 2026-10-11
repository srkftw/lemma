import Lean
import Lemma.Machine.Primitives
import Lemma.Platform.Silicon.Binding

/-! Host export of the narrow architectural reset handoff. Every instruction
comes from the same inspected structured machine primitive renderer used by
the existing compiler. The host never initializes privileged CPU state. -/
namespace Lemma.Platform.Silicon.BootROM
open Lemma.Machine.Primitives

def handoff : Array Line := #[
  .label "_reset",
  .instruction (.loadImmediate .a0 0),
  .instruction (.loadImmediate .a1 Binding.dtb_base.toNat),
  .instruction (.loadImmediate .t0 Binding.entry.toNat),
  .instruction (.jumpRegisterZero .t0)
]

def render : String := String.intercalate "\n" ([
  ".option norvc", ".option norelax", ".section .text, \"ax\", @progbits",
  ".globl _reset", ".balign 4"] ++ handoff.toList.map Line.render ++
  [".section .note.GNU-stack, \"\", @progbits", ""])

end Lemma.Platform.Silicon.BootROM

def main (args : List String) : IO UInt32 := do
  match args with
  | [output] => IO.FS.writeFile output Lemma.Platform.Silicon.BootROM.render; pure 0
  | _ => throw <| IO.userError "silicon BootROM export requires exactly one output path"
