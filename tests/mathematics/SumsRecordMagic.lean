import Lemma.Documents.Mathematics
import Lemma.Services.Arithmetic.ClientV3
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Independent finite-RAM Actions qualify additive codec/wire admission.
Genuine ordinary sums and isolated RV64 persistence are separate checks. -/
namespace SumsRecordMagicFixture
open Lean Elab Command Lemma.Core0 Lemma.Compiler Lemma.Core0.Memory
open Lemma.Documents Lemma.Mathematics Lemma.User
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  polls : UInt64 := 0
  packetBytes : UInt64 := 176
partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status,value)
  | .bind first next => let (status,value) ← execute state first; execute state (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    unless count.toNat ≤ budget do throw <| IO.userError "fold exceeds explicit bound"
    let mut result := (0,initial)
    for i in [:count.toNat] do
      if result.1 = 0 then result ← execute state (step i.toUInt32 count result.2 c0 c1 c2 c3)
    execute state (next result.1 result.2)
  | .platform operation a b c d e f next =>
    let current ← state.get
    if operation = .virtualRead64 then
      unless a % 8 = 0 && 0x329000 ≤ a && a < 0x32c000 do throw <| IO.userError "read escapes owned record/IPC pages"
      execute state (next 0 (current.words.getD a 0))
    else if operation = .virtualWrite64 then
      unless a % 8 = 0 && 0x329000 ≤ a && a < 0x32c000 do throw <| IO.userError "write escapes owned record/IPC pages"
      state.set {current with words := current.words.insert a b}
      execute state (next 0 0)
    else if operation = .syscall then
      unless a = 67 && b = 77 && c = 0x32b100 && d = 256 && e = 0 && f = 0 do throw <| IO.userError "unexpected syscall/poll arguments"
      state.set {current with polls := current.polls+1}
      execute state (next 0 current.packetBytes)
    else throw <| IO.userError "unexpected effect"
  | _ => throw <| IO.userError "unexpected Action"
def require (value : Bool) (message : String) : IO Unit := unless value do throw <| IO.userError message
def value (state : State) (address : UInt64) : UInt64 := state.words.getD address 0
def check : IO Unit := do
  let state ← IO.mkRef ({} : State)
  let buffer : UInt64 := 0x329000
  require ((← execute state (Mathematics.createSums buffer 1 1)).1 = 0) "create format4"
  require ((← execute state (Mathematics.validateSums buffer 1 1)).1 = 0) "valid format4 rejected"
  let before ← state.get
  state.set {before with words := before.words.insert buffer 0}
  require ((← execute state (Mathematics.validateSums buffer 1 1)).1 = 234) "format4 accepted corrupt record magic"
  for i in [:312] do
    require (value (← state.get) (buffer+i.toUInt64*8) =
      (if i = 0 then 0 else value before (buffer+i.toUInt64*8))) "validation mutated corrupt record"
  IO.println "SUMS_RECORD_MAGIC:PASS exact format4 record magic admission without mutation"
end SumsRecordMagicFixture
run_cmd do Lean.Elab.Command.liftTermElabM SumsRecordMagicFixture.check
