import Lemma.User.Runtime.ManagedSums
import Std.Data.HashMap

/-! Host-only finite RAM observation of the actual checked runtime Actions.
This does not execute or interpret an ordinary Lean mathematical program. -/
namespace ManagedSumFixture
open Lean Elab Command Lemma.Core0.Memory Lemma.User.Runtime

structure State where
  bytes : Std.HashMap UInt64 UInt8 := {}
  mapped : Bool := false
  allocations : UInt64 := 0
  releases : UInt64 := 0
  denied : UInt8 := 0
  faultWrite : Option UInt64 := none
  faultSkips : Nat := 0
  faultStatus : UInt8 := 173

def contains (s : State) (address : UInt64) : Bool :=
  (0x20000 ≤ address && address < 0x21000) ||
    (s.mapped && Arena.page ≤ address && address < Arena.page + 4096)

def read (s : State) (address : UInt64) : IO UInt64 := do
  let mut value : UInt64 := 0
  for i in [:8] do
    unless contains s (address + i.toUInt64) do throw <| IO.userError "unmapped sum runtime read"
    value := value ||| ((s.bytes.getD (address + i.toUInt64) 0).toUInt64 <<< (i.toUInt64 * 8))
  return value

def write (s : State) (address value : UInt64) : IO State := do
  let mut s := s
  for i in [:8] do
    unless contains s (address + i.toUInt64) do throw <| IO.userError "unmapped sum runtime write"
    s := {s with bytes := s.bytes.insert (address + i.toUInt64) (value >>> (i.toUInt64 * 8)).toUInt8}
  return s

partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => return (status,value)
  | .bind first next =>
    let (status,value) ← execute ref first
    execute ref (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    unless count.toNat ≤ budget do throw <| IO.userError "sum runtime loop budget exceeded"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        let result ← execute ref (step i.toUInt32 count value c0 c1 c2 c3)
        status := result.1
        value := result.2
    execute ref (next status value)
  | .platform operation a b c _ _ _ next =>
    let s ← ref.get
    match operation with
    | .virtualRead64 => execute ref (next 0 (← read s a))
    | .virtualWrite64 =>
      if s.faultWrite == some a && s.faultSkips = 0 then
        ref.set {s with faultWrite := none}
        execute ref (next s.faultStatus 0)
      else
        let written ← write s a b
        ref.set (if s.faultWrite == some a then {written with faultSkips := s.faultSkips-1} else written)
        execute ref (next 0 0)
    | .syscall =>
      unless b = Arena.page && c = 1 do throw <| IO.userError "undeclared sum runtime syscall arguments"
      if a = Lemma.User.ABI.allocatePages then
        if s.denied ≠ 0 then execute ref (next s.denied 0) else
        if s.mapped then execute ref (next Lemma.User.ABI.duplicateMapping 0) else
        let mut fresh := {s with mapped := true, allocations := s.allocations + 1}
        for i in [:4096] do fresh := {fresh with bytes := fresh.bytes.insert (Arena.page+i.toUInt64) 0}
        ref.set fresh
        execute ref (next 0 Arena.page)
      else if a = Lemma.User.ABI.releasePages then
        if s.mapped then
          ref.set {s with mapped := false, releases := s.releases + 1}
          execute ref (next 0 Arena.page)
        else execute ref (next Lemma.User.ABI.missingMapping 0)
      else throw <| IO.userError "undeclared sum runtime syscall"
    | _ => throw <| IO.userError "sum runtime effect outside finite fixture"
  | _ => throw <| IO.userError "fixture cannot interpret a mathematical source or bridge"

def require (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message

def check : IO Unit := do
  let ref ← IO.mkRef ({} : State)
  -- Constructor catalog has two distinct source payload layouts:24 and16.
  let (status,equal) ← execute ref (ManagedSums.allocate 1 0 24)
  require (status = 0) "actual sum constructor allocation failed"
  require ((← execute ref (ManagedSums.constructorTag equal 1 2 0x23)) = (0,0)) "equal constructor tag/layout"
  require ((← execute ref (ManagedSums.writeField equal 1 0 24 8 5)).1 = 0 &&
    (← execute ref (ManagedSums.writeField equal 1 0 24 16 6)).1 = 0 &&
    (← execute ref (ManagedSums.readField equal 1 0 24 8)) = (0,5) &&
    (← execute ref (ManagedSums.readField equal 1 0 24 16)) = (0,6)) "real sum fields changed"
  let (status,unequal) ← execute ref (ManagedSums.allocate 1 1 16)
  require (status = 0 && (← execute ref (ManagedSums.constructorTag unequal 1 2 0x23)) = (0,1)) "unequal constructor tag/layout"
  for action in #[ManagedSums.constructorTag equal 2 2 0x23,
      ManagedSums.constructorTag equal 1 1 0x3,
      ManagedSums.constructorTag equal 1 9 0x23,
      ManagedSums.constructorTag equal 1 2 0x123,
      ManagedSums.constructorTag equal 1 2 0x22,
      ManagedSums.readField equal 1 1 24 8,
      ManagedSums.readField equal 1 0 16 8,
      ManagedSums.readField equal 1 0 24 0,
      ManagedSums.readField equal 1 0 24 9,
      ManagedSums.readField equal 1 0 24 24] do
    require ((← execute ref action).1 = Arena.invalid) "invalid sum type/tag/layout/index admitted"
  let oldBytes ← read (← ref.get) (Arena.page+128+64)
  require ((← execute ref (ManagedSums.writeField equal 1 1 24 8 99)).1 = Arena.invalid &&
    (← read (← ref.get) (Arena.page+128+64)) = oldBytes) "failed sum write changed authoritative bytes"
  -- A legacy record cookie is not a sum cookie, even at the same logical id.
  require ((← execute ref (Arena.bytesWriteWord equal 0 1)).1 = 0 &&
    (← execute ref (ManagedSums.constructorTag equal 1 2 0x23)).1 = Arena.invalid) "legacy cookie mistaken for sum"
  require ((← execute ref (Arena.bytesWriteWord equal 0 256)).1 = 0) "restore fixture cookie"
  require ((← execute ref (Arena.release equal)).1 = 0 &&
    (← execute ref (ManagedSums.readField equal 1 0 24 8)).1 = Arena.invalid) "sum final release resurrected reference"
  let (status,reused) ← execute ref (ManagedSums.allocate 1 0 24)
  require (status = 0 && reused = equal+32 &&
    (← execute ref (ManagedSums.constructorTag equal 1 2 0x23)).1 = Arena.invalid) "sum generation reuse"
  -- OOM is bounded by the existing31 real slots, and preserves a live object.
  let mut handles := #[reused,unequal]
  for _ in [:29] do
    let (status,handle) ← execute ref (ManagedSums.allocate 1 1 16)
    require (status = 0) "sum slot count differs"
    handles := handles.push handle
  require ((← execute ref (ManagedSums.allocate 1 0 24)) = (Arena.exhausted,0) &&
    (← execute ref (ManagedSums.constructorTag reused 1 2 0x23)) = (0,0) &&
    (← ref.get).allocations = 1) "controlled sum OOM changed live object or duplicated page"
  for handle in handles do require ((← execute ref (Arena.release handle)).1 = 0) "real sum cleanup failed"
  require ((← execute ref Arena.destroy).1 = 0 && !(← ref.get).mapped && (← ref.get).releases = 1) "sum page lifetime leaked"
  -- Inject the actual cookie write failure after successful real allocation;
  -- the constructor attempts final release and preserves the first failure.
  let ref ← IO.mkRef ({} : State)
  require ((← execute ref Arena.ensure).1 = 0) "fault arena initialization"
  ref.modify fun s => {s with faultWrite := some (Arena.page+128+64), faultSkips := 1}
  require ((← execute ref (ManagedSums.allocate 1 0 24)) = (173,0) &&
    (← read (← ref.get) (Arena.control+16)) = 0 &&
    (← read (← ref.get) (Arena.page+128)) = 0) "failed sum cookie publication leaked slot or lost actual fault"
  let (status,handle) ← execute ref (ManagedSums.allocate 1 1 16)
  require (status = 0 && handle = 64) "cookie failure failed generational reclamation"
  require ((← execute ref Arena.cancel).1 = 0 &&
    (← execute ref (ManagedSums.readField handle 1 1 16 8)).1 = Arena.cancelled &&
    (← execute ref (Arena.release handle)).1 = 0 &&
    (← execute ref Arena.destroy).1 = 0) "cancelled sum read/cleanup semantics"
  let ref ← IO.mkRef ({denied := Lemma.User.ABI.quotaExceeded} : State)
  require ((← execute ref (ManagedSums.allocate 1 0 24)) = (Lemma.User.ABI.quotaExceeded,0) &&
    !(← ref.get).mapped) "owned page quota failure manufactured sum allocation"
  let ref ← IO.mkRef ({} : State)
  for (id,tag,bytes) in #[(0,0,24),(65536,0,24),(1,8,24),(1,0,8),(1,0,65),(1,0,17)] do
    require ((← execute ref (ManagedSums.allocate id tag bytes)) = (Arena.invalid,0) &&
      !(← ref.get).mapped) "invalid constructor touched allocator"

run_cmd do
  liftIO check
  logInfo "MANAGED_SUM_RUNTIME:PASS actual generational Actions/type/tag/catalog/bounds/OOM/cookie-fault/cancellation/reclamation; host finite RAM, not ordinary-program or RV64 execution"
end ManagedSumFixture
