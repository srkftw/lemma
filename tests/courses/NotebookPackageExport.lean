import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.Applications.Notebook

/-! Host-only actual declaration export for the independently sealed component.
The maintained production exporter will separately select the deployment. -/
open Lean Elab Command Lemma.Core0 Lemma.Compiler
elab "#export_notebook_package_component" : command => do
  let env ← getEnv
  let roots := #[``Lemma.Applications.Notebook.mainPackageClosureBulk]
  let suite ← match checkAndLowerActionSuiteForProfile env .user_v0_2 roots with
    | .ok value => pure value | .error error => throwError "{error.render}"
  unless suite.usedDeviceOps.isEmpty do throwError "User package main acquired direct device operations"
  for op in suite.usedExecutionOps do
    unless #[``Lemma.Core0.Execution.Op.virtualRead8,``Lemma.Core0.Execution.Op.virtualRead64,
      ``Lemma.Core0.Execution.Op.virtualWrite8,``Lemma.Core0.Execution.Op.virtualWrite64,
      ``Lemma.Core0.Execution.Op.syscall].contains op.sourceIdentity do
      throwError "unaccounted User package operation {op.sourceIdentity}"
  let lowered ← match lowerActionSuiteExecution .user_v0_2 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "lemma_package_notebook_component_" } with
    | .ok value => pure value | .error error => throwError "{error}"
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name := name
        returnType := (if spec.resultKind == .checked then .checkedResult else .i64)
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := "genuine installed package notebook component-v1"
    declarations := declarations
    functions := lowered.functions }
  match LLVM.validateModule module with
  | .ok _ => pure () | .error error => throwError "{error}"
  let symbol (name : Name) : CommandElabM String := do
    let some found := lowered.symbols.find? (·.source == name) | throwError "lost source owner {name}"
    return found.llvm
  let mut fs : Array Json := #[]
  for f in suite.scalarFunctions do
    fs := fs.push <| Json.mkObj [("source",.str ((privateToUserName? f.name).getD f.name).toString),
      ("original_source",.str f.name.toString),("symbol",.str (← symbol f.name)),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",.str "{}")]
  for f in suite.actionFunctions do
    fs := fs.push <| Json.mkObj [("source",.str ((privateToUserName? f.name).getD f.name).toString),
      ("original_source",.str f.name.toString),("symbol",.str (← symbol f.name)),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",.str f.effects.render)]
  let manifest := Json.mkObj [("schema_version",toJson (1:Nat)),("artifact_category",.str "installed-package-notebook-component"),
    ("contract_version",.str suite.contractVersion),("root",.str roots[0]!.toString),("root_symbol",.str (← symbol roots[0]!)),
    ("software_contract",.str "lemma-package-closure-entry2-bulk-deployment-v1"),
    ("qualification_scope",.str "actual imported Actions, genuine checked User2 LLVM and RV64 object; whole image/CPU/Store/checker/controller NOT_RUN"),
    ("functions",.arr fs),("used_execution_ops",.arr (suite.usedExecutionOps.map fun spec => Json.mkObj [
      ("source_identity",.str spec.sourceIdentity.toString),("primitive_symbol",spec.primitiveSymbol?.map Json.str |>.getD .null)])),
    ("used_device_ops",.arr #[])]
  let normalized := String.join (suite.scalarFunctions.toList.map fun f => s!"scalar={f.name}\n" ++ f.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun f => s!"action={f.name};effects={f.effects.render}\n" ++ f.body.renderNormalized ++ "\n")
  let some out ← liftIO <| IO.getEnv "LEMMA_PACKAGE_NOTEBOOK_OUT" | throwError "unused output required"
  let path := System.FilePath.mk out
  if ← liftIO path.pathExists then throwError "retained component output refused"
  liftIO <| IO.FS.createDirAll path
  for (name,contents) in #[("program.ll",module.render),("unit.json",manifest.pretty++"\n"),("symbols.txt",lowered.renderSymbolManifest),("normalized.txt",normalized)] do
    liftIO <| IO.FS.writeFile (path/name) contents
  logInfo m!"PACKAGE_NOTEBOOK_EXPORT:PASS actual User2 main, {fs.size} genuine functions; no whole image or CPU"

#export_notebook_package_component
