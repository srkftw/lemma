import Lemma.Services.Arithmetic.Server
import Lemma.Services.Arithmetic.Client
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  -- The formerly scalar server now calls genuine managed records. Legacy
  -- User1 must reject that extension, while its original Client stays legal.
  match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``Lemma.Services.Arithmetic.Server.main] with
  | .error diagnostic =>
    unless diagnostic.code = .unsupportedPrimitive && diagnostic.message == "Action.managed2 requires explicit core0-user-v0.2" do
      throwError diagnostic.render
  | .ok _ => throwError "managed Arithmetic server escaped historical User1"
  liftCoreM <| Lean.Compiler.compile #[`Lemma.Mathematics.ManagedRational.compareFiveSix]
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_2
      #[``Lemma.Services.Arithmetic.Server.main, ``Lemma.Services.Arithmetic.Client.beginCall,
        ``Lemma.Services.Arithmetic.Client.pollCall] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_2 suite with
  | .ok _ => logInfo "ARITHMETIC_IPC_LOWERING:PASS genuine managed IR and checked User2 LLVM; historical User1 rejects managed server; isolated RV64/death/resource execution separate"
  | .error diagnostic => throwError diagnostic

/-! This independent host RAM fixture tests reply admission, not service
execution. Kernel death, deadlines and isolation require separate real RV64. -/
namespace ArithmeticReplyFixture
open Lemma.Core0.Memory Lemma.User Lemma.Services.Arithmetic
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  status : UInt8 := 0
  bytes : UInt64 := 144
  polls : UInt64 := 0
partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next => let (s,v) ← execute ref first; execute ref (next s v)
  | .platform operation a b c d e f next =>
    let current ← ref.get
    if operation = .virtualRead64 then
      unless a % 8 = 0 && ((0x329000 ≤ a && a < 0x32a000) || (0x32b000 ≤ a && a < 0x32c000)) do
        throw <| IO.userError "reply fixture address outside declared owned pages"
      execute ref (next 0 (current.words.getD a 0))
    else if operation = .syscall then
      unless a = 67 && b = 77 && c = 0x32b100 && d = 256 && e = 0 && f = 0 do
        throw <| IO.userError "reply fixture changed actual nonblocking poll arguments"
      ref.set {current with polls := current.polls+1}; execute ref (next current.status current.bytes)
    else throw <| IO.userError "reply admission attempted unexpected effect"
  | _ => throw <| IO.userError "reply admission attempted unexpected Action"
def require (b : Bool) (message : String) : IO Unit := unless b do throw <| IO.userError message
def base : State := Id.run do
  let mut s : State := {}
  for (offset,value) in [(0,0x3150434854414d4c),(8,1),(16,0x0001000000000001),(24,1),(32,1),(40,7),(48,1),(96,8),(104,9)] do
    s := {s with words := s.words.insert (0x32b000+offset) value}
  for (offset,value) in [(0,0x31504349414d454c),(8,3),(16,3),(24,9),(32,0),(40,80),(48,0),(56,0)] do
    s := {s with words := s.words.insert (0x32b100+offset) value}
  for (offset,value) in [(0,0x3150434854414d4c),(8,1),(16,0x0001000000000001),(24,1),(32,1),(40,7),(48,1),(56,1),(64,8),(72,9)] do
    s := {s with words := s.words.insert (0x32b140+offset) value}
  return s
def check : IO Unit := do
  let ref ← IO.mkRef base
  require ((← execute ref (Client.pollCall 77 0x32b100 0x32b000 9)) = (0,1)) "matching copied reply was rejected"
  for offset in [0,8,16,24,32,40,48,64,72] do
    ref.set {base with words := base.words.insert (0x32b140+offset) ((base.words.getD (0x32b140+offset) 0)+1)}
    require ((← execute ref (Client.pollCall 77 0x32b100 0x32b000 9)).1 = 101) "mismatched checker/request/revision/environment accepted"
  for (offset,value) in [(0,0),(8,2),(16,0),(24,8),(32,1),(40,72),(48,237),(56,1)] do
    ref.set {base with words := base.words.insert (0x32b100+offset) value}
    require ((← execute ref (Client.pollCall 77 0x32b100 0x32b000 9)).1 = 101) "malformed kernel envelope accepted"
  for status in [33,38,236,237,238,239] do
    ref.set {base with words := (base.words.insert 0x32b130 status.toUInt64).insert 0x32b178 0}
    require ((← execute ref (Client.pollCall 77 0x32b100 0x32b000 9)) = (status,0)) "bounded service error forged outcome or disappeared"
  for status in [12,93,94,96] do
    ref.set {base with status := status,bytes := 0}
    require ((← execute ref (Client.pollCall 77 0x32b100 0x32b000 9)) = (status,0)) "kernel transaction error disappeared"
  IO.println "ARITHMETIC_REPLY:PASS exact envelope/environment/revision/request admission; malformed/resource/terminal outcomes reject without document writes"
end ArithmeticReplyFixture
run_cmd do Lean.Elab.Command.liftTermElabM ArithmeticReplyFixture.check
