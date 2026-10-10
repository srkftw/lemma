import Lemma.Applications.Notebook
import Lean.Elab.Command
import Std.Data.HashMap

/-! Literal observations over the production input-drain Action. This fixture
supplies independently serialized controller records and checks retained bytes,
queue read counts, and contact boundaries. CPU/PLIC throughput and persistence
remain actual simulator acceptance, not results of this interpreter. -/
namespace NotebookInputDrainFixture
open Lemma.Core0.Memory

structure Event where
  status : UInt8 := 0
  sequence : UInt64 := 2
  flags : UInt64 := 7
  x : UInt64 := 20000
  y : UInt64 := 40000
  deriving Inhabited

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  events : Array Event := #[]
  consumed : Nat := 0
  polls : Nat := 0

def read (s : State) (address : UInt64) : UInt64 :=
  s.words.getD address (if 0x110000 ≤ address && address < 0x124000 then 0xffffffffffffffff else 0)
def write (s : State) (address value : UInt64) : State := {s with words := s.words.insert address value}
def byte (s : State) (address : UInt64) : UInt64 :=
  (read s (address - address % 8) >>> (address % 8 * 8)) &&& 255

def sample (s : State) (pointer : UInt64) (e : Event) : State := Id.run do
  let mut s := s
  for (offset,value) in #[(0,e.sequence),(8,1000+e.sequence),(16,e.x),(24,e.y),
      (32,2047),(40,e.flags),(48,1),(56,0),(64,1)] do
    s := write s (pointer+offset) value
  return s

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status,value)
  | .bind first next =>
    let (status,value) ← execute state first
    execute state (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then throw <| IO.userError "input fixture exceeded declared fold bound"
    let mut result := ((0 : UInt8),initial)
    for i in [:count.toNat] do
      if result.1 = 0 then result ← execute state (step i.toUInt32 count result.2 c0 c1 c2 c3)
    execute state (next result.1 result.2)
  | .platform op a b c d e _ next =>
    match op with
    | .virtualRead64 => execute state (next 0 (read (← state.get) a))
    | .virtualRead8 => execute state (next 0 (byte (← state.get) a))
    | .virtualWrite64 =>
      state.modify fun s => write s a b
      execute state (next 0 0)
    | .virtualWrite8 =>
      state.modify fun s =>
        let shift := a % 8 * 8
        write s (a-a%8) ((read s (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((b &&& 255) <<< shift))
      execute state (next 0 0)
    | .syscall =>
      if a ≠ 65 || b ≠ 2 || c ≠ 1 || d ≠ 0x20300 || e ≠ 0 then
        throw <| IO.userError "drain attempted blocking input or unrelated service/device syscall"
      let s ← state.get
      if s.consumed = s.events.size then
        state.set {s with polls := s.polls+1}
        execute state (next 174 0)
      else
        let event := s.events[s.consumed]!
        state.set {sample s d event with polls := s.polls+1, consumed := s.consumed+1}
        execute state (next event.status 0)
    | _ => throw <| IO.userError "unexpected input fixture primitive"
  | _ => throw <| IO.userError "unexpected input fixture Action"

def initial (events : Array Event) (count : UInt64 := 0) (active : UInt64 := 13) : State := Id.run do
  let mut s : State := {events}
  -- A store-owned pending buffer stays immutable while working ink is drained.
  for (offset,value) in #[(8,2),(32,512),(40,320),(48,65535),(56,65535),(64,4095),
      (72,1),(80,1),(88,2),(96,14),(104,active),(112,count),(120,0x300000),
      (128,2),(136,1),(144,0x308000),(160,1),(272,256),(288,1),(296,1),
      (304,1001),(336,65535),(344,65535),(408,if active=0 then 0 else 1),(448,128)] do
    s := write s (0x20800+offset) value
  for (offset,value) in #[(0,0x314b4e49414d454c),(8,1),(16,3),(24,1),(32,13),
      (56,256),(64,1),(72,65535),(80,65535),(88,4095),(96,512),(104,320),(112,1)] do
    s := write s (0x300000+offset) value
  for i in [:9] do s := write s (0x308000+i.toUInt64*8) 0xaabbccddeeff1234
  if count ≠ 0 then s := sample s (0x300080+(count-1)*72) {sequence:=1}
  return s

def checkPending (s : State) : IO Unit := do
  for i in [:9] do
    if read s (0x308000+i.toUInt64*8) ≠ 0xaabbccddeeff1234 then
      throw <| IO.userError "queued store-owned raw bytes were overwritten"
  if read s (0x20800+448) ≠ 128 then throw <| IO.userError "input overwrote issued IPC byte count"

def check : IO Unit := do
  let events := (List.range 9).toArray.map fun i => ({sequence:=i.toUInt64+2} : Event)
  let state ← IO.mkRef (initial events)
  if (← execute state (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,8) then
    throw <| IO.userError "eight queued records were not drained in one bounded turn"
  let s ← state.get
  if s.polls ≠ 8 || s.consumed ≠ 8 || read s (0x20800+112) ≠ 8 then
    throw <| IO.userError "drain read beyond eight or failed to retain ordered samples"
  for i in [:8] do
    let expected := sample {} 0 events[i]!
    for word in [:9] do
      if read s (0x300080+i.toUInt64*72+word.toUInt64*8) ≠ read expected (word.toUInt64*8) then
        throw <| IO.userError "retained raw input differs from the literal controller record"
  checkPending s
  if (← execute state (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,1) || (← state.get).polls ≠ 10 then
    throw <| IO.userError "short queue did not stop after one Empty observation"
  let empty ← IO.mkRef (initial #[])
  if (← execute empty (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,0) || (← empty.get).polls ≠ 1 then
    throw <| IO.userError "empty queue was repeatedly polled"
  let full ← IO.mkRef (initial events 384)
  if (← execute full (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,0) || (← full.get).polls ≠ 0 then
    throw <| IO.userError "full immutable chunk fetched another input sample"
  let filling ← IO.mkRef (initial events 383)
  if (← execute filling (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,1) ||
      (← filling.get).polls ≠ 1 || read (← filling.get) (0x20800+112) ≠ 384 then
    throw <| IO.userError "chunk filling did not stop before fetching a further sample"
  checkPending (← filling.get)
  for event in #[({status:=175} : Event), {sequence:=99}] do
    let lost ← IO.mkRef (initial #[event,{sequence:=100}] 1)
    if (← execute lost (Lemma.Applications.Notebook.drainInput 2)).1 ≠ 0 || (← lost.get).polls ≠ 1 ||
        read (← lost.get) (0x20800+104) ≠ 0 || read (← lost.get) (0x20800+112) ≠ 0 ||
        read (← lost.get) (0x20800+432) ≠ 1 then
      throw <| IO.userError "loss/discontinuity crossed into another contact"
    checkPending (← lost.get)
  let release ← IO.mkRef (initial #[{flags:=6},{sequence:=3}] 1)
  if (← execute release (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,1) ||
      (← release.get).polls ≠ 1 || read (← release.get) (0x20800+104) ≠ 0 ||
      read (← release.get) (0x20800+112) ≠ 2 then
    throw <| IO.userError "pen-up did not end the turn and preserve its pending raw tail"
  if (← execute release (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,1) ||
      read (← release.get) (0x20800+112) ≠ 2 || read (← release.get) (0x20800+104) ≠ 0 then
    throw <| IO.userError "new contact joined a completed unsaved stroke"
  let toolbar ← IO.mkRef (initial #[{y:=0},{sequence:=3,flags:=6,y:=0},{sequence:=4}] 0 0)
  if (← execute toolbar (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,1) ||
      (← toolbar.get).polls ≠ 1 || read (← toolbar.get) (0x20800+112) ≠ 0 then
    throw <| IO.userError "toolbar boundary consumed a following page contact"
  if (← execute toolbar (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,1) then
    throw <| IO.userError "toolbar release did not stop the turn"
  if (← execute toolbar (Lemma.Applications.Notebook.drainInput 2)) ≠ (0,1) ||
      read (← toolbar.get) (0x20800+104) ≠ 14 || read (← toolbar.get) (0x20800+112) ≠ 1 ||
      read (← toolbar.get) (0x300000+24) ≠ 1 || read (← toolbar.get) 0x300080 ≠ 4 then
    throw <| IO.userError "fresh page stroke retained toolbar/release input or an old stroke ID"
  checkPending (← toolbar.get)
end NotebookInputDrainFixture
open Lean Elab Command
run_cmd do
  liftIO NotebookInputDrainFixture.check
  logInfo "NOTEBOOK_INPUT_DRAIN:PASS eight/Empty/full384/loss/release/toolbar literal Action boundaries; RV64 throughput separate"
