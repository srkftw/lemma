import Lemma.Compiler.CFGLower
import Lemma.Core0.DeviceModel

/-! Genuine source-profile regressions for the closed kernel FIFO extension.
These checks establish rejection/lowering behavior, not UART execution. -/
namespace Lemma.Compiler.Test.KernelFifo14

open Lean Elab Command
open Lemma.Core0
open Lemma.Compiler

def trigger14 : Memory.Action :=
  .uartEnableAndResetFifo14 fun status => .done status 0

def legacyTrigger1 : Memory.Action :=
  .uartEnableAndResetFifo fun status => .done status 0

run_cmd do
  let env ← getEnv
  let older : Array Profile := #[.v0_1, .v0_2, .v0_3, .v0_4, .v0_5, .v0_6,
    .v0_7, .firmware_v0_1, .kernel_v0_1, .user_v0_1]
  for profile in older do
    match checkAndLowerActionSuiteForProfile env profile #[``trigger14] with
    | .ok _ => throwError "old profile admitted kernel FIFO trigger14: {profile.contractVersion}"
    | .error diagnostic =>
      let expected := if profile == .v0_1 || profile == .v0_2 || profile == .v0_3
        then DiagnosticCode.invalidSuite else DiagnosticCode.unsupportedPrimitive
      unless diagnostic.code == expected do
        throwError "unexpected old-profile rejection: {diagnostic.render}"
  let suite ← match checkAndLowerActionSuiteForProfile env .kernel_v0_2 #[``trigger14] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  unless suite.usedDeviceOps == #[.uartEnableAndResetFifo14] &&
      suite.actionFunctions.all (fun f => f.effects == EffectSet.deviceWrite) do
    throwError "new operation lost its exact device/effect metadata"
  let lowered ← match lowerActionSuiteExecution .kernel_v0_2 suite with
    | .ok lowered => pure lowered
    | .error error => throwError error
  let module : LLVM.Module := {
    sourceName := "kernel FIFO trigger14 genuine frontend regression"
    declarations := #[{ name := "core0_io_fence", returnType := .void, parameters := #[] }]
    functions := lowered.functions }
  match LLVM.validateModule module with
  | .error error => throwError error
  | .ok _ => pure ()
  let ir := module.render
  unless (ir.splitOn "store volatile i8 199, ptr inttoptr (i64 268435458 to ptr), align 1").length == 2 do
    throwError "new operation did not emit exactly one closed FCR byte write"
  match lowerActionSuiteExecution .kernel_v0_2 { suite with usedDeviceOps := #[] } with
  | .ok _ => throwError "lowerer accepted omitted device metadata"
  | .error _ => pure ()
  match lowerActionSuiteExecution .kernel_v0_1
      { suite with contractVersion := Profile.kernel_v0_1.contractVersion } with
  | .ok _ => throwError "lowerer admitted forged old-profile new-op metadata"
  | .error _ => pure ()
  let first := suite.actionFunctions[0]!
  match lowerActionSuiteExecution .kernel_v0_2
      { suite with actionFunctions := #[{ first with effects := .empty }] } with
  | .ok _ => throwError "lowerer accepted erased MMIO effect metadata"
  | .error _ => pure ()
  for profile in #[Profile.v0_5, .v0_6, .v0_7, .firmware_v0_1, .kernel_v0_1, .kernel_v0_2] do
    match checkAndLowerActionSuiteForProfile env profile #[``legacyTrigger1] with
    | .error diagnostic => throwError "legacy FIFO rejected: {diagnostic.render}"
    | .ok legacy =>
      unless legacy.usedDeviceOps == #[.uartEnableAndResetFifo] do
        throwError "legacy FIFO identity changed"
  match Device.Model.stepDeviceAction {} trigger14 with
  | .ok _ => throwError "finite legacy device model simulated new hardware configuration"
  | .error diagnostic =>
    unless diagnostic.code == .executionActionUnsupported do
      throwError "new configuration model rejection has wrong reason"
  logInfo "PASS: kernel-v0.2 FIFO genuine acceptance, ten old-profile rejections, six legacy admissions, metadata defenses, explicit model rejection"

end Lemma.Compiler.Test.KernelFifo14
