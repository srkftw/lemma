import Lemma.User.Runtime.Arena
import Lemma.Mathematics.OwnedSubmission
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

open Lean Elab Command Lemma.Compiler Lemma.Core0
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``Lemma.User.Runtime.Arena.create, ``Lemma.User.Runtime.Arena.newBox,
        ``Lemma.User.Runtime.Arena.newBytes, ``Lemma.User.Runtime.Arena.ensure,
        ``Lemma.User.Runtime.Arena.bytesReadWord, ``Lemma.User.Runtime.Arena.bytesWriteWord, ``Lemma.User.Runtime.Arena.boxGet,
        ``Lemma.User.Runtime.Arena.boxSet, ``Lemma.User.Runtime.Arena.bytesGet,
        ``Lemma.User.Runtime.Arena.bytesSet, ``Lemma.User.Runtime.Arena.bytesLength,
        ``Lemma.User.Runtime.Arena.retain, ``Lemma.User.Runtime.Arena.release,
        ``Lemma.User.Runtime.Arena.cancel, ``Lemma.User.Runtime.Arena.destroy] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => logInfo "OWNED_ARENA_LOWERING:PASS genuine ordinary elaboration, existing scalar user-v0.1 checked LLVM; target execution separate"
  | .error diagnostic => throwError diagnostic

namespace ArenaModelFixture
open Lemma.Core0.Memory Lemma.User.Runtime

structure State where
  bytes : Std.HashMap UInt64 UInt8 := {}
  mapped : Bool := false
  failAllocation : UInt8 := 0
  allocations : UInt64 := 0
  releases : UInt64 := 0

def readable (state : State) (address : UInt64) : Bool :=
  (0x20000 ≤ address && address < 0x21000) ||
    (state.mapped && Arena.page ≤ address && address < Arena.page+4096)

def read (state : State) (address : UInt64) (count : Nat) : IO UInt64 := do
  let mut value : UInt64 := 0
  for i in [:count] do
    unless readable state (address+i.toUInt64) do throw <| IO.userError "unmapped runtime read"
    value := value ||| ((state.bytes.getD (address+i.toUInt64) 0).toUInt64 <<< (i.toUInt64*8))
  pure value

def write (state : State) (address value : UInt64) (count : Nat) : IO State := do
  let mut state := state
  for i in [:count] do
    unless readable state (address+i.toUInt64) do throw <| IO.userError "unmapped runtime write"
    state := {state with bytes := state.bytes.insert (address+i.toUInt64) (value >>> (i.toUInt64*8)).toUInt8}
  pure state

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status,value)
  | .bind first next =>
    let (status,value) ← execute state first
    execute state (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then throw <| IO.userError "runtime fold exceeded its declared bound"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        let result ← execute state (step i.toUInt32 count value c0 c1 c2 c3)
        status := result.1; value := result.2
    execute state (next status value)
  | .platform operation a b c _ _ _ next =>
    let current ← state.get
    match operation with
    | .virtualRead64 => execute state (next 0 (← read current a 8))
    | .virtualRead8 => execute state (next 0 (← read current a 1))
    | .virtualWrite64 => state.set (← write current a b 8); execute state (next 0 0)
    | .virtualWrite8 => state.set (← write current a b 1); execute state (next 0 0)
    | .syscall =>
      unless b = Arena.page && c = 1 do throw <| IO.userError "runtime made undeclared syscall arguments"
      if a = Lemma.User.ABI.allocatePages then
        if current.failAllocation ≠ 0 then execute state (next current.failAllocation 0) else
        if current.mapped then execute state (next Lemma.User.ABI.duplicateMapping 0) else
        let mut fresh := {current with mapped := true, allocations := current.allocations+1}
        for i in [:4096] do fresh := {fresh with bytes := fresh.bytes.insert (Arena.page+i.toUInt64) 0}
        state.set fresh; execute state (next 0 Arena.page)
      else if a = Lemma.User.ABI.releasePages then
        if current.mapped then
          state.set {current with mapped := false,releases := current.releases+1}
          execute state (next 0 Arena.page)
        else execute state (next Lemma.User.ABI.missingMapping 0)
      else throw <| IO.userError "runtime made undeclared syscall"
    | _ => throw <| IO.userError "runtime used unsupported modeled effect"
  | _ => throw <| IO.userError "runtime used unsupported modeled action"

def must (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message

def check : IO Unit := do
  let state ← IO.mkRef ({} : State)
  must ((← execute state Arena.ensure) = (0,Arena.page)) "actual owned-page create"
  must ((← execute state Arena.ensure) = (0,Arena.page) && (← state.get).allocations = 1) "ensure duplicated allocation"
  let (s,box) ← execute state (Arena.newBox 0xdeadbeef)
  must (s = 0 && box = 32 && (← execute state (Arena.boxGet box)) = (0,0xdeadbeef)) "boxed object"
  must ((← execute state (Arena.retain box)) = (0,box)) "real retain"
  must ((← execute state (Arena.release box)).1 = 0 && (← execute state (Arena.boxGet box)) = (0,0xdeadbeef)) "release decremented live references"
  must ((← execute state (Arena.release box)).1 = 0 && (← execute state (Arena.boxGet box)).1 = Arena.invalid) "final release stale handle"
  for i in [:14] do must ((← read (← state.get) (Arena.page+128+16+i.toUInt64*8) 8) = 0) "final release retained payload or metadata"
  let (s,newBox) ← execute state (Arena.newBox 42)
  must (s = 0 && newBox = 64 && (← execute state (Arena.boxGet box)).1 = Arena.invalid) "generation reuse resurrected old handle"
  must ((← execute state Arena.cancel).1 = 0 && (← execute state (Arena.boxGet newBox)).1 = Arena.cancelled) "cancellation"
  must ((← execute state (Arena.release newBox)).1 = 0 && (← execute state Arena.destroy).1 = 0) "cancelled cleanup"
  must (!(← state.get).mapped && (← state.get).releases = 1 && (← execute state Arena.create).1 = Arena.lifetime &&
    (← execute state (Arena.boxGet newBox)).1 = Arena.lifetime) "destroyed arena re-created or accessed unmapped heap"
  let state ← IO.mkRef ({} : State)
  must ((← execute state Arena.create).1 = 0) "second isolated state create"
  let (s,array) ← execute state (Arena.newBytes 64)
  must (s = 0 && (← execute state (Arena.bytesLength array)) = (0,64)) "byte array object"
  must ((← execute state (Arena.bytesGet array 63)) = (0,0) && (← execute state (Arena.bytesSet array 63 255)).1 = 0 &&
    (← execute state (Arena.bytesGet array 63)) = (0,255)) "byte array initialization/access"
  must ((← execute state (Arena.bytesGet array 64)).1 = Arena.invalid && (← execute state (Arena.bytesSet array 0 256)).1 = Arena.invalid &&
    (← execute state (Arena.boxGet array)).1 = Arena.invalid) "byte array bounds/tag"
  must ((← execute state (Arena.bytesWriteWord array 0 0x0123456789abcdef)).1 = 0 &&
    (← execute state (Arena.bytesReadWord array 0)) = (0,0x0123456789abcdef) &&
    (← execute state (Arena.bytesReadWord array 1)).1 = Arena.invalid &&
    (← execute state (Arena.bytesReadWord array 64)).1 = Arena.invalid) "word payload boundaries"
  let mut handles : Array UInt64 := #[array]
  for i in [:30] do
    let (status,handle) ← execute state (Arena.newBox i.toUInt64)
    must (status = 0) "bounded slot allocation"
    handles := handles.push handle
  must ((← execute state (Arena.newBox 99)).1 = Arena.exhausted &&
    (← read (← state.get) (Arena.control+16) 8) = 31 &&
    (← execute state (Arena.bytesReadWord array 0)) = (0,0x0123456789abcdef)) "controlled OOM changed live object"
  let old := handles[7]!
  must ((← execute state (Arena.release old)).1 = 0) "OOM recovery release"
  let (status,reused) ← execute state (Arena.newBox 99)
  must (status = 0 && reused = old+32 && (← execute state (Arena.boxGet old)).1 = Arena.invalid) "OOM recovery generation"
  for i in [:handles.size] do
    must ((← execute state (Arena.release (if i = 7 then reused else handles[i]!))).1 = 0) "clean up actual slots"
  must ((← execute state Arena.destroy).1 = 0 && (← state.get).allocations = 1 && (← state.get).releases = 1) "owned page lifetime"
  let state ← IO.mkRef ({} : State)
  must ((← execute state Arena.create).1 = 0) "retirement arena create"
  let (_,handle) ← execute state (Arena.newBox 99)
  let address := Arena.page+128
  state.set (← write (← state.get) (address+16) 65535 8)
  must ((← execute state (Arena.retain handle)).1 = Arena.lifetime &&
    (← read (← state.get) (address+16) 8) = 65535) "reference overflow wrapped"
  state.set (← write (← state.get) (address+16) 1 8)
  state.set (← write (← state.get) (address+8) Arena.maximumGeneration 8)
  let last := Arena.maximumGeneration <<< 5
  must ((← execute state (Arena.release last)).1 = 0 &&
    (← read (← state.get) address 8) = 2) "maximum generation failed to retire"
  let (status,next) ← execute state (Arena.newBox 42)
  must (status = 0 && next = 33 && (← execute state (Arena.boxGet last)).1 = Arena.invalid) "retired slot reused or generation wrapped"
  must ((← execute state (Arena.release next)).1 = 0 && (← execute state Arena.destroy).1 = 0) "retired cleanup"
  let state ← IO.mkRef ({failAllocation := Lemma.User.ABI.quotaExceeded} : State)
  must ((← execute state Arena.create).1 = Lemma.User.ABI.quotaExceeded && !(← state.get).mapped &&
    (← read (← state.get) Arena.control 8) = 0) "kernel quota failure manufactured allocation"

run_cmd do
  liftIO check
  logInfo "OWNED_ARENA_MODEL:PASS real allocator/lifetime/OOM/tag/bounds/refcount/generation/cancellation semantics; modeled syscalls, not RV64 execution"

end ArenaModelFixture

run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``Lemma.Mathematics.OwnedSubmission.check] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => pure ()
  | .error diagnostic => throwError diagnostic
  let state ← liftIO <| IO.mkRef ({} : ArenaModelFixture.State)
  for (goal,n,d,p0,p1,p2,budget,expected) in
      #[(1,5,6,0,0,0,8,1),(1,5,7,0,0,0,8,2),(1,5,6,0,0,0,0,5),
        (2,5,6,1,2,1,8,1),(2,5,6,1,3,1,8,2),(3,0,0,0,0,0,8,4)] do
    let result ← liftIO <| ArenaModelFixture.execute state
        (Lemma.Mathematics.OwnedSubmission.check goal n d p0 p1 p2 budget)
    unless result = (0,expected) do throwError "owned mathematical object changed exact semantics"
    let count ← liftIO <| ArenaModelFixture.read (← liftIO state.get) (Lemma.User.Runtime.Arena.control+16) 8
    unless count = 0 do throwError "owned mathematical object leaked"
  unless (← liftIO state.get).allocations = 1 do throwError "checker duplicated its per-process owned page"
  logInfo "OWNED_SUBMISSION:PASS exact arithmetic traverses real bounded object allocation/read/release, genuine checked LLVM; target execution separate"
