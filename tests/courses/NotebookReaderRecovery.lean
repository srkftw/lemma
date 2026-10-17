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

namespace NotebookReaderRecoveryTests
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

private def pkg : UInt64 := 0x332000
private def staging : UInt64 := 0x32af00
private def live : UInt64 := workspace + 3712
private def base (r : IO.Ref Model) (image : ByteArray) : IO Unit := do
  r.set ({} : Model)
  for i in [:image.size] do
    r.set (← IO.ofExcept <| write (← r.get) (pkg+i.toUInt64) 1 image[i]!.toUInt64)
  for (a,v) in #[(stateBase+752,12),(stateBase+72,1),(stateBase+80,1),
    (stateBase+128,7),(stateBase+16,9),(stateBase+24,10),
    (stateBase+32,1650),(stateBase+40,2200),
    (app+0,image.size.toUInt64),(app+8,1),(app+32,2),(app+208,3),(app+216,4)] do set r a v
private def reply (r : IO.Ref Model) (operation sequence : UInt64) : IO Unit := do
  let request ← word r (stateBase+176)
  let object := ReaderLocation.object 1
  let fields : Array UInt64 := #[IPCABI.messageMagic,IPCABI.replyKind,3,request,0,64,0,0,
    Lemma.Services.Store.Protocol.magic,1,operation,1,object,sequence,0,0]
  for i in [:fields.size] do set r (Lemma.Applications.Notebook.incoming+i.toUInt64*8) fields[i]!
private def unchanged (before after : Model) : Bool :=
  before.memory.extract (workspace-0x10000).toNat (workspace-0x10000+3712).toNat ==
  after.memory.extract (workspace-0x10000).toNat (workspace-0x10000+3712).toNat &&
  before.memory.extract (doc-0x10000).toNat (doc-0x10000+4096).toNat ==
  after.memory.extract (doc-0x10000).toNat (doc-0x10000+4096).toNat

private def controlReply (r : IO.Ref Model) (operation sequence detail epoch : UInt64) : IO Unit := do
  let request ← word r (stateBase+176)
  let fields : Array UInt64 := #[IPCABI.messageMagic,IPCABI.replyKind,3,request,0,72,0,0,
    Lemma.Services.Store.Protocol.magic,3,operation,1,0,sequence,detail,8,epoch]
  for i in [:fields.size] do set r (Lemma.Applications.Notebook.incoming+i.toUInt64*8) fields[i]!

private def readReply (r : IO.Ref Model) (sequence count : UInt64) : IO Unit := do
  let request ← word r (stateBase+176)
  let fields : Array UInt64 := #[IPCABI.messageMagic,IPCABI.replyKind,3,request,0,64+count,0,0,
    Lemma.Services.Store.Protocol.magic,1,5,1,ReaderLocation.object 1,sequence,0,count]
  for i in [:fields.size] do set r (Lemma.Applications.Notebook.incoming+i.toUInt64*8) fields[i]!
  for i in [:(count/8).toNat] do
    set r (Lemma.Applications.Notebook.incoming+128+i.toUInt64*8) (← word r (staging+i.toUInt64*8))

private def drive (r : IO.Ref Model) (action : Action) (outcomes : Array (UInt8 × UInt64)) : IO Unit := do
  r.modify fun m => {m with returns := outcomes}
  let actual ← run r action
  expect (actual.1 == 0 && (← r.get).returns.isEmpty) "actual Action failed or skipped declared syscall outcome"

private def pendingCommit (r : IO.Ref Model) (image : ByteArray) : IO Unit := do
  base r image
  drive r (notebookAction% "bookmarkRequestSave") #[(0,88),(0,777)]
  for (operation,phase) in #[(2,2),(3,3)] do
    reply r operation 7
    drive r (notebookAction% "readerRecoverablePumpSave") #[(0,128),(0,778)]
    expect ((← word r (stateBase+160)) == phase && (← word r live) == 0) "BEGIN/WRITE manufactured Saved"

def check : IO Unit := do
  let some filename ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE" | throw <| IO.userError "actual package required"
  let image ← IO.FS.readBinFile filename
  let r ← IO.mkRef ({} : Model)
  base r image
  drive r (Lemma.Documents.MathematicsClosure.create doc 1 1) #[]
  drive r (PackageWorkspace.create workspace doc 1 1) #[]
  set r (app+128) 1
  set r (app+136) 1
  set r (app+152) 1
  let fresh ← r.get
  drive r (notebookAction% "readerPrepareSelection") #[]
  expect ((← word r (app+152)) == 0 && unchanged fresh (← r.get) &&
    (← r.get).calls == fresh.calls && (← word r (app+128)) == 1 &&
    (← word r (app+136)) == 1 && (← word r (app+216)) == 4)
    "fresh chooser performed implicit edition read, selected a goal, or acquired IPC/Save authority"
  r.set fresh
  set r (stateBase+512) 1
  set r (app+96) 4
  set r (app+32) 0
  let opening ← r.get
  drive r (notebookAction% "readerPackageWork") #[]
  let expected ← IO.ofExcept <| write opening (app+152) 8 0
  expect ((← r.get).memory == expected.memory && (← r.get).calls == opening.calls)
    "joined reader work issued the implicit missing-edition request after lookup"
  for lookup in #[1,2,4,5] do
    r.set fresh
    set r (app+208) lookup
    let before ← r.get
    drive r (notebookAction% "readerPrepareSelection") #[]
    expect ((← r.get).memory == before.memory && (← r.get).calls == before.calls)
      "in-flight or saved-reader lookup lost its existing automatic load"
  r.set fresh
  r.modify fun m => {m with fault := some (workspace+24)}
  expect ((← run r (notebookAction% "readerPrepareSelection")).1 == 17 &&
    (← word r (app+152)) == 1) "workspace owner-read fault silently selected/cleared a course request"
  pendingCommit r image
  let pending ← r.get
  drive r (notebookAction% "readerRecoverablePumpSave") #[(IPCABI.wouldBlock,0)]
  expect ((← word r live) == 0 && (← word r (app+224)) == 1) "pending reader published or lost its marker"
  reply r 4 8
  drive r (notebookAction% "readerRecoverablePumpSave") #[(0,128),(0,88)]
  expect ((← word r (stateBase+672)) == 8 && (← word r (app+216)) == 5 &&
    (← word r (app+224)) == 0 && (← word r (live+56)) == 2 && unchanged pending (← r.get))
    "ordinary COMMIT did not publish exact reader while retaining workspace/math"

  -- The peer may have persisted the pending COMMIT; the lost reply is an
  -- explicit uncertain outcome. No fixture models a real peer or durability.
  pendingCommit r image
  let expectedSource := (← r.get).memory.extract (staging-0x10000).toNat (staging-0x10000+128).toNat
  let ticket ← word r (stateBase+176)
  drive r (notebookAction% "readerRecoverablePumpSave") #[(227,0),(0,88)]
  expect ((← word r (stateBase+648)) == 1 && (← word r (stateBase+632)) == 7 &&
    (← word r (stateBase+600)) == staging && (← word r (stateBase+608)) == 128 &&
    (← word r (stateBase+616)) == ReaderLocation.object 1 && (← word r (stateBase+624)) == 3 &&
    (← word r (stateBase+680)) == ticket && (← word r (stateBase+136)) == 2 &&
    (← word r (app+224)) == 1 && (← word r live) == 0 && (← word r (app+216)) == 4)
    "uncertain COMMIT lost immutable reader/failure ticket or manufactured Saved"
  let held ← r.get
  for (offset,value) in #[(stateBase+72,2),(stateBase+80,2),(stateBase+536,1),
      (stateBase+752,11),(app+32,1),(app+224,0),(staging+48,1234)] do
    r.set held
    set r offset value
    let before ← r.get
    let (status,_) ← run r ((notebookAction% "readerRecoverableValidate") staging 128 (ReaderLocation.object 1) 3)
    expect (status != 0 && (← r.get).memory == before.memory && (← r.get).calls == before.calls)
      "foreign owner/stale package/active checker/incomplete allocation changed held record or acquired IPC"
  r.set held
  r.modify fun m => {m with fault := some (pkg+24)}
  expect ((← run r ((notebookAction% "readerRecoverableValidate") staging 128 (ReaderLocation.object 1) 3)).1 == 17)
    "actual package read fault was hidden"
  r.set held
  drive r ((notebookAction% "readerRecoverableToolbar") 7) #[(0,88),(0,900)]
  expect ((← word r (stateBase+160)) == 8 && (← word r (stateBase+640)) == 1 &&
    (← word r (Lemma.Applications.Notebook.outgoing+16)) == 14 &&
    (← word r (Lemma.Applications.Notebook.outgoing+40)) == ticket && (← word r live) == 0)
    "explicit retry did not use original failed ticket and remount control"
  let waiting ← r.get
  for button in #[0,1,7,8] do
    let before ← r.get
    let actual ← run r ((notebookAction% "readerRecoverableToolbar") button)
    expect (actual.1 == 0 && (← r.get).memory == before.memory && (← r.get).calls == before.calls)
      "in-progress reconciliation admitted navigation, another Save or workspace mutation"
  drive r (notebookAction% "readerRecoverablePumpSave") #[(IPCABI.wouldBlock,0)]
  expect ((← word r (stateBase+160)) == 8 && (← word r live) == 0) "pending remount acknowledged reader"
  r.set waiting
  controlReply r 14 8 2 1
  drive r (notebookAction% "readerRecoverablePumpSave") #[(0,136),(0,901)]
  expect ((← word r (stateBase+160)) == 10 && (← word r (stateBase+688)) == 1 &&
    (← word r (Lemma.Applications.Notebook.outgoing+16)) == 5 &&
    (← word r (Lemma.Applications.Notebook.outgoing+48)) == 0 &&
    (← word r (Lemma.Applications.Notebook.outgoing+56)) == 128 && (← word r live) == 0)
    "known+1 remount duplicated PUT or published before exact readback"
  let reading ← r.get
  readReply r 8 128
  drive r (notebookAction% "readerRecoverablePumpSave") #[(0,256),(0,902)]
  expect ((← word r (stateBase+160)) == 11 && (← word r (stateBase+648)) == 1 &&
    (← word r (Lemma.Applications.Notebook.outgoing+16)) == 5 &&
    (← word r (Lemma.Applications.Notebook.outgoing+48)) == 128 && (← word r live) == 0)
    "full matching payload skipped exact EOF or manufactured Saved"
  let eof ← r.get
  readReply r 8 0
  drive r (notebookAction% "readerRecoverablePumpSave") #[(0,128),(0,88)]
  expect ((← word r (stateBase+648)) == 0 && (← word r (stateBase+672)) == 8 &&
    (← word r (stateBase+136)) == 0 && (← word r (app+224)) == 0 &&
    (← word r (app+216)) == 5 && (← word r (live+56)) == 2 && unchanged held (← r.get))
    "exact READ/EOF reconciliation failed to publish only the retained reader"
  expect ((← r.get).memory.extract (staging-0x10000).toNat (staging-0x10000+128).toNat == expectedSource)
    "reconciliation rewrote immutable retained source"
  -- Independently corrupt each edge that could falsely accept readback.
  for (checkpoint,mode) in #[(reading,0),(reading,1),(eof,2),(waiting,3)] do
    r.set checkpoint
    if mode == 3 then
      controlReply r 14 8 2 0 -- no newer connection epoch
      drive r (notebookAction% "readerRecoverablePumpSave") #[(0,136),(0,88)]
    else
      readReply r (if mode == 1 then 9 else 8) (if mode == 2 then 8 else 128)
      if mode == 0 then set r (Lemma.Applications.Notebook.incoming+128+120) 1
      drive r (notebookAction% "readerRecoverablePumpSave") #[(0,if mode == 2 then 136 else 256),(0,88)]
    expect ((← word r (stateBase+136)) == 2 && (← word r (stateBase+648)) == 1 &&
      (← word r live) == 0 && (← word r (app+224)) == 1 && (← word r (app+216)) == 4)
      "mismatched byte/sequence/extra tail/old epoch became Saved"
  -- An observed old sequence permits exactly one ordinary transaction for
  -- the retained bytes. It is still Pending; a BEGIN reply is not durability.
  r.set waiting
  controlReply r 14 7 2 1
  drive r (notebookAction% "readerRecoverablePumpSave") #[(0,136),(0,88),(0,903)]
  expect ((← word r (stateBase+160)) == 1 && (← word r (stateBase+648)) == 1 &&
    (← word r (Lemma.Applications.Notebook.outgoing+16)) == 2 &&
    (← word r (Lemma.Applications.Notebook.outgoing+32)) == ReaderLocation.object 1 &&
    (← word r (Lemma.Applications.Notebook.outgoing+56)) == 128 && (← word r live) == 0)
    "known sequence resubmission changed bytes/object or became Saved"
  IO.println "READER_RECOVERY5_ACTIONS:PASS actual COMMIT/lostACK/retention/packagebinding/remount/exactREAD/EOF/resubmit; component only"
end NotebookReaderRecoveryTests

#eval NotebookReaderRecoveryTests.check
