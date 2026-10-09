import Lemma.Core0.IR

/-!
Closed wire contract for the Task 002 typed scalar test runner.

The contract is test-only: it transports cases to an audited freestanding
image and does not broaden the Core0 source language.  Every field is a
little-endian `UInt64`; each record keeps sixteen transport slots so malformed
unused values can be rejected rather than ignored.
-/

namespace Lemma.Compiler.Test.ScalarABI

def name : String := "lemma-scalar-test-v1"

/-- Little-endian integer corresponding to the eight fixture bytes `LEMMA002`. -/
def magic : Nat := 0x323030414d4d454c

def version : Nat := 1
def headerWords : Nat := 16
def headerBytes : Nat := 128
def maxArguments : Nat := 16
def recordWords : Nat := 17
def recordBytes : Nat := 136
def maxCases : Nat := 29

def typeTag : Lemma.Core0.Ty → Nat
  | .bool => 1
  | .u8 => 2
  | .u32 => 3
  | .u64 => 4

def packTagsFrom (types : Array Lemma.Core0.Ty) (start : Nat) : Nat := Id.run do
  let mut packed := 0
  for offset in [:8] do
    let index := start + offset
    if h : index < types.size then
      packed := packed + typeTag types[index] * 2 ^ (8 * offset)
  return packed

def packTagsLow (types : Array Lemma.Core0.Ty) : Nat :=
  packTagsFrom types 0

def packTagsHigh (types : Array Lemma.Core0.Ty) : Nat :=
  packTagsFrom types 8

structure Configuration where
  suiteId : Nat
  sourceSeed : Nat
  runtimeSeed : Nat
  deriving BEq, Inhabited, Repr

def Configuration.validate (config : Configuration) : Except String Unit := do
  for (label, value) in [
      ("suite id", config.suiteId),
      ("source seed", config.sourceSeed),
      ("runtime seed", config.runtimeSeed)] do
    unless value < 2 ^ 64 do
      throw s!"scalar test ABI {label} exceeds UInt64"

end Lemma.Compiler.Test.ScalarABI
