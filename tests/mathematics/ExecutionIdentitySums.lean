import Lemma.Documents.Mathematics
import Lemma.Services.Arithmetic.ClientV3
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Independent finite-RAM Actions qualify additive codec/wire admission.
Genuine ordinary sums and isolated RV64 persistence are separate checks. -/
namespace ExecutionIdentitySumsFixture
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
  require ((← execute state (Mathematics.createCurrent buffer 1 1)).1 = 0) "legacy v3 create"
  require ((← execute state (Mathematics.put buffer 56 5)).1 = 0) "typed numerator"
  require ((← execute state (Mathematics.put buffer 64 6)).1 = 0) "typed denominator"
  require ((← execute state (Mathematics.completeExecution buffer 1 1 1 30 8)).1 = 0) "legacy known publication"
  let legacy ← state.get
  require ((← execute state (Mathematics.upgradeSums buffer)) = (0,1)) "v3 migration"
  let migrated ← state.get
  for i in [:312] do
    unless i = 1 || i = 233 do
      require (value migrated (buffer+i.toUInt64*8) = value legacy (buffer+i.toUInt64*8)) "migration changed old known/history/event bytes"
  require ((← execute state (Mathematics.validateSums buffer 1 1)).1 = 0) "legacy identity rejected after migration"
  require ((← execute state (Mathematics.validate buffer 1 1)).1 = 234) "old parser silently expanded v3 authority"
  require ((← execute state (Mathematics.revise buffer)).1 = 0) "edit migration revision"
  for i in [:8] do require (value (← state.get) (buffer+1920+i.toUInt64*8) = 0) "edit retained current applicability"
  for i in [:8] do require (value (← state.get) (buffer+1984+i.toUInt64*8) = value migrated (buffer+1984+i.toUInt64*8)) "edit erased old immutable history"
  require ((← execute state (Mathematics.completeExecutionSums buffer 2 1 1 31 8)) = (0,1)) "new sums publication"
  let known ← state.get
  require ((← execute state (Mathematics.validateSums buffer 1 1)).1 = 0) "mixed exact old/new identities rejected"
  require ([0,8,16,24,32,40,48,56].map (value known ∘ (buffer+1920+·)) =
    [31,0x0003000100000001,0x0003000000000001,0x0001000100000001,0x000100000000001f,8,0,3]) "new origin/version tuple differs"
  require (value known (buffer+1984+56) = 2) "migration relabeled old implementation"
  for offset in [1864,1928,1936,1944,1952,1976,2048+8,2048+56] do
    state.set {known with words := known.words.insert (buffer+offset) (value known (buffer+offset)+1)}
    require ((← execute state (Mathematics.validateSums buffer 1 1)).1 = 234) "malformed mixed execution authority admitted"
  state.set known
  require ((← execute state (Mathematics.copyCurrent buffer 0x32a000)) = (0,2496)) "v4 full transaction copy"
  for i in [:312] do require (value (← state.get) (0x32a000+i.toUInt64*8) = value known (buffer+i.toUInt64*8)) "copy omitted evidence history"
  let outgoing : UInt64 := 0x32b000
  let incoming : UInt64 := 0x32b100
  require ((← execute state (Lemma.Services.Arithmetic.ProtocolV3.request outgoing 1 1 2 1 5 6 0 0 0 8 9)).1 = 0) "protocol3 request"
  for (offset,v) in [(0,0x31504349414d454c),(8,3),(16,3),(24,9),(32,0),(40,112),(48,0),(56,0)] do
    require ((← execute state (Memory.write64 (incoming+offset) v)).1 = 0) "kernel reply envelope"
  require ((← execute state (Lemma.Services.Arithmetic.ProtocolV3.reply (incoming+64) 1 1 2 1 1 8 9)).1 = 0) "protocol3 reply"
  let reply ← state.get
  require ((← execute state (Lemma.Services.Arithmetic.ClientV3.pollCall 77 incoming outgoing 9)) = (0,1)) "new matching reply rejected"
  for (offset,v) in [(8,2),(80,0x0002000100000001),(88,0x0002000000000001),(96,0x0001000000000001),(72,8),(40,1)] do
    require (value reply (incoming+64+offset) ≠ v) "wire mutation was unchanged"
    state.set {reply with words := reply.words.insert (incoming+64+offset) v}
    require ((← execute state (Lemma.Services.Arithmetic.ClientV3.pollCall 77 incoming outgoing 9)).1 = 101) "old/version/stale request gained sums authority"
  IO.println "EXECUTION_SUMS_IDENTITY:PASS strict v3/v4 migration, old/new history, edited applicability, exact reply admission"
end ExecutionIdentitySumsFixture
run_cmd do Lean.Elab.Command.liftTermElabM ExecutionIdentitySumsFixture.check
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``Lemma.Documents.Mathematics.createSums, ``Lemma.Documents.Mathematics.validateSums,
        ``Lemma.Documents.Mathematics.completeExecutionSums, ``Lemma.Documents.Mathematics.copyCurrent,
        ``Lemma.Services.Arithmetic.ClientV3.beginCall, ``Lemma.Services.Arithmetic.ClientV3.pollCall] with
    | .ok suite => pure suite
    | .error error => throwError error.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => logInfo "EXECUTION_SUMS_IDENTITY_LOWERING:PASS genuine codec Actions->checked LLVM; isolated execution separate"
  | .error error => throwError error
