import Lean
import Lemma.Applications.Notebook
import Lemma.Courses.LocalReduction
import Lemma.Courses.PackageReference
import Std.Data.HashMap

/-! Actual maintained Actions over a finite independent RAM/IPC observer.
No CPU, durable Commit, learner or educational-result claim. -/
open Lean Elab Term
elab "schoolReduction% " short:str : term => do
  let wanted := "Lemma.Applications.Notebook." ++ short.getString
  let found := (← getEnv).constants.toList.filter fun (name,_) =>
    ((privateToUserName? name).getD name).toString == wanted
  if found.length != 1 then throwError "missing actual reduction helper {wanted}"
  return mkConst found.head!.1

namespace LocalReductionTests
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
private def storeReply (r : IO.Ref Model) (packet operation ns object request sequence count detail : UInt64) : IO Unit := do
  for (i,value) in (#[IPCABI.messageMagic,IPCABI.replyKind,3,request,0,64+count,0,0,
      Lemma.Services.Store.Protocol.magic,1,operation,ns,object,sequence,detail,count]).zipIdx do
    put r (packet+value.toUInt64*8) i



private def doc : UInt64 := Lemma.Applications.Notebook.mathematics
private def workspace : UInt64 := 0x33b000
private def staged : UInt64 := 0x33d000
private def stagedWorkspace : UInt64 := Lemma.Applications.Notebook.mathematicsSave
private def request : UInt64 := Lemma.Applications.Notebook.mathematicsIO
private def response : UInt64 := request+256
private def event : UInt64 := request+640
private def toolMeta : UInt64 := request+512
private def fixture : IO (IO.Ref Model) := do
  let r ← IO.mkRef ({} : Model)
  expect ((← run r (Lemma.Documents.MathematicsClosure.create doc 1 1)).1 == 0) "create Doc8"
  put r (doc+56) 10; put r (doc+64) 12
  expect ((← run r (Lemma.Courses.PackageWorkspace.create workspace doc 1 1)).1 == 0) "create original workspace"
  expect ((← run r (Lemma.Courses.LocalReduction.request workspace doc request event toolMeta 1 1 77)).1 == 0) "actual request/prepared row"
  expect ((← get r request) == Lemma.Services.Arithmetic.ProtocolV9.magic && (← get r (request+96)) == 77 &&
    (← get r (request+128)) == 0 && (← get r (request+136)) == 0) "copied144-byte request fields"
  return r
private def adopt (r : IO.Ref Model) : IO Unit := do
  for i in [:464] do put r (workspace+i.toUInt64*8) (← get r (stagedWorkspace+i.toUInt64*8))
  for i in [:312] do put r (doc+i.toUInt64*8) (← get r (workspace+64+i.toUInt64*8))
private def prepare (r : IO.Ref Model) : IO Unit := do
  let before ← get r (doc+192)
  expect ((← run r (Lemma.Courses.LocalReduction.stagePrepared workspace doc staged stagedWorkspace event)).1 == 0) "stage original prepared document"
  expect ((← get r (doc+192)) == before) "staging mutated active work before publication"
  adopt r
  expect ((← get r (doc+192)) == before+8 && (← get r (doc+208)) == 3) "prepared event arena shape"
  expect ((← run r (PackageWorkspace.validate workspace 1 1)).1 == 0) "cold/reopened prepared workspace fails validator"
private def reply (r : IO.Ref Model) : IO Unit := do
  let (status,packed) ← run r (Lemma.Services.Arithmetic.ProtocolV9.evaluate request)
  expect (status == 0) "actual local tool calculation"
  expect ((← run r (Lemma.Services.Arithmetic.ProtocolV9.reply request (response+IPCABI.headerBytes) packed 0)).1 == 0) "actual copied176-byte reply"
  let requestID ← get r (request+96)
  for (offset,value) in (#[(0,IPCABI.messageMagic),(8,IPCABI.replyKind),(16,3),(24,requestID),(32,0),(40,176),(48,0),(56,0)] : Array (UInt64×UInt64)) do put r (response+offset) value
private def toolChecks : IO Unit := do
  let r ← fixture
  prepare r
  let again ← run r (Lemma.Documents.LocalToolEvents.append doc event)
  expect (again == (0,1) && (← get r (doc+192)) == 8) "lost prepared receipt duplicated immutable event"
  reply r
  expect ((← run r (Lemma.Services.Arithmetic.ClientV9.validate response request 77 240)) == (0,1)) "valid real reply not admitted"
  for offset in [0:18] do
    let bad ← IO.mkRef (← r.get)
    put bad (response+64+offset.toUInt64*8) ((← get bad (response+64+offset.toUInt64*8)) ^^^ 1)
    expect ((← run bad (Lemma.Services.Arithmetic.ClientV9.validate response request 77 240)).1 != 0) "changed echoed request admitted"
  for (offset,value) in (#[(16,0),(24,78),(32,1),(40,175),(64+168,0),(64+152,0),(64+160,6)] : Array (UInt64×UInt64)) do
    let bad ← IO.mkRef (← r.get); put bad (response+offset) value
    expect ((← run bad (Lemma.Services.Arithmetic.ClientV9.validate response request 77 240)).1 != 0) "malformed IPC/result admitted"
  for (offset,value) in (#[(40,2),(56,11),(64,13)] : Array (UInt64×UInt64)) do
    let bad ← IO.mkRef (← r.get); put bad (doc+offset) value
    expect ((← run bad (Lemma.Courses.LocalReduction.stageApplied workspace doc staged stagedWorkspace request event response 1 1)).1 != 0) "changed current work admitted"
  expect ((← run r (Lemma.Courses.LocalReduction.stageApplied workspace doc staged stagedWorkspace request event response 1 1)).1 == 0) "actual admitted result could not stage"
  expect ((← get r (doc+56)) == 10) "result changed active document before owned publication"
  adopt r
  expect ((← get r (doc+56)) == 5 && (← get r (doc+64)) == 6 && (← get r (doc+40)) == 2 &&
    (← get r (doc+96)) == 0 && (← get r (doc+104)) == 0 && (← get r (doc+144)) == 0 && (← get r (doc+192)) == 16) "tool relabeled result as checking or lost revision/event"
  expect ((← run r (PackageWorkspace.validate workspace 1 1)).1 == 0) "applied/cold workspace validator"
  let duplicated ← IO.mkRef (← r.get)
  for i in [:16] do put duplicated (doc+832+16*16+i.toUInt64*8) (← get duplicated (doc+832+8*16+i.toUInt64*8))
  put duplicated (doc+192) 24
  expect ((← run duplicated (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 != 0) "cold duplicate terminal history accepted"
  let terminal ← IO.mkRef (← r.get)
  put terminal (event+8) (Lemma.Documents.LocalToolEvents.descriptor 3 3); put terminal (event+16) 0
  put terminal (event+96) 0; put terminal (event+104) 0
  expect ((← run terminal (Lemma.Documents.LocalToolEvents.append doc event)).1 != 0) "conflicting applied/cancelled terminal accepted"
  let malformed ← IO.mkRef (← r.get)
  put malformed (doc+832+8*16+24) 78
  expect ((← run malformed (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 != 0) "terminal without exact prepared request accepted"
  let exhausted ← fixture
  put exhausted (doc+192) 49
  expect ((← run exhausted (Lemma.Courses.LocalReduction.request workspace doc request event toolMeta 1 1 78)).1 != 0) "prepared did not reserve terminal capacity"
  let undefined ← fixture; put undefined (doc+64) 0
  expect ((← run undefined (Lemma.Courses.LocalReduction.request workspace doc request event toolMeta 1 1 78)).1 != 0) "undefined denominator entered prepared service workflow"

private def provenanceChecks : IO Unit := do
  let r ← fixture
  expect ((← run r (Lemma.Documents.MathematicsClosure.completeExecution doc 1 1 1 66 8)).1 == 0) "original independently scoped checker attempt"
  expect ((← run r (PackageWorkspace.create workspace doc 1 1)).1 == 0) "capture original checked work"
  prepare r; reply r
  expect ((← run r (Lemma.Courses.LocalReduction.stageApplied workspace doc staged stagedWorkspace request event response 1 1)).1 == 0) "apply to previously checked work"
  adopt r
  expect ((← get r (doc+96)) == 0 && (← get r (doc+104)) == 0 && (← get r (doc+144)) == 1 &&
    (← get r (doc+256)) == 1 && (← get r (doc+256+16)) == 10 && (← get r (doc+256+24)) == 12 &&
    (← get r (doc+256+56)) == 1) "local edit laundered old checker applicability or rewrote original attempt"
  expect ((← run r (PackageWorkspace.validate workspace 1 1)).1 == 0) "original checked history lost after tool edit"
  let remote : UInt64 := 0x3a0000
  for (offset,value) in (#[(0,2),(8,(7:UInt64) ||| ((1:UInt64)<<<8) ||| ((1:UInt64)<<<16) ||| ((4:UInt64)<<<24) ||| ((9:UInt64)<<<32)),
      (16,PackageWorkspace.object 1),(24,6),(32,2),(40,6),(48,0x12345678),(56,0xabcdef)] : Array (UInt64×UInt64)) do put r (remote+offset) value
  expect ((← run r (Lemma.Documents.Mathematics.appendRemote doc remote)).1 == 0 && (← get r (doc+208)) == 3) "remote append downgraded event3 or misread tool payload"
  expect ((← run r (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 == 0) "remote/tool/ordinary history coexistence"
  let known ← fixture
  let image ← IO.ofExcept <| (Package.encode PackageReference.arithmetic).mapError (·.render)
  for i in [:image.size] do
    let a := (0x332000:UInt64)+i.toUInt64
    let old ← get known (a-a%8)
    put known (a-a%8) ((old &&& ~~~((255:UInt64)<<<(a%8*8))) ||| (image[i]!.toUInt64<<<(a%8*8)))
  expect ((← run known (PackageWorkspace.captureSelection workspace 0x332000 image.size.toUInt64 2 0x33c400)).1 == 0) "known original full-source capture"
  expect ((← run known (Lemma.Courses.LocalReduction.request workspace doc request event toolMeta 1 1 78)).1 == 0) "known source tool request after actual capture"
  for (a,v) in #[(context+2048+32,2),(context+2048,image.size.toUInt64)] do put known a v
  expect ((← run known (schoolReduction% "reductionSourceLoaded")).1 == 0) "genuine current original publication not admitted"
  for (a,v) in #[(request+24,2),(request+32,2),(toolMeta,(← get known toolMeta) ^^^ 1)] do
    let changed ← IO.mkRef (← known.get); put changed a v
    expect ((← run changed (schoolReduction% "reductionSourceLoaded")).1 != 0) "captured original source/edition/CRC mismatch admitted"
  for offset in #[24,32,80] do
    let changed ← IO.mkRef (← known.get)
    put changed (0x332000+offset) ((← get changed (0x332000+offset)) ^^^ 1)
    expect ((← run changed (schoolReduction% "reductionSourceLoaded")).1 != 0) "changed original package/source/CRC admitted"
  let overlay ← IO.mkRef (← known.get)
  put overlay (0x332000+24) 60001
  expect ((← run overlay (schoolReduction% "reductionSourceLoaded")).1 != 0) "help overlay supplied local tool source"
  let badRequest ← IO.mkRef (← known.get)
  put badRequest (request+40) (PackageWorkspace.object 2)
  expect ((← run badRequest (Lemma.Courses.LocalReduction.current workspace doc request event 1 1)).1 != 0) "different work object accepted"
  prepare known; reply known
  expect ((← run known (Lemma.Services.Arithmetic.ClientV9.validate response request 78 240)).1 == 0) "known original reply admission"
  expect ((← run known (Lemma.Courses.LocalReduction.stageApplied workspace doc staged stagedWorkspace request event response 1 1)).1 == 0) "known source application"
  expect ((← run known (schoolReduction% "reductionRecapture")).1 == 0 &&
    (← get known (stagedWorkspace+PackageWorkspace.selection+120)) == 2) "new typed revision did not get real full-source recapture"
  expect ((← run known (PackageWorkspace.snapshotSelection stagedWorkspace 0x33c480)).1 == 0) "ordinary next CHECK cannot snapshot changed local-tool work"

private def notebookChecks : IO Unit := do
  for mode in [0:3] do
    let r ← IO.mkRef ({} : Model)
    expect ((← run r ((schoolReduction% "configureSchoolMode") mode.toUInt64)).1 == 0) "versioned School mode"
    expect ((← get r (base+760)) == (if mode == 2 then 1 else mode.toUInt64) &&
      (← get r (base+728)) == (if mode == 2 then 1 else 0)) "School24 weakened legacy admission flag"
    if mode < 2 then
      r.modify fun m => {m with forbiddenPage:=some request}
      expect ((← run r (schoolReduction% "beginLocalReduction")).1 == 241) "legacy acquired REDUCE or accessed unallocated tool page"
  let r ← fixture
  prepare r
  for (a,v) in #[(base+728,1),(base+536,16),(base+160,1),(base+136,0),(base+128,100),(base+72,1),(base+80,1),(toolMeta+8,100),(base+528,5),(base+552,77),(base+24,3)] do put r a v
  let before := (← r.get).words
  expect ((← run r (schoolReduction% "pumpLocalReduction")) == (0,0) && (← r.get).words == before) "service started before Store terminal"
  put r (base+160) 0
  expect ((← run r (schoolReduction% "pumpLocalReduction")) == (0,0) && (← get r (base+536)) == 16) "RAM-only frontier accepted as durable commit"
  put r (base+128) 101
  r.modify fun m => {m with syscalls:=#[(0,55),(0,88)]}
  expect ((← run r (schoolReduction% "pumpLocalReduction")).1 == 0 && (← get r (base+536)) == 17 &&
    (← get r (base+544)) == 55 && (← r.get).syscalls.isEmpty) "actual committed barrier did not begin isolated IPC"
  r.modify fun m => {m with syscalls:=#[(IPCABI.wouldBlock,0)]}
  expect ((← run r (schoolReduction% "pumpLocalReduction")) == (0,0) && (← get r (base+536)) == 17) "pending call was lost"
  r.modify fun m => {m with syscalls:=#[(0,0),(IPCABI.canceled,0),(0,88)]}
  expect ((← run r (schoolReduction% "cancelArithmetic")).1 == 0 && (← get r (base+536)) == 0 &&
    (← get r (doc+192)) == 8 && (← get r (doc+56)) == 10 && (← r.get).syscalls.isEmpty) "cancel applied tool or erased prepared uncertainty"

def main : IO Unit := do
  toolChecks
  provenanceChecks
  notebookChecks
  IO.println "PASS actual local reduction: durable-row staging/cold validation, 25 copied reply negatives, stale work, bounded resources, legacy/version/Commit/IPC/cancellation ownership"
end LocalReductionTests

def main : IO Unit := LocalReductionTests.main
