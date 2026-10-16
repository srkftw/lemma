import Lemma.Courses.BrowseHistory
import Lemma.Courses.WorkspaceCodec

/-! Component fixture only. Prepared checker outcomes are not guest evidence. -/
namespace BrowseHistoryTests
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
  readFault : Option UInt64 := none
  readonly : Bool := false

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
      if (← state.get).readFault.any (fun point => a ≤ point && point < a+width) then run state (next 17 0)
      else run state (next 0 (← IO.ofExcept <| read (← state.get) a width))
    else if op == .virtualWrite8 || op == .virtualWrite64 then
      if (← state.get).readonly then throw <| IO.userError "browse selection acquired write authority"
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
  state.modify fun m => {m with readonly := true}
  let known ← ok state (BrowseHistory.location wrap2 1 1)
  expect (known == wrap2+PackageWorkspace.selection) "explicit selection lost priority"
  let before ← state.get
  state.modify fun m => {m with readonly := true}
  let found ← ok state (BrowseHistory.location wrap1 1 1)
  expect (found == wrap1+PackageWorkspace.attempts+128 && (← word state (found+40)) == 3)
    "detached answer lost its latest retained installed source"
  expect ((← state.get).memory == before.memory && (← word state (wrap1+48)) == 2)
    "browsing changed current applicability/evidence/history"
  for (address,value) in #[(wrap1+48,514),(wrap1+PackageWorkspace.attempts+128+120,0)] do
    state.set before
    set state address value
    let damaged ← state.get
    state.modify fun m => {m with readonly := true}
    let rejected ← run state (BrowseHistory.location wrap1 1 1)
    expect (rejected.1 != 0 && (← state.get).memory == damaged.memory)
      "malformed source acquired display authority or wrote state"
  state.set {before with readonly := true,readFault := some (wrap1+48)}
  let fault ← run state (BrowseHistory.location wrap1 1 1)
  expect (fault == (17,0) && (← state.get).memory == before.memory) "read fault was hidden or mutated state"
  state.set {before with readonly := false}
  let empty : UInt64 := 0x49000
  let _ ← ok state (PackageWorkspace.create empty doc 1 1)
  let unknown ← state.get
  state.modify fun m => {m with readonly := true}
  expect ((← run state (BrowseHistory.location empty 1 1)) == (0,0) &&
    (← state.get).memory == unknown.memory) "Unknown history inherited an installed source"
  IO.println "BROWSE_HISTORY1:PASS actual validated readonly Actions/current-priority/retained-source/Unknown/malformed/readfault; no evidence/Save/guest-CPU claim"
end BrowseHistoryTests

def main : IO Unit := BrowseHistoryTests.check
