import Lemma.Kernel.IPC
import Lemma.Kernel.Task
import Lemma.Compiler.CFGLower

/-! Genuine elaboration/lowering of the production copy, lookup and deadline
declarations. The emitted module is diagnostic compiler evidence; linked CPU
execution and selected-path stack accounting remain separate checks. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  let env ← getEnv
  let some directory ← liftIO <| IO.getEnv "LEMMA_BULK_PROBE_OUT"
    | throwError "LEMMA_BULK_PROBE_OUT must name a fresh output directory"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite retained probe"
  liftIO <| IO.FS.createDirAll path
  let roots := #[`Lemma.Kernel.Memory.UserCopy.copyFromUser,
    `Lemma.Kernel.Memory.UserCopy.copyToUser, `Lemma.Kernel.Memory.AddressSpace.lookup,
    `Lemma.Kernel.IPC.deadlineWithLimit, `Lemma.Kernel.Task.context,
    `Lemma.Kernel.Task.savedContext, `Lemma.Kernel.Process.validateFrame]
  let suite ← match checkAndLowerActionSuiteForProfile env .kernel_v0_3 roots with
    | .ok suite => pure suite
    | .error error => throwError error.render
  let lowered ← match lowerActionSuiteExecution .kernel_v0_3 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "bulk_probe_" } with
    | .ok result => pure result
    | .error error => throwError error
  let module : LLVM.Module := {
    sourceName := "checked guest bulk copy and deadline"
    functions := lowered.functions
    declarations := #[{
      name := "lemma_exec_firmware_call"
      returnType := .checkedResult
      parameters := #[.i64, .i64, .i64, .i64, .i64, .i64] }] }
  match LLVM.validateModule module with
  | .ok () => pure ()
  | .error error => throwError error
  liftIO <| IO.FS.writeFile (path / "program.ll") module.render
  liftIO <| IO.FS.writeFile (path / "symbols.txt") lowered.renderSymbolManifest
  liftIO <| IO.FS.writeFile (path / "source-declarations.txt")
    (String.intercalate "\n" ((suite.scalarFunctions.map (·.name.toString) ++
      suite.actionFunctions.map (·.name.toString)).toList) ++ "\n")
  logInfo m!"BULK_COMPILE:PASS genuine kernel-v0.3 elaboration and LLVM lowering; CPU execution separate"
