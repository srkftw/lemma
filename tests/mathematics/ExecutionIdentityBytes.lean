import Lemma.Documents.MathematicsBytes
import Lemma.Services.Arithmetic.ClientV4
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Independent finite-RAM Actions qualify codec and wire admission. Ordinary
ByteArray lowering, isolated RV64 lifetime and durable recovery are separate. -/
namespace ExecutionIdentityBytesFixture
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
  require ((← execute state (Mathematics.createCurrent buffer 1 1)).1 = 0) "old create"
  require ((← execute state (Mathematics.put buffer 56 5)).1 = 0) "numerator"
  require ((← execute state (Mathematics.put buffer 64 6)).1 = 0) "denominator"
  require ((← execute state (Mathematics.completeExecution buffer 1 1 1 30 8)).1 = 0) "old known origin2"
  require ((← execute state (Mathematics.upgradeSums buffer)).1 = 0) "old sums migration"
  require ((← execute state (Mathematics.revise buffer)).1 = 0) "old edit"
  require ((← execute state (Mathematics.completeExecutionSums buffer 2 1 1 31 8)).1 = 0) "old known origin3"
  let old ← state.get
  require ((← execute state (MathematicsBytes.upgrade buffer)) = (0,1)) "document5 migration"
  let migrated ← state.get
  for i in [:312] do
    unless i = 1 || i = 233 do
      require (value migrated (buffer+i.toUInt64*8) = value old (buffer+i.toUInt64*8)) "migration changed old known/history/events"
  require ((← execute state (MathematicsBytes.validate buffer 1 1)).1 = 0) "mixed old registries rejected"
  require ((← execute state (Mathematics.validateSums buffer 1 1)).1 = 234) "old sums parser gained format5"
  state.set {migrated with words := migrated.words.insert buffer 0}
  require ((← execute state (MathematicsBytes.validate buffer 1 1)).1 = 234) "format5 accepted corrupt magic"
  state.set migrated
  require ((← execute state (Mathematics.revise buffer)).1 = 0) "new edit"
  require ((← execute state (MathematicsBytes.completeExecution buffer 3 1 1 32 8)) = (0,1)) "new bytes publication"
  let known ← state.get
  require ((← execute state (MathematicsBytes.validate buffer 1 1)).1 = 0) "mixed old/new identities rejected"
  require ([0,8,16,24,32,40,48,56].map (value known ∘ (buffer+1920+·)) =
    [32,0x0004000100000001,0x0004000000000001,0x0001000200000001,0x000200000000001f,8,0,4]) "wrong bytes identity tuple"
  require (value known (buffer+1984+56) = 2 && value known (buffer+2048+56) = 3) "new registry relabeled old attempts"
  for offset in [0,1864,1928,1936,1944,1952,1976,2112+8,2112+56] do
    state.set {known with words := known.words.insert (buffer+offset) (value known (buffer+offset)+1)}
    require ((← execute state (MathematicsBytes.validate buffer 1 1)).1 = 234) "corrupt execution authority accepted"
  state.set known
  require ((← execute state (MathematicsBytes.completeExecution buffer 2 1 1 33 8)).1 = 234) "stale revision accepted"
  for i in [:312] do require (value (← state.get) (buffer+i.toUInt64*8) = value known (buffer+i.toUInt64*8)) "stale result mutated bytes"
  require ((← execute state (Mathematics.copyCurrent buffer 0x32a000)) = (0,2496)) "complete transaction copy"
  for i in [:312] do require (value (← state.get) (0x32a000+i.toUInt64*8) = value known (buffer+i.toUInt64*8)) "copy omitted history"
  let outgoing : UInt64 := 0x32b000
  let incoming : UInt64 := 0x32b100
  require ((← execute state (Lemma.Services.Arithmetic.ProtocolV4.request outgoing 1 1 3 1 5 6 0 0 0 8 9)).1 = 0) "protocol4 request"
  for (offset,v) in [(0,0x31504349414d454c),(8,3),(16,3),(24,9),(32,0),(40,112),(48,0),(56,0)] do
    require ((← execute state (Memory.write64 (incoming+offset) v)).1 = 0) "kernel reply envelope"
  require ((← execute state (Lemma.Services.Arithmetic.ProtocolV4.reply (incoming+64) 1 1 3 1 1 8 9)).1 = 0) "protocol4 reply"
  let reply ← state.get
  require ((← execute state (Lemma.Services.Arithmetic.ClientV4.pollCall 77 incoming outgoing 9)) = (0,1)) "new matching reply rejected"
  for (offset,v) in [(8,3),(80,0x0003000100000001),(88,0x0003000000000001),(96,0x0001000100000001),(104,0x000100000000001f),(72,8),(40,1)] do
    require (value reply (incoming+64+offset) ≠ v) "wire mutation unchanged"
    state.set {reply with words := reply.words.insert (incoming+64+offset) v}
    require ((← execute state (Lemma.Services.Arithmetic.ClientV4.pollCall 77 incoming outgoing 9)).1 = 101) "old/version/stale result gained bytes authority"
  IO.println "EXECUTION_BYTES_IDENTITY:PASS strict format5 migration, old/new history, edited applicability, exact reply admission and fullcopy"
end ExecutionIdentityBytesFixture
run_cmd do Lean.Elab.Command.liftTermElabM ExecutionIdentityBytesFixture.check
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``Lemma.Documents.MathematicsBytes.create, ``Lemma.Documents.MathematicsBytes.validate,
        ``Lemma.Documents.MathematicsBytes.completeExecution, ``Lemma.Documents.Mathematics.copyCurrent,
        ``Lemma.Services.Arithmetic.ClientV4.beginCall, ``Lemma.Services.Arithmetic.ClientV4.pollCall] with
    | .ok suite => pure suite
    | .error error => throwError error.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => logInfo "EXECUTION_BYTES_IDENTITY_LOWERING:PASS genuine codec Actions->checked LLVM; production selection/execution separate"
  | .error error => throwError error
