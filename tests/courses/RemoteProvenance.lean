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

namespace RemoteProvenanceTests
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


private def doc : UInt64 := Lemma.Applications.Notebook.mathematics
private def workspace : UInt64 := 0x33b000
private def event : UInt64 := Lemma.User.Multimodal.records+3072
private def remote : UInt64 := Lemma.User.Multimodal.records+3008
private def tutor : UInt64 := Lemma.User.Multimodal.records+1024
private def proposal : UInt64 := Lemma.User.Multimodal.records+1536
private def school : UInt64 := Lemma.User.Multimodal.records+1152
private def eventAt (r : IO.Ref Model) (scope revision object binding request : UInt64) : IO Unit := do
  for (offset,value) in (#[(0,revision),(8,(7:UInt64) ||| ((2:UInt64)<<<8) ||| (scope<<<16) ||| ((4:UInt64)<<<24) ||| (request<<<32)),
      (16,object),(24,binding),(32,2),(40,6),(48,0x12345678),(56,0xabcdef)] : Array (UInt64 × UInt64)) do put r (event+offset) value
private def fixture : IO (IO.Ref Model) := do
  let r ← IO.mkRef ({} : Model)
  expect ((← run r (Lemma.Documents.MathematicsClosure.create doc 1 1)).1 == 0) "Doc8 create"
  for (offset,value) in #[(48,2),(120,2),(56,0),(64,1),(72,1),(80,2),(88,1)] do put r (doc+offset) value
  expect ((← run r (Lemma.Documents.MathematicsClosure.completeExecution doc 1 2 1 11 8)).1 == 0) "original immutable fixture attempt"
  expect ((← run r (Lemma.Courses.PackageWorkspace.create workspace doc 1 1)).1 == 0) "original workspace"
  eventAt r 1 1 (PackageWorkspace.object 1) 6 1
  return r
private def docChecks : IO Unit := do
  let r ← fixture
  let a ← run r (Lemma.Documents.Mathematics.appendRemote doc event)
  expect (a == (0,2) && (← get r (doc+192)) == 5 && (← get r (doc+208)) == 2) "prepared event not appended after original attempt"
  expect ((← run r (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 == 0) "format2 validator misparsed payload words2/6 as hints"
  let again ← run r (Lemma.Documents.Mathematics.appendRemote doc event)
  expect (again == a && (← get r (doc+192)) == 5) "lost-reply append retry duplicated immutable event"
  eventAt r 2 1 (PackageWorkspace.object 1) 6 1
  expect ((← run r (Lemma.Documents.Mathematics.appendRemote doc event)) == (0,6)) "raster observation missing prepared identity"
  expect ((← run r (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 == 0 &&
    (← get r (doc+192)) == 9 && (← get r (doc+152)) == 0 && (← get r (doc+144)) == 1) "remote events changed local hint count/original attempts"
  for (offset,value) in (#[(208,1),(192,8),(840+16,0),(832+5*16,2),(840+5*16,(7:UInt64) ||| ((2:UInt64)<<<8) ||| ((2:UInt64)<<<16) ||| ((4:UInt64)<<<24) ||| ((2:UInt64)<<<32))] : Array (UInt64 × UInt64)) do
    let changed ← IO.mkRef (← r.get)
    put changed (doc+offset) value
    expect ((← run changed (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 != 0) "malformed/unbacked remote group admitted"
  for (scope,revision,object,binding,request) in #[(2,1,PackageWorkspace.object 1,6,2),
      (1,2,PackageWorkspace.object 1,6,1),(1,1,PackageWorkspace.object 2,6,1),
      (1,1,PackageWorkspace.object 1,0,1),(1,1,PackageWorkspace.object 1,6,0),(3,1,PackageWorkspace.object 1,6,1)] do
    let bad ← fixture
    eventAt bad scope revision object binding request
    expect ((← run bad (Lemma.Documents.Mathematics.appendRemote doc event)).1 != 0 &&
      (← get bad (doc+192)) == 1) "invalid/cross-work remote event mutated original history"
  let full ← fixture
  for _ in [:56] do expect ((← run full (Lemma.Documents.Mathematics.appendEvent doc 4 1 0)).1 == 0) "fill valid event capacity"
  expect ((← run full (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 == 0) "capacity fixture invalid"
  expect ((← run full (Lemma.Documents.Mathematics.appendRemote doc event)).1 == 235 &&
    (← get full (doc+192)) == 57 && (← get full (doc+208)) == 1) "preparation did not reserve terminal observation before mutation"

private def pipelineChecks : IO Unit := do
  let r ← fixture
  for (a,v) in #[(base+72,1),(base+80,1),(base+128,10),(base+24,3),(base+16,7),(base+176,50),
      (base+32,1650),(base+40,2200),(base+336,65535),(base+752,12),
      (tutor+16,1),(tutor+24,PackageWorkspace.object 1),(proposal+40,1),
      (school,Lemma.Multimodal.SchoolPacket.magic),(school+8,1),(school+16,2),(school+24,6),
      (school+32,0x12345678),(school+40,0xabcdef),(school+48,6)] do put r a v
  r.modify fun m => {m with syscalls:=#[(0,88),(0,42)]}
  let prepared ← run r (schoolNotebook% "multimodalPrepareTutor")
  expect (prepared == (0,3) && (← get r (remote)) == 1 && (← get r (app+72)) == 3 &&
      (← get r (base+160)) == 1 && (← get r (base+224)) == PackageWorkspace.object 1 && (← r.get).syscalls.isEmpty)
    "actual write-ahead path did not start owned Store transaction/hold presentation"
  expect ((← get r (workspace+64+192)) == 5 && (← get r (workspace+64+208)) == 2) "prepared identity absent from actual Store snapshot"
  expect ((← run r (schoolNotebook% "packageBusy")) == (0,3)) "queue/ASK/navigation could bypass prepared publication"
  let before := (← r.get).words
  expect ((← run r (schoolNotebook% "multimodalPumpRemote")) == (0,0) && (← r.get).words == before)
    "remote help rasterized before actual Store completion"
  -- Cold observation copies only the actual prepared workspace. No transient
  -- context/flag or prior console receipt supplies durable assistance identity.
  let cold ← IO.mkRef ({} : Model)
  for i in [:464] do put cold (workspace+i.toUInt64*8) (← get r (workspace+i.toUInt64*8))
  expect ((← run cold (PackageWorkspace.validate workspace 1 1)).1 == 0 &&
    (← get cold (workspace+64+208)) == 2 && (← get cold (workspace+64+192)) == 5)
    "actual copied cold workspace lost uncertain remote exposure"
  for changed in #[0,1,2,3,4] do
    let q ← IO.mkRef (← r.get)
    put q (base+160) 0;put q (base+136) 0;put q (base+128) 11
    if changed == 0 then put q (doc+40) 2
    else if changed == 1 then put q (base+80) 2
    else if changed == 2 then put q (base+72) 2
    else if changed == 3 then put q (proposal+40) 2
    else put q (school+48) 7
    q.modify fun m => {m with syscalls:=#[(0,88)],writes:=#[]}
    let stopped ← run q (schoolNotebook% "multimodalPumpRemote")
    expect (stopped.1 == 244 && (← get q remote) == 0 && (← get q (app+72)) == 0)
      "changed exact work/context presented prepared help"
    expect (!((← q.get).writes.any fun a => Lemma.Ink.Surface.framebuffer ≤ a && a < Lemma.Ink.Surface.framebuffer+1815000))
      "changed context rasterized before rejection"

private def fullPipelineChecks : IO Unit := do
  let r ← fixture
  let object := PackageWorkspace.object 1
  let ask : Lemma.School.Client.GuestAsk := {
    session := 1
    consent := 1
    revision := 1
    object := object.toNat
    sequence := 1
    source := 1
    edition := 1
    task_id := 4
    cutoff := 1
    now := 1
    deadline := 1000
    grants := 1 }
  let binding : Lemma.School.Client.SessionBinding := {
    school := "fixture"
    actor := "learner"
    enrollment := "enrollment"
    session := "old-session"
    guestSession := 1
    authority := "020000000000000006000000000000007856341200000000efcdab0000000000"
    bindingRecord := 6
    course := 1
    revision := 1
    policy := 1
    generation := 2
    expires := 1000 }
  let input : Lemma.School.Client.AssistInput := {
    school := "fixture"
    actor := "learner"
    session := "old-session"
    course := 1
    revision := 1
    policy := 1
    generation := 2
    now := 1
    ask := ask }
  let packet ← IO.ofExcept (Lemma.School.Client.handleAssist binding input "Use four products.")
  for i in [:packet.size] do
    let address := (0x332000:UInt64)+i.toUInt64
    let old ← get r (address-address%8)
    put r (address-address%8) ((old &&& ~~~((255:UInt64)<<<(address%8*8))) ||| (packet[i]!.toUInt64<<<(address%8*8)))
  expect ((← run r (Lemma.Multimodal.SchoolPacket.decode 0x332000 packet.size.toUInt64 proposal 2)) == (0,1)) "actual protected package decode"
  for (offset,value) in #[(0,1),(8,1),(16,1),(24,object),(32,0),(40,1),(48,1),(56,1),(64,4),(72,512),(80,0)] do put r (tutor+offset) value
  for (offset,value) in #[(0,Lemma.Multimodal.SchoolPacket.magic),(8,1),(16,2),(24,6),(32,0x12345678),
      (40,0xabcdef),(48,6),(56,2),(64,1000),(72,1),(80,1),(88,1),(96,1)] do put r (school+offset) value
  for (a,v) in #[(base+72,1),(base+80,1),(base+128,10),(base+24,3),(base+16,7),(base+176,50),
      (base+32,1650),(base+40,2200),(base+336,65535),(base+752,12),(app,packet.size.toUInt64),(app+16,1),(app+32,2)] do put r a v
  expect ((← run r (Lemma.Multimodal.SchoolPacket.actionReason proposal tutor school 1)) == (0,0)) "fixture exact original action rejected"
  for (a,v) in #[(base+512,1),(base+760,1),(app+72,1),(app+96,4),(app+208,5),(app+232,2),
      (app+240,1),(app+128,60001),(Lemma.User.Multimodal.state+144+8,1)] do put r a v
  r.modify fun m => {m with syscalls:=#[(0,1),(0,88),(0,88),(0,42)],writes:=#[]}
  expect ((← run r (schoolNotebook% "multimodalPackageWork")).1 == 0 && (← get r remote) == 1 &&
    (← get r (app+72)) == 3 && (← get r (base+160)) == 1 && (← r.get).syscalls.isEmpty)
    "ordinary package consumer bypassed prepared Store transaction"
  expect (!((← r.get).writes.any fun a => Lemma.Ink.Surface.framebuffer+320*825 ≤ a && a < Lemma.Ink.Surface.framebuffer+960*825))
    "assistance body rasterized before actual prepared Commit"
  -- Explicit fixture assumption: that transaction's real Store Commit reply
  -- has arrived. Execute the maintained completion Action, not a host renderer.
  put r (base+128) 11;put r (base+160) 3;put r (base+200) 3
  r.modify fun m => {m with syscalls:=#[(0,88)]}
  expect ((← run r (schoolNotebook% "finishRecord")).1 == 0 && (← get r (base+160)) == 0) "actual prepared completion Action"
  r.modify fun m => {m with syscalls:=#[(0,1),(0,88),(0,43),(0,88)],writes:=#[]}
  let rendered ← run r (schoolNotebook% "multimodalPumpRemote")
  expect (rendered.1 == 0 && (← get r remote) == 2 && (← get r (doc+192)) == 9 &&
    (← get r (app+72)) == 3 && (← get r (base+160)) == 1 && (← get r (tutor+32)) == 1 && (← r.get).syscalls.isEmpty)
    "actual render/second durable observation transaction/raster receipt ordering"
  expect ((← r.get).writes.any fun a => Lemma.Ink.Surface.framebuffer ≤ a && a < Lemma.Ink.Surface.framebuffer+1815000)
    "successful actual renderer did not touch its guest framebuffer"
  expect ((← get r 0x33a000) == 0x5b6f) "actual body renderer lost initial U of UNVERIFIED ASSISTANCE"
  expect ((← get r (workspace+64+192)) == 9 && (← get r (workspace+64+208)) == 2)
    "raster completed observation not in owned second Store snapshot"
  put r (base+128) 12;put r (base+160) 0;put r (base+136) 0
  r.modify fun m => {m with syscalls:=#[]}
  expect ((← run r (schoolNotebook% "multimodalPumpRemote")) == (0,0) && (← get r remote) == 0 &&
    (← get r (app+72)) == 0 && (← get r (app+144)) == 1)
    "second observed Commit did not release ordinary control ownership"

end RemoteProvenanceTests

def main : IO UInt32 := do
  RemoteProvenanceTests.docChecks
  RemoteProvenanceTests.pipelineChecks
  RemoteProvenanceTests.fullPipelineChecks
  IO.println "PASS: durable remote prepared/raster identity, legacy isolation, exact retry, capacity reserve, cold workspace, and real pending Store/context rejection Actions"
  return 0
