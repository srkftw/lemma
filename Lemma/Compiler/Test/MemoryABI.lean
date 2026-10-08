import Lemma.Core0.IR

/-!
Closed host/guest test ABI metadata for the Gate 5 checked-memory suite.

This module describes only the fixed control packet and the physical outcome
returned by compiled action roots.  It does not implement memory semantics or
grant access to any target address.
-/

namespace Lemma.Compiler.Test.MemoryABI

def name : String := "lemma-memory-test-v1"
def resultTag : String := "checked-result-v1"
def magic : Nat := 0x353030414d4d454c
def version : Nat := 1
def headerWords : Nat := 16
def headerBytes : Nat := headerWords * 8
def maximumArguments : Nat := 16
def argumentBytes : Nat := maximumArguments * 8
def controlBytes : Nat := headerBytes + argumentBytes
def outcomeWords : Nat := 2

def typeTag : Lemma.Core0.Ty → Nat
  | .bool => 1
  | .u8 => 2
  | .u32 => 3
  | .u64 => 4

def packTagsLow (types : Array Lemma.Core0.Ty) : Nat := Id.run do
  let mut result := 0
  for _h : index in [:min 8 types.size] do
    result := result ||| (typeTag types[index]! <<< (8 * index))
  return result

def packTagsHigh (types : Array Lemma.Core0.Ty) : Nat := Id.run do
  let mut result := 0
  for _h : index in [8:types.size] do
    if index < maximumArguments then
      result := result ||| (typeTag types[index]! <<< (8 * (index - 8)))
  return result

structure Configuration where
  suiteId : Nat
  sourceSeed : Nat
  runtimeSeed : Nat
  deriving Repr, BEq, Inhabited

def Configuration.validate (config : Configuration) : Except String Unit := do
  for (label, value) in #[
      ("suite id", config.suiteId),
      ("source seed", config.sourceSeed),
      ("runtime seed", config.runtimeSeed)] do
    unless value < 2 ^ 64 do
      throw s!"memory-suite {label} exceeds UInt64"

def validateSignature (args : Array Lemma.Core0.Ty) : Except String Unit := do
  unless args.size ≤ maximumArguments do
    throw s!"memory-suite root has {args.size} arguments; maximum is {maximumArguments}"

def headerFieldNames : Array String := #[
  "magic",
  "version",
  "header_bytes",
  "control_bytes",
  "suite_id",
  "case_id",
  "root_id",
  "argument_count",
  "argument_tags_0_7",
  "argument_tags_8_15",
  "source_seed",
  "runtime_seed",
  "reserved_zero",
  "reserved_zero",
  "reserved_zero",
  "reserved_zero"
]

end Lemma.Compiler.Test.MemoryABI
