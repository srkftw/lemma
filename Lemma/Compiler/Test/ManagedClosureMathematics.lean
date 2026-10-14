import Lean
import Lean.Compiler.Main
import Lemma.Compiler.ManagedClosureMetadata
import Lemma.Services.Arithmetic.ServerV7
import Lemma.Compiler.LLVMValidate

/-! Genuine closed User7 mathematical service component. This checks actual
source/lowering and exports inspectable preimages; isolated IPC/Save execution
is separately required by the deployment qualification. -/
namespace Lemma.Compiler.Test.ManagedClosureMathematics
open Lean Elab Command Lemma.Core0 Lemma.Compiler

run_elab do
  Compiler.compile #[``Lemma.Mathematics.ManagedClosureSubmission.compareFiveSix]
  let env ← getEnv
  let program ← match ManagedClosureIR.buildProgram env ``Lemma.Mathematics.ManagedClosureSubmission.compareFiveSix with
    | .ok p => pure p | .error error => throwError error
  unless program.sourceNames.size == 5 && program.targets.size == 1 &&
      program.targets[0]!.source == ``Lemma.Mathematics.ManagedClosureSubmission.select &&
      program.targets[0]!.captures == 3 do
    throwError "Genuine math closure source/owner/capture inventory differs"
  let roots := #[``Lemma.Services.Arithmetic.ServerV7.main]
  let suite ← match checkAndLowerActionSuiteForProfile env .user_v0_7 roots with
    | .ok s => pure s | .error error => throwError error.render
  for profile in #[Profile.user_v0_1,.user_v0_2,.user_v0_3,.user_v0_4,.user_v0_5,.user_v0_6] do
    match checkAndLowerActionSuiteForProfile env profile roots with
    | .ok _ => throwError "Historical profile admitted the new service closure: {profile.contractVersion}"
    | .error _ => pure ()
  let lowered ← match lowerActionSuiteExecution .user_v0_7 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineLiteralConstants := true,inlineUserWordWrappers := true,
      symbolPrefix := "lemma_user_arithmetic_"} with
    | .ok p => pure p | .error error => throwError error
  let declarations := suite.usedExecutionOps.filterMap fun spec => spec.primitiveSymbol?.map fun name =>
    ({name,returnType := if spec.resultKind == .checked then .checkedResult else .i64,
      parameters := spec.machineArguments.map llvmTy} : LLVM.Declaration)
  let module : LLVM.Module := {
    sourceName := "genuine isolated exact rational closure service User7"
    declarations,functions := lowered.functions}
  match LLVM.validateModule module with
    | .ok _ => pure () | .error error => throwError error
  let sourceSymbol (source : Name) : Except String String := do
    let some row := lowered.symbols.find? (·.source == source) | throw "Missing source symbol"
    pure row.llvm
  let mut rows : Array Json := #[]
  for f in suite.scalarFunctions do
    rows := rows.push <| Json.mkObj [("source",toJson f.name.toString),
      ("symbol",toJson (← IO.ofExcept <| sourceSymbol f.name)),
      ("args",toJson (f.signature.args.map Ty.render)),("effects",Json.arr #[])]
  for f in suite.actionFunctions do
    rows := rows.push <| Json.mkObj [("source",toJson f.name.toString),
      ("symbol",toJson (← IO.ofExcept <| sourceSymbol f.name)),
      ("args",toJson (f.signature.args.map Ty.render)),("effects",if f.effects == .empty then Json.arr #[] else
        Json.arr (((String.ofList (f.effects.render.toList.drop 1 |>.reverse.drop 1 |>.reverse)).splitOn ",").toArray.map Json.str))]
  let managed ← IO.ofExcept <| ManagedClosureMetadata.managedClosureFields env true suite lowered
  let authority ← IO.ofExcept <| ManagedClosureMetadata.executionFields true true "user" suite
  unless managed.length == 1 && authority.length == 1 do throwError "Closed metadata absent"
  let unit := Json.mkObj ([
    ("schema_version",toJson (2 : Nat)),("artifact_category",toJson "development-user-unit"),
    ("configuration",toJson "lemmasim-silicon-closure-bulk-notebook"),
    ("contract_version",toJson suite.contractVersion),("role",toJson "user"),
    ("image_key",toJson "arithmetic"),("image_id",toJson (3 : Nat)),
    ("roots",Json.arr (suite.roots.map fun r => Json.mkObj [("id",toJson r.id),
      ("source",toJson r.source.toString),("symbol",toJson ((sourceSymbol r.source).toOption.getD "")),
      ("args",toJson (r.signature.args.map Ty.render))])),("functions",Json.arr rows),
    ("used_loops",Json.arr (suite.usedLoops.map fun r => Json.mkObj [("stable_id",toJson r.stableId),("callback",toJson r.callback.toString)])),
    ("used_execution_ops",Json.arr (suite.usedExecutionOps.map fun r => Json.mkObj [
      ("stable_id",toJson r.stableId),("source_identity",toJson r.sourceIdentity.toString),
      ("primitive_symbol",r.primitiveSymbol?.map Json.str |>.getD Json.null),
      ("arguments",toJson (r.machineArguments.map Ty.render)),
      ("returnkind",toJson (if r.resultKind == .checked then "checked" else "word"))])),
    ("used_device_ops",Json.arr #[])] ++ managed ++ authority)
  let some output ← IO.getEnv "LEMMA_CLOSURE_MATH_COMPONENT_OUT" | throwError "LEMMA_CLOSURE_MATH_COMPONENT_OUT required"
  let dir := System.FilePath.mk output
  unless !(← dir.pathExists) do throwError "Retained closure math component exists"
  IO.FS.createDirAll dir
  IO.FS.writeFile (dir/"program.ll") module.render
  IO.FS.writeFile (dir/"symbols.txt") lowered.renderSymbolManifest
  IO.FS.writeFile (dir/"unit.json") (unit.pretty++"\n")
  logInfo m!"CLOSURE_MATH_COMPONENT:PASS 5 ordinary sources/1 genuine3capture adapter/{lowered.functions.size} checkedLLVM functions; six historical profiles reject"
end Lemma.Compiler.Test.ManagedClosureMathematics
