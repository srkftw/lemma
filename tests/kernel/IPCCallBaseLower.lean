import Lemma.Kernel.Task
import Lemma.Compiler.CFGLower
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  let some output ← liftIO <| IO.getEnv "LEMMA_IPC_CALL_FIXTURE_DIR"
    | throwError "LEMMA_IPC_CALL_FIXTURE_DIR must select an unused component output"
  for (label, roots) in #[("call", #[`Lemma.Kernel.IPC.callBeginWithLimit])] do
    let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_4
        roots with
      | .ok s => pure s | .error e => throwError e.render
    let lowered ← match lowerActionSuiteExecution .kernel_v0_4 suite {
        preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
        inlineLiteralConstants := true, inlinePrimitiveWrappers := true, symbolPrefix := "ipc_borrow_" } with
      | .ok s => pure s | .error e => throwError e
    let module : LLVM.Module := {
      sourceName := "genuine maintained IPC bounded same-Action call source"
      functions := lowered.functions
      declarations := #[{
        name := "lemma_exec_firmware_call"
        returnType := .checkedResult
        parameters := #[.i64,.i64,.i64,.i64,.i64,.i64] }] }
    match LLVM.validateModule module with
      | .ok () => pure () | .error e => throwError e
    let output := output ++ "/" ++ label
    liftIO <| IO.FS.createDirAll output
    liftIO <| IO.FS.writeFile (output ++ "/production.ll") module.render
    liftIO <| IO.FS.writeFile (output ++ "/production-symbols.txt") lowered.renderSymbolManifest
    let mut functions : Array Json := #[]
    for f in suite.scalarFunctions do
      let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
        | throwError "missing scalar symbol"
      functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
        ("symbol", .str symbol.llvm), ("args", .arr <| f.signature.args.map (Json.str ∘ Ty.render)),
        ("effects", .arr #[])]
    for f in suite.actionFunctions do
      let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
        | throwError "missing Action symbol"
      let effects := (String.ofList (f.effects.render.toList.drop 1 |>.reverse.drop 1 |>.reverse)).splitOn "," |>.toArray.map Json.str
      functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
        ("symbol", .str symbol.llvm), ("args", .arr <| f.signature.args.map (Json.str ∘ Ty.render)),
        ("effects", .arr effects)]
    liftIO <| IO.FS.writeFile (output ++ "/production-unit.json") <|
      (Json.mkObj [("role",.str "kernel"),("functions",.arr functions)]).pretty
    logInfo "IPC_CALL_PRODUCTION_COMPILE:PASS genuine checked LLVM and emitted unit rows"
