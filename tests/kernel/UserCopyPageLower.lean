import tests.kernel.UserCopyPageBefore
import Lemma.Kernel.Memory.UserCopy
import Lemma.Compiler.CFGLower
import Lemma.Compiler.Format
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let some out ← liftIO <| IO.getEnv "LEMMA_USER_COPY_PAGE_FIXTURE_DIR"
    | throwError "LEMMA_USER_COPY_PAGE_FIXTURE_DIR must select an unused component output"
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_4
      #[`Lemma.Kernel.Memory.UserCopy.copyFromUser,`Lemma.Kernel.Memory.UserCopy.copyToUser,
        `UserCopyPageBefore.copyFromUser,`UserCopyPageBefore.copyToUser,
        `UserCopyPageBefore.copyFromUserReadPage,`UserCopyPageBefore.copyFromUserReusingReadPage] with
    | .ok s => pure s | .error e => throwError e.render
  let lowered ← match lowerActionSuiteExecution .kernel_v0_4 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineLiteralConstants := true, inlinePrimitiveWrappers := true, symbolPrefix := "copy_page_" } with
    | .ok s => pure s | .error e => throwError e
  let module : LLVM.Module := {
    sourceName := "Genuinely elaborated bounded UserCopy before/after ordinary source"
    functions := lowered.functions}
  match LLVM.validateModule module with | .ok () => pure () | .error e => throwError e
  liftIO <| IO.FS.createDirAll out
  liftIO <| IO.FS.writeFile (out ++ "/production.ll") module.render
  liftIO <| IO.FS.writeFile (out ++ "/symbols.txt") lowered.renderSymbolManifest
  liftIO <| IO.FS.writeFile (out ++ "/checked.txt") (String.join (suite.scalarFunctions.toList.map (fun f => s!"scalar={f.name}\n{f.body.renderNormalized}\n") ++ suite.actionFunctions.toList.map (fun f => s!"action={f.name}\n{f.body.renderNormalized}\n")))
  logInfo s!"USER_COPY_PAGE_BLOCK_SOURCE_LOWERING:PASS genuine LeanIR -> checked Actions/CFG/LLVM functions{lowered.functions.size}"
