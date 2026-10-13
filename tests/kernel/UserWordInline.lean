import Lemma.Ink.Surface
import Lemma.Compiler.CFGLower
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_2 #[`Lemma.Ink.Surface.loadTile,`Lemma.Ink.Surface.storeTile] with
    | .ok s => pure s | .error e => throwError e.render
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lower (enabled : Bool) := lowerActionSuiteExecution .user_v0_2 suite {
    preserveCalls := preserved, inlineLiteralConstants := true,
    inlineUserWordWrappers := enabled, symbolPrefix := "user_wrapper_" }
  let lowered ← match lower true with | .ok s => pure s | .error e => throwError e
  let before ← match lower false with | .ok s => pure s | .error e => throwError e
  unless lowered.inlineUserWrappers.size == 2 && before.inlineUserWrappers.isEmpty do
    throwError "expected exact two optional User-v0.2 word wrappers"
  let legacy ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[`Lemma.Ink.Surface.loadTile,`Lemma.Ink.Surface.storeTile] with
    | .ok s => pure s | .error e => throwError e.render
  match lowerActionSuiteExecution .user_v0_1 legacy { inlineUserWordWrappers := true } with
    | .error _ => pure () | .ok _ => throwError "legacy User-v0.1 acquired successor word option"
  let disabled ← match lowerActionSuiteExecution .user_v0_1 legacy {
      preserveCalls := preserved, inlineLiteralConstants := true, symbolPrefix := "user_wrapper_" } with
    | .ok s => pure s | .error e => throwError e
  unless before.functions == disabled.functions do throwError "disabled User-v0.2 differs from historical wrapper lowering"
  let some output ← liftIO <| IO.getEnv "LEMMA_WORD_INLINE_FIXTURE_DIR"
    | throwError "LEMMA_WORD_INLINE_FIXTURE_DIR must select an unused fixture output"
  liftIO <| IO.FS.createDirAll output
  for (label,functions) in #[("before",before.functions),("after",lowered.functions)] do
    let module : LLVM.Module := { sourceName := "genuine checked User word optimization", functions := functions }
    match LLVM.validateModule module with | .ok () => pure () | .error e => throwError e
    liftIO <| IO.FS.writeFile (output ++ "/" ++ label ++ ".ll") module.render
  liftIO <| IO.FS.writeFile (output ++ "/symbols.txt") lowered.renderSymbolManifest
  let mut rows : Array Json := #[]
  for f in suite.scalarFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name) | throwError "missing scalar symbol"
    rows := rows.push <| Json.mkObj [("source", .str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr <| f.signature.args.map (Json.str ∘ Ty.render)),("effects",.arr #[])]
  for f in suite.actionFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name) | throwError "missing Action symbol"
    let effects := (String.ofList (f.effects.render.toList.drop 1 |>.reverse.drop 1 |>.reverse)).splitOn "," |>.toArray.map Json.str
    rows := rows.push <| Json.mkObj [("source",.str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr <| f.signature.args.map (Json.str ∘ Ty.render)),("effects",.arr effects)]
  let wrappers := lowered.inlineUserWrappers.map fun f =>
    Json.mkObj [("source",.str f.source.toString),("symbol",.str f.symbol),("operation",.str f.operation.stableId)]
  let literals := lowered.inlineLiterals.map fun f =>
    Json.mkObj [("source",.str f.source.toString),("symbol",.str f.symbol),
      ("type",.str f.ty.render),("value",toJson f.value)]
  let ops := suite.usedExecutionOps.map fun f =>
    Json.mkObj [("stable_id",.str f.stableId),
      ("primitive_symbol",f.primitiveSymbol?.map Json.str |>.getD Json.null),
      ("returnkind",.str (if f.resultKind == .checked then "checked" else "word"))]
  liftIO <| IO.FS.writeFile (output ++ "/unit.json") <|
    (Json.mkObj [("contract_version",.str suite.contractVersion),("role",.str "user"),("functions",.arr rows),
      ("configuration",.str "lemmasim-silicon-managed-notebook"),("image_key",.str "notebook"),
      ("used_execution_ops",.arr ops),("checked_inline",Json.mkObj [
        ("literal_contract",.str "lemma-closed-literals-v1"),
        ("wrapper_contract",.str "lemma-checked-primitive-wrapper-v1"),
        ("user_wrapper_contract",.str "lemma-checked-user-word-wrapper-v1"),
        ("literals",.arr literals),("wrappers",.arr #[]),("user_wrappers",.arr wrappers)])]).pretty
  logInfo "USER_WORD_INLINE:PASS genuine checked User-v0.2 optional lowering; default/legacy exact and v0.1 opt-in denied"
