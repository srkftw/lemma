import Lemma.Core0
import Lemma.Compiler.CFGLower

/-!
Focused source/frontend probe for the closed `core0-v0.7` timer/interrupt
Actions.  The root reaches operations through ordinary Action calls and a
bounded-fold callback, exercising transitive metadata/effect accounting without
claiming to simulate hardware delivery.
-/

namespace Lemma.Examples.Foundation.TimerFrontendProbes

open Lemma.Core0.Memory

def clockOps (deadline : UInt64) : Action :=
  Action.timerReadTime fun status now =>
    if status = Status.ok then
      Action.timerSetCompare deadline fun status value =>
        if status = Status.ok then
          Action.timerReadPending fun status pending =>
            Action.done status (now ||| pending)
        else Action.done status value
    else Action.done status now

def interruptOps (restore enable : Bool) : Action :=
  Action.irqSaveDisable fun status oldMIE =>
    if status = Status.ok then
      Action.irqRestore restore fun status value =>
        if status = Status.ok then
          Action.timerSetInterrupt enable fun status value =>
            Action.done status value
        else Action.done status value
    else Action.done status oldMIE

def probeStep (_index _count : UInt32)
    (accumulator _ctx0 _ctx1 _ctx2 _ctx3 : UInt64) : Action :=
  Action.timerProbe fun status mask =>
    Action.done status (accumulator ||| mask)

/-- v0.7 must retain both earlier effect families without changing their closed
identities or admitting them into older profiles. -/
def retainedLegacy : Action :=
  Action.uartReadStatus fun status lineStatus =>
    if status = Status.ok then
      Action.trapEcall fun status mask =>
        Action.done status (lineStatus ||| mask)
    else Action.done status lineStatus

def root (deadline : UInt64) (restore enable : Bool) (count : UInt32) : Action :=
  Action.bind (clockOps deadline) fun status clock =>
    if status = Status.ok then
      Action.bind (interruptOps restore enable) fun status value =>
        if status = Status.ok then
          Action.boundedFoldU64 4 probeStep count clock 0 0 0 0 fun status value =>
            Action.done status value
        else Action.done status value
    else Action.done status clock

#core0_check_action_v07 root

open Lean Elab Command

elab "#gate8_frontend_probe" : command => do
  let env ← getEnv
  let rootName := ``Lemma.Examples.Foundation.TimerFrontendProbes.root
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV07 env #[rootName] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  unless suite.contractVersion == Lemma.Core0.Profile.v0_7.contractVersion &&
      suite.usedTimerOps.size == Lemma.Core0.Timer.Op.all.size &&
      Lemma.Core0.Timer.Op.all.all suite.usedTimerOps.contains &&
      suite.usedTimerOps.all Lemma.Core0.Timer.Op.all.contains do
    throwError "v0.7 frontend did not retain the exact seven timer identities"
  unless Lemma.Core0.Timer.catalogValid do
    throwError "v0.7 timer catalog is internally invalid"
  let legacyName := ``Lemma.Examples.Foundation.TimerFrontendProbes.retainedLegacy
  let legacySuite ← match Lemma.Core0.checkAndLowerActionSuiteV07 env #[legacyName] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  unless legacySuite.usedDeviceOps == #[.uartReadStatus] &&
      legacySuite.usedTrapOps == #[.ecall] && legacySuite.usedTimerOps.isEmpty do
    throwError "v0.7 did not retain the closed v0.5 UART and v0.6 trap operations"
  let some legacyFunction := legacySuite.findActionFunction? legacyName
    | throwError "v0.7 omitted its retained legacy probe"
  let legacyEffects : Lemma.Core0.EffectSet := {
    mmioRead := true
    ioOrder := true
    syncTrap := true
    machineState := true
  }
  unless legacyFunction.directEffects == legacyEffects &&
      legacyFunction.effects == legacyEffects do
    throwError "v0.7 changed retained UART/trap effects"
  match Lemma.Compiler.lowerActionSuiteV07 legacySuite with
  | .error message => throwError m!"v0.7 failed to lower retained UART/trap operations: {message}"
  | .ok _ => pure ()
  let some rootFunction := suite.findActionFunction? rootName
    | throwError "v0.7 frontend omitted its timer probe root"
  let expectedEffects : Lemma.Core0.EffectSet := {
    mmioRead := true
    mmioWrite := true
    ioOrder := true
    machineState := true
    timerState := true
    interruptState := true
  }
  unless rootFunction.directEffects == .empty &&
      rootFunction.effects == expectedEffects do
    throwError "timer effects were not propagated through calls/fold callbacks"
  unless Lemma.Core0.EffectSet.empty.render == "[]" &&
      Lemma.Core0.EffectSet.deviceRead.render == "[mmio-read,io-order]" &&
      Lemma.Core0.EffectSet.deviceWrite.render == "[mmio-write,io-order]" &&
      Lemma.Core0.EffectSet.trap.render == "[sync-trap,machine-state]" do
    throwError "v0.7 changed a historical effect rendering"
  let lowered ← match Lemma.Compiler.lowerActionSuiteV07 suite with
    | .ok lowered => pure lowered
    | .error message => throwError message
  let rendered := String.join <| lowered.functions.toList.map fun function =>
    function.render ++ "\n"
  for operation in Lemma.Core0.Timer.Op.all do
    unless rendered.contains ("@" ++ operation.llvmSymbol ++ "(") do
      throwError m!"v0.7 lowering omitted exact primitive `{operation.llvmSymbol}`"
  unless rendered.contains "zext i1" &&
      rendered.contains "@core0_irq_restore(i64" &&
      rendered.contains "@core0_timer_set_interrupt(i64" do
    throwError "v0.7 lowering omitted canonical Bool-to-i64 timer ABI conversion"
  let staleMetadata := { suite with usedTimerOps := #[] }
  match Lemma.Compiler.lowerActionSuiteV07 staleMetadata with
  | .error message =>
      unless message.contains "stale timer-operation metadata" do
        throwError m!"stale timer metadata failed for the wrong reason: {message}"
  | .ok _ => throwError "v0.7 lowering accepted stale timer metadata"
  let staleEffects := { suite with
    actionFunctions := suite.actionFunctions.map fun function =>
      if function.name == rootName then { function with effects := .empty }
      else function
  }
  match Lemma.Compiler.lowerActionSuiteV07 staleEffects with
  | .error message =>
      unless message.contains "stale transitive effects" do
        throwError m!"stale timer effects failed for the wrong reason: {message}"
  | .ok _ => throwError "v0.7 lowering accepted stale transitive timer effects"
  let forgedRamEffects := { suite with
    actionFunctions := suite.actionFunctions.map fun function =>
      if function.name == rootName then {
        function with
        directEffects := {
          function.directEffects with checkedAccess := true, ramRead := true
        }
        effects := { function.effects with checkedAccess := true, ramRead := true }
      } else function
  }
  match Lemma.Compiler.lowerActionSuiteV07 forgedRamEffects with
  | .error message =>
      unless message.contains "stale direct memory effects" do
        throwError m!"forged RAM effects failed for the wrong reason: {message}"
  | .ok _ => throwError "v0.7 lowering accepted forged direct RAM effects"
  let forgedLegacy := {
    suite with contractVersion := Lemma.Core0.Profile.v0_6.contractVersion
  }
  match Lemma.Compiler.lowerActionSuiteV06 forgedLegacy with
  | .error message =>
      unless message.contains "timer operations require `core0-v0.7`" do
        throwError m!"v0.6 timer forgery failed for the wrong reason: {message}"
  | .ok _ => throwError "v0.6 lowering accepted a forged timer Action"
  let timerAction := Action.timerReadTime fun status value => Action.done status value
  match Lemma.Core0.Memory.Model.evaluateDefault
      Lemma.Core0.Memory.Model.State.zeroed timerAction with
  | .error diagnostic =>
      unless diagnostic.code == .timerActionUnsupported do
        throwError "finite RAM model rejected a timer Action with the wrong diagnostic"
  | .ok _ => throwError "finite RAM model pretended to execute a timer Action"
  match Lemma.Core0.Device.Model.stepDeviceAction {} timerAction with
  | .error diagnostic =>
      unless diagnostic.code == .timerActionUnsupported do
        throwError "finite UART model rejected a timer Action with the wrong diagnostic"
  | .ok _ => throwError "finite UART model pretended to execute a timer Action"
  unless Status.isKnownV06 Status.missingTimerEvent == false &&
      Status.isKnownV07 Status.missingTimerEvent &&
      Status.isPublicV07 Status.invalidDeadline do
    throwError "v0.7 timer statuses changed an older status predicate"
  logInfo "Gate 8 frontend/lowering probe passed (7 timer ops, canonical Bool ABI, transitive effects, stale metadata/effect and legacy-profile rejections)"

#gate8_frontend_probe

end Lemma.Examples.Foundation.TimerFrontendProbes
