import Lemma.Courses.PackageWorkspace
import Lemma.Courses.WorkspaceCodec

/-! Independent bounded RAM fixture executing the imported guest Actions.
Prepared negative records are fixture inputs, never published guest evidence.
Actual checker/kernel/controller execution and durability are separate. -/
namespace CourseWorkspaceTests
open Lemma.Core0.Memory
open Lemma.Courses
open Lemma.Documents

def base : UInt64 := 0x20000
def doc : UInt64 := 0x30000
def nextDoc : UInt64 := 0x31000
def wrap0 : UInt64 := 0x40000
def wrap1 : UInt64 := 0x42000
def wrap2 : UInt64 := 0x44000
def scratch : UInt64 := 0x46000
def submitted : UInt64 := 0x47000
def package : UInt64 := 0x50000

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
  let some filename ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE"
    | throw <| IO.userError "workspace fixture requires real published package"
  let image ← IO.FS.readBinFile filename
  let state ← IO.mkRef ({} : Model)
  for i in [:image.size] do
    state.set (← IO.ofExcept <| write (← state.get) (package+i.toUInt64) 1 image[i]!.toUInt64)
  let _ ← ok state (MathematicsClosure.create doc 1 1)
  set state (doc+56) 5
  set state (doc+64) 6
  let _ ← ok state (MathematicsClosure.completeExecution doc 1 1 1 11 8)
  let _ ← ok state (MathematicsClosure.validate doc 1 1)
  let _ ← ok state (PackageWorkspace.create wrap0 doc 1 1)
  expect ((← word state (wrap0+48)) == 0) "migration inherited a package origin"
  let _ ← ok state (Mathematics.revise doc)
  let _ ← ok state (Mathematics.hint doc)
  let _ ← ok state (PackageWorkspace.stageRefresh wrap0 doc wrap1)
  let _ ← ok state (PackageWorkspace.validate wrap1 1 1)
  let _ ← ok state (PackageWorkspace.captureSelection wrap1 package image.size.toUInt64 2 scratch)
  let _ ← ok state (PackageWorkspace.snapshotSelection wrap1 submitted)
  let _ ← ok state (Mathematics.copyCurrent (wrap1+PackageWorkspace.inner) nextDoc)
  let _ ← ok state (MathematicsClosure.completeExecution nextDoc 2 1 1 17 8)
  let _ ← ok state (PackageWorkspace.stageCompleted wrap1 nextDoc submitted 17 wrap2)
  let _ ← ok state (PackageWorkspace.validate wrap2 1 1)
  expect ((← word state (wrap2+48)) == 258) "new attempt did not keep old Unknown row"
  expect ((← word state (wrap2+PackageWorkspace.attempts)) == 0) "old Unknown row gained package metadata"
  expect ((← word state (wrap2+PackageWorkspace.attempts+128)) == PackageBinding.magic) "actual new package row missing"
  let _ ← ok state (Mathematics.edit nextDoc 56 1)
  let _ ← ok state (PackageWorkspace.stageUnknownSelection wrap2 nextDoc wrap0)
  expect ((← word state (wrap0+48)) == 2) "builtin selection erased old known package history"
  let _ ← ok state (MathematicsClosure.completeExecution nextDoc 3 1 2 21 8)
  let _ ← ok state (PackageWorkspace.stageCompletedUnknown wrap0 nextDoc 21 wrap1)
  let _ ← ok state (PackageWorkspace.validate wrap1 1 1)
  expect ((← word state (wrap1+48)) == 2) "builtin completion inherited a package or lost history"
  expect ((← word state (wrap1+PackageWorkspace.attempts+256)) == 0) "builtin new row not Unknown"
  let actualGood ← state.get
  -- Lossless envelope2 retains both actual Known and Unknown provenance, all
  -- source anchors and the complete Doc8/learner history, not only live fields.
  for original in #[wrap0,wrap1,wrap2] do
    let length ← ok state (WorkspaceCodec.encode original 0x48000 1 1)
    let _ ← ok state (WorkspaceCodec.decode 0x48000 length 0x4a000 1 1)
    for i in [:464] do
      expect ((← word state (original+i.toUInt64*8)) == (← word state (0x4a000+i.toUInt64*8)))
        "compact envelope lost Known/Unknown provenance or document/history bytes"
  -- The resource override is a real revision of an independently valid Doc8.
  -- The package remains its original declared budget8; changing that binding
  -- to0 would already fail PackageBinding v1, so it is not an independent oracle.
  let _ ← ok state (Mathematics.copyCurrent (wrap2+PackageWorkspace.inner) nextDoc)
  let _ ← ok state (Mathematics.revise nextDoc)
  set state (nextDoc+136) 0
  let _ ← ok state (PackageWorkspace.stageRefresh wrap2 nextDoc wrap0)
  let _ ← ok state (PackageWorkspace.captureSelection wrap0 package image.size.toUInt64 2 scratch)
  let _ ← ok state (PackageWorkspace.validate wrap0 1 1)
  let _ ← ok state (PackageBinding.validate (wrap0+PackageWorkspace.selection))
  let _ ← ok state (MathematicsClosure.validate (wrap0+PackageWorkspace.inner) 1 1)
  let staleBudget ← run state (PackageWorkspace.snapshotSelection wrap0 submitted)
  expect (staleBudget.1 == PackageFormat.selectionAbsent) "current snapshot accepted a differing declared budget"
  let _ ← ok state (PackageBinding.capture submitted package image.size.toUInt64 2 3)
  let _ ← ok state (MathematicsClosure.completeExecution nextDoc 3 1 5 27 0)
  let _ ← ok state (MathematicsClosure.validate nextDoc 1 1)
  let beforeBudgetReject ← state.get
  let badCompletion ← run state (PackageWorkspace.stageCompleted wrap0 nextDoc submitted 27 wrap1)
  expect (badCompletion.1 == PackageFormat.malformed) "package completion accepted a differing actual request budget"
  expect ((beforeBudgetReject.memory.data.extract (wrap0-base).toNat (wrap0-base+PackageWorkspace.bytes).toNat) ==
    ((← state.get).memory.data.extract (wrap0-base).toNat (wrap0-base+PackageWorkspace.bytes).toNat)) "rejected budget mutated active source"
  -- Pose the unsafe published row directly in the independent fixture: both
  -- constituent validators accept, while the wrapper must reject the budget
  -- mismatch. This negative fixture is not a guest publication or checker.
  for i in [:464] do set state (wrap1+i.toUInt64*8) (← word state (wrap0+i.toUInt64*8))
  for i in [:312] do set state (wrap1+PackageWorkspace.inner+i.toUInt64*8) (← word state (nextDoc+i.toUInt64*8))
  for i in [:16] do set state (wrap1+PackageWorkspace.attempts+256+i.toUInt64*8) (← word state (submitted+i.toUInt64*8))
  set state (wrap1+48) 262
  let _ ← ok state (PackageBinding.validate (wrap1+PackageWorkspace.attempts+256))
  let _ ← ok state (MathematicsClosure.validate (wrap1+PackageWorkspace.inner) 1 1)
  let changedBudget ← run state (PackageWorkspace.validate wrap1 1 1)
  expect (changedBudget.1 == PackageFormat.malformed) "known attempt accepted a differing declared budget"
  state.set actualGood
  let good ← state.get
  -- Swap two individually valid learner events. Original Doc8 validation still
  -- accepts their semantics; wrapper transition must reject changed old order.
  let _ ← ok state (Mathematics.copyCurrent (wrap1+PackageWorkspace.inner) nextDoc)
  let a0 ← word state (nextDoc+832)
  let a1 ← word state (nextDoc+840)
  let b0 ← word state (nextDoc+848)
  let b1 ← word state (nextDoc+856)
  set state (nextDoc+832) b0
  set state (nextDoc+840) b1
  set state (nextDoc+848) a0
  set state (nextDoc+856) a1
  let _ ← ok state (MathematicsClosure.validate nextDoc 1 1)
  let changed ← run state (PackageWorkspace.stageRefresh wrap1 nextDoc wrap2)
  expect (changed.1 == PackageFormat.malformed) "valid reordered learner prefix was accepted"
  state.set good
  let before ← state.get
  state.modify fun m => {m with writeFault := some (wrap2+8)}
  let failed ← run state (PackageWorkspace.stageRefresh wrap1 nextDoc wrap2)
  expect (failed.1 == 17) "staging access error was masked"
  let after ← state.get
  expect ((before.memory.data.extract (wrap1-base).toNat (wrap1-base+PackageWorkspace.bytes).toNat) ==
    (after.memory.data.extract (wrap1-base).toNat (wrap1-base+PackageWorkspace.bytes).toNat)) "staging failure changed active source"
  IO.println "COURSE_WORKSPACE_ACTIONS:PASS known/Unknown history, ordered learner-prefix, exact request budget and private staging faults; component only; no CPU/durability claim"
end CourseWorkspaceTests

def main : IO Unit := CourseWorkspaceTests.check
