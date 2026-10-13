import Lemma.Documents.Mathematics
import Lemma.Services.Arithmetic.ClientV2
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Independent host RAM Actions qualify codec/admission only. Actual isolated
RV64 request, barrier and cold persistence require the connected guest run. -/
namespace ExecutionIdentityFixture
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
  require ((← execute state (Mathematics.create buffer 1 1)).1 = 0) "v2 creation"
  require ((← execute state (Mathematics.put buffer 56 5)).1 = 0) "typed numerator"
  require ((← execute state (Mathematics.put buffer 64 6)).1 = 0) "typed denominator"
  require ((← execute state (Mathematics.completeSubmit buffer 1 1 1)).1 = 0) "prior admitted result"
  require ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "original v2 exact validation"
  let legacy ← state.get
  require ((← execute state (Mathematics.upgradeCurrent buffer)) = (0,1)) "v2 migration"
  let migrated ← state.get
  for i in [:232] do
    unless i = 1 do require (value migrated (buffer+i.toUInt64*8) = value legacy (buffer+i.toUInt64*8)) "migration changed old answer/evidence/history/events"
  for i in [:72] do require (value migrated (buffer+1920+i.toUInt64*8) = 0) "migration invented known execution identity"
  require ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "unknown legacy execution rejected"
  require ((← execute state (Mathematics.revise buffer)).1 = 0) "revision"
  require ((← execute state (Mathematics.completeExecution buffer 2 1 1 30 8)) = (0,1)) "new execution publication"
  let known ← state.get
  require ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "new known execution rejected"
  for offset in [1920,1984+64] do
    let slot := buffer+offset
    require ([0,8,16,24,32,40,48,56].map (value known ∘ (slot+·)) =
      [30,0x0002000100000001,0x0002000000000001,0x0001000000000001,0x000100000000001f,8,0,2]) "exact execution/contract/request/status metadata differs"
  for offset in [1856,1864,1872,1920,1928,1936,1944,1952,1960,1968,1976,2048,2056,2064,2072,2080,2088,2096,2104] do
    state.set {known with words := known.words.insert (buffer+offset) (value known (buffer+offset)+1)}
    require ((← execute state (Mathematics.validate buffer 1 1)).1 = 234) "malformed execution identity accepted"
  state.set known
  for (revision,goal,request,budget) in [(1,1,31,8),(2,2,31,8),(2,1,0,8),(2,1,31,0)] do
    require ((← execute state (Mathematics.completeExecution buffer revision goal 1 request budget)).1 ≠ 0) "stale/mismatched identity publication accepted"
    require ((← state.get).words.toList = known.words.toList) "rejected identity changed evidence bytes"
  require ((← execute state (Mathematics.copyCurrent buffer 0x32a000)) = (0,2496)) "full execution transaction copy"
  for i in [:312] do require (value (← state.get) (0x32a000+i.toUInt64*8) = value known (buffer+i.toUInt64*8)) "copy omitted execution identity/history"
  require ((← execute state (Mathematics.revise buffer)).1 = 0) "edited result revision"
  for i in [:8] do require (value (← state.get) (buffer+1920+i.toUInt64*8) = 0) "edit retained applicable execution evidence"
  for i in [:64] do require (value (← state.get) (buffer+1984+i.toUInt64*8) = value known (buffer+1984+i.toUInt64*8)) "edit erased immutable execution history"
  require ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "edited unknown applicability rejected"
  -- Independent exact wire layout and copied-envelope checks.
  let outgoing : UInt64 := 0x32b000
  let incoming : UInt64 := 0x32b100
  require ((← execute state (Lemma.Services.Arithmetic.ProtocolV2.request outgoing 1 1 7 1 5 6 0 0 0 8 9)).1 = 0) "actual protocol2 request"
  for (offset,v) in [(0,0x31504349414d454c),(8,3),(16,3),(24,9),(32,0),(40,112),(48,0),(56,0)] do
    require ((← execute state (Memory.write64 (incoming+offset) v)).1 = 0) "copied kernel envelope"
  require ((← execute state (Lemma.Services.Arithmetic.ProtocolV2.reply (incoming+64) 1 1 7 1 1 8 9)).1 = 0) "actual protocol2 reply"
  let reply ← state.get
  require ((← execute state (Lemma.Services.Arithmetic.ClientV2.pollCall 77 incoming outgoing 9)) = (0,1)) "matching protocol2 reply rejected"
  for offset in [0,8,16,24,32,40,48,64,72,80,88,96,104] do
    state.set {reply with words := reply.words.insert (incoming+64+offset) (value reply (incoming+64+offset)+1)}
    require ((← execute state (Lemma.Services.Arithmetic.ClientV2.pollCall 77 incoming outgoing 9)).1 = 101) "mismatched identity/request/revision accepted"
  state.set {reply with packetBytes := 144}
  require ((← execute state (Lemma.Services.Arithmetic.ClientV2.pollCall 77 incoming outgoing 9)).1 = 101) "legacy-length reply gained protocol2 authority"
  IO.println "EXECUTION_IDENTITY:PASS unknown migration, exact contracts, immutable history, edited applicability, full copy and copied reply admission"
end ExecutionIdentityFixture
run_cmd do Lean.Elab.Command.liftTermElabM ExecutionIdentityFixture.check
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``Lemma.Documents.Mathematics.createCurrent, ``Lemma.Documents.Mathematics.validate,
        ``Lemma.Documents.Mathematics.completeExecution, ``Lemma.Documents.Mathematics.copyCurrent,
        ``Lemma.Services.Arithmetic.ClientV2.beginCall, ``Lemma.Services.Arithmetic.ClientV2.pollCall] with
    | .ok suite => pure suite
    | .error error => throwError error.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => logInfo "EXECUTION_IDENTITY_LOWERING:PASS genuine Lean scalar checked LLVM; actual RV64 and durable cold recovery separate"
  | .error error => throwError error
