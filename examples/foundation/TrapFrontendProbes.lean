import Lemma.Core0
import Lemma.Compiler.CFGLower

/-!
Focused source/frontend probe for the closed `core0-v0.6` synchronous-trap
Actions.  The root deliberately reaches trap effects through ordinary calls,
runtime branches, and an Action-fold callback so transitive effect accounting is
exercised without relying on the Gate 7 target application.
-/

namespace Lemma.Examples.Foundation.TrapFrontendProbes

open Lemma.Core0.Memory

def authorizedEcall : Action :=
  Action.trapEcall fun status mask => Action.done status mask

def fatalUnexpectedEcall : Action :=
  Action.trapUnexpectedEcall fun status mask => Action.done status mask

def fatalIllegalInstruction : Action :=
  Action.trapIllegalInstruction fun status mask => Action.done status mask

def breakpointStep (index _count : UInt32)
    (accumulator _ctx0 _ctx1 _ctx2 _ctx3 : UInt64) : Action :=
  if index = 0 then
    Action.trapBreakpoint fun status mask =>
      if status = Status.ok then Action.done status (accumulator ||| mask)
      else Action.done status mask
  else
    Action.done Status.ok accumulator

def root (selector : UInt64) (count : UInt32) : Action :=
  if selector = 0 then
    authorizedEcall
  else if selector = 1 then
    fatalUnexpectedEcall
  else if selector = 2 then
    fatalIllegalInstruction
  else
    Action.boundedFoldU64 4 breakpointStep count 0 0 0 0 0 fun status value =>
      Action.done status value

#core0_check_action_v06 root

open Lean Elab Command

elab "#gate7_frontend_probe" : command => do
  let env ← getEnv
  let rootName := ``Lemma.Examples.Foundation.TrapFrontendProbes.root
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV06 env #[rootName] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  let expectedOps : Array Lemma.Core0.Trap.Op := #[
    .ecall, .unexpectedEcall, .illegalInstruction, .breakpoint
  ]
  unless suite.contractVersion == Lemma.Core0.Profile.v0_6.contractVersion &&
      suite.usedTrapOps == expectedOps do
    throwError "v0.6 frontend did not retain the exact four trap identities"
  let some rootFunction := suite.findActionFunction? rootName
    | throwError "v0.6 frontend omitted its trap probe root"
  unless rootFunction.directEffects == .empty &&
      rootFunction.effects == Lemma.Core0.EffectSet.trap do
    throwError "trap effects were not propagated through calls/branches/fold callbacks"
  unless Lemma.Core0.EffectSet.empty.render == "[]" &&
      Lemma.Core0.EffectSet.deviceRead.render == "[mmio-read,io-order]" &&
      Lemma.Core0.EffectSet.deviceWrite.render == "[mmio-write,io-order]" do
    throwError "v0.6 changed a historical effect rendering"
  let lowered ← match Lemma.Compiler.lowerActionSuiteV06 suite with
    | .ok lowered => pure lowered
    | .error message => throwError message
  let rendered := String.join <| lowered.functions.toList.map fun function =>
    function.render ++ "\n"
  for operation in Lemma.Core0.Trap.Op.all do
    unless rendered.contains ("@" ++ operation.llvmSymbol ++ "()") do
      throwError m!"v0.6 lowering omitted exact primitive `{operation.llvmSymbol}`"
  let staleMetadata := { suite with usedTrapOps := #[] }
  match Lemma.Compiler.lowerActionSuiteV06 staleMetadata with
  | .error message =>
      unless message.contains "stale trap-operation metadata" do
        throwError m!"stale trap metadata failed for the wrong reason: {message}"
  | .ok _ => throwError "v0.6 lowering accepted stale trap metadata"
  let staleEffects := { suite with
    actionFunctions := suite.actionFunctions.map fun function =>
      if function.name == rootName then { function with effects := .empty }
      else function
  }
  match Lemma.Compiler.lowerActionSuiteV06 staleEffects with
  | .error message =>
      unless message.contains "stale transitive effects" do
        throwError m!"stale trap effects failed for the wrong reason: {message}"
  | .ok _ => throwError "v0.6 lowering accepted stale transitive trap effects"
  let forgedLegacy := {
    suite with contractVersion := Lemma.Core0.Profile.v0_5.contractVersion
  }
  match Lemma.Compiler.lowerActionSuiteV05 forgedLegacy with
  | .error message =>
      unless message.contains "trap operations require `core0-v0.6`" do
        throwError m!"v0.5 trap forgery failed for the wrong reason: {message}"
  | .ok _ => throwError "v0.5 lowering accepted a forged trap Action"
  let trapAction := Action.trapEcall fun status mask => Action.done status mask
  match Lemma.Core0.Memory.Model.evaluateDefault
      Lemma.Core0.Memory.Model.State.zeroed trapAction with
  | .error diagnostic =>
      unless diagnostic.code == .trapActionUnsupported do
        throwError "finite RAM model rejected a trap Action with the wrong diagnostic"
  | .ok _ => throwError "finite RAM model pretended to execute a trap Action"
  match Lemma.Core0.Device.Model.stepDeviceAction {} trapAction with
  | .error diagnostic =>
      unless diagnostic.code == .trapActionUnsupported do
        throwError "finite UART model rejected a trap Action with the wrong diagnostic"
  | .ok _ => throwError "finite UART model pretended to execute a trap Action"
  logInfo "Gate 7 frontend/lowering probe passed (4 trap ops, transitive effects, stale metadata/effect and legacy-profile rejections)"

#gate7_frontend_probe

end Lemma.Examples.Foundation.TrapFrontendProbes
