import Lemma.Compiler.CFGLower
import Lemma.Platform.RiscV.CounterSuPrimitives
import Lemma.Platform.RiscV.Development.CounterSuPolicy
import Lemma.Platform.RiscV.Development.CounterPolicy

/-! Genuine source checks and quarantined admission negatives. These fixtures
are not imported by the emitted counter diagnostic or ordinary applications. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
namespace CounterSuExecutionCompile

def extraOperand : Memory.Action :=
  .platform .readCounterCycle 1 0 0 0 0 0 fun s v => .done s v

def extraTransitionOperand : Memory.Action :=
  .platform .counterEnterUser 0 0 1 0 0 0 fun s v => .done s v

def unadmittedLoop : Memory.Action := .loop Lemma.Platform.RiscV.Development.CounterSuPolicy.main

def failed (result : Except α β) : Bool := match result with | .error _ => true | .ok _ => false
private def require (value : Bool) (message : String) : CommandElabM Unit :=
  unless value do throwError message

run_cmd do
  let env ← getEnv
  let ns := `Lemma.Platform.RiscV.Development.CounterSuPolicy
  let roots := #[ns ++ `main, ns ++ `probe, ns ++ `trap]
  let suite ← match checkAndLowerActionSuiteForProfile env .counter_su_v0_1 roots with
    | .ok v => pure v | .error e => throwError e.render
  require (suite.contractVersion == "core0-counter-su-v0.1" && suite.roots.size == 3)
    "counter-su profile/roots differ"
  require (suite.usedLoops.isEmpty && suite.usedDeviceOps.isEmpty && suite.usedExecutionOps.size == 21)
    "counter-su source closure gained loop/device or lost fixed operations"
  let old := #[Profile.v0_1,.v0_2,.v0_3,.v0_4,.v0_5,.v0_6,.v0_7,
    .firmware_v0_1,.firmware_v0_2,.kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,
    .kernel_v0_5,.kernel_v0_6,.kernel_v0_7,.boot_v0_1,.user_v0_1,.user_v0_2,.user_v0_3,
    .user_v0_4,.user_v0_5,.user_v0_6]
  for profile in old do
    require (failed <| checkAndLowerActionSuiteForProfile env profile roots)
      s!"counter-su diagnostic admitted by old profile {profile.contractVersion}"
    for op in Execution.Op.all do
      if op.admits .counter_su_v0_1 && !op.admits .firmware_v0_2 then
        require (!op.admits profile) "new diagnostic operation widened an old profile"
  for (op,_,write) in Lemma.Platform.RiscV.CounterSuPrimitives.accesses do
    require (op.admits .counter_su_v0_1 && op.argumentCount == (if write then 1 else 0))
      "counter-su CSR fixed arity/admission differs"
    let effect := executionEffects op
    require (effect.machineState && !effect.mayDiverge && !effect.physicalRead && !effect.physicalWrite)
      "counter-su CSR effects contain unrelated RAM/runtime authority"
  for op in #[Execution.Op.counterEnterUser,.counterEnterSupervisor] do
    let effect := executionEffects op
    require (op.argumentCount == 2 && effect.privilegeTransition && effect.syncTrap &&
      effect.machineState && effect.physicalRead && effect.physicalWrite && !effect.mayDiverge)
      "fixed privilege/context transport effects differ"
  for fixture in #[`CounterSuExecutionCompile.extraOperand,
      `CounterSuExecutionCompile.extraTransitionOperand,`CounterSuExecutionCompile.unadmittedLoop] do
    require (failed <| checkAndLowerActionSuiteForProfile env .counter_su_v0_1 #[fixture])
      "unused operands or diagnostic Action.loop admitted"
  require (failed <| lowerActionSuiteExecution .firmware_v0_2 suite) "diagnostic suite lowered under old firmware"
  require (failed <| lowerActionSuiteExecution .counter_su_v0_1 {suite with usedExecutionOps := #[]})
    "absent operation catalog accepted"
  require (failed <| Lemma.Platform.RiscV.CounterSuPrimitives.render "bad symbol" "probe" "trap")
    "unbound primitive symbol accepted"
  let legacy ← match checkAndLowerActionSuiteForProfile env .firmware_v0_2 #[`Lemma.Platform.RiscV.Development.CounterPolicy.main] with
    | .ok v => pure v | .error e => throwError e.render
  require (legacy.usedExecutionOps.size == 11 && legacy.contractVersion == "core0-firmware-v0.2")
    "historical M-counter source admission changed"
  logInfo "COUNTER_SU_EXECUTION_COMPILE:PASS genuine profile/effects/closure guards; hardware observations remain separate"
end CounterSuExecutionCompile
