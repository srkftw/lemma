import Lemma.Documents.MathematicsClosure
import Lemma.Courses.HintVisibility
import Lemma.Courses.Review
import Lemma.Courses.LocalReduction
import Std.Data.HashMap

/-! Execute the actual read-only consumers over structurally valid synthetic
document histories. No CPU, learner assessment or durable-commit claim. -/
namespace DocumentEventConsumerTests
open Lemma.Core0.Memory Lemma.User Lemma.Courses
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

private def doc : UInt64 := 0x10000
private def event : UInt64 := 0x20000
private def fixture : IO (IO.Ref Model) := do
  let r ← IO.mkRef ({} : Model)
  expect ((← run r (Lemma.Documents.MathematicsClosure.create doc 1 1)).1 == 0) "create original document"
  put r (doc+56) 5; put r (doc+64) 6
  return r
private def checked (r : IO.Ref Model) : IO Unit := do
  expect ((← run r (Lemma.Documents.MathematicsClosure.completeExecution doc 1 1 1 66 8)).1 == 0) "original consumer checked attempt"
private def appendTool (r : IO.Ref Model) (source : UInt64) : IO Unit := do
  for (offset,value) in (#[(0,1),(8,Lemma.Documents.LocalToolEvents.descriptor 1 0),(16,0),(24,77),
      (32,Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity),(40,source),(48,1),(56,3),(64,0),
      (72,0x504b000000000001),(80,5),(88,6),(96,0),(104,0),(112,0),(120,0)] : Array (UInt64×UInt64)) do put r (event+offset) value
  expect ((← run r (Lemma.Documents.LocalToolEvents.append doc event)).1 == 0 &&
    (← run r (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 == 0) "valid source257 local event history"
private def remote (r : IO.Ref Model) : IO Unit := do
  for (offset,value) in (#[(0,1),(8,(7:UInt64) ||| ((1:UInt64)<<<8) ||| ((1:UInt64)<<<16) ||| ((4:UInt64)<<<24) ||| ((9:UInt64)<<<32)),
      (16,0x504b000000000001),(24,6),(32,1),(40,0x10102),(48,0),(56,0)] : Array (UInt64×UInt64)) do put r (event+offset) value
  expect ((← run r (Lemma.Documents.Mathematics.appendRemote doc event)).1 == 0 &&
    (← run r (Lemma.Documents.MathematicsClosure.validate doc 1 1)).1 == 0) "valid remote digest resembling authored hint"
private def readOnly (r : IO.Ref Model) (action : Action) : IO (UInt8×UInt64) := do
  let before ← r.get
  let result ← run r action
  expect ((← r.get).words == before.words && (← r.get).writes == before.writes) "read-only consumer changed original document"
  return result
private def afterReduction : IO Unit := do
  let r ← fixture
  put r (doc+56) 10; put r (doc+64) 12
  let workspace : UInt64 := 0x24000
  let staged : UInt64 := 0x28000
  let saved : UInt64 := 0x2c000
  let request : UInt64 := 0x30000
  let response : UInt64 := 0x30400
  let toolMeta : UInt64 := 0x30600
  expect ((← run r (PackageWorkspace.create workspace doc 1 1)).1 == 0 &&
    (← run r (LocalReduction.request workspace doc request event toolMeta 1 1 77)).1 == 0) "actual reduction request"
  expect ((← run r (LocalReduction.stagePrepared workspace doc staged saved event)).1 == 0) "actual prepared staging"
  for i in [:464] do put r (workspace+i.toUInt64*8) (← get r (saved+i.toUInt64*8))
  for i in [:312] do put r (doc+i.toUInt64*8) (← get r (workspace+64+i.toUInt64*8))
  let (status,packed) ← run r (Lemma.Services.Arithmetic.ProtocolV9.evaluate request)
  expect (status == 0 && (← run r (Lemma.Services.Arithmetic.ProtocolV9.reply request (response+64) packed 0)).1 == 0) "actual reduction service result"
  for (offset,value) in (#[(0,IPCABI.messageMagic),(8,IPCABI.replyKind),(16,3),(24,77),(32,0),(40,176),(48,0),(56,0)] : Array (UInt64×UInt64)) do put r (response+offset) value
  expect ((← run r (Lemma.Services.Arithmetic.ClientV9.validate response request 77 240)) == (0,1)) "actual copied reply admission"
  expect ((← run r (LocalReduction.stageApplied workspace doc staged saved request event response 1 1)).1 == 0) "actual admitted reduction staging"
  for i in [:464] do put r (workspace+i.toUInt64*8) (← get r (saved+i.toUInt64*8))
  for i in [:312] do put r (doc+i.toUInt64*8) (← get r (workspace+64+i.toUInt64*8))
  expect ((← run r (PackageWorkspace.validate workspace 1 1)).1 == 0 &&
    (← get r (doc+56)) == 5 && (← get r (doc+64)) == 6 && (← get r (doc+96)) == 0 &&
    (← get r (doc+40)) == 2 && (← get r (doc+208)) == 3) "local reduction became checker evidence or lost format3"
  expect ((← run r (Lemma.Documents.Mathematics.hint doc)).1 == 0 &&
    (← readOnly r (HintVisibility.current doc)) == (0,1)) "actual authored hint after REDUCE disappeared"
  expect ((← run r (Lemma.Documents.MathematicsClosure.completeExecution doc 2 1 1 67 8)).1 == 0 &&
    (← readOnly r (Review.summary doc)) == (0,17)) "later explicit check lost conservative local-tool history"
private def check : IO Unit := do
  afterReduction
  let r ← fixture
  checked r
  appendTool r 257
  let reviewed ← readOnly r (Review.summary doc)
  expect ((← run r (Lemma.Documents.Mathematics.hint doc)).1 == 0) "actual authored hint following format3"
  let visible ← readOnly r (HintVisibility.current doc)
  IO.println s!"OBSERVED_EVENT3_CONSUMERS review={reviewed.2} authoredHint={visible.2}"
  expect (reviewed == (0,17)) "event payload source257 replaced actual checking outcome"
  expect (visible == (0,1)) "actual authored hint after format3 disappeared"
  let rr ← fixture
  remote rr
  expect ((← readOnly rr (HintVisibility.current doc)) == (0,0)) "remote digest payload became authored hint"
  expect ((← run rr (Lemma.Documents.Mathematics.hint doc)).1 == 0 &&
    (← readOnly rr (HintVisibility.current doc)) == (0,1)) "actual authored hint after format2 disappeared"
  let mixed ← fixture
  checked mixed
  remote mixed
  appendTool mixed 257
  expect ((← readOnly mixed (Review.summary doc)) == (0,17) &&
    (← readOnly mixed (HintVisibility.current doc)) == (0,0)) "mixed typed payload changed outcome or created a hint"
  expect ((← run mixed (Lemma.Documents.Mathematics.hint doc)).1 == 0 &&
    (← readOnly mixed (HintVisibility.current doc)) == (0,1)) "hint after mixed remote/tool history disappeared"
  for version in [1,2,3] do
    let old ← fixture
    put old (doc+208) version
    checked old
    expect ((← readOnly old (Review.summary doc)) == (0,26)) "unassisted exact baseline changed"
    expect ((← run old (Lemma.Documents.Mathematics.hint doc)).1 == 0 &&
      (← readOnly old (HintVisibility.current doc)) == (0,1) &&
      (← readOnly old (Review.summary doc)) == (0,17)) "authored hint semantics changed"
    put old (doc+40) 2
    expect ((← readOnly old (HintVisibility.current doc)) == (0,0)) "old-revision hint exposed"
    put old (doc+40) 1; put old (doc+48) 2
    expect ((← readOnly old (HintVisibility.current doc)) == (0,0)) "other-goal hint exposed"
  let unrelated ← fixture
  checked unrelated
  appendTool unrelated 257
  put unrelated (doc+48) 2
  expect ((← readOnly unrelated (Review.summary doc)) == (0,9)) "other-goal tool payload influenced review"
  let malformed ← IO.mkRef (← r.get)
  put malformed (doc+192) 65
  expect ((← readOnly malformed (Review.summary doc)) == (235,0) &&
    (← readOnly malformed (HintVisibility.current doc)) == (235,0)) "event arena overrun accepted"
  put malformed (doc+192) 8
  expect ((← readOnly malformed (Review.summary doc)) == (234,0) &&
    (← readOnly malformed (HintVisibility.current doc)) == (234,0)) "truncated typed payload accepted"
  IO.println "PASS document event consumers: source257 cannot erase check; formats1/2/3 authored hints; payload hint masquerade; mixed groups; current revision/goal; read-only bounds"
end DocumentEventConsumerTests

def main : IO Unit := DocumentEventConsumerTests.check
