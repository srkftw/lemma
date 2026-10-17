import Lemma.Kernel.Memory.Frames
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only execution of genuine allocator Actions against independent sparse
RAM. Counts are actual metadata reads and fold callbacks, not simulated CPU
cycles. Literal full-pool initial states test error precedence separately from
ordinary allocations, holes, ownership, zeroing and generation transitions.
Never imported by a target. -/
namespace FramesScans
open Lemma.Core0.Memory Lemma.Kernel.Memory

def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  metadataReads : Nat := 0
  ownerReads : Nat := 0
  iterations : Nat := 0
  frameWrites : Nat := 0
  failReadOnce : Option UInt64 := none
  failWriteOnce : Option UInt64 := none

def read64 (s : State) (address : UInt64) : UInt64 := s.words.getD address 0
def write64 (s : State) (address value : UInt64) : State :=
  {s with words := if value = 0 then s.words.erase address else s.words.insert address value}

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s value => pure (s,value)
  | .bind first next =>
    let (s,value) ← execute state first
    execute state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "allocator fold exceeds static bound"
    let mut s : UInt8 := 0
    let mut acc := initial
    for i in [:count.toNat] do
      if s = 0 then
        state.modify fun old => {old with iterations := old.iterations+1}
        let result ← execute state (step i.toUInt32 count acc a b c d)
        s := result.1
        acc := result.2
    execute state (next s acc)
  | .platform op address value _ _ _ _ next =>
    require (address % 8 = 0) "allocator unaligned physical word"
    require ((0x80400000 ≤ address && address < 0x80510000) ||
             (0x82000000 ≤ address && address < 0x84000000)) "allocator outside admitted RAM"
    if op = .physicalRead64 then
      if (← state.get).failReadOnce = some address then
        state.modify fun old => {old with failReadOnce := none}
        execute state (next 7 0)
      else
        state.modify fun old =>
          let metadata := Frames.records ≤ address && address < Frames.records+8192*32
          let reads := old.metadataReads + (if metadata then 1 else 0)
          let owners := old.ownerReads + (if metadata && (address-Frames.records)%32 = 0 then 1 else 0)
          {old with metadataReads := reads, ownerReads := owners}
        execute state (next 0 (read64 (← state.get) address))
    else if op = .physicalWrite64 then
      if Frames.records ≤ address && address < Frames.records+8192*32 &&
         (address-Frames.records)%32 = 0 && value ≠ 0 && value ≠ 0xffffffffffffffff then
        let frame := 0x82000000 + (address-Frames.records)/32*4096
        for i in [:512] do
          require (read64 (← state.get) (frame+i.toUInt64*8) = 0) "grant published before complete zeroing"
      if (← state.get).failWriteOnce = some address then
        state.modify fun old => {old with failWriteOnce := none}
        execute state (next 7 0)
      else
        state.modify fun old =>
          let next := write64 old address value
          {next with frameWrites := old.frameWrites + (if 0x82000000 ≤ address && address < 0x84000000 then 1 else 0)}
        execute state (next 0 0)
    else throw <| IO.userError "unexpected allocator platform operation"
  | _ => throw <| IO.userError "unexpected allocator Action"

def success (s : IO.Ref State) (action : Action) : IO UInt64 := do
  let (status,value) ← execute s action
  require (status = 0) s!"unexpected allocator status {status}"
  pure value

def resetCounts (s : IO.Ref State) : IO Unit :=
  s.modify fun old => {old with metadataReads := 0,ownerReads := 0,iterations := 0,frameWrites := 0}

def fresh (amount quota : UInt64) : IO (IO.Ref State) := do
  let s ← IO.mkRef ({} : State)
  discard <| success s (Frames.configure amount quota 4)
  discard <| success s Frames.init
  resetCounts s
  pure s

def handles (s : IO.Ref State) (address amount : UInt64) : IO (Array UInt64) := do
  let state ← s.get
  pure <| (Array.range amount.toNat).map fun i => read64 state (address+i.toUInt64*8)

def checkReads : IO Unit := do
  let s ← fresh 8192 8192
  s.modify fun old => write64 old 0x82000000 0xdeadbeef
  let first ← success s (Frames.allocate 2 4)
  require (first = 8192) "first single grant/first generation differs"
  let one ← s.get
  require (one.metadataReads = 2 && one.ownerReads = 1 && one.iterations = 65 && one.frameWrites = 512)
    "single allocation did not stop at first free slot"
  require (read64 one 0x82000000 = 0) "single grant did not clear stale data"
  let pairState ← fresh 8192 8192
  let pair ← success pairState (Frames.allocateContiguous2 2 5)
  require ((← handles pairState pair 2) = #[8192,8193]) "lowest pair differs"
  let two ← pairState.get
  require (two.metadataReads = 10 && two.ownerReads = 4 && two.iterations = 129 && two.frameWrites = 1024)
    "pair first run did not retain exact preflight reads"
  let quadState ← fresh 8192 8192
  let quad ← success quadState (Frames.allocateContiguous4 2 1)
  require ((← handles quadState quad 4) = #[8192,8193,8194,8195]) "lowest quad differs"
  let four ← quadState.get
  require (four.metadataReads = 20 && four.ownerReads = 8 && four.iterations = 273 && four.frameWrites = 2048)
    "quad first run did not retain exact preflight reads"
  let kernel ← fresh 512 32
  discard <| success kernel (Frames.allocate 1 1)
  require ((← kernel.get).metadataReads = 2) "exempt kernel still counts all owned frames"
  IO.println "FRAMES_READS:PASS single2 pair10 quad20 record reads; zeroing unchanged"

def checkHolesAndLifetime : IO Unit := do
  let s ← fresh 8192 8192
  let mut allocated := #[]
  for _ in [:12] do allocated := allocated.push (← success s (Frames.allocate 2 4))
  discard <| success s (Frames.release 2 allocated[1]!)
  let reused ← success s (Frames.allocate 3 4)
  require (reused = 16385) "single allocation did not reuse lowest hole with new generation"
  discard <| success s (Frames.pin 3 reused)
  require ((← execute s (Frames.release 3 reused)).1 = 35) "pinned grant released"
  discard <| success s (Frames.unpin 3 reused)
  discard <| success s (Frames.release 3 reused)
  for i in #[2,3,5,6,7,8] do discard <| success s (Frames.release 2 allocated[i]!)
  let pair ← success s (Frames.allocateContiguous2 4 5)
  require ((← handles s pair 2) = #[24577,16386]) "pair did not choose first adjacent holes"
  let quad ← success s (Frames.allocateContiguous4 5 1)
  require ((← handles s quad 4) = #[16389,16390,16391,16392]) "quad did not skip fragmented earlier hole"
  require ((← success s (Frames.ownedCount 3)) = 0) "ownedCount returned fabricated fast-path value"
  require ((← success s (Frames.ownedCount 4)) = 2 && (← success s (Frames.ownedCount 5)) = 4)
    "multiowner exact counts differ"
  require ((← execute s (Frames.resolve 3 reused)).1 = 34) "stale generation/owner resolved"
  require ((← success s (Frames.allocate 6 4)) = 16387) "single missed fragmented hole before quad"
  require ((← success s (Frames.allocate 6 4)) = 8204) "single did not cross already occupied suffix"
  resetCounts s
  require ((← success s (Frames.allocate 6 4)) = 8205) "single suffix cursor changed lowest choice"
  require ((← s.get).metadataReads = 2) "single cursor stayed behind scanned occupied suffix"
  IO.println "FRAMES_HOLES:PASS lowest single/pair/quad, zero-before-publication, pins, generation and multiowner counts"

def full (freeSlots : UInt64) : IO (IO.Ref State) := do
  let s ← fresh 8192 8192
  -- Independent valid full-pool initial state; no host mutation API exists in
  -- the machine. Literal pressure cutpoints establish error precedence only.
  s.modify fun old => Id.run do
    let mut value := old
    for i in [:(8192-freeSlots).toNat] do
      value := write64 value (0x80401000+i.toUInt64*32) 2
      value := write64 value (0x80401008+i.toUInt64*32) 4
      value := write64 value (0x80401018+i.toUInt64*32) 1
    value := write64 value 0x80441008 (8192-freeSlots)
    value := write64 value 0x80400108 (8192-freeSlots)
    return write64 value 0x80400100 freeSlots
  resetCounts s
  pure s

def checkPressure : IO Unit := do
  for freeSlots in #[0,1] do
    for owner in #[2,3] do
      for amount in #[2,4] do
        let s ← full freeSlots
        let before := (← s.get).words
        let action := if amount = 2 then Frames.allocateContiguous2 owner 5 else Frames.allocateContiguous4 owner 1
        let result ← execute s action
        let expected : UInt8 := if owner = 2 then 38 else 33
        require (result.1 = expected) "low global supply lost quota-before-exhausted priority"
        for i in [:8192] do
          require (read64 (← s.get) (0x80401000+i.toUInt64*32) = before.getD (0x80401000+i.toUInt64*32) 0)
            "rejected pressure acquired ownership"
        require ((← s.get).ownerReads = 0) "indexed owner pressure performed a whole-pool scan"
  let allOwned ← full 0
  require ((← execute allOwned (Frames.allocate 2 4)).1 = 38) "full owner single not quotaExceeded"
  require ((← execute allOwned (Frames.allocate 3 4)).1 = 33) "other owner full pool not exhausted"
  let legacy ← fresh 512 32
  for _ in [:32] do discard <| success legacy (Frames.allocate 2 4)
  resetCounts legacy
  require ((← execute legacy (Frames.allocate 2 4)).1 = 38) "legacy ordinary quota changed"
  require ((← legacy.get).ownerReads = 0) "legacy quota performed a whole-pool scan for an indexed owner"
  discard <| success legacy (Frames.allocate 3 4)
  require ((← success legacy (Frames.ownedCount 2)) = 32) "legacy ownedCount differs"
  let generation ← fresh 8192 8192
  generation.modify fun old => write64 old 0x80401018 (0xffffffffffffffff/8192)
  require ((← execute generation (Frames.allocate 2 4)).1 = 37) "generation exhaustion changed"
  require ((← success generation Frames.remaining) = 8192) "generation rejection changed global supply"
  for amount in #[1,2,4] do
    let fault ← fresh 8192 8192
    fault.modify fun old => {old with failReadOnce := some 0x80400100}
    let action := if amount = 1 then Frames.allocate 2 4 else
      if amount = 2 then Frames.allocateContiguous2 2 5 else Frames.allocateContiguous4 2 1
    let rejected ← execute fault action
    require (rejected.1 = (if amount = 2 then 39 else 7)) "failed accounting read was swallowed"
    require (read64 (← fault.get) 0x80400100 = 8192 && read64 (← fault.get) 0x80401000 = 0)
      "failed accounting peek granted a frame"
    require ((← fault.get).ownerReads = 0) "failed accounting peek continued into scans"
  IO.println "FRAMES_PRESSURE:PASS quota/OOM priority at0/1 free, legacy ordinary quota, exact counts and generation exhaustion"

/-- Derive every expected counter and cursor property independently from the
literal record array, including fragmented and retired slots. -/
def checkIndex (state : State) (amount : UInt64) : IO Unit := do
  let cursor := read64 state 0x80400108
  require (cursor ≤ amount) "free cursor outside configured pool"
  for i in [:cursor.toNat] do
    require (read64 state (0x80401000+i.toUInt64*32) ≠ 0) "cursor skipped a lower free slot"
  for owner in [1:65] do
    let mut owned := 0
    for i in [:amount.toNat] do
      if read64 state (0x80401000+i.toUInt64*32) = owner.toUInt64 then owned := owned+1
    require (read64 state (0x80441000+(owner.toUInt64-1)*8) = owned)
      s!"owner{owner} index contradicts literal records"

def checkPrefix : IO Unit := do
  let s ← fresh 8192 8192
  for i in [:520] do
    let handle ← success s (Frames.allocate 2 4)
    require (handle = 8192+i.toUInt64) "prefix allocation changed lowest-slot choice"
  let observed ← s.get
  require (observed.metadataReads = 1040 && observed.ownerReads = 520 && observed.iterations = 33800 && observed.frameWrites = 266240)
    "prefix allocation grew its first-free search with the live prefix"
  checkIndex observed 8192
  resetCounts s
  require ((← success s (Frames.ownedCount 2)) = 520) "indexed count lost prefix frames"
  require ((← s.get).ownerReads = 0 && (← s.get).iterations = 0) "indexed count still scans the pool"
  IO.println "FRAMES_PREFIX:PASS 520 allocations record_reads1040 owner_reads520 callbacks33800; prior record_reads135980 callbacks401700"

def checkIndexFaults : IO Unit := do
  for width in #[1,2,4] do
    for fault in #[0x80400100,0x80400108,0x80441008,0x80401000,0x80401018] do
      let s ← fresh 8192 8192
      s.modify fun old => {old with failWriteOnce := some fault}
      let action := if width = 1 then Frames.allocate 2 4 else
        if width = 2 then Frames.allocateContiguous2 2 5 else Frames.allocateContiguous4 2 1
      require ((← execute s action).1 = 39) "failed indexed publication did not reject"
      let after ← s.get
      require (read64 after 0x80400100 = 8192) "failed publication lost free accounting"
      for i in [:width] do
        for offset in #[0,8,16,24] do
          require (read64 after (0x80401000+i.toUInt64*32+offset) = 0)
            "failed indexed publication retained unexposed frame metadata"
      checkIndex after 8192
  for fault in #[0x80400100,0x80400108,0x80441008,0x80401000,0x80401008] do
    let s ← fresh 8192 8192
    let handle ← success s (Frames.allocate 2 4)
    s.modify fun old => {old with failWriteOnce := some fault}
    require ((← execute s (Frames.release 2 handle)).1 = 39) "failed indexed release did not reject"
    require ((← success s (Frames.resolve 2 handle)) = 0x82000000) "failed release revoked a live handle"
    require ((← success s (Frames.purpose 2 handle)) = 4) "failed release lost live purpose"
    require ((← success s Frames.remaining) = 8191) "failed release changed free accounting"
    checkIndex (← s.get) 8192
    discard <| success s (Frames.release 2 handle)
    checkIndex (← s.get) 8192
  for fault in #[0x80400108,0x80441008] do
    let s ← fresh 8192 8192
    s.modify fun old => {old with failReadOnce := some fault}
    require ((← execute s (Frames.allocate 2 4)).1 = 7) "failed index read did not reject"
    require ((← success s Frames.remaining) = 8192) "failed index read granted a frame"
    checkIndex (← s.get) 8192
  let large ← fresh 512 32
  let handle ← success large (Frames.allocate 0x100000000 4)
  resetCounts large
  require ((← success large (Frames.ownedCount 0x100000000)) = 1) "large owner exact scan changed"
  require ((← large.get).ownerReads = 512) "large owner fallback omitted records"
  discard <| success large (Frames.release 0x100000000 handle)
  checkIndex (← large.get) 512
  let retired ← fresh 8192 8192
  retired.modify fun old => write64 old 0x80401018 (0xffffffffffffffff/8192-1)
  let final ← success retired (Frames.allocate 2 4)
  discard <| success retired (Frames.release 2 final)
  require ((← success retired Frames.remaining) = 8191 &&
    read64 (← retired.get) 0x80401000 = 0xffffffffffffffff) "retired final generation reentered free supply"
  checkIndex (← retired.get) 8192
  require ((← success retired (Frames.allocate 3 4)) % 8192 = 1) "cursor reused a retired frame"
  checkIndex (← retired.get) 8192
  IO.println "FRAMES_INDEX_FAULTS:PASS publication/release rollback, read rejection, arbitrary-owner fallback and retirement"

def checkZeroErrors : IO Unit := do
  for cut in #[0,8,56,64,4088] do
    let s ← fresh 8192 8192
    s.modify fun old => Id.run do
      let mut next := old
      for i in [:512] do next := write64 next (0x82000000+i.toUInt64*8) 0xdeadbeef
      return {next with failWriteOnce := some (0x82000000+cut)}
    require ((← execute s (Frames.allocate 2 4)).1 = 7) "zero fault did not retain first write error"
    let after ← s.get
    require (read64 after 0x80400100 = 8192 && read64 after 0x80401000 = 0)
      "zero fault published ownership or changed free supply"
    for i in [:512] do
      require (read64 after (0x82000000+i.toUInt64*8) =
        (if i.toUInt64*8 < cut then 0 else 0xdeadbeef)) "zero fault write order or tail changed"
    checkIndex after 8192
  for (cell,value) in #[(0x80400108,8193),(0x80441008,8193)] do
    let s ← fresh 8192 8192
    s.modify fun old => write64 old cell value
    require ((← execute s (Frames.allocate 2 4)).1 = 39) "out-of-range allocator index accepted"
    require ((← success s Frames.remaining) = 8192 && read64 (← s.get) 0x80401000 = 0)
      "malformed index published ownership"
  IO.println "FRAMES_ZERO_ERRORS:PASS first-word/block/tail failures retain exact prefix writes, malformed indices reject"

/-- The allocator fixture intentionally supplies no devices. This literal
peripheral-control retention check separately exposes overlap with existing
VirtIOBlock, legacy simulator, Power, DeviceService, DTB and isolation state. -/
def checkControlRetention : IO Unit := do
  let s ← IO.mkRef ({} : State)
  discard <| success s (Frames.configure 8192 8192 4)
  for i in [:192] do
    s.modify fun old => write64 old (0x80400a00+i.toUInt64*8) (0x100000+i.toUInt64)
  discard <| success s Frames.init
  for i in [:192] do
    require (read64 (← s.get) (0x80400a00+i.toUInt64*8) = 0x100000+i.toUInt64)
      "allocator initialization changed existing peripheral/descriptor control state"
  let first ← success s (Frames.allocate 1 1)
  let pair ← success s (Frames.allocateContiguous2 2 5)
  let paired ← handles s pair 2
  let quad ← success s (Frames.allocateContiguous4 3 1)
  let quads ← handles s quad 4
  discard <| success s (Frames.release 1 first)
  for handle in paired do discard <| success s (Frames.release 2 handle)
  for handle in quads do discard <| success s (Frames.release 3 handle)
  for i in [:192] do
    require (read64 (← s.get) (0x80400a00+i.toUInt64*8) = 0x100000+i.toUInt64)
      "allocator changed existing peripheral/descriptor control state"
  checkIndex (← s.get) 8192
  require ((← success s Frames.remaining) = 8192) "control retention workload leaked frames"
  IO.println "FRAMES_CONTROL_RETENTION:PASS existing0xa00..0xfff controls unchanged by init/allocation/release"

end FramesScans
open Lean Elab Command
run_cmd do
  liftIO FramesScans.checkReads
  liftIO FramesScans.checkHolesAndLifetime
  liftIO FramesScans.checkPressure
  liftIO FramesScans.checkPrefix
  liftIO FramesScans.checkIndexFaults
  liftIO FramesScans.checkZeroErrors
  liftIO FramesScans.checkControlRetention
