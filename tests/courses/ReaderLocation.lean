import Lemma.Courses.ReaderLocation

/-! Component semantics only: actual maintained Actions, owned RAM and injected
access faults. No Store/barrier/guest CPU execution is implied by this fixture. -/
namespace ReaderLocationTests
open Lemma.Core0.Memory
open Lemma.Courses

def base : UInt64 := 0x20000
def location : UInt64 := 0x40000
def package : UInt64 := 0x50000

structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 262144 0)
  writeFault : Option UInt64 := none
  readFault : Option UInt64 := none
  readonly : Bool := false

private def read (m : Model) (address width : UInt64) : Except String UInt64 := do
  if address < base || m.memory.size.toUInt64 < width || m.memory.size.toUInt64-width < address-base then
    throw "reader-location read escaped declared owned RAM fixture"
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
    if budget < count.toNat then throw <| IO.userError "reader-location exceeded bound"
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
      if (← state.get).readonly then throw <| IO.userError "reader resolution acquired write authority"
      let width := if op == .virtualWrite8 then 1 else 8
      if (← state.get).writeFault.any (fun point => a ≤ point && point < a+width) then
        run state (next 17 0)
      else
        state.set (← IO.ofExcept <| write (← state.get) a width b)
        run state (next 0 0)
    else throw <| IO.userError "reader-location acquired unexpected operation"
  | _ => throw <| IO.userError "reader-location acquired unexpected Action"
private def ok (state : IO.Ref Model) (action : Action) : IO UInt64 := do
  let (s,value) ← run state action
  if s != 0 then throw <| IO.userError s!"actual imported reader-location Action failed {s}"
  return value
private def set (state : IO.Ref Model) (address value : UInt64) : IO Unit := do
  state.set (← IO.ofExcept <| write (← state.get) address 8 value)
private def word (state : IO.Ref Model) (address : UInt64) : IO UInt64 := do
  IO.ofExcept <| read (← state.get) address 8
private def expect (condition : Bool) (message : String) : IO Unit := do
  unless condition do throw <| IO.userError message

def check : IO Unit := do
  let some filename ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE"
    | throw <| IO.userError "reader fixture requires actual published package bytes"
  let image ← IO.FS.readBinFile filename
  let state ← IO.mkRef ({} : Model)
  for i in [:image.size] do
    state.set (← IO.ofExcept <| write (← state.get) (package+i.toUInt64) 1 image[i]!.toUInt64)
  set state 0x30000 0x1122334455667788
  let baseline ← state.get
  let identity ← word state (package+24)
  let edition ← word state (package+32)
  let crc ← word state (package+80)
  let count ← word state (package+40)
  expect (count == 8) "fixture is not the actual eight-node reference sequence"
  let mut sawNonExercise := false
  for i in [:count.toNat] do
    let ordinal := i.toUInt64
    let kind ← word state (package+128+ordinal*192+8)
    if kind != 3 then sawNonExercise := true
    let node ← ok state (ReaderLocation.capture location package image.size.toUInt64 ordinal 1 1 (ordinal+1))
    expect (node == ordinal+1) "capture did not retain actual authored node"
    let expected : Array UInt64 := #[ReaderLocation.magic,1,1,1,identity,edition,crc,node,node,ordinal+1,0,0,0,0,0,0]
    for j in [:16] do
      expect ((← word state (location+j.toUInt64*8)) == expected[j]!) "complete browsing record differs"
    let captured ← state.get
    let mut restored := captured.memory
    for j in [:128] do restored := restored.set! ((location-base).toNat+j) baseline.memory[(location-base).toNat+j]!
    expect (restored == baseline.memory) "capture changed package/document/unowned staging bytes"
    state.modify fun m => {m with readonly := true}
    expect ((← run state (ReaderLocation.validate location 1 1)) == (0,node)) "record validation failed"
    expect ((← run state (ReaderLocation.resolve location 1 1 package image.size.toUInt64)) == (0,node)) "actual package node failed readonly resolution"
    expect ((← state.get).memory == captured.memory) "resolution wrote browsing or mathematical state"
    state.modify fun m => {m with readonly := false}
  expect sawNonExercise "only exercise nodes were tested"
  let valid ← state.get
  for (action,status) in [
      (ReaderLocation.capture location package image.size.toUInt64 8 1 1 1,PackageFormat.selectionAbsent),
      (ReaderLocation.capture location package image.size.toUInt64 0 0 1 1,PackageFormat.malformed),
      (ReaderLocation.capture location package image.size.toUInt64 0 1 65 1,PackageFormat.malformed),
      (ReaderLocation.capture location package image.size.toUInt64 0 1 1 0,PackageFormat.malformed),
      (ReaderLocation.capture location package image.size.toUInt64 0 1 1 0x8000000000000000,PackageFormat.resourceLimit),
      (ReaderLocation.capture package package image.size.toUInt64 0 1 1 1,PackageFormat.malformed)] do
    expect ((← run state action).1 == status) "invalid capture precedence differs"
    expect ((← state.get).memory == valid.memory) "rejected capture changed bytes"
  for (offset,value,status) in [(8,2,PackageFormat.unsupported),(16,2,PackageFormat.malformed),
      (64,1,PackageFormat.malformed),(80,1,PackageFormat.malformed)] do
    state.set valid
    set state (location+offset) value
    let corrupt ← state.get
    expect ((← run state (ReaderLocation.validate location 1 1)) == (status,0)) "bad version/owner/anchor/reserved word returned a selected node"
    expect ((← state.get).memory == corrupt.memory) "invalid record validation wrote bytes"
  for (offset,value) in [(32,identity+1),(40,edition+1),(48,crc ^^^ 1)] do
    state.set valid
    set state (location+offset) value
    let stale ← state.get
    expect ((← run state (ReaderLocation.resolve location 1 1 package image.size.toUInt64)) == (PackageFormat.selectionAbsent,0)) "stale package binding became current context"
    expect ((← state.get).memory == stale.memory) "stale resolution altered record"
  state.set {valid with readFault := some (package+24)}
  expect ((← run state (ReaderLocation.capture location package image.size.toUInt64 0 1 1 9)) == (17,0)) "actual package access fault was hidden"
  expect ((← state.get).memory == valid.memory) "source read fault began publication"
  state.set {valid with writeFault := some (location+40)}
  expect ((← run state (ReaderLocation.capture location package image.size.toUInt64 0 1 1 9)) == (17,0)) "staging write fault was hidden"
  expect ((← word state location) == 0) "partial staging retained a published magic"
  IO.println "READER_LOCATION1:PASS all8actualnodes/completebytes/readonly/stale/invalid/fault/unpublished; noStore/CPU/proofauthorityclaim"
end ReaderLocationTests

def main : IO Unit := ReaderLocationTests.check
