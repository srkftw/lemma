import Lemma.Kernel.Memory.AddressSpace
import Lean.Elab.Command
import Std.Data.HashMap

/-! Independent finite byte RAM interpreting the production Actions. Literal
registry mutations probe duplicate/error ordering at eight-row and page cuts.
The bounded work observations count actual callbacks/accesses, not RV64 cycles. -/
namespace ProductASFixture
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  reads : Array UInt64 := #[]
  writes : Nat := 0
  callbacks : Nat := 0
  operations : Nat := 0
  failRead : Option UInt64 := none
  failWrite : Option (UInt64 × UInt64) := none
  faultUsed : Bool := false

def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  { s with words := if v = 0 then s.words.erase a else s.words.insert a v }
def byte (s : State) (a : UInt64) : UInt64 :=
  (word s (a - a % 8) >>> (a % 8 * 8)) &&& 255
def putByte (s : State) (a v : UInt64) : State :=
  let shift := a % 8 * 8
  put s (a - a % 8) ((word s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) |||
    ((v &&& 255) <<< shift))

def require (b : Bool) (message : String) : IO Unit :=
  if b then pure () else throw <| IO.userError message

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then execute state (next 9 initial) else
    let mut status : UInt8 := 0
    let mut acc := initial
    for i in [:count.toNat] do
      if status = 0 then
        state.modify fun s => { s with callbacks := s.callbacks + 1 }
        let result ← execute state (step i.toUInt32 count acc c0 c1 c2 c3)
        status := result.1
        acc := result.2
    execute state (next status acc)
  | .platform op a b _ _ _ _ next =>
    let s ← state.get
    if s.operations ≥ 10000000 then throw <| IO.userError "fixture budget exhausted"
    state.set { s with operations := s.operations + 1 }
    if op == .installSatp then execute state (next 0 0)
    else if op == .deviceRead64 then execute state (next 0 0)
    else
      require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000))
        s!"access outside finite physical RAM {a}"
      match op with
      | .physicalRead64 =>
        require (a % 8 == 0) "unaligned read64"
        state.modify fun s => { s with reads := s.reads.push a }
        if (← state.get).failRead == some a then execute state (next 95 0)
        else execute state (next 0 (word (← state.get) a))
      | .physicalWrite64 =>
        require (a % 8 == 0) "unaligned write64"
        if s.failWrite == some (a,b) && !s.faultUsed then
          state.modify fun s => { s with faultUsed := true }
          execute state (next 96 0)
        else
          state.modify fun s => { (put s a b) with writes := s.writes + 1 }
          execute state (next 0 0)
      | .physicalRead8 =>
        if (← state.get).failRead == some a then execute state (next 95 0)
        else execute state (next 0 (byte (← state.get) a))
      | .physicalWrite8 =>
        state.modify fun s => { (putByte s a b) with writes := s.writes + 1 }
        execute state (next 0 0)
      | _ => throw <| IO.userError "unexpected primitive"
  | _ => throw <| IO.userError "unexpected Action"

def success (state : IO.Ref State) (action : Action) : IO UInt64 := do
  let (s,v) ← execute state action
  require (s == 0) s!"unexpected status{s}"
  pure v

def resetTrace (s : State) : State := { s with reads := #[], writes := 0, callbacks := 0, operations := 0, failRead := none, failWrite := none, faultUsed := false }
def slot (table va : UInt64) : UInt64 := table + ((va >>> 12) &&& 511) * 8
/-- Independent literal Sv39 walker, without invoking the implementation's
vpn, tableEntry, leafEntry, lookup or permission helpers. -/
def leaf (s : State) (root va : UInt64) : UInt64 := Id.run do
  let first := word s (root + ((va >>> 30) &&& 511) * 8)
  if first &&& 0x3ff != 1 then return 0
  let middle := (first >>> 10) <<< 12
  let second := word s (middle + ((va >>> 21) &&& 511) * 8)
  if second &&& 0x3ff != 1 then return 0
  return word s (((second >>> 10) <<< 12) + ((va >>> 12) &&& 511) * 8)

def run : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 8192 8192 4)
  discard <| success state Frames.init
  let initialized := resetTrace (← state.get)
  state.set (put initialized AddressSpace.productSelection 7)
  let descriptor ← success state (AddressSpace.createProduct 2)
  let address ← success state (AddressSpace.base descriptor)
  let root := word (← state.get) (address + 64)
  let golden := resetTrace (← state.get)
  require (word golden (address + 8) == 3 && word golden (address + 40) == 14 &&
    word golden (address + 88) == 0x3353415000000020) "Product descriptor layout/witness"
  for va in [0x81fc0000,0x81fc1000,0x81fc2000,0x81fc3000,0x10012000] do
    let pte := leaf golden root va
    require (pte == (va >>> 12 <<< 10 ||| 0xc7)) "Product literal supervisor PTE"
    require (pte &&& 0x10 == 0 && pte &&& 8 == 0 && pte &&& 6 == 6)
      "Product alias must be supervisor RW/NX"
  for va in [0x81fbf000,0x81fc4000,0x81fd0000,0x10013000] do
    require (leaf golden root va == 0) "Product alias neighbor escaped exact bounds"
  for i in [:14] do
    let handle := word golden (address + 128 + i.toUInt64 * 8)
    let resolved ← success state (Frames.resolvePurpose 2 handle 2)
    require (0x82000000 ≤ resolved && resolved < 0x84000000) "table outside owned pool"
    require ((← success state (Frames.mappingCount 2 handle)) == 1) "table not pinned exactly once"
  for (offset,value) in [(8,2),(88,32),(88,0x3353415000000021),(40,13)] do
    state.set (put golden (address + offset) value)
    require ((← execute state (AddressSpace.base descriptor)).1 == 70) "Product retag/header corruption accepted"
  state.set golden
  discard <| success state (AddressSpace.destroy descriptor)
  require ((← success state Frames.remaining) == 8192) "Product destroy leaked frames"
  -- An arbitrary or missing selection never allocates/publishes a root.
  for selected in [0,1,6,8,0xffffffffffffffff] do
    state.set (put initialized AddressSpace.productSelection selected)
    let result ← execute state (AddressSpace.createProduct 2)
    require (result == (70,0) && (← state.get).writes == 0) "invalid Product selection changed frames"
  state.set { (put initialized AddressSpace.productSelection 7) with failRead := some AddressSpace.productSelection }
  require ((← execute state (AddressSpace.createProduct 2)) == (95,0)) "selection read error hidden"
  require ((← state.get).writes == 0) "selection read failure allocated"
  -- Legacy construction never reads the selector and retains thirteen tables.
  state.set { (put initialized AddressSpace.productSelection 7) with failRead := some AddressSpace.productSelection }
  let legacy ← success state (AddressSpace.create 2)
  let legacyAddress ← success state (AddressSpace.base legacy)
  let legacyState ← state.get
  let legacyRoot := word legacyState (legacyAddress + 64)
  require (word legacyState (legacyAddress + 8) == 2 && word legacyState (legacyAddress + 40) == 13 &&
    word legacyState (legacyAddress + 88) == 32) "legacy layout changed"
  require (!legacyState.reads.contains AddressSpace.productSelection) "legacy selector read/fault prefix changed"
  require (leaf legacyState legacyRoot 0x81fc0000 == 0 && leaf legacyState legacyRoot 0x10012000 == 0)
    "legacy acquired Product aliases"
  state.set { legacyState with failRead := none }
  discard <| success state (AddressSpace.destroy legacy)
  require ((← success state Frames.remaining) == 8192) "legacy cleanup leaked"
  -- Fail each newly introduced PTE publication independently. All inactive
  -- descriptor/registry/table allocations must roll back, preserving status96.
  let table13Handle := word golden (address + 128 + 13*8)
  state.set golden
  let table13 ← success state (Frames.resolvePurpose 2 table13Handle 2)
  let middle := (word golden (root + 2*8) >>> 10) <<< 12
  let deviceMiddle := (word golden root >>> 10) <<< 12
  let deviceTable := (word golden (deviceMiddle + 128*8) >>> 10) <<< 12
  for target in [(middle + 15*8,table13 >>> 12 <<< 10 ||| 1),
                 (slot table13 0x81fc0000,(0x81fc0000 : UInt64) >>> 12 <<< 10 ||| 0xc7),
                 (slot table13 0x81fc3000,(0x81fc3000 : UInt64) >>> 12 <<< 10 ||| 0xc7),
                 (slot deviceTable 0x10012000,(0x10012000 : UInt64) >>> 12 <<< 10 ||| 0xc7)] do
    state.set { (put initialized AddressSpace.productSelection 7) with failWrite := some target }
    let result ← execute state (AddressSpace.createProduct 2)
    require (result == (96,0) && (← state.get).faultUsed) "Product mapping error/rollback precedence"
    require ((← success state Frames.remaining) == 8192) "Product mapping rollback leaked"
  state.set initialized
  require ((← execute state (AddressSpace.configureProduct 6)) == (70,0)) "unexpected selection admitted"
  require ((← state.get).writes == 0) "unexpected selection published"
  require ((← execute state (AddressSpace.configureProduct 7)).1 == 169) "missing real binding7 admitted"
  require (word (← state.get) AddressSpace.productSelection == 0) "unvalidated Product selector published"
  discard <| success state (AddressSpace.configureProduct 0)
  IO.println "PRODUCT_AS_LAYOUT3:PASS literalPTEs/owned-pins/retag/legacy-prefix/fresh-selection/rollback"
end ProductASFixture
#eval ProductASFixture.run
