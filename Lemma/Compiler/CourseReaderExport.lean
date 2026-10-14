import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.Courses.PackageReader
import Lemma.Courses.PackageBinding

/-! Genuine source exporter for the read-only cooperative package reader. It asks
the maintained frontend to inspect ordinary elaborated declarations, checks
their complete dependency/effect closure, and validates lowered LLVM. -/
namespace Lemma.Compiler.CourseReaderExport
open Lean Elab Command
open Lemma.Core0

private def effects (value : EffectSet) : Json :=
  if value == .empty then .arr #[] else
    let interior := String.ofList (value.render.toList.drop 1 |>.reverse |>.drop 1 |>.reverse)
    .arr ((interior.splitOn ",").toArray.map Json.str)

def exportFiles (env : Environment) (directory : System.FilePath) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "course decoder exporter refuses retained output"
  let roots := #[``Lemma.Courses.PackageReader.start, ``Lemma.Courses.PackageReader.step,
    ``Lemma.Courses.PackageReader.finish, ``Lemma.Courses.PackageReader.cancel,
    ``Lemma.Courses.PackageBinding.capture, ``Lemma.Courses.PackageBinding.validate,
    ``Lemma.Courses.PackageBinding.applicable]
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
    unless #["Lemma.Courses.PackageReader.","Lemma.Courses.PackageBinding.","Lemma.Courses.PackageTarget.",
      "Lemma.Courses.PackageFormat.","Lemma.Services.Store.Client.","Lemma.Services.Store.Format.",
      "Lemma.Services.Store.Protocol.","Lemma.User.Memory.","Lemma.User.IPC.","Lemma.User.IPCABI.",
      "Lemma.User.Syscall."].any (fun stem => source.startsWith stem) ||
        source == "Lemma.Core0.Memory.Status.iterationStop" do
      throw <| IO.userError s!"unaccounted course-install dependency {name}"
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution .user_v0_2 suite {
    preserveCalls := preserved, symbolPrefix := "lemma_course_reader_" }
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name, returnType := if spec.resultKind == .checked then .checkedResult else .i64,
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := "genuine Lean course-reader-v1 copied-IPC client", declarations,
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
    ("artifact_category", .str "course-reader-component"),
    ("contract_version", .str suite.contractVersion), ("package_format", .str "lemma-course-package/1"),
    ("reader_contract", .str "lemma-course-reader/1"),
    ("selection_binding_contract", .str "lemma-course-selection-binding/1"),
    ("maximum_requests", toJson (256 : Nat)), ("maximum_chunk_bytes", toJson (128 : Nat)),
    ("context_bytes", toJson (128 : Nat)), ("maximum_call_ticks", toJson (300000000 : Nat)),
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

syntax (name := lemmaExportCourseReader) "#lemma_export_course_reader" : command
elab_rules : command
  | `(#lemma_export_course_reader) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_COURSE_READER_OUT"
      | throwError "LEMMA_COURSE_READER_OUT must name an unused output directory"
    liftIO <| exportFiles (← getEnv) (System.FilePath.mk output)
    logInfo "COURSE_READER_EXPORT:PASS genuine User2 cooperative copied-IPC/validation/LLVM closure"

end Lemma.Compiler.CourseReaderExport
