import Lemma.User.Runtime.ManagedClosure
import Std.Data.HashMap

/-! Independent finite-memory observation of actual UTF8/runtime Actions.
No ordinary source program is interpreted here. -/
namespace ManagedClosureModelFixture
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

def count (state : IO.Ref State) : IO UInt64 := do read (← state.get) (Arena.control+16) 8
def check : IO Unit := do
  let state ← IO.mkRef ({} : State)
  must ((← execute state Arena.ensure).1 = 0) "actual owned page allocation"
  let (s,capture) ← execute state (Arena.newBox 0xffffffffffffffff)
  must (s = 0) "full64 capture box"
  let (s,closure) ← execute state (ManagedClosure.create 1 1 capture 0 0 0)
  must (s = 0 && (← count state) = 2 &&
    (← execute state (ManagedClosure.capture closure 0)) = (0,0xffffffffffffffff)) "owned full64 environment layout"
  must ((← execute state (ManagedClosure.retain closure)).1 = 0) "real closure alias retain"
  must ((← execute state (ManagedClosure.release closure)).1 = 0 && (← count state) = 2 &&
    (← execute state (ManagedClosure.capture closure 0)).1 = 0) "shared release prematurely reclaimed capture"
  let (s,input) ← execute state (Arena.newBox 0x8000000000000001)
  must (s = 0) "real argument box"
  let (s,result) ← execute state (ManagedClosure.finish closure input 0xfffffffffffffffe)
  must (s = 0 && (← count state) = 1 && (← execute state (Arena.boxGet result)) = (0,0xfffffffffffffffe) &&
    (← execute state (ManagedClosure.capture closure 0)).1 = Arena.invalid &&
    (← execute state (Arena.boxGet capture)).1 = Arena.invalid &&
    (← execute state (Arena.boxGet input)).1 = Arena.invalid) "actual application root/input reclamation and full64 result"
  must ((← execute state (Arena.release result)).1 = 0 && (← count state) = 0) "real result reclamation"
  let (s,capture2) ← execute state (Arena.newBox 42)
  must (s = 0 && capture2 ≠ capture) "generation changed after reclaimed scalar slot"
  let (s,closure2) ← execute state (ManagedClosure.create 2 1 capture2 0 0 0)
  must (s = 0 && closure2 ≠ closure) "generation changed after closure reclamation"
  must ((← execute state Arena.cancel).1 = 0 &&
    (← execute state (ManagedClosure.capture closure2 0)).1 = Arena.cancelled &&
    (← execute state (ManagedClosure.release closure2)).1 = 0 && (← count state) = 0)
    "cancellation blocks observation but actual graph cleanup succeeds"
  must ((← execute state Arena.destroy).1 = 0 && !(← state.get).mapped) "owned page teardown"

  let shared ← IO.mkRef ({} : State)
  must ((← execute shared Arena.ensure).1 = 0) "shared scalar page"
  let (s,box) ← execute shared (Arena.newBox 0x8000000000000001)
  must (s = 0 && (← execute shared (Arena.retain box)).1 = 0) "actual shared-box refcount increment"
  let (s,left) ← execute shared (ManagedClosure.create 1 1 box 0 0 0)
  must (s = 0) "first graph consumes one shared capture reference"
  let (s,right) ← execute shared (ManagedClosure.create 2 1 box 0 0 0)
  must (s = 0 && (← count shared) = 3) "second graph owns remaining shared reference"
  must ((← execute shared (ManagedClosure.release left)).1 = 0 && (← count shared) = 2 &&
    (← execute shared (ManagedClosure.capture right 0)) = (0,0x8000000000000001))
    "first parent release prematurely reclaimed aliased full64 child"
  must ((← execute shared (ManagedClosure.release right)).1 = 0 && (← count shared) = 0 &&
    (← execute shared (Arena.boxGet box)).1 = Arena.invalid &&
    (← execute shared Arena.destroy).1 = 0) "second parent consumes final real boxed reference"

  for captures in (#[1,4] : Array UInt64) do
    let pressure ← IO.mkRef ({} : State)
    must ((← execute pressure Arena.ensure).1 = 0) "bounded pressure page"
    let mut boxes : Array UInt64 := #[]
    for i in [:31] do
      let (s,box) ← execute pressure (Arena.newBox i.toUInt64)
      must (s = 0) "real31 slots filled"
      boxes := boxes.push box
    must ((← execute pressure (ManagedClosure.create 1 captures boxes[0]! (if captures = 4 then boxes[1]! else 0)
      (if captures = 4 then boxes[2]! else 0) (if captures = 4 then boxes[3]! else 0))).1 = Arena.exhausted &&
      (← count pressure) = 31-captures) "PAP OOM consumed actual capture roots and no unrelated boxes"
    for i in [captures.toNat:31] do
      must ((← execute pressure (Arena.release boxes[i]!)).1 = 0) "remaining pressure reclaim"
    must ((← count pressure) = 0 && (← execute pressure Arena.destroy).1 = 0) "OOM graph/page cleanup"

  let rejected ← IO.mkRef ({} : State)
  must ((← execute rejected Arena.ensure).1 = 0) "invalid setup"
  let (s,box) ← execute rejected (Arena.newBox 9)
  must (s = 0 && (← execute rejected (ManagedClosure.create 9 1 box 0 0 0)).1 = Arena.invalid &&
    (← count rejected) = 0) "invalid code rejected with consumed capture cleanup"
  must ((← execute rejected Arena.destroy).1 = 0) "invalid cleanup"
  IO.println "MANAGED_CLOSURE_RUNTIME:PASS real graph/width/alias/generation/cancel/31slot OOM; finite model only"
end ManagedClosureModelFixture

def main : IO Unit := ManagedClosureModelFixture.check
