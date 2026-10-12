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

private def oldCopyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (Access.read64 (source + i.toUInt64 * 8)) fun s value =>
  if Lemma.Kernel.Task.failed s = true then Lemma.Kernel.Task.fatal else
  .bind (Access.write64 (target + i.toUInt64 * 8) value) fun s _ =>
  if Lemma.Kernel.Task.failed s = true then Lemma.Kernel.Task.fatal else .done 0 (acc + 1)

/-- Exact previous capture body, retained only as a host-side comparison oracle. -/
def oldCapture (descriptor frame : UInt64) : Action :=
  .bind (Lemma.Kernel.Process.validateFrame frame) fun s actual =>
  if Lemma.Kernel.Task.failed s = true then Lemma.Kernel.Task.fatal else
  if actual = descriptor then
    .bind (AddressSpace.context descriptor) fun s saved =>
    if Lemma.Kernel.Task.failed s = true then Lemma.Kernel.Task.fatal else
    .boundedFoldU64 36 oldCopyStep 36 0 frame saved 0 0 fun s count =>
    if Lemma.Kernel.Task.failed s = true then Lemma.Kernel.Task.fatal else
    if count = 36 then Lemma.Kernel.Task.context descriptor else Lemma.Kernel.Task.fatal
  else Lemma.Kernel.Task.fatal

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
  let frame := physical + 16368 - 288
  for i in [:36] do
    state.modify fun s => put s (frame + i.toUInt64*8) ((i+1).toUInt64*0x01010101)
  state.modify fun s => put (put (put s Lemma.Kernel.Process.control descriptor)
    (frame + 264) 0x200000020) (frame + 272) translation
  resetCounts state
  let initial ← state.get
  let old ← IO.mkRef initial
  let current ← IO.mkRef initial
  let a ← execute old (oldCapture descriptor frame)
  let b ← execute current (Lemma.Kernel.Task.capture descriptor frame)
  require (a == b && b == (0,saved)) "capture result differs"
  let before ← old.get
  let after ← current.get
  require (before.words == after.words) "capture full authoritative RAM differs"
  require (after.reads64 < before.reads64) "capture must remove redundant validation"
  IO.println s!"TRAP_CAPTURE_REUSE:PASS reads64={before.reads64}→{after.reads64} ownership={before.registryReads}→{after.registryReads} wordsWritten={before.writes64}→{after.writes64}"
  let compare := fun initial descriptor frame => do
    let old ← IO.mkRef initial
    let current ← IO.mkRef initial
    require ((← execute old (oldCapture descriptor frame)) ==
      (← execute current (Lemma.Kernel.Task.capture descriptor frame))) "capture fault/authority result differs"
    require ((← old.get).words == (← current.get).words) "capture failed prefix/authority RAM differs"
  for (location,value) in #[(address,0),(address+24,0),(address+64,root+4096),
      (address+72,translation+1),(frame+264,0x200000120),(frame+272,translation+1),
      (address+2488,handles[1]!),(address+2408,physical+8192),(physical,0),
      (physical+16376,0),(record,descriptor+8192),(record+8,4),
      (Frames.records + handles[0]! % 8192 *32 +16,1)] do
    compare (put initial location value) descriptor frame
  compare initial (descriptor+1) frame
  compare initial descriptor (frame+8)
  for location in #[address,address+64,address+72,address+2408,address+2488,
      address+1432,record,record+8,frame+264,frame+272,physical,physical+16376] do
    compare {initial with failRead := some location} descriptor frame
  for location in #[saved,saved+16,saved+264,saved+280] do
    compare {initial with failWrite := some location} descriptor frame
  IO.println "TRAP_CAPTURE_REUSE_ERRORS:PASS origin/trackedroot/generation/taskstate/stackcanary/adjacency/pins/fault and exact failedcopy prefix"

end AllocationReuseFixture
open Lean Elab Command
run_cmd do
  liftIO AllocationReuseFixture.checkContexts
