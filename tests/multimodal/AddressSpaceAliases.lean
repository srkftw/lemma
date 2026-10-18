import Lemma.Kernel.Memory.AddressSpace
import Lean.Elab.Command
import Std.Data.HashMap

/-! Independent finite byte RAM interpreting the production Actions. Literal
registry mutations probe duplicate/error ordering at eight-row and page cuts.
The bounded work observations count actual callbacks/accesses, not RV64 cycles. -/
namespace MultimodalASFixture
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
  flushes : Nat := 0

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
    if op == .installSatp then
      state.modify fun s => {s with flushes := s.flushes+1}
      execute state (next 0 0)
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
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let root := word (← state.get) (address+64)
  let middle := (word (← state.get) root >>> 10) <<< 12
  let low := (word (← state.get) (middle+128*8) >>> 10) <<< 12
  let original := resetTrace (← state.get)
  for va in [0x10012000,0x10013000,0x10014000,0x10015000,0x10016000] do
    require (leaf original root va == 0) "legacy create gained new device alias"
  state.set original
  discard <| success state (AddressSpace.addMultimodalAliases descriptor)
  let mapped ← state.get
  for va in [0x10014000,0x10015000] do
    let pte := leaf mapped root va
    require (pte == (va >>> 12 <<< 10 ||| 0xc7)) "literal Sv39 S-only PTE differs"
    require (pte &&& 0x18 == 0 && pte &&& 6 == 6) "User or executable device alias"
  for va in [0x10012000,0x10013000,0x10016000,0x10017000] do
    require (leaf mapped root va == 0) "device aperture widened"
  require (mapped.writes == 2 && mapped.flushes == 1) "publication/flush count differs"
  for i in [:512] do
    let a := low+i.toUInt64*8
    if i != 20 && i != 21 then require (word mapped a == word original a) "neighbor PTE changed"
  state.set (resetTrace mapped)
  discard <| success state (AddressSpace.addMultimodalAliases descriptor)
  require ((← state.get).writes == 2) "exact retry did not retain both leaves"
  let lowPin := Frames.record ((low-Frames.pool)/4096)+16
  let mutations : List (UInt64 × UInt64) :=
    [(address+8,3),(root,0),(middle+128*8,0),(lowPin,0),(lowPin,2),
     (low+20*8,0x40050d7),(low+20*8,0x40050cf),(low+20*8,0x40054c7),
     (low+21*8,0x40054d7),(low+21*8,0x40050c7)]
  for (where_,value) in mutations do
    state.set (put original where_ value)
    let result ← execute state (AddressSpace.addMultimodalAliases descriptor)
    require (result.1 != 0 && (← state.get).writes == 0 && (← state.get).flushes == 0)
      s!"malformed alias authority mutated page tables at {where_}"
  for where_ in [root,middle+128*8,low+20*8,low+21*8,lowPin] do
    state.set {original with failRead := some where_}
    let result ← execute state (AddressSpace.addMultimodalAliases descriptor)
    require (result.1 == 95 && (← state.get).writes == 0) "preflight read failure hidden/published"
  for (where_,value,done) in [(low+20*8,0x40050c7,0),(low+21*8,0x40054c7,1)] do
    state.set {original with failWrite := some (where_,value)}
    let result ← execute state (AddressSpace.addMultimodalAliases descriptor)
    require (result.1 == 96 && (← state.get).writes == done && (← state.get).flushes == 0)
      "write failure hid partial prefix or claimed flush"
  state.set original
  discard <| success state (AddressSpace.destroy descriptor)
  require ((← success state Frames.remaining) == 8192) "aliases leaked owned pages"
  IO.println "MULTIMODAL_SV39:PASS exact2 supervisorRW/NX leaves, unchangedlegacy/neighbors,ownedpinnedparents,10mutations/5readfailures/2writeprefixfailures"
end MultimodalASFixture
#eval MultimodalASFixture.run
