import Lean
import Lemma.Applications.Notebook

/-! Test-only constant resolution calls the actual private maintained Action.
No target AST/program/expected notebook implementation is generated here. The
fixture returns modeled syscall transport results and independently authored
framing bytes; it does not establish a real kernel, checker or Store barrier. -/
open Lean Elab Term
elab "notebookAction% " short:str : term => do
  let env ← getEnv
  let wanted := "Lemma.Applications.Notebook." ++ short.getString
  let found := env.constants.toList.filter fun (name,_) =>
    ((privateToUserName? name).getD name).toString == wanted
  if found.length != 1 then throwError "actual private Action owner missing/ambiguous: {wanted}"
  return mkConst found.head!.1

namespace NotebookPackageTests
open Lemma.Core0.Memory Lemma.User Lemma.Courses

def stateBase : UInt64 := 0x20800
def context : UInt64 := 0x33c000
def app : UInt64 := context + 2048
def incoming : UInt64 := context + 256
def outgoing : UInt64 := context + 512
def doc : UInt64 := 0x329000
def workspace : UInt64 := 0x33b000

structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 4194304 0)
  reads : Array UInt64 := #[]
  writes : Array UInt64 := #[]
  calls : Array (UInt64 × UInt64 × UInt64 × UInt64 × UInt64 × UInt64) := #[]
  returns : Array (UInt8 × UInt64) := #[]
  fault : Option UInt64 := none

private def read (m : Model) (address width : UInt64) : Except String UInt64 := do
  if address < 0x10000 || m.memory.size.toUInt64 < width || m.memory.size.toUInt64-width < address-0x10000 then
    throw "package caller escaped independently bounded RAM"
  return (List.range width.toNat).foldl (fun v i => v |||
    (m.memory[(address-0x10000).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0
private def write (m : Model) (address width value : UInt64) : Except String Model := do
  let _ ← read m address width
  return {m with memory := (List.range width.toNat).foldl (fun bytes i =>
    bytes.set! ((address-0x10000).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) m.memory}
partial def run (ref : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
    let (s,v) ← run ref first
    run ref (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if budget < count.toNat then throw <| IO.userError "package caller loop bound exceeded"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status == 0 then
        let result ← run ref (step i.toUInt32 count value a b c d)
        status := result.1; value := result.2
    run ref (next status value)
  | .platform op a b c d e f next => do
    let m ← ref.get
    if op == .virtualRead8 || op == .virtualRead64 then
      let width := if op == .virtualRead8 then 1 else 8
      ref.set {m with reads := m.reads.push a}
      if m.fault.any (fun point => a ≤ point && point < a+width) then run ref (next 17 0)
      else run ref (next 0 (← IO.ofExcept <| read m a width))
    else if op == .virtualWrite8 || op == .virtualWrite64 then
      let width := if op == .virtualWrite8 then 1 else 8
      if m.fault.any (fun point => a ≤ point && point < a+width) then run ref (next 17 0)
      else
        let m ← IO.ofExcept <| write m a width b
        ref.set {m with writes := m.writes.push a}
        run ref (next 0 0)
    else if op == .syscall then
      let some result := m.returns[0]? | throw <| IO.userError s!"unexpected guest syscall {a}/{b}/{c}/{d}/{e}/{f}"
      ref.set {m with calls := m.calls.push (a,b,c,d,e,f), returns := m.returns.extract 1 m.returns.size}
      run ref (next result.1 result.2)
    else throw <| IO.userError "unexpected guest primitive"
  | _ => throw <| IO.userError "unexpected caller Action"
private def set (r : IO.Ref Model) (a v : UInt64) : IO Unit := do r.set (← IO.ofExcept <| write (← r.get) a 8 v)
private def word (r : IO.Ref Model) (a : UInt64) : IO UInt64 := do IO.ofExcept <| read (← r.get) a 8
private def expect (b : Bool) (reason : String) : IO Unit := unless b do throw <| IO.userError reason
private def response (r : IO.Ref Model) (count mode sequence : UInt64) : IO Unit := do
  let fields : Array UInt64 := #[IPCABI.messageMagic,IPCABI.replyKind,3,266,0,64+count,0,0,
    Lemma.Services.Store.Protocol.magic,1,5,1,PackageFormat.object 1 1,sequence,mode,count]
  for i in [:fields.size] do set r (incoming+i.toUInt64*8) fields[i]!
private def setupEOF (r : IO.Ref Model) (count mode sequence : UInt64) : IO Unit := do
  r.set ({} : Model)
  for (a,v) in #[(stateBase+16,9),(stateBase+72,1),(stateBase+128,7),
    (context+64,10),(context+80,99),(app+0,4040),(app+32,5),(app+48,1),(app+56,1)] do set r a v
  response r count mode sequence
  r.modify fun m => {m with returns := #[(0,128+count)]}

def check : IO Unit := do
  let r ← IO.mkRef ({} : Model)
  -- Real Store framing must not overwrite the lazy-page allocation counter.
  -- This reproduces the observed CPU error95: old offset768 is outgoing magic.
  let counter := stateBase + 752
  let packet := Lemma.Applications.Notebook.outgoing
  let framed ← run r (Lemma.Services.Store.Protocol.header packet 1 1 0 0 0 0)
  expect (framed.1 == 0 && (← word r packet) == Lemma.Services.Store.Protocol.magic &&
    (← word r counter) == 0) "Store framing clobbered the package allocation counter"
  r.modify fun m => {m with returns := (Array.range 12).map fun i => (0,0x332000+i.toUInt64*4096)}
  let allocated ← run r (notebookAction% "allocatePackage")
  expect (allocated.1 == 0 && (← word r counter) == 12 &&
    (← word r packet) == Lemma.Services.Store.Protocol.magic && (← r.get).calls.size == 12)
    "framed Store traffic prevents the actual12-page allocation Action"
  let calls := (← r.get).calls
  let reframed ← run r (Lemma.Services.Store.Protocol.header packet 5 1 1 0 0 64)
  let repeated ← run r (notebookAction% "allocatePackage")
  expect (reframed.1 == 0 && repeated == (0,0) && (← word r counter) == 12 &&
    (← r.get).calls == calls) "Store read framing causes package page reallocation"
  r.set ({} : Model)
  r.modify fun m => {m with returns := #[(0,0x332000),(11,0)]}
  let exhausted ← run r (notebookAction% "allocatePackage")
  expect (exhausted.1 == 11 && (← word r counter) == 1 && (← r.get).calls.size == 2)
    "allocation exhaustion lost the successful private prefix or its status"
  let framedAgain ← run r (Lemma.Services.Store.Protocol.header packet 1 1 0 0 0 0)
  r.modify fun m => {m with returns := (Array.range 11).map fun i => (0,0x333000+i.toUInt64*4096)}
  let retried ← run r (notebookAction% "allocatePackage")
  expect (framedAgain.1 == 0 && retried.1 == 0 && (← word r counter) == 12 &&
    (← r.get).calls.size == 13 && (← r.get).calls[2]!.2.1 == 0x333000)
    "framed retry repeated an allocated page or lost the remaining prefix"
  setupEOF r 0 1 8
  let good ← run r ((notebookAction% "packageReadEOF") 5)
  expect (good == (0,0) && (← word r (app+32)) == 2 && (← word r (context+80)) == 0 &&
    (← word r (stateBase+128)) == 8 && (← word r (app+72)) == 1)
    "valid independent EOF did not publish only validated read phase"
  expect ((← r.get).calls.size == 1 && (← r.get).calls[0]!.1 == 67) "EOF consulted unexpected transport"
  for (count,mode,sequence,status) in #[(1,1,8,240),(0,3,8,240),(0,1,6,234)] do
    setupEOF r count mode sequence
    let result ← run r ((notebookAction% "packageReadEOF") 5)
    expect (result.1.toUInt64 == status && (← word r (app+32)) == 5 && (← word r (app+72)) == 0)
      "trailing bytes/mode/sequence regression admitted visible package"
  setupEOF r 0 1 8
  r.modify fun m => {m with returns := #[(IPCABI.wouldBlock,0)]}
  let waiting ← run r ((notebookAction% "packageReadEOF") 5)
  expect (waiting == (0,0) && (← word r (context+80)) == 99 && (← word r (app+32)) == 5)
    "pending EOF mutated terminal state"
  setupEOF r 0 1 8
  r.modify fun m => {m with fault := some (app+32)}
  let failed ← run r ((notebookAction% "packageReadEOF") 5)
  expect (failed.1 == 17 && (← word r (context+80)) == 0 && (← word r (app+32)) == 5)
    "actual publication-write fault was hidden/rolled back"
  r.set ({} : Model)
  set r (stateBase+752) 11
  let unopened ← run r (notebookAction% "pumpPackageWork")
  expect (unopened == (0,0) && (← r.get).reads == #[stateBase+752] && (← r.get).writes.isEmpty)
    "partially allocated package context was accessed"
  setupEOF r 0 1 8
  r.modify fun m => {m with returns := #[(IPCABI.alreadyCompleted,0),(0,128)]}
  let originalDoc := (← r.get).memory.extract (doc-0x10000).toNat (doc-0x10000+2496).toNat
  let canceled ← run r (notebookAction% "cancelPackageRead")
  expect (canceled == (0,0) && (← word r (context+80)) == 0 && (← word r (app+32)) == 4 &&
    (← r.get).calls.map (·.1) == #[25,67]) "already-completed cancellation did not consume once"
  expect ((← r.get).memory.extract (doc-0x10000).toNat (doc-0x10000+2496).toNat == originalDoc)
    "read cancellation changed mathematical bytes"
  -- A valid stale/absent binding may not manufacture a known submission.
  r.set ({} : Model)
  let created ← run r (Lemma.Documents.MathematicsClosure.create doc 1 1)
  expect (created.1 == 0) "real Doc8 setup failed"
  let wrapped ← run r (PackageWorkspace.create workspace doc 1 1)
  expect (wrapped.1 == 0) "real workspace setup failed"
  set r (stateBase+72) 1; set r (stateBase+80) 1
  let before := (← r.get).memory
  let noEndpoint ← run r (notebookAction% "beginPackageArithmetic")
  expect (noEndpoint.1 == 241 && (← r.get).memory == before && (← r.get).calls.isEmpty)
    "missing independent checker manufactured evidence or mutated document"
  let label : UInt64 → UInt64 → UInt64 → UInt64 := notebookAction% "packageIdentityCharacter"
  let revision : UInt64 := 0x8000000000000001
  expect (label 4 revision 0 == 56 && label 19 revision 0 == 49 && label 22 revision 1 == 49)
    "visible revision loses bit63 or domain is not actual canonical field"
  r.set ({} : Model)
  let tile : UInt32 → UInt32 → UInt64 → UInt64 → UInt64 → UInt64 → UInt64 → Action :=
    notebookAction% "packageTileStep"
  for i in [:130] do
    let observed ← run r (tile i.toUInt32 130 0 1650 8195 0 0)
    expect (observed.1 == 0) "actual delta dirty-tile queue failed"
  expect ((← word r (stateBase+456)) == 2 && (← word r (stateBase+472)) == 2 &&
      (← r.get).calls.isEmpty) "delta projection bypassed/overfilled the real queue or acquired device authority"
  let before := (← r.get).memory
  for i in [:130] do
    let observed ← run r (tile i.toUInt32 130 0 1650 0 0 0)
    expect (observed.1 == 0) "empty delta projection failed"
  expect ((← r.get).memory == before) "empty delta dirtied pixels or changed the pending queue"
  r.set ({} : Model)
  let created ← run r (Lemma.Documents.MathematicsClosure.create doc 1 1)
  expect (created.1 == 0) "sparse presentation Doc8 setup failed"
  let old ← IO.mkRef (← r.get)
  let oldResult ← run old (Lemma.Courses.Arithmetic.render doc 1650)
  let newResult ← run r (Lemma.Courses.Arithmetic.renderSparse doc 1650)
  expect (oldResult == newResult && newResult.1 == 0 &&
      (← old.get).memory == (← r.get).memory && (← old.get).reads == (← r.get).reads &&
      (← old.get).writes == (← r.get).writes && (← r.get).calls.isEmpty)
    "sparse math presentation changed actual framebuffer bytes or ordered memory effects"
  -- The actual opener classifies only a64-byte prefix, then schedules a full
  -- exact-length object read. New phase5 must retain the ordinary busy guard.
  for compact in #[false,true] do
    r.set ({} : Model)
    let _ ← run r (Lemma.Documents.MathematicsClosure.create doc 1 1)
    let made ← run r (PackageWorkspace.create workspace doc 1 1)
    expect (made.1 == 0) "workspace header opener setup failed"
    let saved : UInt64 := 0x32a000
    let length ← if compact then do
      let encoded ← run r (WorkspaceCodec.encode workspace saved 1 1)
      expect (encoded.1 == 0) "compact header setup failed"
      pure encoded.2
    else do
      for i in [:8] do set r (saved+i.toUInt64*8) (← word r (workspace+i.toUInt64*8))
      pure 3712
    for (a,v) in #[(stateBase+72,1),(stateBase+80,1),(stateBase+752,12),
        (app+96,1),(context+128+56,4)] do set r a v
    r.modify fun m => {m with calls := #[],returns := #[(0,123)]}
    let opened ← run r (notebookAction% "pumpOpenPackageCourse")
    expect (opened == (0,0) && (← word r (app+96)) == 5 &&
        (← word r (context+128+16)) == length && (← word r (context+128+8)) == saved &&
        (← word r (context+128+88)) == 0 && (← word r (context+128+56)) == 0)
      "actual raw/compact header bypassed full exact reader or independent EOF"
    let busy ← run r (notebookAction% "packageBusy")
    expect (busy == (0,1)) "full workspace read phase5 exposed idle writing policy"
    set r (context+128+32) 99
    let immutable := (← r.get).memory.extract (workspace-0x10000).toNat (workspace-0x10000+3712).toNat
    r.modify fun m => {m with calls := #[],returns := #[(0,0),(0,128)]}
    let canceled ← run r (notebookAction% "cancelPackageWork")
    expect (canceled == (0,0) && (← word r (app+96)) == 0 &&
        (← word r (context+128+32)) == 0 && (← word r (context+128+56)) == 5 &&
        (← r.get).calls.map (·.1) == #[25,67])
      "new opening phase failed to cancel/consume its actual transaction before ink"
    expect ((← r.get).memory.extract (workspace-0x10000).toNat (workspace-0x10000+3712).toNat == immutable)
      "opening cancellation published or damaged active workspace"
    if compact then
      -- Run the actual full-record branch through decode, all3712 staging
      -- bytes and live adoption. Stop at its following course-visible flag so
      -- this fixture does not substitute for controller/render execution.
      set r (app+96) 5
      set r (context+128+56) 4
      r.modify fun m => {m with fault := some (stateBase+512),calls := #[],returns := #[]}
      let restored ← run r (notebookAction% "pumpOpenPackageCourse")
      expect (restored.1 == 17 && (← word r (app+96)) == 4 && (← r.get).calls.isEmpty &&
          (← r.get).memory.extract (saved-0x10000).toNat (saved-0x10000+3712).toNat == immutable &&
          (← r.get).memory.extract (workspace-0x10000).toNat (workspace-0x10000+3712).toNat == immutable)
        "actual full compact opener failed before complete workspace adoption (sector-copy limit regression)"
  IO.println "NOTEBOOK_PACKAGE_ACTIONS:PASS actual private EOF/framing/sequence/wait/fault/cancel/partial-allocation/checker/header/busy guards; no CPU or durability claim"
end NotebookPackageTests

def main : IO Unit := NotebookPackageTests.check
