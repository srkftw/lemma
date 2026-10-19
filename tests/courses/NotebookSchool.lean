import Lean
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
  put r (base+712) 99; put r (base+720) 99; put r (base+760) 99
  let cleared ← run r ((schoolNotebook% "clearStep") 0 80 0 0 0 0 0)
  expect (cleared.1 == 0 && (← get r (base+712)) == 0 && (← get r (base+720)) == 0 && (← get r (base+760)) == 0)
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

def main : IO Unit := do
  floorChecks; recordChecks; selectedNodeCheck; saveChecks; bootGateCheck;queueHandoffCheck
  IO.println "NOTEBOOK_SCHOOL_ACTIONS:PASS reader-local floor/global maximum,regression rejection,exact record copy,same-edition review node,old Save reply,mapped first Save,foreground IPC handoff and context-bound control; component only"
end NotebookSchoolTests

def main : IO Unit := NotebookSchoolTests.main
