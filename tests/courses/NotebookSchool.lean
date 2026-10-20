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
  syscallArguments : Array (Array UInt64) := #[]
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
  | .platform op a b c d e f next => do
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
      r.set {m with syscalls := m.syscalls.extract 1 m.syscalls.size, syscallArguments:=m.syscallArguments.push #[a,b,c,d,e,f]}
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
  put r (base+656) 99; put r (base+712) 99; put r (base+720) 99; put r (base+736) 99; put r (base+744) 99; put r (base+760) 99
  let cleared ← run r ((schoolNotebook% "clearStep") 0 80 0 0 0 0 0)
  expect (cleared.1 == 0 && (← get r (base+656)) == 0 && (← get r (base+712)) == 0 && (← get r (base+720)) == 0 && (← get r (base+736)) == 0 && (← get r (base+744)) == 0 && (← get r (base+760)) == 0)
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
private def capturedMicrobatchChecks : IO Unit := do
  IO.println "CAPTURE_CASE:r"
  let r ← rawFixture
  for a in #[base+112,base+136,base+144,base+160] do put r a 0
  let mut captured : Array (Array UInt64) := #[]
  for i in [:96] do
    captured := captured.push (← captureSample r (100+i.toUInt64) 7 (40000+i.toUInt64) 40000)
  -- The real first contact cancels an idle arithmetic view and emits458.
  -- This is an exact88-byte Console acknowledgement, not an IPC grant.
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  let progressed ← run r (schoolNotebook% "multimodalAdvanceCaptured")
  expect (progressed == (0,8) && (← get r (rawState+16)) == 88 &&
      (← get r (base+112)) == 8 && (← get r (base+104)) != 0 && (← r.get).syscalls.isEmpty)
    "microbatch did not retire exactly its bounded eight eligible captured samples"
  let cancelTag := "0000000000000458"
  for i in [:16] do
    let address := Lemma.User.Console.packetAddress+3+i.toUInt64
    expect (((← get r (address-address%8)) >>> (address%8*8) &&& 255) == cancelTag.toUTF8[i]!.toUInt64)
      "eligible first stroke did not emit its exact idle-checker cancellation observation"
  for i in [:8] do
    for j in [:9] do
      expect ((← get r (Lemma.Applications.Notebook.ink1+128+i.toUInt64*72+j.toUInt64*8)) == captured[i]![j]!)
        "microbatch altered a full-width ordered controller record"
  IO.println "CAPTURE_CASE:empty"
  let empty ← rawFixture
  let untouched ← run empty (schoolNotebook% "multimodalAdvanceCaptured")
  expect (untouched == (0,0) && (← empty.get).syscalls.isEmpty && (← get empty (base+160)) == 1)
    "empty capture polled or modified another foreground transaction"
  IO.println "CAPTURE_CASE:blocked"
  let blocked ← rawFixture
  let _ ← captureSample blocked 1 7 40000 40000
  blocked.modify fun m => {m with syscalls := (Array.range 8).map fun _ => (IPCABI.wouldBlock,0)}
  let waiting ← run blocked (schoolNotebook% "multimodalAdvanceCaptured")
  expect (waiting == (0,8) && (← get blocked (rawState+16)) == 1 &&
      (← get blocked (base+112)) == 2 && (← get blocked (base+160)) == 1 &&
      (← blocked.get).syscalls.isEmpty)
    "blocked raw buffers were overwritten or real owned Store polls were omitted/unbounded"
  -- A validated actual Commit reply advances the real owner and releases
  -- only its raw buffer. The other completed tail cannot be skipped merely
  -- because more capture is waiting; main-loop enqueue still owns that step.
  IO.println "CAPTURE_CASE:completed"
  let completed ← rawFixture
  let _ ← captureSample completed 1 7 40000 40000
  let ownedSource := Lemma.Applications.Notebook.ink0
  for (a,v) in #[(base+736,1),(base+760,1),(base+160,3),(base+168,42),
      (base+200,0),(base+208,ownedSource),(base+224,65547),(base+232,4),
      (base+176,7),(ownedSource+32,11),(ownedSource+112,3)] do put completed a v
  reply completed Lemma.Applications.Notebook.incoming 4 1 65547 7 11 0 0
  completed.modify fun m => {m with syscalls:=#[(0,128),(0,88)],writes:=#[]}
  let acknowledged ← run completed (schoolNotebook% "multimodalAdvanceCaptured")
  expect (acknowledged == (0,1) && (← get completed (rawState+16)) == 1 &&
      (← get completed (base+112)) == 2 && (← get completed (base+144)) == 0 &&
      (← get completed (base+160)) == 0 && (← get completed (base+744)) == 1 &&
      (← get completed (base+128)) == 11 &&
      (← get completed (Lemma.Applications.Notebook.pageIndex+32)) == 1 &&
      (← completed.get).syscalls.isEmpty)
    "real Commit did not release exactly its completed owner while preserving captured/tail ordering"
  expect (!((← completed.get).writes.any fun a => ownedSource ≤ a && a < ownedSource+32768))
    "Store progress rewrote its pinned raw artifact"
  IO.println "CAPTURE_CASE:queue"
  let queue ← rawFixture
  let _ ← captureSample queue 1 7 40000 40000
  put queue (base+760) 1;put queue (base+712) 1;put queue SchoolSubmission.arena 41
  let guarded ← run queue (schoolNotebook% "multimodalAdvanceCaptured")
  expect (guarded == (0,8) && (← get queue (rawState+16)) == 1 &&
      (← get queue (base+160)) == 1 && (← queue.get).syscalls.isEmpty)
    "microbatch borrowed the queue's actual in-flight read endpoint"
  IO.println "CAPTURE_CASE:paper"
  let paper ← rawFixture
  for a in #[base+112,base+144,base+160] do put paper a 0
  put paper (base+336) 0
  let _ ← captureSample paper 1 7 54600 1907
  let yielded ← run paper (schoolNotebook% "multimodalAdvanceCaptured")
  expect (yielded == (0,1) && (← get paper (rawState+16)) == 1 && (← paper.get).syscalls.isEmpty)
    "paper-only control dependency spun instead of yielding to ordinary display/safety/device work"


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

private def rawCoalescingChecks : IO Unit := do
  let r ← rawFixture
  let index := Lemma.Applications.Notebook.pageIndex
  let source := Lemma.Applications.Notebook.ink0
  let encoded := (schoolNotebook% "loadedInk")
  let oldImage : UInt64 := 0x390000
  let restored : UInt64 := 0x398000
  let oldPacked ← run r (Lemma.Documents.Ink.encodePage index oldImage)
  expect (oldPacked == (0,128)) "acknowledged empty packed page fixture failed"
  -- These are independently supplied successful raw Commit bytes, not a
  -- simulated journal or a manufactured durable page reference.
  for (a,v) in #[(base+736,1),(base+744,0),(rawState+16,2),(base+112,0),
      (base+104,0),(base+160,3),(base+200,0),(base+208,source),
      (base+224,65547),(base+240,11),(base+128,17),
      (source+32,11),(source+112,3)] do put r a v
  r.modify fun m => {m with syscalls:=#[(0,88)],writes:=#[]}
  let committed ← run r (schoolNotebook% "finishRecord")
  expect (committed.1 == 0 && (← get r (base+744)) == 1 &&
      (← get r (base+160)) == 0 && (← get r (base+144)) == 0 && (← get r (base+136)) == 1 &&
      (← get r (index+32)) == 1 && (← get r (index+128)) == 65547 &&
      (← get r (index+136)) == 11 && (← get r (index+48)) == 1 && (← get r (base+128)) == 17)
    "raw Commit did not coalesce its exact ordered reference and release only the completed buffer"
  expect (!((← r.get).writes.any fun a => encoded ≤ a && a < encoded+32768 || source ≤ a && a < source+32768))
    "coalescing overwrote pinned raw bytes or published a page snapshot per stroke"
  expectConsoleTag r "0000000000000423"
  -- Fresh RAM can decode only the separately retained published prefix.
  -- These are actual Ink codec/boot Actions over independent fixture bytes,
  -- not a journal power-cut or CPU cold-recovery measurement.
  let cold ← IO.mkRef ({forbiddenPage:=some Lemma.User.Multimodal.records} : Model)
  for i in [:16] do put cold (oldImage+i.toUInt64*8) (← get r (oldImage+i.toUInt64*8))
  put cold (base+744) 99
  let reset ← run cold ((schoolNotebook% "clearStep") 0 80 0 0 0 0 0)
  let recovered ← run cold (Lemma.Documents.Ink.decodePage oldImage restored 1 128)
  expect (reset.1 == 0 && recovered.1 == 0 && (← get cold (base+744)) == 0 &&
      (← get cold (restored+32)) == 0 && (← get r (index+32)) == 1)
    "unpublished resident raw references leaked into the retained cold prefix"
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  let _ ← run r ((schoolNotebook% "reportCommitState") 0x421 17 11)
  expectConsoleTag r "0000000000000423"
  put r (rawState+16) 0;put r (base+200) 3
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  let inspected ← run r (schoolNotebook% "finishRecord")
  expect (inspected.1 == 0 && (← get r (base+744)) == 1 && (← get r (base+136)) == 1)
    "Inspect completion promoted unpublished references to Saved"
  expectConsoleTag r "0000000000000423"
  put r (base+136) 0
  let _ ← run r (schoolNotebook% "multimodalRawStatus")
  expect ((← get r (base+136)) == 1) "unpublished page index appeared Saved after capture drained"
  for (a,v) in #[(base+112,0),(base+104,0),(base+144,0),(base+160,0),(base+536,0)] do put r a v
  let work ← run r (schoolNotebook% "schoolForegroundWork")
  expect (work == (0,1)) "school queue borrowed IPC while raw references were unpublished"
  put r (Lemma.User.Multimodal.state+144+16) 3
  let ask ← run r (schoolNotebook% "multimodalPumpTutor")
  expect (ask.1 == 0 && (← get r (Lemma.User.Multimodal.state+144+16)) == 3 && (← r.get).syscalls.isEmpty)
    "ASK consumed its intent before the deferred index publication"
  put r (Lemma.User.Multimodal.state+144+16) 0
  let nav ← run r (schoolNotebook% "pumpBookControlBacklog")
  expect (nav.1 == 0 && (← get r (base+80)) == 1) "navigation escaped an unpublished page index"
  -- An ordered Save stays at the raw head until the actual page/root chain
  -- publishes all preceding committed raw chunks. It cannot inspect a stale
  -- prefix and call that Save completion.
  let _ ← captureSample r 100 7 54600 1907
  -- Independently completed prior status upload; ordered control must still
  -- wait for durable publication once the paper path is available.
  put r (base+336) 65535
  r.modify fun m => {m with syscalls:=#[(0,88),(0,42)]}
  let waiting ← run r (schoolNotebook% "multimodalRawPump")
  expect (waiting.1 == 0 && (← get r (base+744)) == 1 && (← get r (rawState+16)) == 1 &&
      (← get r (base+200)) == 1 && (← get r (base+232)) == 2 && (← get r (base+224)) == 257 &&
      (← get r (base+160)) == 1 && (← get r (index+32)) == 1)
    "ordered control bypassed deferred page publication or consumed the captured control"
  -- Even page Commit alone is not a saved prefix: the existing root Commit
  -- must complete before the dirty flag is cleared.
  put r (base+200) 1;put r (base+88) 1;put r (base+272) 512
  r.modify fun m => {m with syscalls:=#[(0,88),(0,43)]}
  let pageDone ← run r (schoolNotebook% "finishRecord")
  expect (pageDone.1 == 0 && (← get r (base+744)) == 1 && (← get r (base+200)) == 2)
    "page Commit prematurely cleared deferred durability before root Commit"
  put r (base+200) 2;put r (base+128) 19
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  let rootDone ← run r (schoolNotebook% "finishRecord")
  expect (rootDone.1 == 0 && (← get r (base+744)) == 0 && (← get r (base+160)) == 0 &&
      (← get r (index+32)) == 1 && (← get r (base+128)) == 19)
    "actual root Commit failed to retire only the deferred publication flag"
  expectConsoleTag r "0000000000000423"
  -- A quiet batch starts the same unchanged page/root protocol. Failure
  -- preserves the dirty state and cannot silently retry or claim Saved.
  let q ← rawFixture
  for (a,v) in #[(base+736,1),(base+744,1),(base+112,0),(base+104,0),(base+144,0),(base+160,0),
      (rawState+16,0),(base+136,1)] do put q a v
  q.modify fun m => {m with syscalls:=#[(0,88),(0,44)]}
  let flushed ← run q (schoolNotebook% "multimodalPublishDeferredIndex")
  expect (flushed.1 == 0 && (← get q (base+744)) == 1 && (← get q (base+160)) == 1 &&
      (← get q (base+200)) == 1 && (← get q (base+224)) == 257)
    "quiescent raw references did not start the real existing page publication"
  put q (base+160) 0;put q (base+136) 2
  let failed ← run q (schoolNotebook% "multimodalPublishDeferredIndex")
  expect (failed.1 == 0 && (← get q (base+744)) == 1 && (← get q (base+136)) == 2 && (← q.get).syscalls.isEmpty)
    "failed metadata publication discarded its pending references or manufactured Saved"

private def deferredSavedChecks : IO Unit := do
  let receipt := Lemma.User.Multimodal.records+2816
  let candidate : IO (IO.Ref Model) := do
    let r ← rawFixture
    for (a,v) in #[(base+736,1),(base+112,0),(base+144,0),(base+104,0),(base+160,0),
        (base+128,17),(base+136,0),(rawState+16,1)] do put r a v
    r.modify fun m => {m with syscalls:=#[(0,88)]}
    let result ← run r ((schoolNotebook% "reportCommitState") 0x421 17 99)
    expect (result.1 == 0 && (← get r receipt) == 1) "suppressed actual ACK was not retained"
    expectConsoleTag r "0000000000000423"
    return r
  let r ← candidate
  -- This is the observed real-machine sequence: root ACK while a pen-up is
  -- captured, Pending reconciliation, then the last captured input retires.
  let waiting ← run r (schoolNotebook% "multimodalRawStatus")
  expect (waiting.1 == 0 && (← get r (base+136)) == 1 && (← get r receipt) == 1)
    "pending presentation released a deferred Saved receipt too early"
  put r (rawState+16) 0
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  let finished ← run r (schoolNotebook% "multimodalRawStatus")
  expect (finished.1 == 0 && (← get r receipt) == 0 && (← get r (base+136)) == 0 &&
      (← get r (base+128)) == 17 && (← r.get).syscalls.isEmpty)
    "quiescence did not re-present the exact acknowledged prefix once"
  expectConsoleTag r "0000000000000421"
  for (offset,text) in #[(20,"0000000000000011"),(37,"0000000000000001"),
      (54,"0000000000000001"),(71,"0000000000000063")] do
    for i in [:16] do
      let address := Lemma.User.Console.packetAddress+offset+i.toUInt64
      expect (((← get r (address-address%8)) >>> (address%8*8) &&& 255) == text.toUTF8[i]!.toUInt64)
        "deferred Saved tuple was retargeted or its original ACK changed"
  let duplicate ← run r (schoolNotebook% "multimodalRawStatus")
  expect (duplicate.1 == 0 && (← r.get).syscalls.isEmpty) "deferred ACK emitted twice"
  -- Every independent current-work owner prevents the deferred observation.
  for offset in #[104,112,144,160,536,744] do
    let p ← candidate
    put p (rawState+16) 0;put p (base+offset) 1
    let held ← run p (schoolNotebook% "pumpDeferredSavedReceipt")
    expect (held.1 == 0 && (← get p receipt) == 1 && (← p.get).syscalls.isEmpty)
      "deferred receipt escaped current capture/Store/checker ownership"
  -- Exact document/work context and monotone ACK binding, not the latest
  -- unrelated reply or current page, authorize this receipt.
  for (offset,value) in #[(72,2),(80,2),(96,12),(512,1),(520,7),(752,1),(128,16),(136,2)] do
    let p ← candidate
    put p (rawState+16) 0;put p (base+offset) value
    let rejected ← run p (schoolNotebook% "pumpDeferredSavedReceipt")
    expect (rejected.1 == 0 && (← get p receipt) == 0 && (← p.get).syscalls.isEmpty)
      "changed context, regressed frontier or failed state reused a stale Saved receipt"
  for changed in #[Lemma.Applications.Notebook.mathematics+40,0x33c800+128,0x33c800+136,
      0x33c800+160,0x33c800+8] do
    let p ← candidate
    for (address,value) in #[(base+512,1),(base+752,1),(base+520,9),
        (Lemma.Applications.Notebook.mathematics+40,7),(0x33c800+128,803),
        (0x33c800+136,2),(0x33c800+160,12345),(0x33c800+8,4)] do put p address value
    p.modify fun m => {m with syscalls:=#[(0,88)]}
    let captured ← run p ((schoolNotebook% "reportCommitState") 0x421 17 99)
    expect (captured.1 == 0) "publication receipt fixture did not retain actual ACK"
    put p (rawState+16) 0;put p changed ((← get p changed)+1)
    let rejected ← run p (schoolNotebook% "pumpDeferredSavedReceipt")
    expect (rejected.1 == 0 && (← get p receipt) == 0 && (← p.get).syscalls.isEmpty)
      "changed publication/edition/source/node or exact mathematical revision reused Saved"
  -- A new loss invalidates even when no samples were discarded, so the
  -- retained ACK cannot silently present loss as completion of queued work.
  let lost ← candidate
  put lost (rawState+16) 0
  lost.modify fun m => {m with syscalls:=#[(0,88)]}
  let loss ← run lost ((schoolNotebook% "multimodalRawLoss") 3)
  expect (loss.1 == 0 && (← get lost receipt) == 0) "loss retained deferred presentation authority"
  put lost (base+136) 0
  let afterLoss ← run lost (schoolNotebook% "pumpDeferredSavedReceipt")
  expect (afterLoss.1 == 0 && (← lost.get).syscalls.isEmpty) "lost work acquired a deferred Saved receipt"
  -- A new actual ACK supersedes the candidate; all original legacy tests
  -- continue exercising preallocation with the whole MM page forbidden.
  let replaced ← candidate
  replaced.modify fun m => {m with syscalls:=#[(0,88)]}
  let newer ← run replaced ((schoolNotebook% "reportCommitState") 0x421 18 101)
  expect (newer.1 == 0 && (← get replaced (receipt+8)) == 18 &&
      (← get replaced (receipt+16)) == 101) "new acknowledged receipt did not replace the old tuple"

private def writeImage (r : IO.Ref Model) (address : UInt64) (image : ByteArray) : IO Unit := do
  for i in [:image.size] do
    let a := address+i.toUInt64
    let old ← get r (a-a%8)
    put r (a-a%8) ((old &&& ~~~((255:UInt64)<<<(a%8*8))) ||| (image[i]!.toUInt64<<<(a%8*8)))

private def warmSubmissionChecks : IO Unit := do
  let doc := Lemma.Applications.Notebook.mathematics
  let work : UInt64 := 0x33b000
  let tutor := Lemma.User.Multimodal.records+1024
  let tutorState := Lemma.User.Multimodal.state+144
  let school := Lemma.User.Multimodal.records+1152
  let q := SchoolSubmission.arena
  let image ← IO.ofExcept <| (Package.encode {
    identity:=803,edition:=2,title:="Original algebra",sourceAnchor:="owned fixture source",
    editionAnchor:="fixture edition2",rightsAnchor:="fixture authored text",
    nodes:=#[{kind:=.explanation,title:="Definitions",body:="A sum.",sourceAnchor:="source1"},
      {kind:=.worked,title:="Expansion",body:="Four products.",sourceAnchor:="source2"},
      {kind:=.explanation,title:="Assumptions",body:="For integers.",sourceAnchor:="source3"},
      {kind:=.exercise .binomialSquare,title:="Expand",body:="Expand (N+1)^2.",exercise:="Give coefficients.",sourceAnchor:="source4"}] }).mapError (·.render)
  let r ← IO.mkRef ({} : Model)
  for (a,v) in #[(base+72,1),(base+80,1),(base+24,3),(base+128,40),(base+176,100),
      (base+752,12),(base+760,1),(base+512,1),(base+712,1),(base+32,1650),
      (base+40,2200),(base+336,65535),(base+16,7),(base+576,7),(app,image.size.toUInt64),
      (app+8,3),(app+16,1),(app+32,2),(app+48,803),(app+56,2),(base+528,9)] do put r a v
  writeImage r 0x332000 image
  expect ((← run r (Lemma.Documents.MathematicsClosure.create doc 1 1)).1 == 0) "warm original Doc8"
  for (offset,value) in #[(72,1),(80,2),(88,1)] do put r (doc+offset) value
  expect ((← run r (PackageWorkspace.create work doc 1 1)).1 == 0) "warm original workspace"
  expect ((← run r ((schoolNotebook% "stagePackageExercise") 3)).1 == 0) "warm actual USE selection"
  expect ((← run r (schoolNotebook% "adoptPackageWorkspace")).1 == 0) "warm selected workspace publication"
  let crc ← get r (0x332000+80)
  r.modify fun m => {m with syscalls:=#[(0,1),(0,88),(0,88),(0,88)]}
  expect ((← run r (schoolNotebook% "multimodalAsk")).1 == 0 && (← get r (tutor+112)) == 1 &&
      (← get r (tutor+88)) == crc && (← get r (tutor+96)) == 1 && (← get r (tutor+104)) == 1)
    "ASK did not freeze exact validated source before overlay"
  let ask : Lemma.School.Client.GuestAsk := {
    session:=2,consent:=1,revision:=2,object:=(PackageWorkspace.object 1).toNat,sequence:=41,
    source:=803,edition:=2,task_id:=4,cutoff:=1,now:=1,deadline:=10000,grants:=1 }
  let binding : Lemma.School.Client.SessionBinding := {
    school:="fixture",actor:="learner",enrollment:="enrolled",session:="session",
    guestSession:=2,course:=803,revision:=2,policy:=2,generation:=22,expires:=10000,
    authority:="020000000000000006000000000000007856341200000000efcdab0000000000",bindingRecord:=27 }
  let input : Lemma.School.Client.AssistInput := {
    school:="fixture",actor:="learner",session:="session",course:=803,revision:=2,
    policy:=2,generation:=22,now:=1,ask:=ask }
  let overlay ← IO.ofExcept (Lemma.School.Client.handleAssist binding input "Expand into four products.")
  writeImage r 0x332000 overlay
  for (offset,value) in #[(0,Lemma.Multimodal.SchoolPacket.magic),(8,1),(16,2),(24,6),(32,0x12345678),
      (40,0xabcdef),(48,27),(56,22),(64,10000),(72,2),(80,2),(88,803),(96,2)] do put r (school+offset) value
  for (a,v) in #[(app,overlay.size.toUInt64),(app+8,0),(app+32,2),(app+128,60001),
      (app+136,41),(app+72,1),(app+96,4),(app+208,5),(app+232,2),(app+240,1),
      (tutorState+8,1)] do put r a v
  r.modify fun m => {m with syscalls:=#[(0,1),(0,88),(0,88),(0,42)]}
  expect ((← run r (schoolNotebook% "multimodalPackageWork")).1 == 0 &&
      (← get r (Lemma.User.Multimodal.records+3008)) == 1 && (← get r (base+160)) == 1)
    "warm help did not reach actual prepared write-ahead consumer"
  -- Explicit component premise: actual Store ACKs, separately exercised by
  -- native545 evidence, authorize the same maintained completion actions.
  put r (base+128) 41;put r (base+160) 3;put r (base+200) 3
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  expect ((← run r (schoolNotebook% "finishRecord")).1 == 0) "warm prepared ACK completion"
  r.modify fun m => {m with syscalls:=#[(0,1),(0,88),(0,43),(0,88)]}
  expect ((← run r (schoolNotebook% "multimodalPumpRemote")).1 == 0 &&
      (← get r (tutor+32)) == 41 && (← get r (work+64+192)) == 9)
    "warm actual guest raster/observation consumer"
  put r (base+128) 42;put r (base+160) 0;put r (base+136) 0
  r.modify fun m => {m with syscalls:=#[]}
  expect ((← run r (schoolNotebook% "multimodalPumpRemote")).1 == 0) "warm raster ACK release"
  -- CHECK snapshots the existing original binding even though reader bytes
  -- still contain60001. A terminal checker result is an explicit premise,
  -- never inferred from assistance or from this component observer.
  r.modify fun m => {m with syscalls:=#[(0,55),(0,88)]}
  expect ((← run r (schoolNotebook% "beginPackageArithmetic")).1 == 0 &&
      (← get r (app+80)) == 1) "warm CHECK lost original typed source"
  put r (base+560) 1
  expect ((← run r (schoolNotebook% "stagePackageCompletion")).1 == 0) "warm checker completion binding"
  expect ((← run r (schoolNotebook% "adoptPackageWorkspace")).1 == 0) "warm checked workspace publication"
  put r (base+536) 0;put r (base+136) 0
  expect ((← get r (0x332000+24)) == 60001 && (← get r (doc+96)) == 1)
    "test silently reloaded original package or changed checker result"
  expect ((← run r (Lemma.Documents.Ink.emptyPage Lemma.Applications.Notebook.pageIndex 1)).1 == 0) "warm empty ink page"
  let original ← r.get
  r.modify fun m => {m with syscalls:=#[(0,2)]}
  let sent ← run r (schoolNotebook% "schoolSend")
  expect (sent.1 == 0 && (← get r q) == 1 && (← get r (SchoolSubmission.metadata+64)) == 803 &&
      (← get r (SchoolSubmission.metadata+72)) == 2 && (← get r (SchoolSubmission.metadata+80)) == 4 &&
      (← get r (SchoolSubmission.metadata+88)) == crc && (← get r (SchoolSubmission.metadata+104)) == 1 &&
      (← get r (base+720)) == 0 && (← r.get).syscalls.isEmpty)
    "warm SEND retargeted original work to help overlay or failed to start queue"
  -- Cross-work/source/session and missing snapshot cases reject before a
  -- queue phase or output stream exists, but emit a usable ordinary732 error.
  for (address,value) in #[(tutor+112,0),(tutor+96,2),(tutor+104,2),
      (tutor+24,PackageWorkspace.object 2),(tutor+16,3),(tutor+0,3),
      (tutor+48,802),(tutor+56,3),(tutor+88,crc+1),(school+88,802),(school+96,3),
      (work+PackageWorkspace.selection+16,802),(work+PackageWorkspace.selection+24,3),
      (work+PackageWorkspace.selection+32,crc+1)] do
    let bad ← IO.mkRef original
    put bad address value
    bad.modify fun m => {m with syscalls:=#[(0,88)]}
    let refused ← run bad (schoolNotebook% "schoolSend")
    expect (refused.1 == 240 && (← get bad q) == 0 && (← get bad (base+720)) == 240 &&
      (← bad.get).syscalls.isEmpty) "warm changed source/work/session was not rejected visibly before queue start"
    expectConsoleTag bad "0000000000000732"
  -- Retry after validation failure uses the corrected original context and
  -- clears only its error field. Existing queue retry never rewrites metadata.
  let retry ← IO.mkRef original
  put retry (tutor+112) 0
  retry.modify fun m => {m with syscalls:=#[(0,88)]}
  expect ((← run retry (schoolNotebook% "schoolSend")).1 == 240) "retry failure fixture"
  put retry (tutor+112) 1
  retry.modify fun m => {m with syscalls:=#[(0,2)]}
  expect ((← run retry (schoolNotebook% "schoolSend")).1 == 0 &&
      (← get retry (base+720)) == 0 && (← get retry q) == 1) "successful retry retained stale queue error"
  -- A changed answer with a stale typed binding remains usable opaque work;
  -- its old exact checker outcome is never inherited as current verification.
  let edited ← IO.mkRef original
  expect ((← run edited (Lemma.Documents.Mathematics.edit doc 72 1)).1 == 0) "warm edit fixture"
  expect ((← run edited (PackageWorkspace.stageRefresh work doc Lemma.Applications.Notebook.mathematicsSave)).1 == 0) "warm edit staging"
  expect ((← run edited (schoolNotebook% "adoptPackageWorkspace")).1 == 0) "warm edit publication"
  edited.modify fun m => {m with syscalls:=#[(0,2)]}
  expect ((← run edited (schoolNotebook% "schoolSend")).1 == 0 &&
      (← get edited (SchoolSubmission.metadata+104)) == 2 &&
      (← get edited (SchoolSubmission.metadata+56)) == 3 && (← get edited (doc+96)) == 0)
    "warm edited work inherited stale typed/Verified identity or was discarded"
  -- An already frozen pending attempt ignores later source selection: retry
  -- means its original immutable bytes and queue, never a new validation.
  let pending ← IO.mkRef (← r.get)
  let oldQueue ← get pending (q+96)
  let oldRevision ← get pending (SchoolSubmission.metadata+56)
  for (a,v) in #[(q,26),(q+152,43),(tutor+48,802),(base+720,240)] do put pending a v
  pending.modify fun m => {m with syscalls:=#[]}
  expect ((← run pending (schoolNotebook% "schoolSend")).1 == 0 && (← get pending (q+304)) == 1 &&
      (← get pending (q+96)) == oldQueue && (← get pending (SchoolSubmission.metadata+64)) == 803 &&
      (← get pending (SchoolSubmission.metadata+56)) == oldRevision && (← get pending (base+720)) == 0)
    "pending retry retargeted frozen bytes or retained stale validation error"
  -- An overlay can never become a new original school ASK.
  retry.modify fun m => {m with syscalls:=#[]}
  expect ((← run retry (schoolNotebook% "multimodalAsk")).1 == 244 &&
      (← get retry (tutor+112)) == 0) "help overlay became source authority for a new ASK"

private def capturedIdleSchedulingChecks : IO Unit := do
  let r ← rawFixture
  for a in #[base+112,base+136,base+144,base+160] do put r a 0
  put r (base+656) 1
  for i in [:16] do
    let _ ← captureSample r (100+i.toUInt64) 7 40000 40000
    pure ()
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  expect ((← run r (schoolNotebook% "multimodalAdvanceInput")).1 == 0 &&
      (← get r (rawState+16)) == 8) "idle scheduling fixture did not retain its ordered captured suffix"
  -- This is the real existing op1 nonblocking FIFO take. Its actual empty174
  -- result reaches the maintained suffix; only the new mode chooses yield.
  r.modify fun m => {m with syscalls:=#[(174,0),(0,0)],syscallArguments:=#[]}
  let empty ← run r ((schoolNotebook% "multimodalDrainInput") 7)
  expect (empty.1 == 0 && (← get r (rawState+16)) == 8 &&
      (← r.get).syscalls.isEmpty && (← r.get).syscallArguments ==
      #[#[65,7,1,Lemma.Applications.Notebook.raw,0,0],#[3,0,0,0,0,0]])
    "pending capture slept on an empty nonblocking FIFO instead of yielding its timeslice"
  let next ← run r (schoolNotebook% "multimodalAdvanceInput")
  expect (next.1 == 0 && (← get r (rawState+16)) == 0 && (← get r (base+112)) == 16)
    "next progress turn required new hardware input or skipped the captured suffix"
  r.modify fun m => {m with syscalls:=#[(174,0),(0,0)],syscallArguments:=#[]}
  let idle ← run r ((schoolNotebook% "multimodalDrainInput") 7)
  expect (idle.1 == 0 && (← r.get).syscallArguments ==
      #[#[65,7,1,Lemma.Applications.Notebook.raw,0,0],#[4,10000,0,0,0,0]])
    "empty capture lost the existing bounded idle sleep"
  for enabled in #[0,1] do
    for captured in #[0,1] do
      let old ← rawFixture
      put old (base+656) enabled;put old (rawState+16) captured
      old.modify fun m => {m with syscalls:=#[(0,0)],syscallArguments:=#[]}
      let result ← run old (schoolNotebook% "multimodalIdleInput")
      let expected : Array UInt64 := if enabled == 1 && captured == 1 then #[3,0,0,0,0,0] else #[4,10000,0,0,0,0]
      expect (result.1 == 0 && (← old.get).syscallArguments == #[expected] &&
          (← get old (rawState+16)) == captured)
        "capture idle scheduling changed a legacy mode or mutated retained samples"

private def schoolWireModeChecks : IO Unit := do
  for mode in #[0,1,2,3] do
    let r ← IO.mkRef ({} : Model)
    put r (base+656) 9
    let result ← run r ((schoolNotebook% "configureSchoolMode") mode)
    expect (result.1 == 0 && (← get r (base+656)) == (if mode == 3 then 1 else 0) &&
        (← get r (base+728)) == (if 2 ≤ mode then 1 else 0) &&
        (← get r (base+760)) == (if 2 ≤ mode then 1 else mode))
      "school mode did not explicitly reset legacy wire/capture authority"
    let captured ← rawFixture
    for a in #[base+112,base+136,base+144,base+160] do put captured a 0
    for i in [:16] do
      let _ ← captureSample captured (100+i.toUInt64) 7 40000 40000
      pure ()
    put captured (base+656) (if mode == 3 then 1 else 0)
    captured.modify fun m => {m with syscalls:=#[(0,88)]}
    let advanced ← run captured (schoolNotebook% "multimodalAdvanceInput")
    expect (advanced.1 == 0 && (← get captured (rawState+16)) == (if mode == 3 then 8 else 15))
      "bounded capture progress changed a legacy root or was absent in version25"
    let q ← IO.mkRef ({} : Model)
    put q (base+760) 1;put q (base+656) (if mode == 3 then 1 else 0);put q (base+176) 7
    q.modify fun m => {m with syscalls:=(Array.range 8).map fun i => (0,SchoolSubmission.arena+i.toUInt64*4096)}
    let initialized ← run q (schoolNotebook% "schoolQueueInitialize")
    expect (initialized.1 == 0 && (← get q (SchoolSubmission.arena+336)) == (if mode == 3 then 1 else 0) &&
        (← get q (base+712)) == 1 && (← get q SchoolSubmission.arena) == 40 && (← q.get).syscalls.isEmpty)
      "school queue selected a wire mode before initialization or leaked new wire authority to a legacy root"
  let invalid ← IO.mkRef ({} : Model)
  put invalid (base+656) 9
  let rejected ← run invalid ((schoolNotebook% "configureSchoolMode") 4)
  expect (rejected.1 == 234 && (← get invalid (base+656)) == 9 && (← invalid.get).writes.size == 1)
    "unknown school mode was admitted or mutated startup authority"

def main : IO Unit := do
  capturedIdleSchedulingChecks;schoolWireModeChecks;capturedMicrobatchChecks;warmSubmissionChecks;deferredSavedChecks;rawCoalescingChecks;rawCommitReceiptChecks;rawStatusChecks;rawCaptureChecks;floorChecks; recordChecks; selectedNodeCheck; saveChecks; bootGateCheck;queueHandoffCheck;schoolJoinCheck
  IO.println "NOTEBOOK_SCHOOL_ACTIONS:PASS warm-help original-publication CHECK/SEND and visible732 rejection/source isolation, reader-local floor/global maximum,regression rejection,exact record copy,same-edition review node,old Save reply,mapped first Save,foreground IPC handoff and context-bound control,actual JOIN async source/EOF presentation,32stroke full9word capture/replay,Save ordering,mute/full-buffer safety,overflow/gap/view-loss,captured-work Pending/Saved header+421/423 ownership,burst raw-reference coalescing before ordered controls and actual page/root commit; component only"
end NotebookSchoolTests

def main : IO Unit := NotebookSchoolTests.main
