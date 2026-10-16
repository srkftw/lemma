import Lemma.Courses.PackageWorkspace
import Lemma.Courses.WorkspaceCodec
import Lemma.Documents.MathematicsEntry
import Lemma.Courses.Arithmetic

/-! Independent bounded RAM fixture executing the imported guest Actions.
Prepared negative records are fixture inputs, never published guest evidence.
Actual checker/kernel/controller execution and durability are separate. -/
namespace NumberEntryTests
open Lemma.Core0.Memory
open Lemma.Courses
open Lemma.Documents

def base : UInt64 := 0x20000
def doc : UInt64 := 0x30000

structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 262144 0)
  writeFault : Option UInt64 := none

private def read (m : Model) (address width : UInt64) : Except String UInt64 := do
  if address < base || m.memory.size.toUInt64 < width || m.memory.size.toUInt64-width < address-base then
    throw "workspace read escaped declared owned RAM fixture"
  return (List.range width.toNat).foldl (fun value i => value |||
    (m.memory[(address-base).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0
private def write (m : Model) (address width value : UInt64) : Except String Model := do
  let _ ← read m address width
  let bytes := (List.range width.toNat).foldl
    (fun bytes i => bytes.set! ((address-base).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) m.memory
  return {m with memory := bytes}
partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
    let (s,value) ← run state first
    run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if budget < count.toNat then throw <| IO.userError "workspace exceeded bound"
    let mut s : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if s == 0 then
        let result ← run state (step i.toUInt32 count value a b c d)
        s := result.1
        value := result.2
    run state (next s value)
  | .platform op a b _ _ _ _ next => do
    if op == .virtualRead8 || op == .virtualRead64 then
      let width := if op == .virtualRead8 then 1 else 8
      run state (next 0 (← IO.ofExcept <| read (← state.get) a width))
    else if op == .virtualWrite8 || op == .virtualWrite64 then
      let width := if op == .virtualWrite8 then 1 else 8
      if (← state.get).writeFault.any (fun point => a ≤ point && point < a+width) then
        run state (next 17 0)
      else
        state.set (← IO.ofExcept <| write (← state.get) a width b)
        run state (next 0 0)
    else throw <| IO.userError "workspace acquired unexpected operation"
  | _ => throw <| IO.userError "workspace acquired unexpected Action"
private def ok (state : IO.Ref Model) (action : Action) : IO UInt64 := do
  let (s,value) ← run state action
  if s != 0 then throw <| IO.userError s!"actual imported workspace Action failed {s}"
  return value
private def set (state : IO.Ref Model) (address value : UInt64) : IO Unit := do
  state.set (← IO.ofExcept <| write (← state.get) address 8 value)
private def word (state : IO.Ref Model) (address : UInt64) : IO UInt64 := do
  IO.ofExcept <| read (← state.get) address 8
private def expect (condition : Bool) (message : String) : IO Unit := do
  unless condition do throw <| IO.userError message

def check : IO Unit := do
  let state ← IO.mkRef ({} : Model)
  let _ ← ok state (MathematicsClosure.create doc 1 1)
  set state (doc+56) 5
  set state (doc+64) 6
  let outcome := Mathematics.result 1 5 6 0 0 0 8
  expect (outcome == 1) "independent prepared arithmetic premise differs"
  let _ ← ok state (MathematicsClosure.completeExecution doc 1 1 outcome 11 8)
  let historical ← state.get
  let _ ← ok state (MathematicsEntry.press doc 10)
  expect ((← word state (doc+56)) == 0 && (← word state (doc+40)) == 2) "clear/revision"
  expect ((← word state (doc+96)) == 0 && (← word state (doc+104)) == 0) "stale evidence retained"
  for i in [:8] do
    expect ((← word state (doc+1920+i.toUInt64*8)) == 0) "stale execution retained"
  let _ ← ok state (MathematicsEntry.press doc 9)
  let _ ← ok state (MathematicsEntry.press doc 9)
  let beforeLimit ← state.get
  let limited ← run state (MathematicsEntry.press doc 9)
  expect (limited == (0,2) && beforeLimit.memory == (← state.get).memory) "overflow mutated bytes"
  let _ ← ok state (MathematicsEntry.press doc 11)
  expect ((← word state (doc+56)) == 9) "backspace"
  let beforeSame ← state.get
  let same ← run state (MathematicsEntry.set doc 56 9)
  expect (same == (0,0) && beforeSame.memory == (← state.get).memory) "same value made revision"
  for field in [:5] do
    let column := (#[6,8,10,13,16] : Array UInt64)[field]!
    let _ ← ok state (Arithmetic.press doc (column*12) 60)
    let _ ← ok state (MathematicsEntry.press doc 10)
    let _ ← ok state (MathematicsEntry.press doc 5)
    expect ((← word state (doc+56+field.toUInt64*8)) == 5) "selected field differs"
  -- A typed zero denominator is editable but is never Verified by the checker.
  let _ ← ok state (MathematicsEntry.set doc 64 0)
  expect (Mathematics.result 1 5 0 0 0 0 8 != 1) "division by zero Verified"
  let after ← state.get
  let relative := (doc-base).toNat
  for (first,last) in #[(256,832),(832,1856),(1984,2496)] do
    expect (historical.memory.data.extract (relative+first) (relative+last) ==
      after.memory.data.extract (relative+first) (relative+last)) "edit lost immutable history/events"
  for (offset,value) in #[(48,1),(57,1),(96,1),(56,100)] do
    let before ← state.get
    let rejected ← run state (MathematicsEntry.set doc offset value)
    expect (rejected.1 == 234 && before.memory == (← state.get).memory) "invalid setter touched bytes"
  -- All ordinary selectors above execute the real shared UI declaration.
  -- Small nonzero indices are invalid under Doc8 and must never be accepted.
  for selected in (#[(1 : UInt64),2,3,4,5]) do
    set state (doc+160) selected
    let before ← state.get
    let rejected ← run state (MathematicsEntry.press doc 1)
    expect (rejected.1 == 234 && before.memory == (← state.get).memory) "index substituted for actual selected offset"
  set state (doc+160) 5
  let before ← state.get
  let rejected ← run state (MathematicsEntry.press doc 1)
  expect (rejected.1 == 234 && before.memory == (← state.get).memory) "invalid selection mutated"
  set state (doc+160) 0
  set state (doc+40) 0x7ffffffffffffffe
  let before ← state.get
  let exhausted ← run state (MathematicsEntry.press doc 10)
  expect (exhausted.1 == 235 && before.memory == (← state.get).memory) "revision exhaustion mutated"
  IO.println "NUMBER_ENTRY1:PASS actual Actions/5fields/clear/backspace/idempotence/overflow/stale-evidence/history/zero-denominator/rejections; component only"
end NumberEntryTests

def main : IO Unit := NumberEntryTests.check
