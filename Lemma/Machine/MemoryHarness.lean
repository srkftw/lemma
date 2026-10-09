import Lemma.Compiler.CFGLower
import Lemma.Compiler.Test.MemoryABI
import Lemma.Machine.Harness
import Lemma.Machine.MemoryLayout

/-!
Freestanding one-case harness for the checked `core0-v0.4` memory suite.

The harness validates the complete fixed control packet before dispatching to one
statically enumerated Action root.  It observes the returned two-word ABI value,
then emits every byte of all four ordinary regions as consecutive little-endian
64-bit words before printing every boundary canary.  The host can therefore
reconstruct and hash the complete target post-state instead of inferring stores
from the scalar result.  Memory algorithms remain in the elaborated source
declarations; this module performs only test dispatch and observation.
-/

namespace Lemma.Machine.MemoryHarness

open Lemma.Compiler
open Lemma.Compiler.LLVM
open Lemma.Compiler.Test.MemoryABI

private def value (name : String) : Operand := .local name
private def int1 (n : Nat) : Operand := .int .i1 n
private def int8 (n : Nat) : Operand := .int .i8 n
private def int64 (n : Nat) : Operand := .int .i64 n

private def callsForString (text : String) : Array Instruction :=
  text.toUTF8.foldl (init := #[]) fun instructions byte =>
    instructions.push (.call none .void "core0_uart_putc" #[(.i8, int8 byte.toNat)])

private def hexDigit (value : Nat) : Char :=
  if value < 10 then
    Char.ofNat ('0'.toNat + value)
  else
    Char.ofNat ('a'.toNat + value - 10)

private def hexByte (value : Nat) : String :=
  String.ofList [hexDigit ((value / 16) % 16), hexDigit (value % 16)]

private def constantLoad64 (name : String) (address : Nat) : Array Instruction := #[
  .ptrFromInt (name ++ ".ptr") address,
  .load name .i64 (value (name ++ ".ptr")) 8 true
]

private def appendCheck (instructions : Array Instruction) (next : Nat)
    (predicate : Predicate) (lhs rhs : Operand) : Array Instruction × Nat :=
  let checkName := s!"input.check.{next}"
  let instructions := instructions.push (.icmp checkName predicate .i64 lhs rhs)
  if next == 0 then
    (instructions, 1)
  else
    let previous := if next == 1 then value "input.check.0"
      else value s!"input.all.{next - 1}"
    (instructions.push (.bin s!"input.all.{next}" .and .i1 previous
      (value checkName)), next + 1)

private def rangeLimit? : Lemma.Core0.Ty → Option Nat
  | .bool => some 1
  | .u8 => some 0xff
  | .u32 => some 0xffffffff
  | .u64 => none

private def commonEntry (layout : MemoryLayout) (config : Configuration) : Block := Id.run do
  let mut instructions : Array Instruction := #[]
  for index in [:headerWords] do
    instructions := instructions ++ constantLoad64 s!"header.{index}"
      (layout.machine.input.start + index * 8)
  for index in [:maximumArguments] do
    instructions := instructions ++ constantLoad64 s!"argument.{index}"
      (layout.machine.input.start + headerBytes + index * 8)

  let mut checkIndex := 0
  for (index, expected) in #[
      (0, magic), (1, version), (2, headerBytes), (3, controlBytes),
      (4, config.suiteId), (10, config.sourceSeed), (11, config.runtimeSeed),
      (12, 0), (13, 0), (14, 0), (15, 0)] do
    let checked := appendCheck instructions checkIndex .eq
      (value s!"header.{index}") (int64 expected)
    instructions := checked.1
    checkIndex := checked.2
  for index in #[5, 6] do
    let checked := appendCheck instructions checkIndex .ugt
      (value s!"header.{index}") (int64 0)
    instructions := checked.1
    checkIndex := checked.2
  let bounded := appendCheck instructions checkIndex .ule
    (value "header.7") (int64 maximumArguments)
  instructions := bounded.1
  checkIndex := bounded.2
  let finalCheck := if checkIndex == 1 then value "input.check.0"
    else value s!"input.all.{checkIndex - 1}"
  instructions := instructions.push (.branch finalCheck "validate.root.1" "bad_input")
  return { label := "entry", instructions }

private def validateRootBlock (root : LoweredActionRoot) (isLast : Bool) : Block := Id.run do
  let stem := s!"root.{root.id}.meta"
  let mut instructions : Array Instruction := #[
    .icmp (stem ++ ".id") .eq .i64 (value "header.6") (int64 root.id),
    .icmp (stem ++ ".arity") .eq .i64 (value "header.7")
      (int64 root.signature.args.size),
    .icmp (stem ++ ".tags-low") .eq .i64 (value "header.8")
      (int64 (packTagsLow root.signature.args)),
    .icmp (stem ++ ".tags-high") .eq .i64 (value "header.9")
      (int64 (packTagsHigh root.signature.args))
  ]
  let mut valid : Operand := value (stem ++ ".id")
  for suffix in #["arity", "tags-low", "tags-high"] do
    let combined := stem ++ ".all." ++ suffix
    instructions := instructions.push
      (.bin combined .and .i1 valid (value (stem ++ "." ++ suffix)))
    valid := value combined
  for slot in [:maximumArguments] do
    let check := s!"{stem}.argument.{slot}"
    if h : slot < root.signature.args.size then
      match rangeLimit? root.signature.args[slot] with
      | some limit =>
          instructions := instructions.push
            (.icmp check .ule .i64 (value s!"argument.{slot}") (int64 limit))
      | none =>
          instructions := instructions.push
            (.icmp check .eq .i64 (int64 0) (int64 0))
    else
      instructions := instructions.push
        (.icmp check .eq .i64 (value s!"argument.{slot}") (int64 0))
    let combined := s!"{stem}.arguments-through.{slot}"
    instructions := instructions.push (.bin combined .and .i1 valid (value check))
    valid := value combined
  let next := if isLast then "bad_input" else s!"validate.root.{root.id + 1}"
  instructions := instructions.push (.branch valid "announce" next)
  return { label := s!"validate.root.{root.id}", instructions }

private def announceBlock : Block := {
  label := "announce"
  instructions := callsForString "LEMMA_MEMORY/1\nCASE:" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header.4")]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header.5")]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header.6")]
  ] ++ callsForString "\n" ++ #[.jump "dispatch.root.1"]
}

private def dispatchRootBlock (root : LoweredActionRoot) (isLast : Bool) : Block := {
  label := s!"dispatch.root.{root.id}"
  instructions := #[
    .icmp s!"dispatch.is.{root.id}" .eq .i64 (value "header.6") (int64 root.id),
    .branch (value s!"dispatch.is.{root.id}") s!"root.{root.id}.call"
      (if isLast then "bad_input" else s!"dispatch.root.{root.id + 1}")
  ]
}

private def rootCallBlock (root : LoweredActionRoot) : Block := Id.run do
  let stem := s!"root.{root.id}"
  let mut instructions : Array Instruction := #[]
  let mut arguments : Array ABIArgument := #[]
  for h : index in [:root.signature.args.size] do
    let source := value s!"argument.{index}"
    let ty := root.signature.args[index]
    let operand ← match ty with
      | .bool =>
          let name := s!"{stem}.argument.{index}.i1"
          instructions := instructions.push (.trunc name .i64 source .i1)
          pure (value name)
      | .u8 =>
          let name := s!"{stem}.argument.{index}.i8"
          instructions := instructions.push (.trunc name .i64 source .i8)
          pure (value name)
      | .u32 =>
          let name := s!"{stem}.argument.{index}.i32"
          instructions := instructions.push (.trunc name .i64 source .i32)
          pure (value name)
      | .u64 => pure source
    arguments := arguments.push {
      ty := Lemma.Compiler.llvmTy ty
      value := operand
      extension := Lemma.Compiler.rv64LP64Extension ty
    }
  instructions := instructions.push
    (.abiCall (some (stem ++ ".outcome")) .checkedResult none root.llvm arguments)
  instructions := instructions.push
    (.extractResultStatus (stem ++ ".status") (value (stem ++ ".outcome")))
  instructions := instructions.push
    (.extractResultValue (stem ++ ".value") (value (stem ++ ".outcome")))
  instructions := instructions.push (.jump "report")
  return { label := stem ++ ".call", instructions }

private def canaryInstructions (layout : MemoryLayout) : Array Instruction := Id.run do
  let mut instructions : Array Instruction := #[]
  for canary in layout.canaries do
    let stem := s!"canary.{canary.id}"
    instructions := instructions ++ constantLoad64 (stem ++ ".low") canary.start
    instructions := instructions ++ constantLoad64 (stem ++ ".high") (canary.start + 8)
    let idText := hexByte canary.id
    instructions := instructions ++ callsForString ("CANARY:" ++ idText ++ ":")
    instructions := instructions.push
      (.call none .void "core0_put_hex64" #[(.i64, value (stem ++ ".low"))])
    instructions := instructions ++ callsForString ":"
    instructions := instructions.push
      (.call none .void "core0_put_hex64" #[(.i64, value (stem ++ ".high"))])
    instructions := instructions ++ callsForString "\n"
  return instructions

/-- Emit one exact, reversible frame for each ordinary region.  Each payload is
the concatenation of `core0_put_hex64` renderings of consecutive aligned words;
the host decodes every word back to eight little-endian bytes.  Gate 5 freezes
all ordinary lengths at 4 KiB and the layout validator requires their base
alignment, so there is neither a partial final word nor an unaligned observer
load. -/
private def postStateInstructions (layout : MemoryLayout) : Array Instruction := Id.run do
  let mut instructions : Array Instruction := #[]
  for region in layout.regions do
    if region.kind == .ordinary then
      let idText := hexByte region.id
      instructions := instructions ++ callsForString ("REGION:" ++ idText ++ ":")
      instructions := instructions.push
        (.call none .void "core0_put_hex64" #[(.i64, int64 region.length)])
      instructions := instructions ++ callsForString ":"
      for index in [:region.length / 8] do
        let stem := s!"region.{region.id}.word.{index}"
        instructions := instructions ++ constantLoad64 stem (region.base + index * 8)
        instructions := instructions.push
          (.call none .void "core0_put_hex64" #[(.i64, value stem)])
      instructions := instructions ++ callsForString "\n"
  return instructions

private def reportBlock (layout : MemoryLayout)
    (roots : Array LoweredActionRoot) : Block := Id.run do
  let statusIncoming := roots.map fun root =>
    (value s!"root.{root.id}.status", s!"root.{root.id}.call")
  let valueIncoming := roots.map fun root =>
    (value s!"root.{root.id}.value", s!"root.{root.id}.call")
  let mut instructions : Array Instruction := #[
    .phi "outcome.status" .i64 statusIncoming,
    .phi "outcome.value" .i64 valueIncoming
  ]
  instructions := instructions ++ callsForString "OUTCOME:"
  instructions := instructions.push
    (.call none .void "core0_put_hex64" #[(.i64, value "header.5")])
  instructions := instructions ++ callsForString ":"
  instructions := instructions.push
    (.call none .void "core0_put_hex64" #[(.i64, value "outcome.status")])
  instructions := instructions ++ callsForString ":"
  instructions := instructions.push
    (.call none .void "core0_put_hex64" #[(.i64, value "outcome.value")])
  instructions := instructions ++ callsForString "\n"
  instructions := instructions ++ postStateInstructions layout
  instructions := instructions ++ canaryInstructions layout
  instructions := instructions ++ callsForString "END:"
  instructions := instructions.push
    (.call none .void "core0_put_hex64" #[(.i64, value "header.5")])
  instructions := instructions ++ callsForString "\n"
  instructions := instructions.push (.call none .void "core0_exit_success" #[])
  instructions := instructions.push .unreachable
  return { label := "report", instructions }

private def badInputBlock : Block := {
  label := "bad_input"
  instructions := callsForString "ERROR:MEMORY-INPUT\n" ++ #[
    .call none .void "core0_exit_failure" #[],
    .unreachable
  ]
}

def main (layout : MemoryLayout) (config : Configuration)
    (roots : Array LoweredActionRoot) : Function := {
  name := "core0_main"
  returnType := .void
  parameters := #[]
  attributes := #["noreturn", "nounwind"]
  blocks := Id.run do
    let mut blocks := #[commonEntry layout config]
    for h : index in [:roots.size] do
      blocks := blocks.push (validateRootBlock roots[index] (index + 1 == roots.size))
    blocks := blocks.push announceBlock
    for h : index in [:roots.size] do
      let root := roots[index]
      blocks := blocks.push (dispatchRootBlock root (index + 1 == roots.size))
      blocks := blocks.push (rootCallBlock root)
    blocks := blocks.push (reportBlock layout roots)
    blocks := blocks.push badInputBlock
    return blocks
}

def functions (layout : MemoryLayout) (config : Configuration)
    (roots : Array LoweredActionRoot) : Array Function := #[
  Lemma.Machine.Harness.exitFailure layout.machine,
  Lemma.Machine.Harness.exitSuccess layout.machine,
  Lemma.Machine.Harness.uartPutc layout.machine,
  Lemma.Machine.Harness.uartDrain layout.machine,
  Lemma.Machine.Harness.putHex64,
  main layout config roots
]

def declarations : Array Declaration := Lemma.Machine.Harness.declarations

end Lemma.Machine.MemoryHarness
