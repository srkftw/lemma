import Lemma.User.Runtime.ManagedArray
import Std.Data.HashMap

/-! Finite host RAM observation of real runtime Actions; no ordinary source
program or managed bridge is interpreted by this fixture. -/
namespace ManagedArrayModelFixture
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

def value (state : IO.Ref State) (array index : UInt64) : IO (UInt8 × UInt64) := do
  let (s,child) ← execute state (ManagedArray.getBorrowed array index)
  if s = 0 then execute state (ManagedArray.unbox child) else pure (s,0)

def pushValue (state : IO.Ref State) (array input : UInt64) : IO (UInt8 × UInt64) := do
  let (s,child) ← execute state (ManagedArray.box input)
  if s = 0 then execute state (ManagedArray.push array child) else pure (s,0)

def count (state : IO.Ref State) : IO UInt64 := do read (← state.get) (Arena.control+16) 8

def check : IO Unit := do
  let state ← IO.mkRef ({} : State)
  let (s,empty) ← execute state (ManagedArray.emptyWithCapacity 6)
  must (s = 0 && (← execute state (ManagedArray.size empty)) = (0,0)) "actual array empty"
  let (s,first) ← pushValue state empty 0xffffffffffffffff
  must (s = 0 && (← value state first 0) = (0,0xffffffffffffffff) && (← count state) = 2) "full64 box/parent allocation"
  must ((← execute state (ManagedArray.size empty)).1 = Arena.invalid) "push did not consume old root"
  let (s,source) ← pushValue state first 0x8000000000000001
  must (s = 0 && (← value state source 1) = (0,0x8000000000000001) && (← count state) = 3) "full64 second child"
  must ((← execute state (ManagedArray.retain source)) = (0,source)) "real array root retain"
  let (s,replacement) ← execute state (ManagedArray.box 0xfeedfacecafebeef)
  must (s = 0) "replacement box allocation"
  let (s,changed) ← execute state (ManagedArray.set source 0 replacement)
  must (s = 0 && changed ≠ source && (← count state) = 5 &&
    (← value state source 0) = (0,0xffffffffffffffff) &&
    (← value state changed 0) = (0,0xfeedfacecafebeef) &&
    (← value state changed 1) = (0,0x8000000000000001)) "COW alias/value/graph identity"
  let (s,sharedChild) ← execute state (ManagedArray.getBorrowed source 1)
  must (s = 0 && (← read (← state.get) (Arena.page+128+(sharedChild &&& 31)*128+16) 8) = 2) "COW failed to retain child"
  must ((← execute state (ManagedArray.retain changed)).1 = 0) "OOB set retained alias setup"
  let (s,discarded) ← execute state (ManagedArray.box 0xaaaaaaaaaaaaaaaa)
  must (s = 0 && (← execute state (ManagedArray.set changed 6 discarded)).1 = Arena.invalid &&
    (← execute state (ManagedArray.unbox discarded)).1 = Arena.invalid && (← count state) = 5 &&
    (← value state changed 0) = (0,0xfeedfacecafebeef)) "controlled OOB set did not consume input and preserve alias"
  must ((← execute state (ManagedArray.getBorrowed changed 2)).1 = Arena.invalid) "controlled get! panic escaped"
  must ((← execute state (ManagedArray.release changed)).1 = 0 && (← count state) = 3 &&
    (← value state source 1) = (0,0x8000000000000001)) "final COW graph release damaged alias"
  must ((← execute state (ManagedArray.release source)).1 = 0 && (← count state) = 0 &&
    (← execute state (ManagedArray.unbox sharedChild)).1 = Arena.invalid &&
    (← execute state Arena.destroy).1 = 0) "real final graph/generation cleanup"
  state.set {}
  let (s,array) ← execute state (ManagedArray.emptyWithCapacity 0)
  must (s = 0) "OOM setup empty"
  let (s,array) ← pushValue state array 0x8000000000000000
  must (s = 0 && (← execute state (ManagedArray.retain array)).1 = 0) "OOM source alias"
  let mut fillers : Array UInt64 := #[]
  for _ in [:28] do
    let (s,box) ← execute state (Arena.newBox 9)
    must (s = 0) "OOM filler"
    fillers := fillers.push box
  let (s,replacement) ← execute state (ManagedArray.box 42)
  must (s = 0 && (← count state) = 31) "literal31 live object setup"
  must ((← execute state (ManagedArray.set array 0 replacement)).1 = Arena.exhausted &&
    (← count state) = 30 && (← value state array 0) = (0,0x8000000000000000) &&
    (← execute state (ManagedArray.unbox replacement)).1 = Arena.invalid) "OOM cleanup/root alias preservation"
  for filler in fillers do must ((← execute state (Arena.release filler)).1 = 0) "OOM filler release"
  must ((← execute state (ManagedArray.release array)).1 = 0 && (← count state) = 0 &&
    (← execute state Arena.destroy).1 = 0) "OOM final graph cleanup"
  state.set {}
  let (s,array) ← execute state (ManagedArray.emptyWithCapacity 6)
  must (s = 0) "capacity setup"
  let mut boundedArray := array
  for i in [:6] do
    let (s,next) ← pushValue state boundedArray (0x8000000000000000+i.toUInt64)
    must (s = 0) "six-box bound"
    boundedArray := next
  must ((← count state) = 7 && (← value state boundedArray 5) = (0,0x8000000000000005)) "six-box full64 bound"
  must ((← pushValue state boundedArray 7).1 = Arena.exhausted && (← count state) = 0 &&
    (← execute state Arena.destroy).1 = 0) "seventh push failed to reclaim graph"
  state.set {}
  let (_,array) ← execute state (ManagedArray.emptyWithCapacity 1)
  let (s,array) ← pushValue state array 0xdeadbeefcafebabe
  must (s = 0 && (← execute state (ManagedArray.retain array)).1 = 0) "cancel array setup"
  let (_,element) ← execute state (ManagedArray.box 1)
  must ((← execute state Arena.cancel).1 = 0 &&
    (← execute state (ManagedArray.push array element)).1 = Arena.cancelled && (← count state) = 2) "cancel resource cleanup"
  must ((← execute state (ManagedArray.release array)).1 = 0 && (← count state) = 0 &&
    (← execute state Arena.destroy).1 = 0) "cancel-independent graph release"
  state.set {}
  let (_,array) ← execute state (ManagedArray.emptyWithCapacity 1)
  let (_,array) ← pushValue state array 0x123456789abcdef0
  let (_,foreign) ← execute state (ManagedArray.emptyWithCapacity 0)
  let slot := Arena.page+128+(array &&& 31)*128
  let child ← read (← state.get) (slot+80) 8
  state.set (← write (← state.get) (Arena.control+16) 32 8)
  must ((← execute state (ManagedArray.size array)).1 = Arena.lifetime &&
    (← execute state (ManagedArray.release array)).1 = Arena.lifetime) "corrupted live-count header admitted"
  state.set (← write (← state.get) (Arena.control+16) 3 8)
  state.set (← write (← state.get) (slot+80) foreign 8)
  must ((← execute state (ManagedArray.getBorrowed array 0)).1 = Arena.invalid &&
    (← execute state (ManagedArray.release array)).1 = Arena.invalid && (← count state) = 3) "array reference accepted as scalar child"
  state.set (← write (← state.get) (slot+80) child 8)
  must ((← execute state (ManagedArray.release array)).1 = 0 &&
    (← execute state (ManagedArray.release foreign)).1 = 0 && (← count state) = 0 &&
    (← execute state Arena.destroy).1 = 0) "corruption fixture cleanup"
  state.set ({failAllocation := Lemma.User.ABI.quotaExceeded} : State)
  must ((← execute state (ManagedArray.emptyWithCapacity 0)).1 = Lemma.User.ABI.quotaExceeded &&
    !(← state.get).mapped) "kernel allocation quota manufactured graph"
  must ((← execute state (ManagedArray.natural 6)) = (0,6) &&
    (← execute state (ManagedArray.natural 7)).1 = Arena.invalid &&
    (← execute state (ManagedArray.emptyWithCapacity 7)).1 = Arena.invalid) "bounded Nat/capacity admission"
  IO.println "MANAGED_ARRAY_RUNTIME:PASS full64 boxes/graphCOW/refcounts/OOM/generation/bounds/cancellation; host finite-memory fixture, not RV64 execution"
end ManagedArrayModelFixture
run_cmd do Lean.Elab.Command.liftTermElabM ManagedArrayModelFixture.check
