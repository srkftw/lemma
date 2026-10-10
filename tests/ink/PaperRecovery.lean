import Lemma.Applications.Notebook
import Lemma.Platform.LemmaSim.DeviceService
import Lean.Elab.Command
import Std.Data.HashMap

/-! Independent literal Action observations, not a replacement controller or
RV64 acceptance. The real v1 model owns reset/visible/IRQ transitions elsewhere.
This fixture checks bounded guest restoration and interrupt masking/reenabling. -/
namespace PaperRecoveryFixture
open Lemma.Core0.Memory

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  status : UInt64 := 8
  uploads : Array (UInt64 × UInt64) := #[]
  refreshes : Nat := 0
  enable : UInt64 := 0x3002
  ack : Nat := 0

def read (s : State) (address : UInt64) : UInt64 :=
  if 0x110000 ≤ address && address < 0x124000 then 0x5a5a5a5a5a5a5a5a
  else s.words.getD address 0
def write (s : State) (address value : UInt64) : State := {s with words := s.words.insert address value}
def byte (s : State) (address : UInt64) : UInt64 :=
  (read s (address - address % 8) >>> (address % 8 * 8)) &&& 255

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status,value)
  | .bind first next =>
    let (status,value) ← execute state first
    execute state (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then throw <| IO.userError "recovery fold exceeds bound"
    let mut result := ((0 : UInt8),initial)
    for i in [:count.toNat] do
      if result.1 = 0 then result ← execute state (step i.toUInt32 count result.2 c0 c1 c2 c3)
    execute state (next result.1 result.2)
  | .platform op a b c d e _ next =>
    match op with
    | .virtualRead64 | .physicalRead64 => execute state (next 0 (read (← state.get) a))
    | .virtualRead8 => execute state (next 0 (byte (← state.get) a))
    | .virtualWrite64 | .physicalWrite64 =>
      state.modify fun s => write s a b
      execute state (next 0 0)
    | .virtualWrite8 =>
      state.modify fun s =>
        let shift := a % 8 * 8
        write s (a - a % 8) ((read s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((b &&& 255) <<< shift))
      execute state (next 0 0)
    | .deviceRead32 =>
      if a ≠ 0x0c002080 then throw <| IO.userError "unexpected PLIC read"
      execute state (next 0 (← state.get).enable)
    | .deviceWrite32 =>
      if a ≠ 0x0c002080 then throw <| IO.userError "unexpected PLIC write"
      state.modify fun s => {s with enable := b}
      execute state (next 0 0)
    | .deviceRead64 =>
      if a = 0x10010010 then execute state (next 0 (← state.get).status)
      else if a = 0x100100a0 then execute state (next 0 7)
      else throw <| IO.userError "unexpected paper MMIO read"
    | .deviceWrite64 =>
      if a ≠ 0x100100a8 || b ≠ 7 then throw <| IO.userError "unexpected paper ACK"
      state.modify fun s => {s with status := s.status &&& ~~~(6 : UInt64), ack := s.ack + 1}
      execute state (next 0 0)
    | .syscall =>
      if a ≠ 64 || b ≠ 1 then throw <| IO.userError "unexpected recovery syscall"
      if c = 4 then execute state (next 0 (← state.get).status)
      else if c = 3 then execute state (next 0 7)
      else if c = 1 then
        let s ← state.get
        let x := read s d; let y := read s (d + 8)
        if d ≠ 0x20200 || e ≠ 0x20500 || read s (d+16) ≠ 32 || read s (d+24) ≠ 32 then
          throw <| IO.userError "unexpected restored tile metadata"
        for i in [:512] do
          if byte s (e + i.toUInt64) ≠ 0x5a then throw <| IO.userError "restore pixels were not copied from owned framebuffer"
        state.modify fun s => {s with uploads := s.uploads.push (x,y)}
        execute state (next 0 512)
      else if c = 2 then
        let s ← state.get
        if d ≠ 0x20200 || read s d ≠ 0 || read s (d+8) ≠ 0 || read s (d+16) ≠ 512 ||
           read s (d+24) ≠ 320 || read s (d+32) ≠ 2 || read s (d+40) ≠ 8 then
          throw <| IO.userError "recovery did not name full quality rectangle/new sequence"
        if s.uploads.size ≠ 160 then throw <| IO.userError "recovery published before all framebuffer tiles"
        state.modify fun s => {s with status := 9, refreshes := s.refreshes + 1}
        execute state (next 0 8)
      else throw <| IO.userError "unexpected recovery surface operation"
    | _ => throw <| IO.userError "unexpected recovery primitive"
  | _ => throw <| IO.userError "unexpected recovery Action"

def check : IO Unit := do
  let mut initial : State := {}
  for (offset,value) in #[(0,1),(32,512),(40,320),(336,65535),(344,65535),(448,128),(456,9),(464,7),(472,16)] do
    initial := write initial (0x20800 + offset) value
  let state ← IO.mkRef initial
  -- There is no dirty rectangle after an accepted request. Sticky8 must still
  -- start recovery; every call uploads at most four tiles and preserves IPC448.
  for batch in [:40] do
    let before := (← state.get).uploads.size
    if (← execute state Lemma.Applications.Notebook.pumpRefresh).1 ≠ 0 then throw <| IO.userError "recovery progress failed"
    let after ← state.get
    if after.uploads.size - before > 4 || read after 0x209c0 ≠ 128 then throw <| IO.userError "unbounded upload or overwritten IPC chunk count"
    if batch < 39 && after.refreshes ≠ 0 then throw <| IO.userError "premature recovery refresh"
  let after ← state.get
  for i in [:160] do
    if after.uploads[i]! ≠ ((i % 16).toUInt64 * 32,(i / 16).toUInt64 * 32) then throw <| IO.userError "restore tile sequence differs"
  if after.refreshes ≠ 1 || read after 0x209e0 ≠ 2 then throw <| IO.userError "missing accepted recovery phase"
  if (← execute state Lemma.Applications.Notebook.pumpRefresh).1 ≠ 0 || (← state.get).uploads.size ≠ 160 then
    throw <| IO.userError "Busy recovery uploaded or resubmitted"
  -- Model completion clears Unknown8. The subsequent status observation clears
  -- the active polling phase so input can return to its blocking idle path.
  state.modify fun s => {s with status := 2}
  if (← execute state Lemma.Applications.Notebook.pumpRefresh).1 ≠ 0 || read (← state.get) 0x209e0 ≠ 0 then
    throw <| IO.userError "completed recovery stayed active"
  let irq ← IO.mkRef ({status := 8} : State)
  if (← execute irq (Lemma.Platform.LemmaSim.DeviceService.notification 12)).1 ≠ 0 then throw <| IO.userError "IRQ notification failed"
  if (← irq.get).enable ≠ 0x2002 || read (← irq.get) 0x80400c58 ≠ 1 then throw <| IO.userError "sticky IRQ was not masked"
  if (← execute irq Lemma.Platform.LemmaSim.DeviceService.deferred).1 ≠ 0 || (← irq.get).enable ≠ 0x2002 || (← irq.get).ack ≠ 1 then
    throw <| IO.userError "sticky Unknown IRQ was reenabled or not acknowledged"
  irq.modify fun s => {s with status := 2}
  if (← execute irq (Lemma.Platform.LemmaSim.DeviceService.surfaceStatus 0 0)) ≠ (0,2) || (← irq.get).enable ≠ 0x3002 then
    throw <| IO.userError "completed recovery failed to rearm actual PLIC source"
  if (← execute irq (Lemma.Platform.LemmaSim.DeviceService.notification 12)).1 ≠ 0 ||
     (← execute irq Lemma.Platform.LemmaSim.DeviceService.deferred).1 ≠ 0 ||
     (← irq.get).status ≠ 0 || (← irq.get).enable ≠ 0x3002 || (← irq.get).ack ≠ 2 then
    throw <| IO.userError "actual completion transport did not ACK and return to quiescent source"
end PaperRecoveryFixture
open Lean Elab Command
run_cmd do
  liftIO PaperRecoveryFixture.check
  logInfo "PAPER_RECOVERY:PASS empty-dirty interruption; four-tile batches; fullquality; Busy; IPC448 intact; stickyIRQ mask/rearm; Action boundary only"
