import Lemma.User.Runtime.ManagedString
import Std.Data.HashMap

/-! Independent finite-memory observation of actual UTF8/runtime Actions.
No ordinary source program is interpreted here. -/
namespace ManagedStringModelFixture
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
def bytes (state : IO.Ref State) (input : Array UInt8) : IO UInt64 := do
  let (status,first) ← execute state (ManagedBytes.emptyWithCapacity input.size.toUInt64)
  must (status = 0) "actual ByteArray allocation"
  let mut handle := first
  for byte in input do
    let (status,next) ← execute state (ManagedBytes.push handle byte.toUInt64)
    must (status = 0) "actual ByteArray owned push"
    handle := next
  pure handle
def text (state : IO.Ref State) (input : Array UInt8) : IO UInt64 := do
  let source ← bytes state input
  let (status,value) ← execute state (ManagedString.fromByteArray source)
  must (status = 0) "actual UTF8 string allocation"
  must ((← execute state (ManagedBytes.size source)).1 = Arena.invalid) "string constructor did not consume bytes"
  pure value
def data (state : IO.Ref State) (handle : UInt64) : IO (Array UInt8) := do
  must ((← execute state (ManagedString.retain handle)).1 = 0) "borrowed inspection retains before consuming conversion"
  let (status,copy) ← execute state (ManagedString.toByteArray handle)
  must (status = 0) "actual independent bytes copy"
  let (status,size) ← execute state (ManagedBytes.size copy)
  must (status = 0) "typed bytes copy"
  let mut output := #[]
  for i in [:size.toNat] do
    let (status,byte) ← execute state (ManagedBytes.get copy i.toUInt64)
    must (status = 0) "bytes copy read"
    output := output.push byte.toUInt8
  must ((← execute state (Arena.release copy)).1 = 0) "real bytes copy reclamation"
  pure output

def check : IO Unit := do
  let valid : Array (Array UInt8 × UInt64) := #[
    (#[],0),(#[0],1),(#[127],1),(#[194,128],1),(#[223,191],1),
    (#[224,160,128],1),(#[237,159,191],1),(#[238,128,128],1),(#[239,191,191],1),
    (#[240,144,128,128],1),(#[244,143,191,191],1),
    (#[65,195,169,226,130,172,240,159,152,128],4)]
  let invalid : Array (Array UInt8) := #[
    #[128],#[191],#[192,175],#[193,191],#[194],#[194,127],#[223,192],
    #[224,159,191],#[237,160,128],#[239,191],#[240,143,191,191],
    #[244,144,128,128],#[245,128,128,128],#[254],#[255],#[226,40,161],
    #[240,144,128],#[240,144,128,128,128]]
  for (input,points) in valid do
    let state ← IO.mkRef ({} : State)
    let source ← bytes state input
    must ((← execute state (ManagedString.validateUTF8 source)) = (0,1)) "strict valid UTF8 decision"
    let (status,string) ← execute state (ManagedString.fromByteArray source)
    must (status = 0 && (← execute state (ManagedString.length string)) = (0,points) &&
      (← execute state (ManagedString.byteSize string)) = (0,input.size.toUInt64)) "cached count agrees with actual UTF8"
    must ((← data state string) = input) "full UTF8 bytes preserved including NUL"
    must ((← execute state (ManagedString.release string)).1 = 0 && (← count state) = 0) "real string lifetime"
    must ((← execute state Arena.destroy).1 = 0 && !(← state.get).mapped) "real owned page release"
  for input in invalid do
    let state ← IO.mkRef ({} : State)
    let source ← bytes state input
    must ((← execute state (ManagedString.validateUTF8 source)) = (0,0)) "malformed UTF8 accepted"
    must ((← execute state (ManagedString.fromByteArray source)).1 = Arena.invalid &&
      (← count state) = 0) "erased proof replaced runtime validation or input cleanup"
    must ((← execute state Arena.destroy).1 = 0) "invalid UTF8 cleanup page release"

  let consumed ← IO.mkRef ({} : State)
  let source ← text consumed #[65,0,195,169]
  let (status,output) ← execute consumed (ManagedString.toByteArray source)
  must (status = 0 && (← count consumed) = 1 &&
    (← execute consumed (ManagedString.byteSize source)).1 = Arena.invalid)
    "String.toByteArray failed to consume its original owned reference"
  must ((← execute consumed (Arena.release output)).1 = 0 &&
    (← execute consumed Arena.destroy).1 = 0) "consuming conversion reclamation"

  let state ← IO.mkRef ({} : State)
  let first ← text state #[195,169]
  must ((← execute state (ManagedString.retain first)).1 = 0) "real aliased String retain"
  let (status,joined) ← execute state (ManagedString.append first first)
  must (status = 0 && joined ≠ first && (← data state first) = #[195,169] &&
    (← data state joined) = #[195,169,195,169] && (← execute state (ManagedString.length joined)) = (0,2))
    "append mutated aliased source or wrong scalar count"
  must ((← execute state (ManagedString.release joined)).1 = 0) "append output reclamation"
  let (status,parent) ← execute state (ManagedString.some first)
  must (status = 0 && (← count state) = 2 &&
    (← execute state (ManagedString.optionTag parent)) = (0,1)) "real Option.some child graph"
  let (status,borrowed) ← execute state (ManagedString.getSome parent)
  must (status = 0 && borrowed = first) "borrowed exact String projection"
  must ((← execute state (ManagedString.retain borrowed)).1 = 0) "real projected String retain"
  must ((← execute state (ManagedString.retainOption parent)).1 = 0 &&
    (← execute state (ManagedString.releaseOption parent)).1 = 0 &&
    (← execute state (ManagedString.getSome parent)).1 = 0 && (← count state) = 2)
    "shared Option parent decremented its owned child prematurely"
  must ((← execute state (ManagedString.releaseOption parent)).1 = 0 && (← count state) = 1 &&
    (← data state borrowed) = #[195,169]) "parent release consumed retained projection"
  must ((← execute state (ManagedString.release borrowed)).1 = 0 && (← count state) = 0) "child graph reclamation"
  must ((← execute state (ManagedString.optionTag 0)) = (0,0) &&
    (← execute state (ManagedString.releaseOption 0)) = (0,0) && (← count state) = 0)
    "immediate Option.none allocated a fictitious object"

  let whole ← text state (Array.replicate 40 65)
  must ((← execute state (ManagedString.retain whole)).1 = 0) "overflow alias retain"
  must ((← execute state (ManagedString.append whole whole)).1 = Arena.exhausted &&
    (← execute state (ManagedString.byteSize whole)) = (0,40) && (← count state) = 1)
    "append overflow lost retained source or fabricated result"
  must ((← execute state (ManagedString.release whole)).1 = 0) "overflow alias cleanup"
  let (status,parent) ← execute state (ManagedString.some (← text state #[65]))
  must (status = 0) "cancel graph setup"
  must ((← execute state Arena.cancel).1 = 0 &&
    (← execute state (ManagedString.getSome parent)).1 = Arena.cancelled) "canceled graph accepted observation"
  must ((← execute state (ManagedString.releaseOption parent)).1 = 0 && (← count state) = 0)
    "cancellation-independent graph release missing"
  must ((← execute state Arena.destroy).1 = 0) "canceled page release"

  for mode in #[0,1,2] do
    let pressure ← IO.mkRef ({} : State)
    must ((← execute pressure Arena.ensure).1 = 0) "pressure owns actual mapped page"
    let source ← if mode = 0 then bytes pressure #[65] else text pressure #[65]
    let mut boxes := #[]
    for i in [:30] do
      let (status,box) ← execute pressure (Arena.newBox i.toUInt64)
      must (status = 0) "literal30 object pressure"
      boxes := boxes.push box
    if mode = 2 then
      must ((← count pressure) = 31 && (← execute pressure (ManagedString.toByteArray source)).1 = Arena.exhausted &&
        (← count pressure) = 30) "consuming conversion OOM lost unrelated objects or leaked input"
    else if mode = 1 then
      must ((← count pressure) = 31 && (← execute pressure (ManagedString.some source)).1 = Arena.exhausted &&
        (← count pressure) = 30) "Option OOM did not reclaim consumed child"
    else
      must ((← count pressure) = 31 && (← execute pressure (ManagedString.fromByteArray source)).1 = Arena.exhausted &&
        (← count pressure) = 30) "String OOM did not reclaim consumed bytes"
    for box in boxes do must ((← execute pressure (Arena.release box)).1 = 0) "unrelated object lost at OOM"
    must ((← count pressure) = 0 && (← execute pressure Arena.destroy).1 = 0) "OOM page cleanup"
  IO.println s!"MANAGED_STRING_RUNTIME:PASS UTF8={valid.size+invalid.size}, real String/Option graph allocation, alias-safe append, typed projection, retain/release, NUL/scalar counts, literal31-slot OOM and cancellation; host model only"
#eval check
end ManagedStringModelFixture
