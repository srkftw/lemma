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

def freshUpload (count : Nat) : IO (IO.Ref State × UInt64 × UInt64 × UInt64) := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 8192 8192 4)
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let scratch ← success state (Frames.allocate 1 1)
  for i in [:count] do
    let frame ← success state (Frames.allocate 2 4)
    discard <| success state (AddressSpace.mapUser descriptor (if i = 0 then 0x20000 else 0x1000000 + (i-1).toUInt64 * 4096) frame 3)
  let physical ← success state (AddressSpace.lookup descriptor 0x20400 1)
  state.modify fun s => put (put (put (put s physical 0) (physical+8) 0) (physical+16) 32) (physical+24) 32
  state.modify fun s => put (put s (physical+256) 0x0123456789abcdef) (physical+264) 0xfedcba9876543210
  resetCounts state
  pure (state,descriptor,scratch,physical)

def oldUploadCopy (descriptor scratch fields pixels length : UInt64) : Action :=
  .bind (UserCopy.copyFromUser descriptor fields scratch 1024 32) fun s _ =>
  if s = 0 then UserCopy.copyFromUser descriptor pixels scratch 0 length else .done s 0

def newUploadCopy (descriptor scratch fields pixels length : UInt64) : Action :=
  if scratch = descriptor then oldUploadCopy descriptor scratch fields pixels length else
  .bind (UserCopy.copyFromUserReadPage descriptor fields scratch 1024 32) fun s first =>
  if s = 0 then UserCopy.copyFromUserReusingReadPage descriptor fields first pixels scratch 0 length
  else .done s 0

def uploadCounts (count : Nat) : IO Unit := do
  let (state,descriptor,scratch,_) ← freshUpload count
  let saved ← state.get
  let old ← IO.mkRef saved
  let new ← IO.mkRef saved
  let beforeResult ← execute old (oldUploadCopy descriptor scratch 0x20400 0x20500 512)
  let afterResult ← execute new (newUploadCopy descriptor scratch 0x20400 0x20500 512)
  require (beforeResult == afterResult && beforeResult == (0,512)) "upload copy status differs"
  let a ← old.get
  let b ← new.get
  require (a.words == b.words) "upload copy exact authoritative bytes differ"
  IO.println s!"USER_PAGE_REUSE:PASS leaves={count} reads64={a.reads64}→{b.reads64} ownership={a.registryReads}→{b.registryReads} writes64={a.writes64}→{b.writes64}"
def compareUpload (initial : State) (descriptor scratch fields pixels length : UInt64) : IO Unit := do
  let old ← IO.mkRef initial
  let new ← IO.mkRef initial
  let a ← execute old (oldUploadCopy descriptor scratch fields pixels length)
  let b ← execute new (newUploadCopy descriptor scratch fields pixels length)
  require (a == b) s!"transfer first result differs {a}/{b} pointers{fields}/{pixels} length{length}"
  require ((← old.get).words == (← new.get).words) "transfer complete RAM differs"

def uploadErrors : IO Unit := do
  let (state,descriptor,scratch,physical) ← freshUpload 444
  let saved ← state.get
  for (fields,pixels,length) in #[(0x20400,0x20500,512),(0x20401,0x20503,511),
      (0x20400,0x20f00,512),(0x20400,0x1000000,512),(0x20400,0x2000,1),
      (0x20400,0x3fffffff,2),(0x20400,0x20500,0),(0x20400,0x20500,4097),
      (0x20400,0x21500,8),(0x20ff0,0x20500,512)] do
    compareUpload saved descriptor scratch fields pixels length
  let address := Frames.pool + (descriptor % 8192) * 4096
  let registryPhysical := word saved (address + 1432)
  let tile := Frames.pool + (scratch % 8192) * 4096
  for (location,value) in #[(address,0),(address+16,descriptor+1),(address+24,0),
      (address+64,0),(address+72,0),(address+1432,0),(registryPhysical+32,0x20000),
      (registryPhysical+8,word saved (registryPhysical+8)+8192),
      (registryPhysical+16,0),(registryPhysical+24,5)] do
    compareUpload (put saved location value) descriptor scratch 0x20400 0x20500 512
  for location in #[address,address+24,address+64,address+1432,registryPhysical,
      word saved (address + 1432 + 3*16) + (443 % 128)*32,physical,physical+256,physical+264,
      Frames.records + (scratch % 8192) * 32] do
    compareUpload {saved with failRead := some location} descriptor scratch 0x20400 0x20500 512
  for location in #[tile+1024,tile+1032,tile,tile+16,tile+504] do
    compareUpload {saved with failWrite := some location} descriptor scratch 0x20400 0x20500 512
  -- A malformed tile handle that aliases the descriptor must retain the old
  -- path: copied metadata could otherwise mutate authority before the reuse.
  compareUpload saved descriptor descriptor 0x20400 0x20500 512
  IO.println "USER_PAGE_REUSE_ERRORS:PASS exact metadata-first faults, duplicate/PTE/ownership corruption, byte/cross-page/range fallback and partial-write RAM; aliased descriptor falls back"
end AllocationReuseFixture
open Lean Elab Command
run_cmd do
  liftIO <| AllocationReuseFixture.uploadCounts 1
  liftIO <| AllocationReuseFixture.uploadCounts 444
  liftIO <| AllocationReuseFixture.uploadErrors
