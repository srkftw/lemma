import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.Courses.ReaderLocation

/-! Genuine component export, not an installed Notebook or proof authority.
Every body comes from ordinary elaborated declarations and the maintained
User2 checker/lowering. No target syntax tree is manufactured by this exporter.
-/
namespace Lemma.Compiler.ReaderLocationExport
open Lean Elab Command Lemma.Core0

def exportFiles (env : Environment) (out : System.FilePath) : IO Unit := do
  if ← out.pathExists then throw <| IO.userError "unused reader-location output required"
  let profile := Profile.user_v0_2
  let roots := #[``Lemma.Courses.ReaderLocation.capture,
    ``Lemma.Courses.ReaderLocation.validate, ``Lemma.Courses.ReaderLocation.resolve]
  let suite ← IO.ofExcept <| (checkAndLowerActionSuiteForProfile env profile roots).mapError (·.render)
  unless suite.usedDeviceOps.isEmpty do throw <| IO.userError "reader location acquired device authority"
  for op in suite.usedExecutionOps do
    unless #[``Lemma.Core0.Execution.Op.virtualRead8, ``Lemma.Core0.Execution.Op.virtualRead64,
      ``Lemma.Core0.Execution.Op.virtualWrite8, ``Lemma.Core0.Execution.Op.virtualWrite64].contains op.sourceIdentity do
      throw <| IO.userError s!"reader location acquired undeclared effect {op.sourceIdentity}"
  let sources := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  for source in sources do
    let name := ((privateToUserName? source).getD source).toString
    unless #["Lemma.Courses.ReaderLocation.", "Lemma.Courses.PackageTarget.",
      "Lemma.Courses.PackageFormat.", "Lemma.User.Memory."].any (fun stem => name.startsWith stem) ||
        name == "Lemma.Core0.Memory.Status.iterationStop" do
      throw <| IO.userError s!"unaccounted reader-location dependency {name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {
    preserveCalls := sources, symbolPrefix := "lemma_course_location_" }
  let mut declarations : Array LLVM.Declaration := #[]
  for op in suite.usedExecutionOps do
    if let some name := op.primitiveSymbol? then
      declarations := declarations.push {
        name, returnType := if op.resultKind == .checked then .checkedResult else .i64,
        parameters := op.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := "genuine Lean reader-location1, browsing only"
    declarations, functions := lowered.functions }
  IO.ofExcept <| LLVM.validateModule module
  let symbol (source : Name) : Except String String := do
    let some row := lowered.symbols.find? (·.source == source) | throw "missing source-derived symbol"
    return row.llvm
  let entries ← roots.mapM fun source => do
    pure <| Json.mkObj [("source",toJson source.toString),
      ("symbol",toJson (← IO.ofExcept <| symbol source))]
  let mut rows : Array Json := #[]
  for f in suite.scalarFunctions do
    rows := rows.push <| Json.mkObj [("source",toJson f.name.toString),
      ("symbol",toJson (← IO.ofExcept <| symbol f.name)),("args",toJson (f.signature.args.map Ty.render)),
      ("effects",toJson "pure")]
  for f in suite.actionFunctions do
    rows := rows.push <| Json.mkObj [("source",toJson f.name.toString),
      ("symbol",toJson (← IO.ofExcept <| symbol f.name)),("args",toJson (f.signature.args.map Ty.render)),
      ("effects",toJson f.effects.render)]
  let unit := Json.mkObj [("schema",toJson "lemma-reader-location-component/1"),
    ("contract_version",toJson profile.contractVersion),("roots",.arr entries),("functions",.arr rows),
    ("execution_ops",toJson (suite.usedExecutionOps.map (·.stableId))),
    ("allowed_helper_symbols",toJson (suite.usedExecutionOps.filterMap (·.primitiveSymbol?))),
    ("device_ops",.arr #[]),("scope",toJson "Genuine component only; guest Store integration and CPU execution pending")]
  IO.FS.createDirAll out
  IO.FS.writeFile (out/"program.ll") module.render
  IO.FS.writeFile (out/"unit.json") (unit.pretty++"\n")
  IO.FS.writeFile (out/"symbols.txt") lowered.renderSymbolManifest

syntax (name := lemmaExportReaderLocation) "#lemma_export_reader_location" : command
elab_rules : command
  | `(#lemma_export_reader_location) => do
    let some out ← liftIO <| IO.getEnv "LEMMA_READER_LOCATION_OUT"
      | throwError "LEMMA_READER_LOCATION_OUT requires unused output"
    liftIO <| exportFiles (← getEnv) out
    logInfo "READER_LOCATION_GENUINE_EXPORT:PASS User2 source/checked LLVM; browsing only"
end Lemma.Compiler.ReaderLocationExport
