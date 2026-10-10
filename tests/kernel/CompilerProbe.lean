import Lemma.Compiler.CFGLower

/-! Host-only genuine elaboration probes. Rejected source remains quarantined in
this fixture; none of these declarations is imported by a production unit. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
namespace CompilerLoopProbe

def successfulStep : Memory.Action := .done 0 99
def failedStep : Memory.Action := .done 73 0x123456789abcdef0
def repeats : Memory.Action := .loop successfulStep
def fails : Memory.Action := .loop failedStep
def failureContinuation : Memory.Action :=
  .bind (.loop failedStep) fun status value => .done status value

def dynamic (choose : Bool) : Memory.Action :=
  .loop (if choose then successfulStep else failedStep)
def inlineStep : Memory.Action := .loop (.done 0 1)
def stored : Memory.Action :=
  let step := successfulStep
  .loop step
def scalarStep (_ : UInt64) : Memory.Action := .done 0 1
def appliedStep : Memory.Action := .loop (scalarStep 0)
def pending : Memory.Action :=
  .platform .readSupervisorPending 0 0 0 0 0 0 fun status value => .done status value

def failed (result : Except α β) : Bool :=
  match result with | .error _ => true | .ok _ => false
private def require (condition : Bool) (message : String) : CommandElabM Unit :=
  unless condition do throwError message

run_cmd do
  let env ← getEnv
  let out ← liftIO <| IO.getEnv "LEMMA_COMPILER_PROBE_OUT"
  let some out := out | throwError "LEMMA_COMPILER_PROBE_OUT must name an evidence directory"
  liftIO <| IO.FS.createDirAll out
  let mut count : Nat := 0
  for (profile, root, label) in #[(Profile.kernel_v0_1, `CompilerLoopProbe.repeats, "kernel-repeat"),
      (.user_v0_1, `CompilerLoopProbe.repeats, "user-repeat"),
      (.kernel_v0_1, `CompilerLoopProbe.failureContinuation, "kernel-failure")] do
    let suite ← match checkAndLowerActionSuiteForProfile env profile #[root] with
      | .ok suite => pure suite | .error diagnostic => throwError diagnostic.render
    require (suite.usedLoops.size == 1) "closed loop metadata missing"
    let some entry := suite.findActionFunction? root | throwError "root missing"
    require entry.effects.mayDiverge "loop may-diverge effect missing"
    let lower := lowerActionSuiteExecution profile
    require (failed <| lower { suite with usedLoops := #[] }) "absent loop metadata accepted"
    require (failed <| lower { suite with usedLoops := suite.usedLoops ++ suite.usedLoops })
      "duplicate loop metadata accepted"
    require (failed <| lower { suite with usedLoops := suite.usedLoops.map fun use =>
      { use with stableId := "action.unknown" } }) "unknown loop identity accepted"
    let omitDependency := { suite with actionFunctions := suite.actionFunctions.map fun f =>
      if f.name == root then { f with actionDependencies := #[] } else f }
    require (failed <| lower omitDependency) "loop callback dependency omission accepted"
    let omitEffect := { suite with actionFunctions := suite.actionFunctions.map fun f =>
      if f.name == root then { f with directEffects := { f.directEffects with mayDiverge := false } }
      else f }
    require (failed <| lower omitEffect) "loop direct-effect omission accepted"
    let lowered ← match lowerActionSuiteExecution profile suite { symbolPrefix := "probe_" } with
      | .ok result => pure result | .error message => throwError message
    let module : LLVM.Module := { sourceName := label, functions := lowered.functions }
    match LLVM.validateModule module with
    | .ok () => pure () | .error message => throwError message
    require (!(module.render.splitOn "action.loop.repeat").tail.isEmpty)
      "real loop backedge was not emitted"
    require (!(module.render.splitOn "action.loop.failure").tail.isEmpty)
      "failure edge was not emitted"
    require ((module.render.splitOn "mustprogress").tail.isEmpty)
      "loop incorrectly promises progress"
    liftIO <| IO.FS.writeFile (System.FilePath.mk out / (label ++ ".ll")) module.render
    count := count + 9
  for profile in #[Profile.v0_1, .v0_2, .v0_3, .v0_4, .v0_5, .v0_6, .v0_7, .firmware_v0_1] do
    require (failed <| checkAndLowerActionSuiteForProfile env profile #[`CompilerLoopProbe.repeats])
      s!"loop accepted by {profile.contractVersion}"
    count := count + 1
  for name in #[`CompilerLoopProbe.dynamic, `CompilerLoopProbe.inlineStep,
      `CompilerLoopProbe.stored, `CompilerLoopProbe.appliedStep] do
    require (failed <| checkAndLowerActionSuiteForProfile env .kernel_v0_1 #[name])
      s!"non-closed callback accepted: {name}"
    count := count + 1
  let pendingSuite ← match checkAndLowerActionSuiteForProfile env .kernel_v0_1 #[`CompilerLoopProbe.pending] with
    | .ok suite => pure suite | .error diagnostic => throwError diagnostic.render
  require (pendingSuite.usedExecutionOps == #[Execution.Op.readSupervisorPending.spec])
    "pending operation catalog signature differs"
  let some pendingEntry := pendingSuite.findActionFunction? `CompilerLoopProbe.pending
    | throwError "pending root missing"
  require (pendingEntry.effects.interruptState && !pendingEntry.effects.machineState &&
    !pendingEntry.effects.ioOrder) "pending read effects are not precise"
  let pendingLowered ← match lowerActionSuiteExecution .kernel_v0_1 pendingSuite with
    | .ok result => pure result | .error message => throwError message
  let pendingModule : LLVM.Module := {
    sourceName := "kernel-pending"
    functions := pendingLowered.functions
    declarations := #[{ name := "lemma_exec_supervisor_pending"
                        returnType := .i64
                        parameters := #[] }] }
  match LLVM.validateModule pendingModule with
    | .ok () => pure () | .error message => throwError message
  liftIO <| IO.FS.writeFile (System.FilePath.mk out / "kernel-pending.ll") pendingModule.render
  count := count + 3
  for profile in #[Profile.firmware_v0_1, .user_v0_1, .v0_7] do
    require (failed <| checkAndLowerActionSuiteForProfile env profile #[`CompilerLoopProbe.pending])
      s!"pending read accepted by {profile.contractVersion}"
    count := count + 1
  require (failed <| Memory.Model.evaluateDefault Memory.Model.State.zeroed repeats)
    "finite RAM model fabricated unbounded execution"
  require (failed <| Device.Model.stepDeviceAction {} repeats)
    "finite UART model fabricated unbounded execution"
  count := count + 2
  logInfo m!"COMPILER_LOOP_PROBES:PASS cases={count}"
end CompilerLoopProbe
