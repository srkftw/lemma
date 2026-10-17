import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.Courses.PackageTarget
import Lemma.Courses.PackageStore

/-! Genuine source exporter for the read-only guest package decoder. It asks
the maintained frontend to inspect ordinary elaborated declarations, checks
their complete dependency/effect closure, and validates lowered LLVM. -/
namespace Lemma.Compiler.CoursePackageExport
open Lean Elab Command
open Lemma.Core0

private def effects (value : EffectSet) : Json :=
  if value == .empty then .arr #[] else
    let interior := String.ofList (value.render.toList.drop 1 |>.reverse |>.drop 1 |>.reverse)
    .arr ((interior.splitOn ",").toArray.map Json.str)

def exportFiles (env : Environment) (directory : System.FilePath) (store : Bool := false) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "course decoder exporter refuses retained output"
  let roots := if store then #[``Lemma.Courses.PackageStore.load] else
    #[``Lemma.Courses.PackageTarget.validate,``Lemma.Courses.PackageTarget.select,
      ``Lemma.Courses.PackageTarget.goal,``Lemma.Courses.PackageTarget.character]
  let suite ← match checkAndLowerActionSuiteForProfile env .user_v0_2 roots with
    | .ok value => pure value | .error error => throw <| IO.userError error.render
  unless suite.usedDeviceOps.isEmpty do throw <| IO.userError "course decoder acquired device effects"
  for operation in suite.usedExecutionOps do
    unless operation.sourceIdentity == ``Lemma.Core0.Execution.Op.virtualRead8 ||
      operation.sourceIdentity == ``Lemma.Core0.Execution.Op.virtualRead64 ||
      (store && (operation.sourceIdentity == ``Lemma.Core0.Execution.Op.virtualWrite8 ||
        operation.sourceIdentity == ``Lemma.Core0.Execution.Op.virtualWrite64 ||
        operation.sourceIdentity == ``Lemma.Core0.Execution.Op.syscall)) do
      throw <| IO.userError s!"course decoder acquired an undeclared operation {operation.sourceIdentity}"
  for name in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let source := ((Lean.privateToUserName? name).getD name).toString
    unless source.startsWith "Lemma.Courses.PackageTarget." || source.startsWith "Lemma.Courses.PackageFormat." ||
      source.startsWith "Lemma.User.Memory." ||
      (store && (source.startsWith "Lemma.Courses.PackageStore." || source.startsWith "Lemma.Services.Store.Client." ||
        source.startsWith "Lemma.Services.Store.Format." || source.startsWith "Lemma.Services.Store.Protocol." ||
        source.startsWith "Lemma.User.IPC." || source.startsWith "Lemma.User.IPCABI." ||
        source.startsWith "Lemma.User.Syscall.")) do
      throw <| IO.userError s!"unaccounted course dependency {name}"
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution .user_v0_2 suite {
    preserveCalls := preserved, symbolPrefix := "lemma_course_package_" }
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name, returnType := if spec.resultKind == .checked then .checkedResult else .i64,
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := if store then "genuine Lean course-package-v1 Store client" else "genuine Lean course-package-v1 guest decoder", declarations,
    functions := lowered.functions }
  IO.ofExcept <| LLVM.validateModule module
  let symbolFor (name : Name) : Except String String := do
    let some row := lowered.symbols.find? (fun row => row.source == name)
      | throw s!"missing genuine course symbol {name}"
    return row.llvm
  let mut functions : Array Json := #[]
  for f in suite.scalarFunctions do
    functions := functions.push <| Json.mkObj [
      ("source", .str ((Lean.privateToUserName? f.name).getD f.name).toString),
      ("symbol", .str (← IO.ofExcept <| symbolFor f.name)),
      ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))), ("effects", .arr #[])]
  for f in suite.actionFunctions do
    functions := functions.push <| Json.mkObj [
      ("source", .str ((Lean.privateToUserName? f.name).getD f.name).toString),
      ("symbol", .str (← IO.ofExcept <| symbolFor f.name)),
      ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))), ("effects", effects f.effects)]
  let mut selected : Array Json := #[]
  for root in roots do
    selected := selected.push <| Json.mkObj [("source", .str root.toString),
      ("symbol", .str (← IO.ofExcept <| symbolFor root))]
  let manifest := Json.mkObj [
    ("schema_version", toJson (1 : Nat)),
    ("artifact_category", .str (if store then "course-package-store-client-component" else "course-package-decoder-component")),
    ("contract_version", .str suite.contractVersion), ("package_format", .str "lemma-course-package/1"),
    ("roots", .arr selected), ("functions", .arr functions),
    ("used_execution_ops", .arr <| suite.usedExecutionOps.map fun spec => Json.mkObj [
      ("stable_id", .str spec.stableId), ("source_identity", .str spec.sourceIdentity.toString),
      ("primitive_symbol", spec.primitiveSymbol?.map Json.str |>.getD .null)]),
    ("used_device_ops", .arr #[]),
    ("qualification_scope", .str "component LLVM/object; notebook installation and RV64 execution not implied")]
  let normalized := String.join (suite.scalarFunctions.toList.map fun f =>
      s!"scalar={f.name}\n" ++ f.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun f =>
      s!"action={f.name};effects={f.effects.render}\n" ++ f.body.renderNormalized ++ "\n")
  IO.FS.createDirAll directory
  for (name, contents) in #[("program.ll",module.render),("unit.json",manifest.pretty ++ "\n"),
      ("symbols.txt",lowered.renderSymbolManifest),("normalized.txt",normalized)] do
    IO.FS.writeFile (directory / name) contents

syntax (name := lemmaExportCoursePackage) "#lemma_export_course_package" : command
syntax (name := lemmaExportCoursePackageStore) "#lemma_export_course_package_store" : command
elab_rules : command
  | `(#lemma_export_course_package) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_COURSE_PACKAGE_OUT"
      | throwError "LEMMA_COURSE_PACKAGE_OUT must name an unused output directory"
    liftIO <| exportFiles (← getEnv) (System.FilePath.mk output)
    logInfo "COURSE_PACKAGE_EXPORT:PASS genuine read-only User2 source/LLVM closure"
  | `(#lemma_export_course_package_store) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_COURSE_STORE_OUT"
      | throwError "LEMMA_COURSE_STORE_OUT must name an unused output directory"
    liftIO <| exportFiles (← getEnv) (System.FilePath.mk output) true
    logInfo "COURSE_PACKAGE_STORE_EXPORT:PASS genuine User2 copied-IPC/source/LLVM closure"

end Lemma.Compiler.CoursePackageExport
