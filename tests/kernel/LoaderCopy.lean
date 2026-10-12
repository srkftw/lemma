import Lemma.Kernel.Loader
import Lean.Elab.Term
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only finite RAM interprets the actual maintained loader Actions.
Literal payload spans, errors, neighbors, mappings and lifetimes are independent
expectations. These checks are not linked RV64 execution or a compiler proof. -/
open Lean Elab Term
/-- Host-only name resolution exposes the imported private implementation to
this fixture without adding a raw-copy entry point to the maintained target or
changing the Core0 compiler language. The Action body is the production body. -/
elab "loaderPrivateCopy%" : term => do
  let name := mkPrivateNameCore `Lemma.Kernel.Loader `Lemma.Kernel.Loader.copy
  let info ← getConstInfo name
  if info.name != name then throwError "unexpected loader declaration"
  pure (mkConst name)
private def productionCopy : UInt64 → UInt64 → UInt64 → Lemma.Core0.Memory.Action :=
  loaderPrivateCopy%

namespace LoaderFixture
open Lemma.Core0.Memory Lemma.Kernel.Memory

structure AccessEvent where
  op : Lemma.Core0.Execution.Op
  address : UInt64
  bytes : UInt64
  deriving BEq, Inhabited

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  events : Array AccessEvent := #[]
  callbacks : Nat := 0
  sourceSpan : Option (UInt64 × UInt64) := none
  targetSpan : Option (UInt64 × UInt64) := none
  failRead : Option UInt64 := none
  failWrite : Option UInt64 := none

def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  {s with words := if v = 0 then s.words.erase a else s.words.insert a v}
def byte (s : State) (a : UInt64) : UInt64 :=
  (word s (a - a % 8) >>> (a % 8 * 8)) &&& 255
def putByte (s : State) (a v : UInt64) : State :=
  let shift := a % 8 * 8
  put s (a - a % 8) ((word s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) |||
    ((v &&& 255) <<< shift))
def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message

def physical (a n : UInt64) : Bool :=
  ((0x80400000 ≤ a && a ≤ 0x80510000 - n) ||
   (0x80600000 ≤ a && a ≤ 0x80700000 - n) ||
   (0x82000000 ≤ a && a ≤ 0x84000000 - n))
def permitted (span : Option (UInt64 × UInt64)) (a n : UInt64) : Bool :=
  match span with
  | none => true
  | some (begin,length) => begin ≤ a && a - begin ≤ length && n ≤ length - (a - begin)

partial def execute (memory : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute memory first
    execute memory (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "fold exceeded its declared bound"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        memory.modify fun s => {s with callbacks := s.callbacks + 1}
        let result ← execute memory (step i.toUInt32 count value a b c d)
        status := result.1
        value := result.2
    execute memory (next status value)
  | .platform op a b _ _ _ _ next =>
    if op == .fenceInstruction || op == .installSatp then execute memory (next 0 0) else
    let n : UInt64 := if op == .physicalRead64 || op == .physicalWrite64 then 8 else 1
    let reading := op == .physicalRead64 || op == .physicalRead8
    let writing := op == .physicalWrite64 || op == .physicalWrite8
    require (reading || writing) "unexpected loader primitive"
    require ((← memory.get).events.size < 5000000) "fixture operation bound exceeded"
    memory.modify fun s => {s with events := s.events.push {op,address := a,bytes := n}}
    let state ← memory.get
    if n = 8 && a % 8 != 0 then execute memory (next 8 0) else
    if physical a n = false then execute memory (next 7 0) else
    if reading && state.failRead == some a then execute memory (next 95 0) else
    if writing && state.failWrite == some a then execute memory (next 96 0) else
    if reading then
      require (permitted state.sourceSpan a n) "copy read outside selected payload"
      execute memory (next 0 (if n = 8 then word state a else byte state a))
    else
      require (permitted state.targetSpan a n) "copy write outside selected destination"
      memory.modify fun s => if n = 8 then put s a b else putByte s a b
      execute memory (next 0 0)
  | _ => throw <| IO.userError "unexpected loader Action"

def success (memory : IO.Ref State) (action : Action) : IO UInt64 := do
  let (s,v) ← execute memory action
  require (s = 0) s!"unexpected status{s}"
  pure v
def pattern (i : Nat) : UInt64 := ((i * 37 + 19) % 256).toUInt64

def direct (sourceOffset targetOffset amount : UInt64) : IO Unit := do
  let source := 0x80601000 + sourceOffset
  let target := 0x82001000 + targetOffset
  let mut initial : State := {sourceSpan := some (source,amount),targetSpan := some (target,amount)}
  for i in [:amount.toNat] do initial := putByte initial (source + i.toUInt64) (pattern i)
  for i in [:4112] do initial := putByte initial (0x82000ff8 + i.toUInt64) 0xa5
  let memory ← IO.mkRef initial
  require ((← execute memory (productionCopy source target amount)) = (0,0))
    "copy status differs"
  let result ← memory.get
  for i in [:4112] do
    let a := 0x82000ff8 + i.toUInt64
    let expected := if target ≤ a && a - target < amount then pattern (a - target).toNat else 0xa5
    require (byte result a = expected) s!"copy or destination sentinel differs at{sourceOffset}/{targetOffset}/{amount}/{i}"
  for i in [:amount.toNat] do require (byte result (source + i.toUInt64) = pattern i) "source changed"
  let aligned := (source ||| target) &&& 7 = 0
  let words := result.events.filter fun e => e.op == .physicalRead64
  let bytes := result.events.filter fun e => e.op == .physicalRead8
  require (words.size = (if aligned then (amount / 8).toNat else 0)) "wrong complete-word count"
  require (bytes.size = (if aligned then (amount % 8).toNat else amount.toNat)) "wrong exact byte tail/fallback"

def failures : IO Unit := do
  for (source,target,amount) in #[(0x80601000,0x82001000,4097),
      (0xfffffffffffffffc,0x82001000,8),(0x80601000,0xfffffffffffffffc,8)] do
    let memory ← IO.mkRef ({} : State)
    require ((← execute memory (productionCopy source target amount)) = (83,0))
      "invalid bound/overflow admitted"
    require ((← memory.get).events.isEmpty) "invalid bound performed an access"
  let empty ← IO.mkRef ({} : State)
  require ((← execute empty (productionCopy 0xffffffffffffffff 0xffffffffffffffff 0)) = (0,0))
    "zero copy inspected arbitrary addresses"
  require ((← empty.get).events.isEmpty) "zero copy performed an access"
  for (offset,readFailure) in #[(0,true),(8,true),(16,true),(0,false),(8,false),(16,false)] do
    let source : UInt64 := 0x80601000
    let target : UInt64 := 0x82001000
    let mut initial : State := {
      sourceSpan := some (source,23)
      targetSpan := some (target,23)
      failRead := (if readFailure then some (source + offset) else none)
      failWrite := (if readFailure then none else some (target + offset))}
    for i in [:23] do
      initial := putByte (putByte initial (source + i.toUInt64) (pattern i))
        (target + i.toUInt64) 0xa5
    let memory ← IO.mkRef initial
    require ((← execute memory (productionCopy source target 23)) =
      (if readFailure then 95 else 96,0)) "copy swallowed read/write failure"
    let result ← memory.get
    require (result.events.back!.address = (if readFailure then source + offset else target + offset))
      "failed access did not short-circuit"
    for i in [:23] do
      require (byte result (target + i.toUInt64) = (if i.toUInt64 < offset then pattern i else 0xa5))
        "failed access altered remaining destination bytes"
  IO.println "LOADER_FAILURES:PASS overflow/zero/read/write exact-short-circuit"

def work : IO Unit := do
  let source : UInt64 := 0x80601000
  let target : UInt64 := 0x82001000
  let new ← IO.mkRef ({} : State)
  discard <| success new (productionCopy source target 4096)
  require ((← new.get).events.size = 1024 && (← new.get).callbacks = 512)
    "aligned loader did not reduce real accesses/callbacks"
  let actual ← new.get
  IO.println s!"LOADER_COPY_WORK:4096bytes accesses{actual.events.size} callbacks{actual.callbacks}"

def package (s : State) (textOffset textBytes dataOffset dataBytes : UInt64) : State := Id.run do
  let p : UInt64 := 0x80600000
  let values : Array UInt64 := #[0x31474b50414d454c,2,1,dataOffset + dataBytes,
    1,0x1000000,0x1000000,textOffset,textBytes,0x20000,dataOffset,dataBytes,
    4096,0x3fffa000,4,0]
  let mut result := s
  for i in [:values.size] do result := put result (p + i.toUInt64 * 8) values[i]!
  for i in [:textBytes.toNat] do result := putByte result (p + textOffset + i.toUInt64) (pattern i)
  for i in [:dataBytes.toNat] do result := putByte result (p + dataOffset + i.toUInt64) (pattern (i + 7000))
  return {result with events := #[],callbacks := 0}

def lifetime : IO Unit := do
  let memory ← IO.mkRef ({} : State)
  discard <| success memory (Frames.configure 8192 8192 4)
  discard <| success memory Frames.init
  let initial := package (← memory.get) 160 4111 4280 17
  memory.set initial
  let descriptor ← success memory (Lemma.Kernel.Loader.load 0 2 0)
  let first ← success memory (AddressSpace.lookup descriptor 0x1000000 4)
  let second ← success memory (AddressSpace.lookup descriptor 0x1001000 4)
  let data ← success memory (AddressSpace.lookup descriptor 0x20000 1)
  let loaded ← memory.get
  for i in [:4111] do
    let physical := if i < 4096 then first + i.toUInt64 else second + (i - 4096).toUInt64
    require (byte loaded physical = pattern i) "loaded text bytes differ"
  for i in [15:4096] do require (byte loaded (second + i.toUInt64) = 0) "final text page padding not zero"
  for i in [:17] do require (byte loaded (data + i.toUInt64) = pattern (i + 7000)) "loaded data differs"
  for i in [17:4096] do require (byte loaded (data + i.toUInt64) = 0) "BSS was not zero"
  require ((← execute memory (AddressSpace.lookup descriptor 0x1000000 2)).1 = AddressSpace.invalidPermission)
    "text mapping became writable"
  discard <| success memory (Lemma.Kernel.Loader.teardown descriptor)
  require (word (← memory.get) Frames.accounting = 8192) "successful teardown leaked owned frames"
  require ((← execute memory (AddressSpace.base descriptor)).1 != 0) "released descriptor remained live"
  for failedAt in #[0x806000a0,0x806000a8,0x806010a0,0x806010a8,0x806010b8] do
    memory.set {initial with failRead := some failedAt}
    require ((← execute memory (Lemma.Kernel.Loader.load 0 2 0)) = (95,0)) "load did not retain original copy failure"
    require (word (← memory.get) Frames.accounting = 8192) "failed unmapped copy leaked owned frames"
    for index in [:8192] do
      require (word (← memory.get) (0x80401000 + index.toUInt64 * 32) = 0)
        "failed load published an owned frame"
  memory.set (put initial (0x80600000 + 56) 0xfffffffffffffff0)
  require ((← execute memory (Lemma.Kernel.Loader.load 0 2 0)).1 = 83) "wrapped source package accepted"
  require (word (← memory.get) Frames.accounting = 8192) "malformed package allocated a frame"
  IO.println "LOADER_LIFETIME:PASS real-owned pages, exact copied text/data, zero BSS/padding, RX permission, teardown, failed-copy abort, malformed package"

def check : IO Unit := do
  for amount in #[0,1,7,8,9,15,16,17,31,4095,4096] do
    for source in [:8] do
      for target in [:8] do direct source.toUInt64 target.toUInt64 amount
  failures
  work
  lifetime
  IO.println "LOADER_COPY:PASS maintained Lean Action fixture; linked RV64 execution separate"
end LoaderFixture
open Lean Elab Command
run_cmd liftIO LoaderFixture.check
