import Lemma.Compiler.CFGLower
import Lemma.Platform.LemmaSim.IO

/-! Genuine declarations and forged-metadata negatives for the additive
kernel-v0.4 PLIC priority14 aperture. The companion host checker executes the
emitted guard CFG against synthetic mapped registers; target execution is a
separate power-probe observation. -/
namespace Lemma.Compiler.Test.PowerBoundary
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler

def read (address : UInt64) : Memory.Action :=
  Lemma.Platform.LemmaSim.IO.read32 address
def write (address value : UInt64) : Memory.Action :=
  Lemma.Platform.LemmaSim.IO.write32 address value

run_cmd do
  let env ← getEnv
  let roots := #[``read, ``write]
  for profile in #[Profile.user_v0_1, .firmware_v0_1, .kernel_v0_1, .kernel_v0_2] do
    match checkAndLowerActionSuiteForProfile env profile roots with
    | .ok _ => throwError "unprivileged/old profile admitted device32"
    | .error _ => pure ()
  let some directory ← liftIO <| IO.getEnv "LEMMA_POWER_BOUNDARY_OUT"
    | throwError "LEMMA_POWER_BOUNDARY_OUT must name a fresh output directory"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite retained boundary probe"
  liftIO <| IO.FS.createDirAll path
  for profile in #[Profile.kernel_v0_3, .kernel_v0_4] do
    let suite ← match checkAndLowerActionSuiteForProfile env profile roots with
      | .ok suite => pure suite
      | .error diagnostic => throwError diagnostic.render
    for forged in #[Profile.kernel_v0_3, .kernel_v0_4] do
      if forged != profile then
        match lowerActionSuiteExecution forged suite with
        | .ok _ => throwError "lowerer accepted a mismatched contract"
        | .error _ => pure ()
    let lowered ← match lowerActionSuiteExecution profile suite {
        preserveCalls := suite.actionFunctions.map (·.name), symbolPrefix := "boundary_" } with
      | .ok lowered => pure lowered
      | .error diagnostic => throwError diagnostic
    let module : LLVM.Module := {
      sourceName := "checked power priority boundary"
      declarations := #[{ name := "core0_io_fence", returnType := .void, parameters := #[] }]
      functions := lowered.functions }
    match LLVM.validateModule module with
    | .ok _ => pure ()
    | .error error => throwError error
    liftIO <| IO.FS.writeFile (path / (profile.contractVersion ++ ".ll")) module.render
    liftIO <| IO.FS.writeFile (path / (profile.contractVersion ++ ".symbols"))
      lowered.renderSymbolManifest
  logInfo "POWER_BOUNDARY:PASS genuine profiles and authority/contract negatives; guard execution follows"
end Lemma.Compiler.Test.PowerBoundary
