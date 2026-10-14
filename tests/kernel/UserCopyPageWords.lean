import tests.kernel.UserCopyPageBefore
import Lemma.Kernel.Memory.UserCopy
import Lean.Elab.Command
import Std.Data.HashMap
set_option maxHeartbeats 0
namespace CopyComparison
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.User
structure Request where
  op : Lemma.Core0.Execution.Op
  address : UInt64
  value : UInt64
  status : UInt8
  deriving BEq
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  requests : Array Request := #[]
  callbacks : Nat := 0
  faultAt : Option Nat := none
  faultStatus : UInt8 := 95
  globalFault : Bool := false

def require (b : Bool) (m : String) : IO Unit := if b then pure () else throw <| IO.userError m
def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State := {s with words := if v = 0 then s.words.erase a else s.words.insert a v}
def byte (s : State) (a : UInt64) : UInt64 := (word s (a - a%8) >>> (a%8*8)) &&& 255
def putByte (s : State) (a v : UInt64) : State :=
  let shift := a%8*8
  put s (a-a%8) ((word s (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((v &&& 255) <<< shift))
def reset (s : State) : State := {s with requests := #[], callbacks := 0, faultAt := none, faultStatus := 95, globalFault := false}
partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next => let (s,v) ← execute ref first; execute ref (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    if budget < count.toNat then execute ref (next 9 initial) else
    let mut result : UInt8 × UInt64 := (0,initial)
    for i in [:count.toNat] do
      if result.1 = 0 then
        ref.modify fun st => {st with callbacks := st.callbacks+1}
        result ← execute ref (step i.toUInt32 count result.2 a b c d)
    execute ref (next result.1 result.2)
  | .platform op a b _ _ _ _ next =>
    let st ← ref.get
    require (st.requests.size < 10000000) "actual Action model ceiling"
    if op == .installSatp then execute ref (next 0 0) else
    require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000)) "finite actual physical RAM envelope"
    if op == .physicalRead64 || op == .physicalWrite64 then require (a % 8 == 0) "aligned physical64"
    let failed := st.faultAt == some st.requests.size
    let status : UInt8 := if failed then st.faultStatus else 0
    let value := if op == .physicalRead64 then word st a else if op == .physicalRead8 then byte st a else b
    ref.set {st with requests := st.requests.push ⟨op,a,value,status⟩}
    if failed && st.globalFault then throw <| IO.userError "injected actual physical global fault"
    if failed then execute ref (next status 0) else
    if op == .physicalRead64 || op == .physicalRead8 then execute ref (next 0 value) else
    if op == .physicalWrite64 then ref.modify fun s => put s a b; execute ref (next 0 0) else
    if op == .physicalWrite8 then ref.modify fun s => putByte s a b; execute ref (next 0 0) else
    throw <| IO.userError "unknown primitive rejected"
  | _ => throw <| IO.userError "unknown Action rejected"
def success (ref : IO.Ref State) (action : Action) : IO UInt64 := do
  let (s,v) ← execute ref action; require (s == 0) s!"setup status{s}"; return v

def compare (snapshot : State) (before after : Action) : IO (State × State) := do
  let a ← IO.mkRef snapshot; let b ← IO.mkRef snapshot
  let left ← try pure (Except.ok (← execute a before)) catch _ => pure (Except.error ())
  let right ← try pure (Except.ok (← execute b after)) catch _ => pure (Except.error ())
  let x ← a.get; let y ← b.get
  let sameResult := match left,right with
    | .ok a,.ok b => a == b
    | .error _,.error _ => snapshot.globalFault &&
      snapshot.faultAt == some (x.requests.size - 1) && x.requests.size > 0
    | _,_ => false
  require (sameResult && x.words == y.words && x.requests == y.requests)
    s!"Actual result/RAM/ordered operation prefix mismatch at fault{snapshot.faultAt} left{repr left} right{repr right}"
  return (x,y)

def check (expanded : Bool) : IO Unit := do
  let ref ← IO.mkRef ({} : State)
  let amount : UInt64 := if expanded then 8192 else 512
  discard <| success ref (Frames.configure amount (if expanded then 8192 else 32) 4)
  discard <| success ref Frames.init
  let descriptor ← success ref (AddressSpace.create 2)
  let address ← success ref (AddressSpace.base descriptor)
  let scratch ← success ref (Frames.allocate 1 1)
  let scratchPA ← success ref (Frames.resolvePurpose 1 scratch 1)
  let first ← success ref (Frames.allocate 2 4)
  discard <| success ref (Frames.allocate 3 4)
  let second ← success ref (Frames.allocate 2 4)
  let firstPA ← success ref (Frames.resolve 2 first)
  let secondPA ← success ref (Frames.resolve 2 second)
  discard <| success ref (AddressSpace.mapUser descriptor 0x40000 first 3)
  discard <| success ref (AddressSpace.mapUser descriptor 0x41000 second 3)
  for i in [:4096] do
    ref.modify fun s =>
      putByte (putByte (putByte s (scratchPA+i.toUInt64) ((i.toUInt64*13+19)%256))
        (firstPA+i.toUInt64) ((i.toUInt64*3+7)%256)) (secondPA+i.toUInt64) ((i.toUInt64*5+9)%256)
  let saved := reset (← ref.get)
  let mut cases := 0
  let mut faults := 0
  for direction in #[false,true] do
    for (pointer,offset,length) in #[(0x40000,0,0),(0x40000,0,8),(0x40008,8,56),
        (0x40000,0,64),(0x40000,0,72),(0x40000,0,3840),(0x40800,0,4096),
        (0x40ff8,0,16),(0x40001,1,129),(0x40fff,0,2)] do
      let old := if direction then UserCopyPageBefore.copyToUser descriptor pointer scratch offset length else UserCopyPageBefore.copyFromUser descriptor pointer scratch offset length
      let fresh := if direction then UserCopy.copyToUser descriptor pointer scratch offset length else UserCopy.copyFromUser descriptor pointer scratch offset length
      let successful ← IO.mkRef saved
      let baseline ← execute successful old
      require (baseline == (0,length)) "literal successful copy result"
      let (a,b) ← compare saved old fresh
      cases := cases+1
      if length == 3840 || length == 4096 then
        IO.println s!"COPY_WORK expanded={expanded} toUser={direction} length={length} actualPrimitiveOperations={a.requests.size} callbacksBefore={a.callbacks} callbacksAfter={b.callbacks}"
      if length == 4096 then
        for index in [:a.requests.size] do
          discard <| compare {saved with faultAt := some index} old fresh
          faults := faults+1
        -- Primitive return statuses and unrecoverable bus/global exceptions
        -- retain each exact performed read/write prefix, including partial RAM.
        for index in #[0,a.requests.size/2,a.requests.size-1] do
          for code in #[7,9,95,255] do
            discard <| compare {saved with faultAt := some index, faultStatus := code} old fresh
            discard <| compare {saved with faultAt := some index, faultStatus := code, globalFault := true} old fresh
            faults := faults+2
  -- Scratch may be the descriptor itself. Its full authority is checked before
  -- copying; overwriting ABI/context bytes cannot cause a later revalidation,
  -- skipped word or reordered read. Both directions keep every exact prefix.
  for direction in #[false,true] do
    let old := if direction then UserCopyPageBefore.copyToUser descriptor 0x40800 descriptor 0 4096
      else UserCopyPageBefore.copyFromUser descriptor 0x40800 descriptor 0 4096
    let fresh := if direction then UserCopy.copyToUser descriptor 0x40800 descriptor 0 4096
      else UserCopy.copyFromUser descriptor 0x40800 descriptor 0 4096
    let ref ← IO.mkRef saved
    require ((← execute ref old) == (0,4096)) "literal descriptor-scratch copy result"
    let (a,_) ← compare saved old fresh
    for index in [:a.requests.size] do
      discard <| compare {saved with faultAt := some index} old fresh
      faults := faults+1
    cases := cases+1
  -- All early admission priorities are retained; these are genuine public APIs.
  for (pointer,offset,length,handle) in #[(0,0,1,scratch),(0x40000,0,4097,scratch),
      (0x40000,4097,1,scratch),(0x40000,4096,1,scratch),(0x40000,0,1,0),
      (0x40000,0,1,first),(0x40000,0,1,scratch+amount),(0x40000000,0,1,scratch)] do
    discard <| compare saved (UserCopyPageBefore.copyFromUser descriptor pointer handle offset length)
      (UserCopy.copyFromUser descriptor pointer handle offset length)
    cases := cases+1
  -- Corrupt generations/owners/purposes/PTE/permissions/directory pins cannot
  -- become fast aliases; source is physically noncontiguous across the cut.
  for (slot,value) in #[(Frames.record (first%amount),3),(Frames.record (first%amount)+24,2),
      (Frames.record (first%amount)+8,1),(address+0,0),(address+64,0),
      (Frames.record (scratch%amount)+16,1)] do
    let changed := put saved slot value
    discard <| compare changed (UserCopyPageBefore.copyToUser descriptor 0x40800 scratch 0 4096)
      (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)
    cases := cases+1
  -- An ordinary metadata-read alias is freshly obtained, then reused only
  -- inside one same-page nonpreemptible Action; fallback cases stay exact.
  let oldBorrow := .bind (UserCopyPageBefore.copyFromUserReadPage descriptor 0x40000 scratch 1024 32) fun s first =>
    if s = 0 then UserCopyPageBefore.copyFromUserReusingReadPage descriptor 0x40000 first 0x40080 scratch 0 512 else .done s 0
  let newBorrow := .bind (UserCopy.copyFromUserReadPage descriptor 0x40000 scratch 1024 32) fun s first =>
    if s = 0 then UserCopy.copyFromUserReusingReadPage descriptor 0x40000 first 0x40080 scratch 0 512 else .done s 0
  let (a,_) ← compare saved oldBorrow newBorrow
  for index in [:a.requests.size] do
    discard <| compare {saved with faultAt := some index} oldBorrow newBorrow
    faults := faults+1
  IO.println s!"USER_COPY_PAGE_BLOCK_EQUIVALENCE:PASS expanded={expanded} cases={cases+1} actualOrderedFaultPrefixes={faults} exactResultsRAM primitiveStatuses globalFaults partialWrites fullPreflight generation owner purpose pins noncontiguousPages alignedWords byteFallback aliasLifetime"
end CopyComparison
open Lean Elab Command
run_cmd do
  liftIO <| CopyComparison.check false
  liftIO <| CopyComparison.check true
