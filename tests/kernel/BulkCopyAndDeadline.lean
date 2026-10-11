import Lemma.Kernel.IPC
import Lemma.Kernel.Task
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only literal boundary checks over the production Actions. RAM is
byte-addressed; timer responses and access counts are observations of this
fixture, not CPU timing or a proof of the complete kernel. -/
namespace BulkCopyDeadlineFixture
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  operations : Nat := 0
  reads8 : Nat := 0
  writes8 : Nat := 0
  writes64 : Nat := 0
  now : UInt64 := 123456

def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  { s with words := if v = 0 then s.words.erase a else s.words.insert a v }
def byte (s : State) (a : UInt64) : UInt64 :=
  (word s (a - a % 8) >>> (a % 8 * 8)) &&& 255
def putByte (s : State) (a v : UInt64) : State :=
  let shift := a % 8 * 8
  put s (a - a % 8) ((word s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) |||
    ((v &&& 255) <<< shift))

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
        let result ← execute state (step i.toUInt32 count acc c0 c1 c2 c3)
        status := result.1
        acc := result.2
    execute state (next status acc)
  | .platform op a b _ _ _ _ next =>
    let s ← state.get
    if s.operations ≥ 10000000 then throw <| IO.userError "fixture budget exhausted"
    state.set { s with operations := s.operations + 1 }
    if op == .firmwareCall then
      if a = 2 && b = 0 then execute state (next 0 (← state.get).now)
      else throw <| IO.userError "unexpected firmware call"
    else if op == .installSatp then execute state (next 0 0)
    else
      if !((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000)) then
        throw <| IO.userError s!"access outside finite physical RAM {a}"
      match op with
      | .physicalRead64 =>
        if a % 8 ≠ 0 then throw <| IO.userError "unaligned read64"
        execute state (next 0 (word (← state.get) a))
      | .physicalWrite64 =>
        if a % 8 ≠ 0 then throw <| IO.userError "unaligned write64"
        state.modify fun s => { (put s a b) with writes64 := s.writes64 + 1 }
        execute state (next 0 0)
      | .physicalRead8 =>
        state.modify fun s => { s with reads8 := s.reads8 + 1 }
        execute state (next 0 (byte (← state.get) a))
      | .physicalWrite8 =>
        state.modify fun s => { (putByte s a b) with writes8 := s.writes8 + 1 }
        execute state (next 0 0)
      | _ => throw <| IO.userError "unexpected physical primitive"
  | _ => throw <| IO.userError "unexpected Action"

def require (b : Bool) (message : String) : IO Unit :=
  if b then pure () else throw <| IO.userError message
def success (state : IO.Ref State) (action : Action) : IO UInt64 := do
  let (s,v) ← execute state action
  require (s == 0) s!"unexpected status{s}"
  pure v
def status (state : IO.Ref State) (expected : UInt8) (action : Action) : IO Unit := do
  let (s,_) ← execute state action
  require (s == expected) s!"expected status{expected}, got{s}"
def resetCounts (state : IO.Ref State) : IO Unit :=
  state.modify fun s => { s with reads8 := 0, writes8 := 0, writes64 := 0 }

def checkCopies (expanded : Bool) : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure (if expanded then 8192 else 512)
    (if expanded then 8192 else 32) 4)
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let scratch ← success state (Frames.allocate 1 1)
  let scratchPA ← success state (Frames.resolvePurpose 1 scratch 1)
  let first ← success state (Frames.allocate 2 4)
  discard <| success state (Frames.allocate 3 4)
  let second ← success state (Frames.allocate 2 4)
  let firstPA ← success state (Frames.resolve 2 first)
  let secondPA ← success state (Frames.resolve 2 second)
  require (secondPA ≠ firstPA + 4096) "fixture must use physically nonadjacent leaves"
  discard <| success state (AddressSpace.mapUser descriptor 0x40000 first 3)
  discard <| success state (AddressSpace.mapUser descriptor 0x41000 second 3)
  for i in [:4096] do
    state.modify fun s => putByte s (scratchPA + i.toUInt64) ((i.toUInt64 * 17 + 31) % 256)
  resetCounts state
  require ((← success state (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)) == 4096)
    "two-page word copy length"
  let memory ← state.get
  require (memory.reads8 == 0 && memory.writes8 == 0 && memory.writes64 == 512)
    "aligned bulk path should issue512 complete-word writes"
  for i in [:4096] do
    let pa := if i < 2048 then firstPA + 2048 + i.toUInt64 else secondPA + i.toUInt64 - 2048
    require (byte memory pa == (i.toUInt64 * 17 + 31) % 256) "literal two-page byte result"
  resetCounts state
  require ((← success state (UserCopy.copyFromUser descriptor 0x40800 scratch 0 4096)) == 4096)
    "inverse two-page copy length"
  let memory ← state.get
  require (memory.reads8 == 0 && memory.writes8 == 0 && memory.writes64 == 512)
    "inverse aligned bulk path"
  for i in [:4096] do
    require (byte memory (scratchPA + i.toUInt64) == (i.toUInt64 * 17 + 31) % 256)
      "inverse literal bytes"
  resetCounts state
  require ((← success state (UserCopy.copyToUser descriptor 0x40ffb scratch 1 13)) == 13)
    "unaligned boundary copy length"
  let memory ← state.get
  require (memory.reads8 == 13 && memory.writes8 == 13 && memory.writes64 == 0)
    "unaligned tail preserves byte semantics"
  for i in [:13] do
    let pa := if i < 5 then firstPA + 4091 + i.toUInt64 else secondPA + i.toUInt64 - 5
    require (byte memory pa == ((i.toUInt64 + 1) * 17 + 31) % 256) "unaligned literal bytes"
  -- Read-only/missing second leaves must fail before changing the first.
  discard <| success state (AddressSpace.unmap descriptor 0x41000)
  discard <| success state (AddressSpace.mapUser descriptor 0x41000 second 1)
  let before ← state.get
  status state ABI.permissionDenied (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)
  require ((← state.get).words == before.words) "read-only second leaf exposed partial destination"
  discard <| success state (AddressSpace.unmap descriptor 0x41000)
  let before ← state.get
  status state ABI.missingMapping (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)
  require ((← state.get).words == before.words) "missing second leaf exposed partial destination"
  status state ABI.missingMapping (UserCopy.copyFromUser descriptor 0x40800 scratch 0 4096)
  require ((← state.get).words == before.words) "missing second leaf changed scratch before full preflight"
  status state ABI.invalidArgument (UserCopy.copyToUser descriptor 0x40000 scratch 0 4097)
  status state ABI.kernelFatal (UserCopy.copyFromUser descriptor 0x40000 scratch 4090 8)
  status state ABI.kernelFatal (UserCopy.copyFromUser descriptor 0x40000 (scratch + (if expanded then 8192 else 512)) 0 8)
  status state ABI.kernelFatal (UserCopy.copyFromUser descriptor 0x40000 first 0 8)
  -- A duplicate after the first matching registry row, including a later
  -- registry page, must remain a corrupt descriptor rather than early success.
  if expanded then
    -- Each directory grant is still checked for current ownership,
    -- generation, purpose, exact physical address, uniqueness and zero pins.
    -- Literal corruptions must fail before any user-copy write becomes visible.
    let savedRegistry ← state.get
    let registryHandle := word savedRegistry (address + 1424)
    let registryRecord := 0x80401000 + registryHandle % 8192 * 32
    let registryPhysical := word savedRegistry (address + 1432)
    for (location,value,expected) in #[(registryRecord,3,Frames.notOwned),
        (registryRecord + 8,4,Frames.purposeDenied),
        (registryRecord + 16,1,AddressSpace.invalidDescriptor),
        (registryRecord + 24,2,Frames.notOwned),
        (address + 1432,registryPhysical + 4096,AddressSpace.invalidDescriptor)] do
      state.modify fun s => put s location value
      let beforeRegistry ← state.get
      status state expected (AddressSpace.base descriptor)
      status state ABI.kernelFatal (UserCopy.copyFromUser descriptor 0x40000 scratch 0 8)
      require ((← state.get).words == beforeRegistry.words)
        "corrupt registry caused partial copy or metadata mutation"
      state.set savedRegistry
    state.modify fun s => put (put s (address + 1440) registryHandle)
      (address + 1448) registryPhysical
    status state AddressSpace.invalidDescriptor (AddressSpace.base descriptor)
    state.set savedRegistry
    for i in [:128] do
      let handle ← success state (Frames.allocate 2 4)
      discard <| success state (AddressSpace.mapUser descriptor (0x42000 + i.toUInt64 * 4096) handle 3)
    let saved ← state.get
    let page1 := word saved (address + 1448)
    state.modify fun s => put s page1 0x40000
    status state AddressSpace.invalidDescriptor (AddressSpace.lookup descriptor 0x40000 1)
    state.set saved
    discard <| success state (AddressSpace.lookup descriptor 0x40000 1)
  else
    let saved ← state.get
    -- Add a deliberately duplicated second literal row to the legacy list.
    state.modify fun s => put (put s (address + 48) 2) (address + 416) 0x40000
    status state AddressSpace.invalidDescriptor (AddressSpace.lookup descriptor 0x40000 1)
    state.set saved
  IO.println s!"BULK_COPY_BOUNDARIES:PASS expanded={expanded} exactbytes4096+13 complete-preflight duplicate-registry"

def checkContexts : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 8192 8192 4)
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let root := word (← state.get) (address + 64)
  let translation := word (← state.get) (address + 72)
  let stack ← success state (Frames.allocateContiguous4 2 1)
  let handles := #[(word (← state.get) stack), word (← state.get) (stack + 8),
    word (← state.get) (stack + 16), word (← state.get) (stack + 24)]
  let physical ← success state (Frames.resolvePurpose 2 handles[0]! 1)
  for (slot,value) in #[((2400 : UInt64),handles[0]!),(2480,handles[1]!),(2488,handles[2]!),
      (2496,handles[3]!),(2504,4),(2512,physical),(2408,physical + 16368)] do
    state.modify fun s => put s (address + slot) value
  state.modify fun s => put (put s physical Lemma.Kernel.Loader.stackCanary)
    (physical + 16376) Lemma.Kernel.Loader.stackCanary
  discard <| success state Lemma.Kernel.Task.init
  let record ← success state Lemma.Kernel.Task.table
  state.modify fun s => put (put s record descriptor) (record + 8) Lemma.Kernel.Task.running
  let saved := address + 2048
  state.modify fun s => put (put (put s (saved + 272) translation) saved 0)
    (saved + 264) 0x200000020
  require ((← success state (Lemma.Kernel.Task.context descriptor)) == saved)
    "running context physical identity"
  require (word (← state.get) (saved + 280) == physical + 16368)
    "running context uses exact owned four-page top"
  let running ← state.get
  for (slot,value) in #[(address + 72,translation + 1),(saved + 272,translation + 1),
      (address + 64,root + 4096),(address + 2488,handles[1]!),
      (address + 2408,physical + 8192),(physical,0),(physical + 16376,0),
      ((0x80401000 : UInt64) + handles[0]! % 8192 * 32 + 16,1)] do
    state.modify fun s => put s slot value
    status state 50 (Lemma.Kernel.Task.context descriptor)
    state.set running
  state.modify fun s => put s (record + 8) Lemma.Kernel.Task.blocked
  require ((← success state (Lemma.Kernel.Task.savedContext descriptor)) == saved)
    "blocked context exact identity"
  let blocked ← state.get
  for (slot,value) in #[(AddressSpace.activeRoot,root),(saved,1),(saved + 264,0),
      (saved + 280,physical + 8192),(saved + 272,translation + 1),
      (address + 72,translation + 1),(physical,0),
      ((0x80401000 : UInt64) + handles[3]! % 8192 * 32 + 16,1)] do
    state.modify fun s => put s slot value
    status state 50 (Lemma.Kernel.Task.savedContext descriptor)
    state.set blocked
  -- Trap validation rejects a frame before treating its bytes as authority.
  let frame := physical + 16368 - 288
  state.modify fun s => put (put (put s Lemma.Kernel.Process.control descriptor)
    (frame + 264) 0x200000020) (frame + 272) translation
  require ((← success state (Lemma.Kernel.Process.validateFrame frame)) == descriptor)
    "validated trap frame owns current descriptor"
  let trap ← state.get
  for (slot,value) in #[(frame + 264,0x200000120),(frame + 272,translation + 1),
      (physical + 16376,0),(address + 2408,physical + 8192)] do
    state.modify fun s => put s slot value
    status state 50 (Lemma.Kernel.Process.validateFrame frame)
    state.set trap
  status state 50 (Lemma.Kernel.Process.validateFrame (frame + 8))
  IO.println "CONTEXT_VALIDATION_BOUNDARIES:PASS running blocked frame; translation root owner pins adjacency top canaries privilege"

def checkDeadlines : IO Unit := do
  let state ← IO.mkRef ({} : State)
  require ((← success state (Lemma.Kernel.IPC.deadlineWithLimit 1000 IPCABI.maximumTicks)) == 124456)
    "minimum deadline"
  require ((← success state (Lemma.Kernel.IPC.deadlineWithLimit 10000000 IPCABI.maximumTicks)) == 10123456)
    "legacy1second deadline"
  require ((← success state (Lemma.Kernel.IPC.deadlineWithLimit 300000000 IPCABI.lemmaSimMaximumTicks)) == 300123456)
    "explicit LemmaSim30second deadline"
  for (ticks,maximum) in #[(999,IPCABI.maximumTicks), (10000001,IPCABI.maximumTicks),
      (300000001,IPCABI.lemmaSimMaximumTicks),(1000,999),(1000,10000001),
      (1000,300000001),(1000,0xffffffffffffffff)] do
    status state 22 (Lemma.Kernel.IPC.deadlineWithLimit ticks maximum)
  state.modify fun s => { s with now := 0xffffffffffffffff - 999 }
  status state 22 (Lemma.Kernel.IPC.deadlineWithLimit 1000 IPCABI.maximumTicks)
  state.modify fun s => { s with now := 0xffffffffffffffff - 1000 }
  require ((← success state (Lemma.Kernel.IPC.deadlineWithLimit 1000 IPCABI.maximumTicks)) == 0xffffffffffffffff)
    "exact maximal monotonic deadline"
  status state 22 (Lemma.Kernel.IPC.dispatchWithLimit 10000001 0 0 0 0 0 0 0)
  IO.println "IPC_DEADLINE_BOUNDARIES:PASS legacy1s sim30s arbitrary-selector minimum overflow"
end BulkCopyDeadlineFixture

open Lean Elab Command
run_cmd do
  liftIO <| BulkCopyDeadlineFixture.checkCopies false
  liftIO <| BulkCopyDeadlineFixture.checkCopies true
  liftIO BulkCopyDeadlineFixture.checkContexts
  liftIO BulkCopyDeadlineFixture.checkDeadlines
