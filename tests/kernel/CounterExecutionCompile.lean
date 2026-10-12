import Lemma.Compiler.CFGLower
import Lemma.Platform.RiscV.CounterPrimitives
import Lemma.Platform.RiscV.Development.CounterPolicy

/-! Genuine source admission/lowering negatives; quarantined diagnostic source
is not imported by the emitted CounterPolicy target. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
namespace CounterExecutionCompile

def extraOperand : Memory.Action :=
  .platform .readMisa 1 0 0 0 0 0 fun s v => .done s v

def unadmittedLoop : Memory.Action := .loop Lemma.Platform.RiscV.Development.CounterPolicy.main

def failed (result : Except α β) : Bool := match result with | .error _ => true | .ok _ => false
private def require (value : Bool) (message : String) : CommandElabM Unit :=
  unless value do throwError message

run_cmd do
  let env ← getEnv
  let root := `Lemma.Platform.RiscV.Development.CounterPolicy.main
  let suite ← match checkAndLowerActionSuiteForProfile env .firmware_v0_2 #[root] with
    | .ok v => pure v | .error e => throwError e.render
  require (suite.contractVersion == "core0-firmware-v0.2") "new profile metadata differs"
  require (suite.usedLoops.isEmpty && suite.usedDeviceOps.isEmpty) "counter policy gained loop or device authority"
  require (suite.usedExecutionOps.size == 11) "counter closed source operation inventory differs"
  for profile in #[Profile.v0_1, .v0_2, .v0_3, .v0_4, .v0_5, .v0_6, .v0_7,
      .firmware_v0_1, .kernel_v0_1, .kernel_v0_2, .kernel_v0_3, .kernel_v0_4, .user_v0_1] do
    require (failed <| checkAndLowerActionSuiteForProfile env profile #[root])
      s!"new machine-counter operations silently admitted by {profile.contractVersion}"
  for (op, _, write) in Lemma.Platform.RiscV.CounterPrimitives.accesses do
    require (op.admits .firmware_v0_2 && !op.admits .firmware_v0_1) "CSR admission widened an old profile"
    require (op.argumentCount == (if write then 1 else 0)) "CSR fixed arity differs"
    let effect := executionEffects op
    require (effect.machineState && !effect.mayDiverge && !effect.physicalRead && !effect.physicalWrite)
      "CSR effects are absent or contain RAM/runtime authority"
  require (failed <| checkAndLowerActionSuiteForProfile env .firmware_v0_2 #[`CounterExecutionCompile.extraOperand])
    "nonzero unused CSR operand was accepted"
  require (failed <| checkAndLowerActionSuiteForProfile env .firmware_v0_2 #[`CounterExecutionCompile.unadmittedLoop])
    "firmware-v0.2 silently gained Action.loop"
  require (failed <| lowerActionSuiteExecution .firmware_v0_1 suite) "new checked suite was lowered under an old profile"
  require (failed <| lowerActionSuiteExecution .firmware_v0_2 {suite with usedExecutionOps := #[]})
    "absent execution catalog was accepted"
  require (failed <| lowerActionSuiteExecution .firmware_v0_2 {suite with usedExecutionOps := suite.usedExecutionOps ++ suite.usedExecutionOps})
    "duplicated execution catalog was accepted"
  require (failed <| Lemma.Platform.RiscV.CounterPrimitives.render "bad symbol")
    "primitive startup accepted an unbound entry spelling"
  logInfo "COUNTER_EXECUTION_COMPILE:PASS genuine source admission/effects/catalog guards; hardware execution remains separate"

end CounterExecutionCompile
