import Lemma.User.Runtime.ManagedBytes
import Std.Data.HashMap

/-! Finite host RAM observation of real runtime Actions; no ordinary source
program or managed bridge is interpreted by this fixture. -/
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
  let (s,empty) ← execute state (ManagedBytes.emptyWithCapacity 48)
  must (s = 0 && (← execute state (ManagedBytes.size empty)) = (0,0)) "ordinary empty allocation"
  let (s,bytes) ← execute state (ManagedBytes.push empty 17)
  must (s = 0 && (← execute state (ManagedBytes.get bytes 0)) = (0,17)) "real push payload"
  must ((← execute state (Arena.bytesLength empty)).1 = Arena.invalid) "push did not consume input"
  must ((← execute state (ManagedBytes.retain bytes)) = (0,bytes)) "real RC increment"
  let (s,changed) ← execute state (ManagedBytes.set bytes 0 99)
  must (s = 0 && changed ≠ bytes && (← execute state (ManagedBytes.get bytes 0)) = (0,17) &&
    (← execute state (ManagedBytes.get changed 0)) = (0,99)) "copy-on-write changed an alias"
  must ((← execute state (ManagedBytes.set changed 48 8)) = (0,changed)) "out-of-bounds set! changed object"
  must ((← execute state (ManagedBytes.get changed 1)).1 = Arena.invalid) "get! bounds passed"
  must ((← execute state (ManagedBytes.natural 48)) = (0,48) && (← execute state (ManagedBytes.natural 49)).1 = Arena.invalid) "bounded Nat domain"
  must ((← execute state (Arena.release changed)).1 = 0) "changed object release"
  let mut boxes : Array UInt64 := #[]
  for _ in [:30] do
    let (s,box) ← execute state (Arena.newBox 123)
    must (s = 0) "OOM preparation allocation"
    boxes := boxes.push box
  must ((← execute state (ManagedBytes.retain bytes)).1 = 0) "OOM source alias"
  must ((← execute state (ManagedBytes.push bytes 42)).1 = Arena.exhausted) "actual copy allocation did not exhaust31 slots"
  must ((← execute state (ManagedBytes.get bytes 0)) = (0,17)) "failed COW consumed remaining alias"
  for box in boxes do must ((← execute state (Arena.release box)).1 = 0) "OOM cleanup"
  must ((← execute state (Arena.release bytes)).1 = 0 && (← execute state Arena.destroy).1 = 0) "all references not reclaimed"
  state.set {}
  let (s,array) ← execute state (ManagedBytes.emptyWithCapacity 0)
  must (s = 0) "full-byte domain empty"
  let mut array := array
  for i in [:48] do
    let (s,next) ← execute state (ManagedBytes.push array i.toUInt64)
    must (s = 0) "valid push failed"
    array := next
  must ((← execute state (ManagedBytes.size array)) = (0,48) && (← execute state (ManagedBytes.get array 47)) = (0,47)) "maximum payload boundary"
  must ((← execute state (ManagedBytes.push array 255)).1 = Arena.exhausted) "payload limit not controlled"
  must ((← execute state Arena.destroy).1 = 0) "overflow did not consume owned input"
  state.set {}
  let (s,cancelArray) ← execute state (ManagedBytes.emptyWithCapacity 1)
  must (s = 0 && (← execute state (ManagedBytes.retain cancelArray)).1 = 0) "cancel setup"
  must ((← execute state Arena.cancel).1 = 0 && (← execute state (ManagedBytes.push cancelArray 1)).1 = Arena.cancelled) "cancel did not preserve resource outcome"
  must ((← execute state (Arena.release cancelArray)).1 = 0 && (← execute state Arena.destroy).1 = 0) "cancellation cleanup"
  state.set {}
  must ((← execute state Arena.ensure).1 = 0) "foreign setup"
  let (s,foreign) ← execute state (Arena.newBytes 64)
  must (s = 0 && (← execute state (ManagedBytes.size foreign)).1 = Arena.invalid) "foreign cookie admitted"
  must ((← execute state (Arena.release foreign)).1 = 0) "foreign fixture cleanup"
  IO.println "MANAGED_BYTES_RUNTIME:PASS real generational allocation/COW/refcounts/OOM/bounds/cancellation; host-state fixture only"
end ArenaModelFixture
run_cmd do Lean.Elab.Command.liftTermElabM ArenaModelFixture.check
