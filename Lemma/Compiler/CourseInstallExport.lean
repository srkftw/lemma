import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.Courses.PackageTarget
import Lemma.Courses.PackageStore
import Lemma.Courses.PackageInstaller
import Lemma.Services.Store.Server

/-! Genuine source exporter for the guest course installer and opt-in Store guard. It asks
the maintained frontend to inspect ordinary elaborated declarations, checks
their complete dependency/effect closure, and validates lowered LLVM. -/
namespace Lemma.Compiler.CourseInstallExport
open Lean Elab Command
open Lemma.Core0

private def effects (value : EffectSet) : Json :=
  if value == .empty then .arr #[] else
    let interior := String.ofList (value.render.toList.drop 1 |>.reverse |>.drop 1 |>.reverse)
    .arr ((interior.splitOn ",").toArray.map Json.str)

def exportFiles (env : Environment) (directory : System.FilePath) (guard : Bool := false) (selection : Bool := false) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "course decoder exporter refuses retained output"
  let roots := if guard then #[``Lemma.Services.Store.Server.courseMain] else
    if selection then #[``Lemma.Courses.PackageInstaller.mainAwaitSelected] else
    #[``Lemma.Courses.PackageStore.install, ``Lemma.Courses.PackageInstaller.main]
  let suite ← match checkAndLowerActionSuiteForProfile env .user_v0_2 roots with
    | .ok value => pure value | .error error => throw <| IO.userError error.render
  unless suite.usedDeviceOps.isEmpty do throw <| IO.userError "course decoder acquired device effects"
  for operation in suite.usedExecutionOps do
    unless #[``Lemma.Core0.Execution.Op.virtualRead8, ``Lemma.Core0.Execution.Op.virtualRead64,
      ``Lemma.Core0.Execution.Op.virtualWrite8, ``Lemma.Core0.Execution.Op.virtualWrite64,
      ``Lemma.Core0.Execution.Op.syscall].contains operation.sourceIdentity do
      throw <| IO.userError s!"course installer acquired an undeclared operation {operation.sourceIdentity}"
  for name in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let source := ((Lean.privateToUserName? name).getD name).toString
    unless #["Lemma.Courses.PackageTarget.","Lemma.Courses.PackageFormat.",
      "Lemma.Courses.PackageStore.","Lemma.Courses.PackageCommand.",
      "Lemma.Courses.PackageInstaller.","Lemma.Courses.PackageAwaitClient.",
      "Lemma.Courses.PackageAwaitProtocol.","Lemma.Services.Store.","Lemma.User."].any
        (fun stem => source.startsWith stem) || source == "Lemma.Core0.Memory.Status.iterationStop" do
      throw <| IO.userError s!"unaccounted course-install dependency {name}"
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution .user_v0_2 suite {
    preserveCalls := preserved, symbolPrefix := "lemma_course_install_" }
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name, returnType := if spec.resultKind == .checked then .checkedResult else .i64,
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := if guard then "genuine Lean course-store-guard-v1 service" else
      if selection then "genuine Lean course-command-v2 selected-publication installer" else
      "genuine Lean course-command-v1 installer", declarations,
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
    ("artifact_category", .str (if guard then "course-store-guard-component" else
      if selection then "course-selection-component" else "course-install-component")),
    ("contract_version", .str suite.contractVersion), ("package_format", .str "lemma-course-package/1"),
    ("roots", .arr selected), ("functions", .arr functions),
    ("used_execution_ops", .arr <| suite.usedExecutionOps.map fun spec => Json.mkObj [
      ("stable_id", .str spec.stableId), ("source_identity", .str spec.sourceIdentity.toString),
      ("primitive_symbol", spec.primitiveSymbol?.map Json.str |>.getD .null)]),
    ("used_device_ops", .arr #[]),
    ("qualification_scope", .str "component LLVM/object; CPU execution and durable media not implied")]
  let normalized := String.join (suite.scalarFunctions.toList.map fun f =>
      s!"scalar={f.name}\n" ++ f.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun f =>
      s!"action={f.name};effects={f.effects.render}\n" ++ f.body.renderNormalized ++ "\n")
  IO.FS.createDirAll directory
  for (name, contents) in #[("program.ll",module.render),("unit.json",manifest.pretty ++ "\n"),
      ("symbols.txt",lowered.renderSymbolManifest),("normalized.txt",normalized)] do
    IO.FS.writeFile (directory / name) contents

syntax (name := lemmaExportCourseInstall) "#lemma_export_course_install" : command
syntax (name := lemmaExportCourseSelection) "#lemma_export_course_selection" : command
syntax (name := lemmaExportCourseGuard) "#lemma_export_course_guard" : command
elab_rules : command
  | `(#lemma_export_course_install) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_COURSE_INSTALL_OUT"
      | throwError "LEMMA_COURSE_INSTALL_OUT must name an unused output directory"
    liftIO <| exportFiles (← getEnv) (System.FilePath.mk output)
    logInfo "COURSE_INSTALL_EXPORT:PASS genuine User2 copied-IPC/console/source/LLVM closure"
  | `(#lemma_export_course_selection) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_COURSE_SELECTION_OUT"
      | throwError "LEMMA_COURSE_SELECTION_OUT must name an unused output directory"
    liftIO <| exportFiles (← getEnv) (System.FilePath.mk output) false true
    logInfo "COURSE_SELECTION_EXPORT:PASS genuine User2 copied-IPC/selection/console/source/LLVM closure"
  | `(#lemma_export_course_guard) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_COURSE_GUARD_OUT"
      | throwError "LEMMA_COURSE_GUARD_OUT must name an unused output directory"
    liftIO <| exportFiles (← getEnv) (System.FilePath.mk output) true
    logInfo "COURSE_GUARD_EXPORT:PASS genuine User2 opt-in Store/source/LLVM closure"

end Lemma.Compiler.CourseInstallExport
