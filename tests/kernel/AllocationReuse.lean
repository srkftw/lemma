import Lemma.Kernel.Syscall
import Lemma.Kernel.Task
import Lean.Elab.Command
import Std.Data.HashMap

/-! Independent finite RAM checks over the actual production allocator syscall.
The reference executes the previous separately validated descriptor path.
This is host-only observation of work/error boundaries, never target code. -/
namespace AllocationReuseFixture
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  operations : Nat := 0
  reads8 : Nat := 0
  writes8 : Nat := 0
  writes64 : Nat := 0
  now : UInt64 := 123456
  reads64 : Nat := 0
  registryReads : Nat := 0
  failRead : Option UInt64 := none
  failWrite : Option UInt64 := none
  flushFailure : Bool := false

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
    else if op == .installSatp then execute state (next (if s.flushFailure then 7 else 0) 0)
    else
      if !((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000)) then
        throw <| IO.userError s!"access outside finite physical RAM {a}"
      match op with
      | .physicalRead64 =>
        if a % 8 ≠ 0 then throw <| IO.userError "unaligned read64"
        if s.failRead == some a then
          state.set {s with failRead := none}
          execute state (next 7 0)
        else
          state.modify fun s => {s with
            reads64 := s.reads64 + 1
            registryReads := s.registryReads +
              (if Frames.records ≤ a && a < Frames.records + 8192 * 32 then 1 else 0)}
          execute state (next 0 (word (← state.get) a))
      | .physicalWrite64 =>
        if a % 8 ≠ 0 then throw <| IO.userError "unaligned write64"
        if s.failWrite == some a then
          state.set {s with failWrite := none}
          execute state (next 7 0)
        else
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
  state.modify fun s => { s with reads8 := 0, writes8 := 0, writes64 := 0, reads64 := 0, registryReads := 0, operations := 0 }

-- The previous syscall algorithm, retained only as a fixture comparison.
def referenceAllocate (descriptor va count : UInt64) : Action :=
  if count = 1 then
    .bind (Lemma.Kernel.Syscall.ownedArenaAddress va) fun s _ =>
    if s = 0 then
      .bind (AddressSpace.owner descriptor) fun s owner =>
      if s ≠ 0 then .done 255 0 else
      .bind (Frames.allocate owner 4) fun s handle =>
      if s ≠ 0 then .done (Lemma.Kernel.Syscall.memoryStatus s) 0 else
      .bind (AddressSpace.mapUser descriptor va handle 3) fun s _ =>
      if s ≠ 0 then
        .bind (Frames.release owner handle) fun status _ =>
        if status ≠ 0 then .done 255 0 else
          .done (Lemma.Kernel.Syscall.memoryStatus s) 0
      else .done 0 va
    else .done s 0
  else .done 16 0

def fresh (expanded : Bool) : IO (IO.Ref State × UInt64 × UInt64) := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure (if expanded then 8192 else 512)
    (if expanded then 8192 else 32) 4)
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  pure (state,descriptor,address)

def compare (initial : State) (descriptor va count : UInt64) : IO (State × State) := do
  let old ← IO.mkRef initial
  let new ← IO.mkRef initial
  let oldResult ← execute old (referenceAllocate descriptor va count)
  let newResult ← execute new (Lemma.Kernel.Syscall.allocate descriptor va count)
  require (oldResult == newResult) s!"allocation status/value differs {oldResult} / {newResult}"
  let before ← old.get
  let after ← new.get
  require (before.words == after.words) "allocation changed complete authoritative RAM"
  pure (before,after)

def check (expanded : Bool) : IO Unit := do
  let (state,descriptor,address) ← fresh expanded
  resetCounts state
  let (before,after) ← compare (← state.get) descriptor 0x40000 1
  require (after.reads64 < before.reads64 && after.registryReads < before.registryReads)
    "validated address reuse must remove redundant descriptor reads"
  IO.println s!"ALLOCATE_LOCAL_REUSE:PASS expanded={expanded} reads64={before.reads64}→{after.reads64} ownershipreads={before.registryReads}→{after.registryReads}"
  state.set after
  -- Old and new status/order/final RAM agree for malformed descriptor state,
  -- duplicate maps, arena/count rejection, first-access faults and rollback.
  let saved ← state.get
  for (slot,value) in #[(address,0),(address + 8,3),(address + 16,descriptor + 1),
      (address + 24,0),(address + 32,0),(address + 56,0),
      (address + 64,0),(address + 72,0)] do
    let broken := put saved slot value
    discard <| compare broken descriptor 0x41000 1
  for (va,count) in #[(0x40001,1),(0x100000,1),(0x40000,0),(0x40000,2),(0x40000,1)] do
    discard <| compare saved descriptor va count
  for slot in #[address,address + 24,address + 48,address + 64] do
    discard <| compare {saved with failRead := some slot} descriptor 0x41000 1
  discard <| compare {saved with failWrite := some (address + 48)} descriptor 0x41000 1
  -- No row or grant remains published when a mapping flush fails.
  discard <| compare {saved with flushFailure := true} descriptor 0x41000 1
  if expanded then
    let registryHandle := word saved (address + 1424)
    let record := 0x80401000 + registryHandle % 8192 * 32
    for (slot,value) in #[(record,3),(record + 8,4),(record + 16,1),(record + 24,2),
        (address + 1432,0)] do
      discard <| compare (put saved slot value) descriptor 0x41000 1
    -- A duplicate in a later row remains a full-scan rejection.
    let physical := word saved (address + 1432)
    discard <| compare (put (put saved (address + 48) 2) (physical + 32) 0x40000)
      descriptor 0x40000 1
  IO.println s!"ALLOCATE_ERROR_BOUNDARIES:PASS expanded={expanded} priority authoritativeRAM duplicate registry fault rollback"

def referenceTable : Action :=
  .bind (Access.read64 Lemma.Kernel.Task.tableHandle) fun s handle =>
  if s ≠ 0 then .done 50 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s address =>
  if s ≠ 0 then .done 50 0 else
  .bind (Frames.mappingCount 1 handle) fun s pins =>
  if s ≠ 0 then .done 50 0 else
  if pins = 0 then .done 0 address else .done 50 0

def checkTable : IO Unit := do
  let (state,_,_) ← fresh true
  let handle ← success state Lemma.Kernel.Task.init
  resetCounts state
  let saved ← state.get
  let old ← IO.mkRef saved
  let new ← IO.mkRef saved
  let oldResult ← execute old referenceTable
  let newResult ← execute new Lemma.Kernel.Task.table
  require (oldResult == newResult) "checked table identity differs"
  require ((← old.get).words == (← new.get).words) "checked table mutated RAM"
  let before ← old.get
  let after ← new.get
  require (after.registryReads < before.registryReads) "table must reuse freshly checked ownership slot"
  IO.println s!"TASK_TABLE_LOCAL_REUSE:PASS reads64={before.reads64}→{after.reads64} ownershipreads={before.registryReads}→{after.registryReads}"
  let slot := 0x80401000 + handle % 8192 * 32
  for (location,value) in #[(slot,2),(slot + 8,4),(slot + 16,1),(slot + 24,2),
      (Lemma.Kernel.Task.tableHandle,handle + 8192)] do
    let corrupted := put saved location value
    for action in #[referenceTable,Lemma.Kernel.Task.table] do
      let test ← IO.mkRef corrupted
      status test 50 action
      require ((← test.get).words == corrupted.words) "invalid table changed RAM"
  for location in #[slot,slot + 8,slot + 16,slot + 24,Lemma.Kernel.Task.tableHandle] do
    for action in #[referenceTable,Lemma.Kernel.Task.table] do
      let test ← IO.mkRef {saved with failRead := some location}
      status test 50 action
  IO.println "TASK_TABLE_ERROR_BOUNDARIES:PASS exactowner purpose generation zero-pins first-read errors"

namespace Cap
open Lemma.User
open Lemma.Kernel.Capability
open Lemma.Kernel
private def referenceZeroHeaderStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (Objects.get (base + headerOffset + i.toUInt64 * 8)) fun s value =>
  if failed s = true then fatal else .done 0 (if value = 0 then acc else 0)
private def referenceHeader (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (Objects.get (base + headerOffset)) fun s tag =>
  if failed s = true then fatal else
  if tag = magic then
  .bind (Objects.get (base + headerOffset + 8)) fun s version =>
  if failed s = true then fatal else
  if version = 1 then
  .bind (Objects.get (base + headerOffset + 16)) fun s self =>
  if failed s = true then fatal else
  if self = descriptor then
  .bind (Objects.get (base + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if (if state = active then true else if state = constructing then true else false) = true then
  .bind (Objects.get (base + headerOffset + 32)) fun s count =>
  if failed s = true then fatal else
  if count = capacity then
  .bind (Objects.get (base + headerOffset + 40)) fun s used =>
  if failed s = true then fatal else
  if used ≤ capacity then
  .bind (Objects.get (base + headerOffset + 48)) fun s registry =>
  if failed s = true then fatal else
  if registry < Objects.registryCapacity then
  .bind (Objects.registryDescriptor registry) fun s registered =>
  if failed s = true then fatal else
  if registered = descriptor then
  .bind (Objects.get (base + headerOffset + 56)) fun s reserved =>
  if failed s = true then fatal else
  if reserved = 0 then .done 0 base else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else if tag = 0 then .done CapabilityABI.invalidHandle 0 else fatal

def referenceManaged (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (Objects.get (base + headerOffset)) fun s tag =>
  if failed s = true then fatal else
  if tag = 0 then
  .boundedFoldU64 8 referenceZeroHeaderStep 8 1 base 0 0 0 fun s allZero =>
  if failed s = true then fatal else
  if allZero = 1 then .done 0 0 else fatal
  else
  .bind (referenceHeader descriptor) fun s checked =>
  if failed s = true then fatal else
  .bind (Objects.get (checked + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if state = active then .done 0 1 else fatal

end Cap

def checkManaged (expanded : Bool) : IO Unit := do
  let (state,descriptor,address) ← fresh expanded
  -- A genuinely legacy zero capability header must work without Objects.init.
  let legacy ← IO.mkRef (← state.get)
  let legacyNew ← IO.mkRef (← state.get)
  require ((← execute legacy (Cap.referenceManaged descriptor)) == (0,0))
    "reference unmanaged legacy header is not zero"
  require ((← execute legacyNew (Lemma.Kernel.Capability.managed descriptor)) == (0,0))
    "zero legacy header now requires managed object initialization"
  require ((← legacy.get).words == (← legacyNew.get).words)
    "zero legacy header changed authoritative RAM"
  discard <| success state Lemma.Kernel.Objects.init
  discard <| success state (Lemma.Kernel.Capability.attach descriptor)
  discard <| success state (Lemma.Kernel.Capability.activate descriptor)
  resetCounts state
  let original ← IO.mkRef (← state.get)
  let current ← IO.mkRef (← state.get)
  let expected ← execute original (Cap.referenceManaged descriptor)
  let observed ← execute current (Lemma.Kernel.Capability.managed descriptor)
  require (expected == observed && observed == (0,1)) "managed caller status differs"
  let a ← original.get
  let b ← current.get
  require (a.words == b.words) "managed validation mutated authoritative RAM"
  require (b.reads64 < a.reads64 && b.registryReads < a.registryReads) "managed header must reuse its freshly validated descriptor"
  IO.println s!"CAPABILITY_LOCAL_REUSE:PASS expanded={expanded} reads64={a.reads64}→{b.reads64} ownershipreads={a.registryReads}→{b.registryReads}"
  let saved := b
  for (location,value) in #[(address,0),(address + 8,3),(address + 16,descriptor + 1),
      (address + 24,0),(address + 32,0),(address + 64,0),(address + 72,0),
      (address + 2560,0),(address + 2560,1),(address + 2568,2),
      (address + 2576,descriptor + 1),(address + 2584,0),(address + 2584,2),
      (address + 2592,15),(address + 2600,17),(address + 2608,8),(address + 2616,1)] do
    let initial := put saved location value
    let a ← IO.mkRef initial
    let b ← IO.mkRef initial
    require ((← execute a (Cap.referenceManaged descriptor)) ==
      (← execute b (Lemma.Kernel.Capability.managed descriptor))) "corrupt managed metadata precedence differs"
    require ((← a.get).words == (← b.get).words) "corrupt managed validation changed RAM"
  for location in #[address,address + 24,address + 64,address + 2560,address + 2568,
      address + 2576,address + 2584,address + 2592,address + 2600,address + 2608,address + 2616] do
    let a ← IO.mkRef {saved with failRead := some location}
    let b ← IO.mkRef {saved with failRead := some location}
    require ((← execute a (Cap.referenceManaged descriptor)) ==
      (← execute b (Lemma.Kernel.Capability.managed descriptor))) "managed first fault precedence differs"
  IO.println s!"CAPABILITY_AUTHORITY_ERRORS:PASS expanded={expanded} status, complete RAM, corrupt authority and first read errors"
end AllocationReuseFixture

open Lean Elab Command
run_cmd do
  liftIO <| AllocationReuseFixture.check false
  liftIO <| AllocationReuseFixture.check true
  liftIO AllocationReuseFixture.checkTable

run_cmd do
  liftIO <| AllocationReuseFixture.checkManaged false
  liftIO <| AllocationReuseFixture.checkManaged true
