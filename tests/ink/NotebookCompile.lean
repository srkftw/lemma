import Lemma.Applications.Notebook
import Lemma.Compiler.CFGLower

/-! Host-only source/LLVM probe for the actual guest entry. Full RV64 linking,
startup audit and execution belong to the ordinary LemmaSim build and runs. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  let env ← getEnv
  let some directory ← liftIO <| IO.getEnv "LEMMA_NOTEBOOK_PROBE_OUT"
    | throwError "LEMMA_NOTEBOOK_PROBE_OUT must name a fresh artifact directory"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite retained notebook probe"
  let suite ← match checkAndLowerActionSuiteForProfile env .user_v0_1
      #[`Lemma.Applications.Notebook.main] with
    | .ok result => pure result
    | .error diagnostic => throwError diagnostic.render
  let result ← match lowerActionSuiteExecution .user_v0_1 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "notebook_probe_" } with
    | .ok result => pure result
    | .error diagnostic => throwError diagnostic
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := "genuine guest notebook v1", declarations, functions := result.functions }
  match LLVM.validateModule module with
  | .ok () => pure ()
  | .error error => throwError error
  liftIO <| IO.FS.createDirAll path
  liftIO <| IO.FS.writeFile (path / "program.ll") module.render
  liftIO <| IO.FS.writeFile (path / "symbols.txt") result.renderSymbolManifest
  liftIO <| IO.FS.writeFile (path / "source-declarations.txt")
    (String.intercalate "\n" ((suite.scalarFunctions.map (·.name.toString) ++
      suite.actionFunctions.map (·.name.toString)).toList) ++ "\n")
  logInfo "NOTEBOOK_COMPILE:PASS genuine declarations checked/lowered; guest execution separate"
