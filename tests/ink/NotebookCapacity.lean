import Lemma.Applications.Notebook
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only bounded execution of the actual admission/failure Actions.
Literal page counts are independent inputs. The fixture asserts read-only
preflight, unchanged indexed/root bytes, no document/block syscall on failure,
and the real Failed diagnostic/status-render path. It is not CPU or durability
acceptance and does not reconstruct a document for a running guest. -/
namespace NotebookCapacityFixture
open Lemma.Core0.Memory
open Lemma.Applications

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  writes : Nat := 0
  console : Array String := #[]
  uploads : Nat := 0

def read (s : State) (address : UInt64) : UInt64 := s.words.getD address 0
def write (s : State) (address value : UInt64) : State :=
  { s with words := s.words.insert address value }
def byte (s : State) (address : UInt64) : UInt64 :=
  (read s (address - address % 8) >>> (address % 8 * 8)) &&& 255

def packet (s : State) (pointer length : UInt64) : String :=
  String.ofList <| (List.range length.toNat).map fun i =>
    Char.ofNat (byte s (pointer + i.toUInt64)).toNat

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
  | .platform op a b c d e _ next =>
    match op with
    | .virtualRead64 => execute state (next 0 (read (← state.get) a))
    | .virtualRead8 => execute state (next 0 (byte (← state.get) a))
    | .virtualWrite64 =>
      state.modify fun s => { write s a b with writes := s.writes + 1 }
      execute state (next 0 0)
    | .virtualWrite8 =>
      state.modify fun s =>
        let shift := a % 8 * 8
        { write s (a - a % 8) ((read s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) |||
            ((b &&& 255) <<< shift)) with writes := s.writes + 1 }
      execute state (next 0 0)
    | .syscall =>
      if a = 15 then
        if b ≠ 4 || c ≠ 0 || d ≠ 0x20200 || e ≠ 88 then
          throw <| IO.userError "unexpected failed-state console transport"
        state.modify fun s => { s with console := s.console.push (packet s d e) }
        execute state (next 0 88)
      else if a = 64 then
        if b ≠ 1 || c ≠ 1 || d ≠ 0x20200 || e ≠ 0x20500 then
          throw <| IO.userError "unexpected failed-state tile transport"
        state.modify fun s => { s with uploads := s.uploads + 1 }
        execute state (next 0 0)
      else throw <| IO.userError s!"failure path attempted syscall {a}"
    | _ => throw <| IO.userError "unexpected fixture primitive"
  | _ => throw <| IO.userError "unexpected fixture Action"

def initial (count edits cursor : UInt64) : State := Id.run do
  let mut s : State := {}
  for (offset, value) in #[(0,1),(24,4),(32,1650),(40,2200),(72,1),(80,1),(88,16),
      (104,13),(112,77),(128,147),(136,1),(144,0x300000),(160,3),(224,65537),
      (272,512),(296,996),(304,1000),(336,65535),(344,65535),(408,1),(448,128)] do
    s := write s (0x20800 + offset) value
  s := write s (0x310000 + 32) count
  s := write s (0x310000 + 40) edits
  s := write s (0x310000 + 48) cursor
  for i in [:16] do
    s := write s (0x310080 + i.toUInt64 * 8) 0xabcdef0012345678
    s := write s (0x313080 + i.toUInt64 * 8) 0x7777777777777777
    s := write s (0x320000 + i.toUInt64 * 8) 0x123456789abcdef0
    s := write s (0x300000 + i.toUInt64 * 8) 0xa5a5a5a5a5a5a5a5
  return s

def admission : IO Unit := do
  -- A new operation may replace a redo suffix. A continuation consumes no new
  -- edit, while every chunk needs one remaining entry.
  for (count, edits, cursor, starting, expected) in
      #[(511,512,511,1,0), (511,512,512,1,235), (512,0,0,1,235),
        (512,0,0,0,235), (511,512,512,0,0), (513,0,0,0,234),
        (511,512,513,1,234), (511,513,0,1,234), (0,0,0,2,234)] do
    let state ← IO.mkRef (initial count edits cursor)
    let result ← execute state (Notebook.preflightChunk 0x310000 starting)
    if result.1.toUInt64 ≠ expected || (← state.get).writes ≠ 0 then
      throw <| IO.userError "page admission changed bytes or returned an incorrect literal boundary"
  let state ← IO.mkRef (initial 512 512 512)
  if (← execute state (Notebook.preflightEdit 0x310000)).1 ≠ 235 || (← state.get).writes ≠ 0 then
    throw <| IO.userError "full edit preflight changed visibility/index bytes"

def failure : IO Unit := do
  let before := initial 512 512 512
  let state ← IO.mkRef before
  if (← execute state (Notebook.failWriting 235)).1 ≠ 0 then
    throw <| IO.userError "declared full limit terminated the notebook Action"
  let after ← state.get
  for offset in #[104,112,144,160,296,304,408] do
    if read after (0x20800 + offset) ≠ 0 then throw <| IO.userError "unsaved tail stayed active"
  if read after 0x20888 ≠ 2 || read after 0x209a8 ≠ 235 || read after 0x209b0 ≠ 1 ||
      read after 0x20880 ≠ 147 then
    throw <| IO.userError "Failed/resynchronization state or prior acknowledged sequence differs"
  for base in #[0x310000,0x310080,0x313080,0x320000,0x300000] do
    for i in [:16] do
      let address := base + i.toUInt64 * 8
      if read after address ≠ read before address then
        throw <| IO.userError "capacity failure mutated a page/root/raw record"
  let expected := "K1 0000000000000424 00000000000000eb 0000000000000001 0000000000000001 0000000000010001\n"
  if after.console ≠ #[expected] || after.uploads ≠ 0 || read after (0x20800 + 456) ≠ 9 || read after (0x20800 + 448) ≠ 128 then
    throw <| IO.userError "missing actual guest Failed diagnostic or bounded deferred status tile queue"
  for i in [:9] do
    if (read after (0x321000 + i.toUInt64 / 4 * 8) >>> (i.toUInt64 % 4 * 16)) &&& 0xffff ≠ 4 * 52 + i.toUInt64 then
      throw <| IO.userError "Failed status queued an incorrect dirty tile"

end NotebookCapacityFixture
open Lean Elab Command
run_cmd do
  liftIO NotebookCapacityFixture.admission
  liftIO NotebookCapacityFixture.failure
  logInfo "NOTEBOOK_CAPACITY:PASS literal bounds, no partial index mutation/publication, Failed235 and cancelled tail; CPU/durability acceptance separate"
