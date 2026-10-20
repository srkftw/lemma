import Lean
import Lemma.School.Client
import Lemma.Applications.Notebook
import Std.Data.HashMap

/-! Execute the actual private Notebook actions over independent copied Store
reply bytes. This finite RAM/IPC observer covers reader ordering and selected
node precedence; it is not CPU execution, a journal barrier or a learner run. -/
open Lean Elab Term
elab "schoolNotebook% " short:str : term => do
  let wanted := "Lemma.Applications.Notebook." ++ short.getString
  let found := (← getEnv).constants.toList.filter fun (name,_) =>
    ((privateToUserName? name).getD name).toString == wanted
  if found.length != 1 then throwError "maintained Notebook Action missing/ambiguous: {wanted}"
  return mkConst found.head!.1

namespace NotebookSchoolTests
open Lemma.Core0.Memory Lemma.User Lemma.Courses
private def base : UInt64 := 0x20800
private def context : UInt64 := 0x33c000
private def app : UInt64 := context+2048
private def record : UInt64 := context+128
private def incoming : UInt64 := context+256
private def scratch : UInt64 := context+1024
structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  syscalls : Array (UInt8 × UInt64) := #[]
  writes : Array UInt64 := #[]
  forbiddenPage : Option UInt64 := none
private def word (m : Model) (a : UInt64) : UInt64 := m.words.getD a 0
private def write (m : Model) (a v : UInt64) : Model :=
  {m with words := m.words.insert a v, writes := m.writes.push a}
partial def run (r : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
    let (s,v) ← run r first
    run r (next s v)
  | .boundedFoldU64 bound step count value a b c d next => do
    if count.toNat > bound then throw <| IO.userError "actual fold bound exceeded"
    let mut s : UInt8 := 0
    let mut v := value
    for i in [:count.toNat] do
      if s == 0 then
        let result ← run r (step i.toUInt32 count v a b c d)
        s := result.1; v := result.2
    run r (next s v)
  | .platform op a b _ _ _ _ next => do
    let m ← r.get
    if op == .virtualRead64 || op == .virtualWrite64 || op == .virtualRead8 || op == .virtualWrite8 then
      if m.forbiddenPage == some (a-a%4096) then
        throw <| IO.userError s!"access to unallocated private page {a-a%4096} at {a}"
    if op == .virtualRead64 then
      if a%8 != 0 then throw <| IO.userError "unaligned read"
      run r (next 0 (word m a))
    else if op == .virtualWrite64 then
      if a%8 != 0 then throw <| IO.userError "unaligned write"
      r.set (write m a b); run r (next 0 0)
    else if op == .virtualRead8 then
      run r (next 0 ((word m (a-a%8) >>> (a%8*8)) &&& 255))
    else if op == .virtualWrite8 then
      let shift := a%8*8
      let value := (word m (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((b &&& 255) <<< shift)
      r.set (write m (a-a%8) value); run r (next 0 0)
    else if op == .syscall then
      let some result := m.syscalls[0]? | throw <| IO.userError s!"unexpected actual syscall {a}"
      r.set {m with syscalls := m.syscalls.extract 1 m.syscalls.size}
      run r (next result.1 result.2)
    else throw <| IO.userError "undeclared actual primitive"
  | _ => throw <| IO.userError "unexpected actual Action"
private def put (r : IO.Ref Model) (a v : UInt64) : IO Unit := r.modify fun m => write m a v
private def get (r : IO.Ref Model) (a : UInt64) : IO UInt64 := return word (← r.get) a
private def expect (b : Bool) (why : String) : IO Unit := unless b do throw <| IO.userError why
private def reply (r : IO.Ref Model) (packet operation ns object request sequence count detail : UInt64) : IO Unit := do
  for (i,value) in (#[IPCABI.messageMagic,IPCABI.replyKind,3,request,0,64+count,0,0,
      Lemma.Services.Store.Protocol.magic,1,operation,ns,object,sequence,detail,count]).zipIdx do
    put r (packet+value.toUInt64*8) i

private def floorChecks : IO Unit := do
  let r ← IO.mkRef ({} : Model)
  put r (base+760) 1; put r (base+128) 20; put r (app+256) 10
  put r (incoming+104) 15
  let a ← run r (schoolNotebook% "packageReadFloor")
  expect (a.1 == 0 && (← get r (base+128)) == 20 && (← get r (app+256)) == 15)
    "valid earlier read reply was rejected or lowered the concurrent queue frontier"
  put r (incoming+104) 14
  let b ← run r (schoolNotebook% "packageReadFloor")
  expect (b.1 == 234 && (← get r (base+128)) == 20 && (← get r (app+256)) == 15)
    "reader-local sequence regression was accepted"
  put r (incoming+104) 21
  let c ← run r (schoolNotebook% "packageReadFloor")
  expect (c.1 == 0 && (← get r (base+128)) == 21 && (← get r (app+256)) == 21)
    "new foreground reply failed to advance the maximum observation frontier"
  put r (base+760) 0; put r (incoming+104) 20
  let d ← run r (schoolNotebook% "packageReadFloor")
  expect (d.1 == 234 && (← get r (base+128)) == 21)
    "historical reader sequence policy changed"

private def recordChecks : IO Unit := do
  let r ← IO.mkRef ({} : Model)
  let target : UInt64 := 0x33d000
  for (a,v) in #[(base+760,1),(base+128,20),(record,1),(record+8,target),
      (record+16,8),(record+24,0),(record+32,42),(record+40,8),
      (record+48,7),(record+80,1),(record+88,0),(record+96,10)] do put r a v
  reply r incoming 5 1 1 7 15 8 1
  put r (incoming+128) 0x123456789abcdef0
  r.modify fun m => {m with syscalls := #[(0,136)]}
  let a ← run r ((schoolNotebook% "pollPackageRecordPiece") 1)
  expect (a.1 == 0 && (← get r target) == 0x123456789abcdef0 &&
    (← get r (record+96)) == 15 && (← get r (base+128)) == 20 && (← get r (record+56)) == 2)
    "fixed record reader failed valid concurrent reply or exact copy/EOF transition"
  put r (record+24) 0; put r (record+32) 42; put r target 99
  reply r incoming 5 1 1 7 14 8 1
  r.modify fun m => {m with syscalls := #[(0,136)]}
  let b ← run r ((schoolNotebook% "pollPackageRecordPiece") 1)
  expect (b.1 == 234 && (← get r target) == 99 && (← get r (base+128)) == 20)
    "fixed record regression was copied before rejection"

private def selectedNodeCheck : IO Unit := do
  let r ← IO.mkRef ({} : Model)
  for (a,v) in #[(base+760,1),(app+232,1),(app+128,802),(app+136,1),
      (app+176,0),(app+208,4),(record+56,4)] do put r a v
  for (value,i) in (#[PackageCommand.selectedMagic,1,1,802,1,0x1234,2,0]).zipIdx do
    put r (scratch+i.toUInt64*8) value
  let a ← run r (schoolNotebook% "schoolSelectionWork")
  expect (a.1 == 0 && (← get r (app+176)) == 2 && (← get r (app+208)) == 3 &&
    (← get r (app+232)) == 2 && (← get r (app+160)) == 0x1234)
    "same-publication review node was replaced by its older bookmark"
  let writes := (← r.get).writes
  expect (!(writes.any fun a => 0x329000 ≤ a && a < 0x32a000 || 0x33b000 ≤ a && a < 0x33c000))
    "source selection rewrote mathematical document/workspace"

private def saveChecks : IO Unit := do
  let r ← IO.mkRef ({} : Model)
  for (a,v) in #[(base+760,1),(base+128,20),(base+160,1),(base+168,42),
      (base+232,2),(base+72,1),(base+224,1),(base+176,7),(base+216,0),(base+384,16)] do put r a v
  reply r Lemma.Applications.Notebook.incoming 2 1 1 7 15 0 0
  r.modify fun m => {m with syscalls := #[(0,128),(0,43)]}
  let a ← run r (schoolNotebook% "pumpSave")
  expect (a.1 == 0 && (← get r (base+128)) == 20 && (← get r (base+160)) == 3 &&
      (← get r (base+232)) == 4 && (← get r (base+168)) == 43)
    "older foreground Begin lowered concurrent commit frontier or failed real next Commit"

private def bootGateCheck : IO Unit := do
  let r ← IO.mkRef ({forbiddenPage:=some Lemma.User.Multimodal.records} : Model)
  put r (base+712) 99; put r (base+720) 99; put r (base+736) 99; put r (base+760) 99
  let cleared ← run r ((schoolNotebook% "clearStep") 0 80 0 0 0 0 0)
  expect (cleared.1 == 0 && (← get r (base+712)) == 0 && (← get r (base+720)) == 0 && (← get r (base+736)) == 0 && (← get r (base+760)) == 0)
    "boot did not clear always-mapped queue lifecycle gates before fresh Save"
  for school in #[0,1] do
    put r (base+760) school;put r (base+16) 7;put r (base+72) 1
    put r (base+224) 1;put r (base+384) 16;put r (base+176) 9
    r.modify fun m => {m with syscalls:=#[(0,42)]}
    let issued ← run r ((schoolNotebook% "issue") 2 0 0 0)
    expect (issued.1 == 0 && (← get r (base+168)) == 42 && (← get r (base+232)) == 2)
      "first Save failed before multimodal/queue allocation in ordinary or school root"

private def queueHandoffCheck : IO Unit := do
  let tutor := Lemma.User.Multimodal.state+144
  -- The actual queue pump cannot reserve request IDs or allocate its arena
  -- while any foreground owner/intent still exists. No syscall is available.
  for owner in #[base+160,base+112,base+144,base+104,base+536,tutor+16] do
    let r ← IO.mkRef ({} : Model)
    put r (base+760) 1;put r (base+176) 7;put r owner 1
    let held ← run r (schoolNotebook% "schoolQueuePump")
    expect (held.1 == 0 && (← get r (base+712)) == 0 && (← get r (base+176)) == 7)
      "queue initialization borrowed a live foreground request/call"
  let r ← IO.mkRef ({} : Model)
  put r (base+760) 1;put r (base+176) 7
  r.modify fun m => {m with syscalls := (Array.range 8).map fun i => (0,SchoolSubmission.arena+i.toUInt64*4096)}
  let initialized ← run r (schoolNotebook% "schoolQueuePump")
  expect (initialized.1 == 0 && (← get r (base+712)) == 1 && (← get r (base+176)) == 1000007 &&
    (← get r SchoolSubmission.arena) == 40 && (← r.get).syscalls.isEmpty)
    "idle queue did not reserve once and prepare its actual recovery"
  -- A real queue read now owns the one task IPC slot. Save must retain its
  -- buffers in deferred phase8; it must not issue a competing Store Begin.
  put r SchoolSubmission.arena 41
  put r (base+160) 1
  let owns ← run r (schoolNotebook% "schoolQueueOwnsIPC")
  let deferred ← run r ((schoolNotebook% "issue") 2 0 64 0)
  expect (owns == (0,1) && deferred.1 == 0 && (← get r (base+160)) == 8 &&
    (← get r (base+176)) == 1000007 && (← r.get).syscalls.isEmpty)
    "foreground Save started before actual queue read completion"
  -- Transient controls preserve exact context and coalesce without borrowing
  -- document/IPC state. A changed view rejects replay before any Store call.
  put r (base+72) 1;put r (base+80) 1;put r (base+512) 0
  r.modify fun m => {m with syscalls := #[(0,88)]}
  let queued ← run r ((schoolNotebook% "schoolQueueControl") 1400 64)
  let operation ← get r (tutor+16)
  expect (queued.1 == 0 && operation == ((0x100000000 : UInt64) ||| (1400 : UInt64) ||| ((64 : UInt64) <<< 16)) &&
    (← get r (tutor+32)) == 1 && (← get r (tutor+56)) == 1)
    "queued navigation/Save control lost its original page binding"
  put r (base+80) 2
  let changed ← run r (schoolNotebook% "schoolControlContext")
  expect (changed.1 == 175 && (← get r (base+176)) == 1000007)
    "deferred control was silently retargeted to a changed page"
  put r (base+80) 1
  let original ← run r (schoolNotebook% "schoolControlContext")
  expect (original.1 == 0) "unchanged original home control was rejected"

private def schoolJoinCheck : IO Unit := do
  let tutor := Lemma.User.Multimodal.records+1024
  let tutorState := Lemma.User.Multimodal.state+144
  let school := Lemma.User.Multimodal.records+1152
  let ask : Lemma.School.Client.GuestAsk := {
    session:=99,consent:=1,revision:=7,object:=0x504b000000000001,sequence:=11,
    source:=803,edition:=2,task_id:=4,cutoff:=100,now:=101,deadline:=140,grants:=1 }
  let binding : Lemma.School.Client.SessionBinding := {
    school:="component-school",actor:="learner-a",enrollment:="enrolled",session:="session-a",
    guestSession:=99,course:=803,revision:=2,policy:=2,generation:=12,expires:=500,
    authority:="0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20",bindingRecord:=27 }
  let invitation ← IO.ofExcept <| Lemma.School.Client.invitation binding ask
  let r ← IO.mkRef ({} : Model)
  -- The complete invitation has already passed the actual reader's EOF. Both
  -- pending presentation flags are still set, exactly as in native 727→454244.
  for (a,v) in #[(base+760,1),(base+752,12),(base+512,1),(base+80,1),
      (base+72,1),(base+176,100),(base+128,20),(base+24,3),
      (app,invitation.size.toUInt64),(app+32,2),(app+72,1),(app+144,1),
      (app+128,60000),(app+136,11),(app+232,2),(app+240,1),
      (tutorState+24,1),(Lemma.Applications.Notebook.mathematics+40,7)] do put r a v
  for (value,i) in (#[99,1,7,0x504b000000000001,10,1,803,2,4,512,0] : Array UInt64).zipIdx do
    put r (tutor+i.toUInt64*8) value
  for i in [:invitation.size] do
    let a := (0x332000 : UInt64)+i.toUInt64
    r.modify fun m => write m (a-a%8) ((word m (a-a%8)) ||| (invitation[i]!.toUInt64 <<< (a%8*8)))
  r.modify fun m => {m with syscalls:=#[(0,101),(0,88),(0,101)],writes:=#[]}
  let result ← run r (schoolNotebook% "multimodalPackageWork")
  expect (result.1 == 0 && (← get r school) == Lemma.Multimodal.SchoolPacket.magic &&
    (← get r (school+48)) == 27 && (← get r (base+512)) == 1)
    "successful actual JOIN abandoned the course or failed its joined context"
  expect ((← get r (app+32)) == 1 && (← get r (app+48)) == 803 &&
    (← get r (app+56)) == 2 && (← get r (app+176)) == 3 &&
    (← get r (app+72)) == 0 && (← get r (app+144)) == 0 &&
    (← get r (base+176)) == 357 && (← r.get).syscalls.isEmpty)
    "JOIN rendered stale invitation flags before original publication EOF or lost source/node/request ownership"
  let writes := (← r.get).writes
  expect (!(writes.any fun a => (0x329000 ≤ a && a < 0x32a000) ||
      (0x33b000 ≤ a && a < 0x33c000) || (Lemma.Ink.Surface.framebuffer ≤ a && a < Lemma.Ink.Surface.framebuffer+1815000)))
    "JOIN changed saved mathematics/workspace or rasterized before original source EOF"
  -- Only a completed, validated source read authorizes its fresh presentation.
  let ready ← run r (schoolNotebook% "packageReadComplete")
  expect (ready.1 == 0 && (← get r (app+32)) == 2 &&
    (← get r (app+72)) == 1 && (← get r (app+144)) == 1)
    "original source EOF did not release its own text/control presentation"

private def rawState : UInt64 := Lemma.User.Multimodal.records+2432
private def captureSample (r : IO.Ref Model) (sequence flags x y : UInt64) : IO (Array UInt64) := do
  let words := #[sequence,0x100000000+sequence,x,y,2047,flags,0x123456789abcdef0,0xfedcba9876543210,9]
  for (value,i) in words.zipIdx do put r (Lemma.Applications.Notebook.raw+i.toUInt64*8) value
  let accepted ← run r (schoolNotebook% "multimodalInputSample")
  expect (accepted.1 == 0) "bounded raw capture rejected a well-formed sample"
  return words
private def rawFixture : IO (IO.Ref Model) := do
  let r ← IO.mkRef ({} : Model)
  for (a,v) in #[(rawState,4),(base+32,1650),(base+40,2200),(base+48,65535),
      (base+56,65535),(base+64,2047),(base+72,1),(base+80,1),(base+96,11),
      (base+120,Lemma.Applications.Notebook.ink1),(base+128,10),(base+136,1),
      (base+144,Lemma.Applications.Notebook.ink0),(base+160,1),(base+24,3),
      (base+112,2),(base+272,512),(base+336,65535)] do put r a v
  let empty ← run r (Lemma.Documents.Ink.emptyPage Lemma.Applications.Notebook.pageIndex 1)
  expect (empty.1 == 0) "raw fixture empty page failed"
  return r
private def rawCaptureChecks : IO Unit := do
  let r ← rawFixture
  let mut captured : Array (Array UInt64) := #[]
  for i in [:96] do
    captured := captured.push (← captureSample r (100+i.toUInt64) (if i%3 == 2 then 6 else 7) (40000+(i%3).toUInt64*20) 40000)
  expect ((← get r (rawState+16)) == 96 && (← get r (base+112)) == 2 && (← get r (base+408)) == 0)
    "occupied buffers silently consumed a new stroke instead of retaining it"
  for i in [:96] do
    for j in [:9] do
      expect ((← get r (0x350000+i.toUInt64*128+j.toUInt64*8)) == captured[i]![j]!)
        "raw backlog truncated/reordered one of nine controller words"
  let blocked ← run r (schoolNotebook% "multimodalRawPump")
  expect (blocked.1 == 0 && (← get r (rawState+16)) == 96)
    "new stroke overwrote an occupied complete raw buffer"
  -- The finite observer releases an independently assumed prior Store/buffer
  -- completion. This is not a journal execution claim. Every following sample
  -- is applied by the actual Notebook Actions, finished by the real Ink codec,
  -- then copied before the observer releases that completed buffer in turn.
  put r (base+112) 0;put r (base+136) 0;put r (base+144) 0
  for i in [:96] do
    let applied ← run r (schoolNotebook% "multimodalRawPump")
    expect (applied.1 == 0 && (← get r (rawState+16)) == 95-i.toUInt64)
      "bounded replay failed progress after raw buffer became available"
    if i%3 == 2 then
      expect ((← get r (base+112)) == 3 && (← get r (base+104)) == 0)
        "replay lost stroke down/move/release boundaries"
      let buffer := Lemma.Applications.Notebook.ink1
      let finished ← run r (Lemma.Documents.Ink.finishChunk buffer 3 3)
      expect (finished == (0,344)) "actual replayed raw chunk failed full codec finish"
      for k in [:3] do
        for j in [:9] do
          expect ((← get r (buffer+128+k.toUInt64*72+j.toUInt64*8)) == captured[i-2+k]![j]!)
            "applied raw stroke changed full sequence/timestamp/availability/epoch fields"
      put r (base+112) 0;put r (base+136) 0
  expect ((← get r (rawState+16)) == 0 && (← get r (base+96)) == 43)
    "32 real stroke admissions were merged or silently discarded"
  put r (base+336) 65535
  let _ ← captureSample r 196 7 54500 1900
  let _ ← captureSample r 197 6 54500 1900
  let waiting ← run r (schoolNotebook% "multimodalRawPump")
  expect (waiting.1 == 0 && (← get r (rawState+16)) == 2 && (← get r (base+160)) == 1)
    "Save consumed before preceding Store operation completed"
  -- Real local inhibition is observed despite an occupied raw backlog. Only
  -- the declared controller syscall and its console receipt may execute.
  put r (rawState+24) 0
  r.modify fun m => {m with syscalls:=#[(0,0),(0,88)]}
  let _ ← captureSample r 198 7 22000 4200
  expect ((← get r (rawState+16)) == 2 && (← get r (base+160)) == 1 && (← r.get).syscalls.isEmpty)
    "mute waited behind captured ink or changed Store ownership"
  let saturated ← rawFixture
  put saturated (base+112) 384
  let _ ← captureSample saturated 1 6 40000 40000
  -- Seed the next genuine controller response without advancing the capture
  -- cursor. Even a completely full Ink buffer must drain local MUTE input.
  for (offset,value) in #[(0,2),(8,0x100000002),(16,22000),(24,4200),(40,7),(64,9)] do
    put saturated (Lemma.Applications.Notebook.raw+offset) value
  saturated.modify fun m => {m with syscalls:=#[(0,0),(0,0),(0,88)]}
  let drained ← run saturated ((schoolNotebook% "drainMultimodalInput") 2)
  expect (drained == (0,1) && (← saturated.get).syscalls.isEmpty && (← get saturated (base+112)) == 384)
    "full raw buffer prevented controller MUTE input from bypassing capture backlog"
  let full ← rawFixture
  put full (base+112) 2
  for i in [:128] do
    let _ ← captureSample full (1000+i.toUInt64) 7 40000 40000
  full.modify fun m => {m with syscalls:=#[(0,88)]}
  let _ ← captureSample full 1128 7 40000 40000
  expect ((← get full (rawState+16)) == 0 && (← get full (rawState+32)) == 131 &&
      (← get full (rawState+40)) == 1 && (← get full (rawState+48)) == 1 &&
      (← get full (base+160)) == 1 && (← get full (base+144)) == Lemma.Applications.Notebook.ink0)
    "overflow hid loss, failed held-contact resync, or released pinned Store bytes"
  let _ ← captureSample full 1129 7 40000 40000
  expect ((← get full (rawState+16)) == 0) "overflow resumed halfway through held stroke"
  let _ ← captureSample full 1130 6 40000 40000
  let _ ← captureSample full 1131 7 40000 40000
  expect ((← get full (rawState+16)) == 1 && (← get full (rawState+40)) == 0)
    "fresh contact after release could not resume bounded capture"
  let changed ← rawFixture
  let _ ← captureSample changed 1 7 40000 40000
  put changed (base+112) 0;put changed (base+80) 2
  changed.modify fun m => {m with syscalls:=#[(0,88)]}
  let rejected ← run changed (schoolNotebook% "multimodalRawPump")
  expect (rejected.1 == 0 && (← get changed (rawState+16)) == 0 && (← get changed (rawState+48)) == 1 &&
      (← get changed (base+160)) == 1)
    "captured ink was silently retargeted to another notebook page"
  let gap ← rawFixture
  let _ ← captureSample gap 1 7 40000 40000
  gap.modify fun m => {m with syscalls:=#[(0,88)]}
  let _ ← captureSample gap 3 7 40000 40000
  expect ((← get gap (rawState+16)) == 0 && (← get gap (rawState+40)) == 1 &&
      (← get gap (rawState+48)) == 1 && (← get gap (base+160)) == 1)
    "capture discontinuity crossed retained sample order without declared loss"

private def rawStatusChecks : IO Unit := do
  let r ← rawFixture
  put r (base+112) 0;put r (base+144) 0;put r (base+160) 0;put r (base+136) 0
  put r (rawState+16) 3;put r (rawState+48) 1
  let waiting ← run r (schoolNotebook% "multimodalRawStatus")
  expect (waiting.1 == 0 && (← get r (base+136)) == 1 && (← get r (rawState+56)) == 1 &&
      (← get r (rawState+48)) == 1)
    "Saved hid captured unsaved input or cleared its LOSS latch"
  put r (rawState+16) 0;put r (base+160) 1
  let pending ← run r (schoolNotebook% "multimodalRawStatus")
  expect (pending.1 == 0 && (← get r (base+136)) == 1 && (← get r (rawState+56)) == 1)
    "capture status promoted Saved before the last Store completion"
  put r (base+160) 0;put r (base+128) 17
  let complete ← run r (schoolNotebook% "multimodalRawStatus")
  expect (complete.1 == 0 && (← get r (base+136)) == 0 && (← get r (rawState+56)) == 0 &&
      (← get r (base+128)) == 17 && (← get r (rawState+48)) == 1 && (← r.get).syscalls.isEmpty)
    "completed capture left a false Pending state, changed durable frontier or erased LOSS"
  put r (base+136) 1
  let unrelated ← run r (schoolNotebook% "multimodalRawStatus")
  expect (unrelated.1 == 0 && (← get r (base+136)) == 1)
    "capture status promoted unrelated Pending work to Saved"
  put r (base+136) 2;put r (rawState+56) 1
  let failed ← run r (schoolNotebook% "multimodalRawStatus")
  expect (failed.1 == 0 && (← get r (base+136)) == 2)
    "capture status replaced a Failed state with Saved"

private def expectConsoleTag (r : IO.Ref Model) (tag : String) : IO Unit := do
  for i in [:16] do
    let a := Lemma.User.Console.packetAddress+3+i.toUInt64
    expect (((← get r (a-a%8)) >>> (a%8*8) &&& 255) == tag.toUTF8[i]!.toUInt64)
      "Save receipt described captured/uncommitted input as all-input Saved"
private def rawCommitReceiptChecks : IO Unit := do
  for stage in #[2,3] do
    let r ← rawFixture
    for (a,v) in #[(base+736,1),(rawState+16,2),(base+112,0),(base+144,0),
        (base+200,stage),(base+128,17),(base+224,99)] do put r a v
    r.modify fun m => {m with syscalls:=#[(0,88)]}
    let finished ← run r (schoolNotebook% "finishRecord")
    expect (finished.1 == 0 && (← get r (base+128)) == 17 && (← get r (base+160)) == 0)
      "completed actual record changed its acknowledged frontier"
    expectConsoleTag r "0000000000000423"
    let shown ← run r (schoolNotebook% "multimodalRawStatus")
    expect (shown.1 == 0 && (← get r (base+136)) == 1)
      "post-commit controller publication hid captured input behind Saved"
  for tail in #[0,1] do
    let r ← rawFixture
    r.modify fun m => {m with forbiddenPage:=some Lemma.User.Multimodal.records,syscalls:=#[(0,88)]}
    for (a,v) in #[(base+736,0),(base+112,tail),(base+144,0),(base+200,3),(base+128,17)] do put r a v
    let finished ← run r (schoolNotebook% "finishRecord")
    expect (finished.1 == 0) "first preallocation Save read an unallocated multimodal page"
    expectConsoleTag r (if tail == 0 then "0000000000000421" else "0000000000000423")

def main : IO Unit := do
  rawCommitReceiptChecks;rawStatusChecks;rawCaptureChecks;floorChecks; recordChecks; selectedNodeCheck; saveChecks; bootGateCheck;queueHandoffCheck;schoolJoinCheck
  IO.println "NOTEBOOK_SCHOOL_ACTIONS:PASS reader-local floor/global maximum,regression rejection,exact record copy,same-edition review node,old Save reply,mapped first Save,foreground IPC handoff and context-bound control,actual JOIN async source/EOF presentation,32stroke full9word capture/replay,Save ordering,mute/full-buffer safety,overflow/gap/view-loss,captured-work Pending/Saved header+421/423 ownership; component only"
end NotebookSchoolTests

def main : IO Unit := NotebookSchoolTests.main
