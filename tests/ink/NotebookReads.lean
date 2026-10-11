import Lemma.Applications.Notebook
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only literal IPC fixture. It executes the production exact-record
reader against two independently constructed service replies. It models neither
the CPU nor disk durability. The short reply is valid IPC/Store framing and must
still fail before the reader copies any of it to its destination. -/
namespace NotebookReadsFixture
open Lemma.Core0.Memory

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  short : Bool := false
  request : UInt64 := 0
  calls : Nat := 0

def read (s : State) (address : UInt64) : UInt64 := s.words.getD address 0
def write (s : State) (address value : UInt64) : State :=
  { s with words := s.words.insert address value }

def literalReply (s : State) (pointer : UInt64) : State := Id.run do
  let count := if s.short then (127 : UInt64) else 128
  let mut result := s
  -- Literal v1 kernel-stamped IPC header, followed by Store read response.
  for (offset, value) in #[(0,0x31504349414d454c), (8,3), (16,2),
      (24,s.request), (32,0), (40,64 + count), (48,0), (56,0),
      (64,0x31525453414d454c), (72,1), (80,5), (88,1), (96,1),
      (104,9), (112,0), (120,count)] do
    result := write result (pointer + offset) value
  for i in [:16] do
    result := write result (pointer + 128 + i.toUInt64 * 8) 0x4242424242424242
  return result

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status, value)
  | .bind first next =>
    let (status, value) ← execute state first
    execute state (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then throw <| IO.userError "fixture fold budget"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        let result ← execute state (step i.toUInt32 count value c0 c1 c2 c3)
        status := result.1
        value := result.2
    execute state (next status value)
  | .platform op a b c _ e _ next =>
    match op with
    | .virtualRead64 => execute state (next 0 (read (← state.get) a))
    | .virtualWrite64 =>
      state.modify fun s => write s a b
      execute state (next 0 0)
    | .virtualRead8 =>
      execute state (next 0 ((read (← state.get) (a - a % 8) >>> (a % 8 * 8)) &&& 255))
    | .virtualWrite8 =>
      state.modify fun s =>
        let shift := a % 8 * 8
        write s (a - a % 8) ((read s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) |||
          ((b &&& 255) <<< shift))
      execute state (next 0 0)
    | .syscall =>
      if a = 22 then
        if read (← state.get) (c + 16) ≠ 5 then throw <| IO.userError "fixture expected read request"
        state.modify fun s => { s with request := e, calls := s.calls + 1 }
        execute state (next 0 7)
      else if a = 23 then
        state.modify fun s => literalReply s c
        execute state (next 0 (if (← state.get).short then 255 else 256))
      else throw <| IO.userError "unexpected fixture syscall"
    | _ => throw <| IO.userError "unexpected fixture primitive"
  | _ => throw <| IO.userError "unexpected fixture Action"

def check (short : Bool) : IO Unit := do
  let mut initial : State := { short }
  initial := write initial 0x20810 99
  initial := write initial 0x20848 1
  for i in [:16] do
    initial := write initial (0x40000 + i.toUInt64 * 8) 0xaaaaaaaaaaaaaaaa
  let state ← IO.mkRef initial
  let (status, count) ← execute state (Lemma.Applications.Notebook.readObject 1 0x40000 128)
  if short then
    if status ≠ 234 then throw <| IO.userError s!"short fixed record accepted: {status}"
    for i in [:16] do
      if read (← state.get) (0x40000 + i.toUInt64 * 8) ≠ 0xaaaaaaaaaaaaaaaa then
        throw <| IO.userError "short fixed record partially copied"
  else
    if status ≠ 0 || count ≠ 128 then throw <| IO.userError "literal exact record rejected"
    for i in [:16] do
      if read (← state.get) (0x40000 + i.toUInt64 * 8) ≠ 0x4242424242424242 then
        throw <| IO.userError "literal exact record copy mismatch"
  if (← state.get).calls ≠ 1 then throw <| IO.userError "unexpected request count"

end NotebookReadsFixture
open Lean Elab Command
run_cmd do
  liftIO <| NotebookReadsFixture.check false
  liftIO <| NotebookReadsFixture.check true
  logInfo "NOTEBOOK_FIXED_READ:PASS exact128 copied; valid short127 rejected without destination writes"
