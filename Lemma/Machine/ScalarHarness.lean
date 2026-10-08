import Lemma.Compiler.Lower
import Lemma.Compiler.Test.ScalarABI
import Lemma.Machine.Harness

/-!
Freestanding batch harness for the additive typed scalar test ABI.

The harness dispatches only to roots present in the checked/lowered suite.  It
validates the complete fixed header, the selected root signature, every narrow
transport value, and all unused argument slots before making a typed direct
call.  Runtime packets therefore cannot select arbitrary symbols or smuggle a
truncated value through the ABI.
-/

namespace Lemma.Machine.ScalarHarness

open Lemma.Compiler
open Lemma.Compiler.LLVM
open Lemma.Compiler.Test.ScalarABI

private def value (name : String) : Operand := .local name
private def int1 (n : Nat) : Operand := .int .i1 n
private def int8 (n : Nat) : Operand := .int .i8 n
private def int32 (n : Nat) : Operand := .int .i32 n
private def int64 (n : Nat) : Operand := .int .i64 n

private def llvmTy : Lemma.Core0.Ty → Ty
  | .bool => .i1
  | .u8 => .i8
  | .u32 => .i32
  | .u64 => .i64

private def callsForString (text : String) : Array Instruction :=
  text.toUTF8.foldl (init := #[]) fun instructions byte =>
    instructions.push (.call none .void "core0_uart_putc" #[(.i8, int8 byte.toNat)])

private def constantInputLoad (name : String) (address : Nat) : Array Instruction := #[
  .ptrFromInt (name ++ "_ptr") address,
  .load name .i64 (value (name ++ "_ptr")) 8 true
]

private def appendCheck (instructions : Array Instruction) (next : Nat)
    (predicate : Predicate) (lhs rhs : Operand) : Array Instruction × Nat :=
  let checkName := s!"header_check{next}"
  let instructions := instructions.push (.icmp checkName predicate .i64 lhs rhs)
  if next == 0 then
    (instructions, 1)
  else
    (instructions.push (.bin s!"header_all{next}" .and .i1
      (if next == 1 then value "header_check0" else value s!"header_all{next - 1}")
      (value checkName)), next + 1)

private def commonEntry (layout : Layout) (config : Configuration) : Block := Id.run do
  let mut instructions := #[]
  for index in [:headerWords] do
    instructions := instructions ++ constantInputLoad s!"header{index}"
      (layout.input.start + index * 8)
  let expected : Array Nat := #[
    magic,
    version,
    headerBytes,
    recordBytes,
    config.suiteId,
  ]
  let mut checkIndex := 0
  for index in [:expected.size] do
    let pair := appendCheck instructions checkIndex .eq
      (value s!"header{index}") (int64 expected[index]!)
    instructions := pair.1
    checkIndex := pair.2
  -- Batch/root IDs must be nonzero, and the bounded batch must contain 1..29 cases.
  for index in #[5, 6, 7] do
    let pair := appendCheck instructions checkIndex .ugt (value s!"header{index}") (int64 0)
    instructions := pair.1
    checkIndex := pair.2
  let bounded := appendCheck instructions checkIndex .ule (value "header7") (int64 maxCases)
  instructions := bounded.1
  checkIndex := bounded.2
  for (index, expectedValue) in #[(12, config.sourceSeed), (13, config.runtimeSeed), (14, 0), (15, 0)] do
    let pair := appendCheck instructions checkIndex .eq
      (value s!"header{index}") (int64 expectedValue)
    instructions := pair.1
    checkIndex := pair.2
  let finalCheck := if checkIndex == 1 then value "header_check0" else value s!"header_all{checkIndex - 1}"
  instructions := instructions.push (.branch finalCheck "validate_root_1" "bad_input")
  return { label := "entry", instructions }

private def validateRootBlock (root : LoweredRoot) (isLast : Bool) : Block := Id.run do
  let stem := s!"root_{root.id}_meta"
  let expected := #[
    (8, root.signature.args.size),
    (9, typeTag root.signature.result),
    (10, packTagsLow root.signature.args),
    (11, packTagsHigh root.signature.args),
  ]
  let mut instructions := #[]
  for index in [:expected.size] do
    instructions := instructions.push (.icmp s!"{stem}_{index}" .eq .i64
      (value s!"header{expected[index]!.1}") (int64 expected[index]!.2))
  instructions := instructions.push (.icmp (stem ++ "_id") .eq .i64
    (value "header6") (int64 root.id))
  let mut combined := value (stem ++ "_0")
  for index in [1:expected.size] do
    let name := s!"{stem}_all_{index}"
    instructions := instructions.push (.bin name .and .i1 combined (value s!"{stem}_{index}"))
    combined := value name
  instructions := instructions.push (.bin (stem ++ "_all_id") .and .i1 combined
    (value (stem ++ "_id")))
  let next := if isLast then "bad_input" else s!"validate_root_{root.id + 1}"
  instructions := instructions.push (.branch (value (stem ++ "_all_id")) "announce" next)
  return { label := s!"validate_root_{root.id}", instructions }

private def announceBlock : Block := {
  label := "announce"
  instructions := callsForString "LEMMA_SCALAR/1\nBATCH:" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header4")]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header5")]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header6")]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header7")]
  ] ++ callsForString "\n" ++ #[.jump "dispatch_root_1"]
}

private def dispatchRootBlock (root : LoweredRoot) (isLast : Bool) : Block := {
  label := s!"dispatch_root_{root.id}"
  instructions := #[
    .icmp s!"dispatch_is_{root.id}" .eq .i64 (value "header6") (int64 root.id),
    .branch (value s!"dispatch_is_{root.id}") s!"root_{root.id}_start"
      (if isLast then "bad_input" else s!"dispatch_root_{root.id + 1}")
  ]
}

private def rootStartBlock (root : LoweredRoot) : Block := {
  label := s!"root_{root.id}_start"
  instructions := #[.jump s!"root_{root.id}_loop"]
}

private def rangeLimit? : Lemma.Core0.Ty → Option Nat
  | .bool => some 1
  | .u8 => some 0xff
  | .u32 => some 0xffffffff
  | .u64 => none

private def rootLoopBlock (layout : Layout) (root : LoweredRoot) : Block := Id.run do
  let stem := s!"root_{root.id}"
  let mut instructions := #[
    .phi (stem ++ "_index") .i64 #[(int64 0, stem ++ "_start"),
      (value (stem ++ "_next"), stem ++ "_call")],
    .bin (stem ++ "_record_delta") .mul .i64 (value (stem ++ "_index"))
      (int64 recordBytes),
    .bin (stem ++ "_record_address") .add .i64
      (value (stem ++ "_record_delta")) (int64 (layout.input.start + headerBytes)),
    .intToPtr (stem ++ "_case_ptr") (value (stem ++ "_record_address")),
    .load (stem ++ "_case") .i64 (value (stem ++ "_case_ptr")) 8 true,
  ]
  let mut valid : Operand := int1 1
  for slot in [:maxArguments] do
    let address := s!"{stem}_arg{slot}_address"
    let pointer := s!"{stem}_arg{slot}_ptr"
    let argument := s!"{stem}_arg{slot}"
    instructions := instructions.push (.bin address .add .i64
      (value (stem ++ "_record_address")) (int64 (8 * (slot + 1))))
    instructions := instructions.push (.intToPtr pointer (value address))
    instructions := instructions.push (.load argument .i64 (value pointer) 8 true)
    let check := s!"{stem}_arg{slot}_valid"
    if h : slot < root.signature.args.size then
      match rangeLimit? root.signature.args[slot] with
      | some limit =>
          instructions := instructions.push (.icmp check .ule .i64 (value argument) (int64 limit))
      | none =>
          instructions := instructions.push (.icmp check .eq .i64 (int64 0) (int64 0))
    else
      instructions := instructions.push (.icmp check .eq .i64 (value argument) (int64 0))
    let combined := s!"{stem}_args_valid_{slot}"
    instructions := instructions.push (.bin combined .and .i1 valid (value check))
    valid := value combined
  instructions := instructions.push (.branch valid (stem ++ "_call") "bad_input")
  return { label := stem ++ "_loop", instructions }

private def rootCallBlock (root : LoweredRoot) : Block := Id.run do
  let stem := s!"root_{root.id}"
  let mut instructions := #[]
  let mut arguments : Array ABIArgument := #[]
  for h : index in [:root.signature.args.size] do
    let source := value s!"{stem}_arg{index}"
    let ty := root.signature.args[index]
    let operand ← match ty with
      | .bool =>
          let name := s!"{stem}_arg{index}_i1"
          instructions := instructions.push (.trunc name .i64 source .i1)
          pure (value name)
      | .u8 =>
          let name := s!"{stem}_arg{index}_i8"
          instructions := instructions.push (.trunc name .i64 source .i8)
          pure (value name)
      | .u32 =>
          let name := s!"{stem}_arg{index}_i32"
          instructions := instructions.push (.trunc name .i64 source .i32)
          pure (value name)
      | .u64 => pure source
    arguments := arguments.push {
      ty := llvmTy ty
      value := operand
      extension := rv64LP64Extension ty
    }
  instructions := instructions.push (.abiCall (some (stem ++ "_result_typed"))
    (llvmTy root.signature.result) (rv64LP64Extension root.signature.result)
    root.llvm arguments)
  match root.signature.result with
  | .bool =>
      instructions := instructions.push (.zext (stem ++ "_result") .i1
        (value (stem ++ "_result_typed")) .i64)
  | .u8 =>
      instructions := instructions.push (.zext (stem ++ "_result") .i8
        (value (stem ++ "_result_typed")) .i64)
  | .u32 =>
      instructions := instructions.push (.zext (stem ++ "_result") .i32
        (value (stem ++ "_result_typed")) .i64)
  | .u64 =>
      instructions := instructions.push (.bin (stem ++ "_result") .or .i64
        (value (stem ++ "_result_typed")) (int64 0))
  instructions := instructions ++ callsForString "RESULT:" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value (stem ++ "_case"))]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, int64 (typeTag root.signature.result))]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value (stem ++ "_result"))]
  ] ++ callsForString "\n"
  instructions := instructions.push (.bin (stem ++ "_next") .add .i64
    (value (stem ++ "_index")) (int64 1))
  instructions := instructions.push (.icmp (stem ++ "_more") .ult .i64
    (value (stem ++ "_next")) (value "header7"))
  instructions := instructions.push (.branch (value (stem ++ "_more"))
    (stem ++ "_loop") "done")
  return { label := stem ++ "_call", instructions }

private def doneBlock : Block := {
  label := "done"
  instructions := callsForString "END:" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header5")]
  ] ++ callsForString ":" ++ #[
    .call none .void "core0_put_hex64" #[(.i64, value "header7")]
  ] ++ callsForString "\n" ++ #[
    .call none .void "core0_exit_success" #[],
    .unreachable
  ]
}

private def badInputBlock : Block := {
  label := "bad_input"
  instructions := callsForString "ERROR:TYPED-INPUT\n" ++ #[
    .call none .void "core0_exit_failure" #[],
    .unreachable
  ]
}

def main (layout : Layout) (config : Configuration) (roots : Array LoweredRoot) : Function := {
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
      blocks := blocks.push (rootStartBlock root)
      blocks := blocks.push (rootLoopBlock layout root)
      blocks := blocks.push (rootCallBlock root)
    blocks := blocks.push doneBlock
    blocks := blocks.push badInputBlock
    return blocks
}

def functions (layout : Layout) (config : Configuration)
    (roots : Array LoweredRoot) : Array Function := #[
  Lemma.Machine.Harness.exitFailure layout,
  Lemma.Machine.Harness.exitSuccess layout,
  Lemma.Machine.Harness.uartPutc layout,
  Lemma.Machine.Harness.uartDrain layout,
  Lemma.Machine.Harness.putHex64,
  main layout config roots,
]

def declarations : Array Declaration := Lemma.Machine.Harness.declarations

end Lemma.Machine.ScalarHarness
