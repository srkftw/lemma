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

namespace NotebookReaderTests
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

def check : IO Unit := do
  let some filename ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE" | throw <| IO.userError "actual package required"
  let image ← IO.FS.readBinFile filename
  let r ← IO.mkRef ({} : Model)
  base r image
  let baseline ← r.get
  r.modify fun m => {m with returns := #[(0,88),(0,777)]}
  let requested ← run r (notebookAction% "bookmarkRequestSave")
  expect (requested.1 == 0 && (← word r (stateBase+160)) == 1 &&
    (← word r (stateBase+136)) == 1 && (← word r (app+224)) == 1 &&
    (← word r (app+216)) == 4 && (← word r live) == 0 &&
    (← word r (staging+56)) == 2 && (← word r (staging+72)) == 5 &&
    (← word r (stateBase+224)) == ReaderLocation.object 1 &&
    (← word r (stateBase+216)) == 128 && unchanged baseline (← r.get))
    "Save must start actual separate Store transaction without publishing reader or modifying authority"
  r.modify fun m => {m with returns := #[(IPCABI.wouldBlock,0)]}
  let blocked ← run r (notebookAction% "pumpBookmarkSave")
  expect (blocked.1 == 0 && (← word r live) == 0 && (← word r (app+216)) == 4 &&
    (← word r (stateBase+136)) == 1) "pending transaction acknowledged reader early"
  -- BEGIN reply starts actual WRITE; WRITE reply starts actual COMMIT.
  for (operation,phase) in #[(2,2),(3,3)] do
    reply r operation 7
    r.modify fun m => {m with returns := #[(0,128),(0,778)]}
    let advanced ← run r (notebookAction% "pumpBookmarkSave")
    expect (advanced.1 == 0 && (← word r (stateBase+160)) == phase &&
      (← word r live) == 0 && (← word r (app+216)) == 4)
      "BEGIN/WRITE response published reader before durable COMMIT response"
  reply r 4 8
  r.modify fun m => {m with returns := #[(0,128),(0,88)]}
  let committed ← run r (notebookAction% "pumpBookmarkSave")
  expect (committed.1 == 0 && (← word r (stateBase+160)) == 0 &&
    (← word r (stateBase+136)) == 0 && (← word r (app+224)) == 0 &&
    (← word r (app+216)) == 5 && (← word r live) == ReaderLocation.magic &&
    (← word r (live+56)) == 2 && unchanged baseline (← r.get))
    "durable reply must publish exact saved node with authority and workspace unchanged"
  -- A failed transaction clears pending publication and keeps the old live reader.
  let acknowledged ← r.get
  r.modify fun m => {m with returns := #[(0,88),(0,779)]}
  let second ← run r (notebookAction% "bookmarkRequestSave")
  expect (second.1 == 0 && (← word r (staging+72)) == 6 &&
    (← word r (app+216)) == 5 && (← word r (live+72)) == 5)
    "second actual transaction did not preserve the acknowledged reader while pending"
  r.modify fun m => {m with returns := #[(231,0),(0,88)]}
  let failed ← run r (notebookAction% "pumpBookmarkSave")
  expect (failed.1 == 0 && (← word r (stateBase+136)) == 2 &&
    (← word r (app+224)) == 0 && (← word r (app+216)) == 5 &&
    (← word r (live+72)) == 5 && unchanged acknowledged (← r.get))
    "failed Store transaction must preserve last acknowledged reader without Saved"
  -- Every independent active-work gate rejects Save before staging or syscalls.
  for offset in #[160,112,144,536] do
    base r image
    set r (stateBase+offset) 1
    let before ← r.get
    let ignored ← run r (notebookAction% "bookmarkRequestSave")
    expect (ignored.1 == 0 && (← r.get).memory == before.memory && (← r.get).calls.isEmpty)
      "Save crossed active raw/checker/transaction boundary"
  -- Lookup publishes private selection only; current mathematical authority is immutable.
  base r image
  let captured ← run r (ReaderLocation.capture staging pkg image.size.toUInt64 4 1 1 11)
  expect (captured.1 == 0) "actual reader capture failed"
  let beforeLookup ← r.get
  let found ← run r (notebookAction% "finishBookmarkLookup")
  expect (found.1 == 0 && (← word r (app+176)) == 4 &&
    (← word r (app+208)) == 4 && unchanged beforeLookup (← r.get))
    "lookup changed submitted goal or failed to restore arbitrary node"
  let resolved ← run r (notebookAction% "validateBookmarkPackage")
  expect (resolved.1 == 0 && (← word r (app+208)) == 5 && unchanged beforeLookup (← r.get))
    "current validated package did not resolve saved source anchor"
  -- StoreNotFound alone is a valid legacy absence; no other error may select fallback.
  base r image
  set r (app+96) 8
  set r (app+208) 2
  set r (context+128+56) 5
  set r (context+128+64) 230
  let absent ← run r (notebookAction% "pumpBookmarkOpen")
  expect (absent.1 == 0 && (← word r (app+208)) == 3 &&
    (← word r (app+96)) == 4 && (← r.get).calls.isEmpty)
    "missing reader record did not preserve validated legacy history fallback"
  -- A pending actual read cannot publish or invent a bookmark.
  base r image
  set r (app+96) 8
  set r (app+208) 2
  set r (context+128+56) 1
  set r (context+128+72) 300000000
  set r (context+128+32) 99
  set r (context+128+0) (ReaderLocation.object 1)
  set r (context+128+8) staging
  set r (context+128+16) 128
  set r (context+128+40) 128
  set r (context+128+48) 8
  set r (context+128+80) 1
  r.modify fun m => {m with returns := #[(0,1),(IPCABI.wouldBlock,0)]}
  let waiting ← run r (notebookAction% "pumpBookmarkOpen")
  expect (waiting.1 == 0 && (← word r live) == 0 && (← word r (app+208)) == 2 &&
    (← word r (app+96)) == 8) "pending read manufactured a bookmark"
  -- Full actual128-byte READ reply remains unpublished until a separate exact EOF reply.
  let capturedRead ← run r (ReaderLocation.capture 0x33f000 pkg image.size.toUInt64 4 1 1 11)
  expect (capturedRead.1 == 0) "reader fixture capture failed"
  let header : Array UInt64 := #[IPCABI.messageMagic,IPCABI.replyKind,3,8,0,192,0,0,
    Lemma.Services.Store.Protocol.magic,1,5,1,ReaderLocation.object 1,8,1,128]
  for i in [:header.size] do set r (incoming+i.toUInt64*8) header[i]!
  for i in [:16] do set r (incoming+128+i.toUInt64*8) (← word r (0x33f000+i.toUInt64*8))
  r.modify fun m => {m with returns := #[(0,1),(0,256)]}
  let body ← run r (notebookAction% "pumpBookmarkOpen")
  expect (body.1 == 0 && (← word r (context+128+56)) == 2 &&
    (← word r live) == 0 && (← word r (app+208)) == 2)
    "complete body published reader without a separately observed EOF"
  r.modify fun m => {m with returns := #[(0,2),(0,778)]}
  let eofRequest ← run r (notebookAction% "pumpBookmarkOpen")
  expect (eofRequest.1 == 0 && (← word r (context+128+56)) == 3 && (← word r live) == 0)
    "EOF request admission published unacknowledged reader"
  let eofRequestID ← word r (context+128+48)
  let eof : Array UInt64 := #[IPCABI.messageMagic,IPCABI.replyKind,3,eofRequestID,0,64,0,0,
    Lemma.Services.Store.Protocol.magic,1,5,1,ReaderLocation.object 1,8,1,0]
  for i in [:eof.size] do set r (incoming+i.toUInt64*8) eof[i]!
  r.modify fun m => {m with returns := #[(0,3),(0,128)]}
  let complete ← run r (notebookAction% "pumpBookmarkOpen")
  expect (complete.1 == 0 && (← word r (context+128+56)) == 4 &&
    (← word r (app+208)) == 4 && (← word r (app+176)) == 4 &&
    (← word r (live+72)) == 11 && (← word r (app+216)) == 11)
    "exact EOF did not publish the independently framed actual reader record"
  -- A deferred lookup may outlive a course-close edge, but must not spin a closed reader.
  base r image
  set r (app+96) 4
  set r (app+208) 1
  let closedBusy ← run r (notebookAction% "bookmarkBusy")
  expect (closedBusy == (0,0)) "closed course retains a ghost busy reader lookup"
  set r (stateBase+512) 1
  let openBusy ← run r (notebookAction% "bookmarkBusy")
  expect (openBusy == (0,1)) "open deferred reader is allowed to block instead of making progress"
  base r image
  set r (app+96) 8
  set r (app+208) 2
  set r (context+128+32) 99
  set r (context+128+56) 1
  r.modify fun m => {m with returns := #[(0,0),(IPCABI.canceled,0)]}
  let beforeCancel ← r.get
  let canceled ← run r (notebookAction% "cancelBookmarkWork")
  expect (canceled.1 == 0 && (← word r (context+128+32)) == 0 &&
    (← word r (app+208)) == 0 && (← word r (app+96)) == 0 &&
    (← r.get).calls.size == 2 && unchanged beforeCancel (← r.get))
    "reader cancellation lost terminal consumption, private phase or mathematical isolation"
  IO.println "PASS actual Notebook reader Save/poll/failure/authority/component Actions"
end NotebookReaderTests
#eval NotebookReaderTests.check
