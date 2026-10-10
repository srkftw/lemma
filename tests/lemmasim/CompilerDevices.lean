import Lemma.Compiler.CFGLower
import Lemma.Platform.LemmaSim.IO

/-! Independent genuine-declaration membership/lowering checks. These do not
execute a device or certify QEMU. The new profile alone accepts the four
bounded operations and records exact MMIO effects and ordering calls. -/
namespace Lemma.Compiler.Test.SimDevices
open Lean Elab Command
open Lemma.Core0
open Lemma.Compiler

def probe : Memory.Action :=
  .bind (Lemma.Platform.LemmaSim.IO.read32 0x10001000) fun s v =>
  if s = 0 then .bind (Lemma.Platform.LemmaSim.IO.write32 0x10001070 0) fun s _ =>
  if s = 0 then .bind (Lemma.Platform.LemmaSim.IO.read64 0x10010000) fun s v =>
  if s = 0 then Lemma.Platform.LemmaSim.IO.write64 0x100100b0 v else .done s 0
  else .done s 0 else .done s v

run_cmd do
  let env ← getEnv
  for profile in #[Profile.v0_4, .v0_5, .v0_6, .v0_7, .firmware_v0_1,
      .kernel_v0_1, .kernel_v0_2, .user_v0_1] do
    match checkAndLowerActionSuiteForProfile env profile #[``probe] with
    | .ok _ => throwError "historical profile accepted new device authority"
    | .error _ => pure ()
  let suite ← match checkAndLowerActionSuiteForProfile env .kernel_v0_3 #[``probe] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  unless (suite.usedExecutionOps.filter (·.operation.isDevice)).size == 4 do
    throwError "new profile lost exact operation accounting"
  let lowered ← match lowerActionSuiteExecution .kernel_v0_3 suite with
    | .ok lowered => pure lowered
    | .error error => throwError error
  let module : LLVM.Module := {
    sourceName := "genuine LemmaSim device declarations"
    declarations := #[{ name := "core0_io_fence", returnType := .void, parameters := #[] }]
    functions := lowered.functions }
  match LLVM.validateModule module with
  | .ok _ => pure ()
  | .error error => throwError error
  let ir := module.render
  for expected in ["load volatile i32", "store volatile i32", "load volatile i64", "store volatile i64"] do
    unless (ir.splitOn expected).length > 1 do throwError "missing actual width lowering"
  unless (ir.splitOn "call void @core0_io_fence()").length > 8 do
    throwError "device accesses lost ordering calls"
  match lowerActionSuiteExecution .kernel_v0_2
      { suite with contractVersion := Profile.kernel_v0_2.contractVersion } with
  | .ok _ => throwError "forged old profile accepted new device metadata"
  | .error _ => pure ()
  logInfo "PASS: genuine device declarations, eight old-profile rejections, width/fence lowering and metadata rejection"

end Lemma.Compiler.Test.SimDevices
