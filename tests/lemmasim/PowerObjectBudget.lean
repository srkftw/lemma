import Lemma.Kernel.Objects
import Lean.Elab.Command
import Std.Data.HashMap

/-! Independent finite-RAM observations of production object Actions. All
ordinary pressure uses the real frame allocator, AddressSpace and IPC metadata;
literal header corruption is confined to malformed-state negative fixtures. -/
namespace PowerObjectBudgetFixture
open Lemma.Core0.Memory Lemma.Kernel Lemma.Kernel.Memory Lemma.User

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  writes : Nat := 0
  operations : Nat := 0

def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  { s with words := if v = 0 then s.words.erase a else s.words.insert a v }
def require (condition : Bool) (message : String) : IO Unit :=
  if condition then pure () else throw <| IO.userError message

partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status, value)
  | .bind first next =>
    let (status, value) ← execute ref first
    execute ref (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    require (count.toNat ≤ budget) "count exceeds declared Action budget"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status == 0 then
        let result ← execute ref (step i.toUInt32 count value c0 c1 c2 c3)
        status := result.1
        value := result.2
    execute ref (next status value)
  | .platform op a b _ _ _ _ next =>
    let current ← ref.get
    require (current.operations < 3000000) "finite RAM oracle exhausted"
    require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x82200000))
      "operation outside independently bounded RAM"
    require (a % 8 == 0) "unaligned word operation"
    ref.set { current with operations := current.operations + 1 }
    if op == .physicalRead64 then execute ref (next 0 (word current a))
    else if op == .physicalWrite64 then
      ref.modify fun s => { (put s a b) with writes := s.writes + 1 }
      execute ref (next 0 0)
    else throw <| IO.userError "unexpected hardware primitive"
  | _ => throw <| IO.userError "unexpected Action constructor"

def success (ref : IO.Ref State) (action : Action) : IO UInt64 := do
  let (status, value) ← execute ref action
  require (status == 0) s!"expected success, observed {status}"
  pure value

def denied (ref : IO.Ref State) (status : UInt8) (action : Action) : IO Unit := do
  let before ← ref.get
  let result ← execute ref action
  let after ← ref.get
  require (result.1 == status && result.2 == 0) s!"expected status {status}, observed {result}"
  require (before.words == after.words && before.writes == after.writes)
    "rejection allocated or published RAM"

def main : IO Unit := do
  for power in [false, true] do
    let ref ← IO.mkRef ({} : State)
    discard <| success ref (Frames.configure 512 32 4)
    discard <| success ref Frames.init
    let before ← ref.get
    let handle ← success ref (if power then Objects.initPower else Objects.init)
    let base ← success ref Objects.table
    let state ← ref.get
    require (word state Objects.control == handle && word state base == 0x314a424f414d454c &&
      word state (base+8) == (if power then 2 else 1) &&
      word state (base+24) == (if power then 5 else 0) && word state (base+32) == 3 &&
      word state (base+40) == 0) "object constructor header differs from literal version contract"
    require (state.writes > before.writes) "constructor did not allocate/init real RAM"
    denied ref 16 (if power then Objects.initPower else Objects.init)
    let mut callers : Array UInt64 := #[]
    for owner in [2:10] do
      let descriptor ← success ref (AddressSpace.create owner.toUInt64)
      discard <| success ref (IPCStorage.initialize descriptor)
      callers := callers.push descriptor
    let mut endpoints : Array UInt64 := #[]
    let mut fourEndpoints ← ref.get
    for _ in [:if power then 5 else 4] do
      let key ← success ref (Objects.createEndpoint callers[0]!)
      require (key / 16 == 1 && key % 16 == (endpoints.size + 3).toUInt64)
        "endpoint keys/generations/rows changed"
      endpoints := endpoints.push key
      if endpoints.size == 4 then fourEndpoints ← ref.get
    let accepted ← ref.get
    let fullCount : UInt64 := if power then 8 else 7
    require (word accepted (base+32) == fullCount) "wrong live object count after endpoints"
    denied ref 90 (Objects.createEndpoint callers[0]!)
    require ((← success ref Objects.replyAvailable) == 8)
      "endpoint successor changed independent Reply budget"
    for i in [:8] do
      let caller := callers[i]!
      let transaction ← success ref (IPCStorage.prepare caller 3 endpoints[0]! 0 0 12345)
      discard <| success ref (Objects.createReply caller endpoints[0]! transaction 12345)
    let full ← ref.get
    require (word full (base+32) == fullCount + 8) "eight real replies did not retain 16-row limit"
    denied ref 90 Objects.replyAvailable
    denied ref 90 (Objects.createReply callers[0]! endpoints[0]! 1 12345)
    denied ref 90 (Objects.createEndpoint callers[0]!)
    -- Every malformed header must fail before queue allocation or publication.
    for (version, limit) in [(0,0),(1,5),(2,0),(2,4),(2,6),(3,5)] do
      ref.set (put (put accepted (base+8) version) (base+24) limit)
      denied ref 255 Objects.table
      denied ref 255 (Objects.createEndpoint callers[0]!)
    for (offset, value) in [(0,0),(16,0),(16,0x1000000000000001),(32,17),(40,9)] do
      ref.set (put accepted (base+offset) value)
      denied ref 255 Objects.table
      denied ref 255 (Objects.createEndpoint callers[0]!)
    ref.set accepted
    denied ref 80 (Objects.createEndpoint (callers[0]! + 0x200))
    discard <| success ref (Frames.pin 1 handle)
    denied ref 255 Objects.table
    denied ref 255 (Objects.createEndpoint callers[0]!)
    ref.set accepted
    ref.modify fun s => put s Objects.control callers[0]!
    denied ref 255 Objects.table
    ref.set accepted
    ref.modify fun s => put s Objects.control (handle + 512)
    denied ref 255 Objects.table
    if power then
      -- Queue allocation for an admitted fifth Endpoint must propagate real
      -- exhaustion without publishing a row/header or altering frame counts.
      ref.set fourEndpoints
      let remaining ← success ref Frames.remaining
      for _ in [:remaining.toNat] do
        discard <| success ref (Frames.allocate 1 1)
      require ((← success ref Frames.remaining) == 0) "ordinary allocation did not exhaust the pool"
      denied ref 33 (Frames.allocate 1 1)
      denied ref 33 (Objects.createEndpoint callers[0]!)
      require (word (← ref.get) (base+32) == 7) "OOM published the provisional fifth Endpoint"
  IO.println "PASS real allocator/Object v1 fourth/v2 fifth limits, eight Replies, OOM, and no-effect malformed/header/full rejections"

end PowerObjectBudgetFixture
run_cmd do
  Lean.Elab.Command.liftTermElabM do
    PowerObjectBudgetFixture.main
