import Lean
import Lemma.Compiler.CFGLower
import Lemma.Courses.ControlRender

/-! Actual declarations only: source -> elaboration -> checked scalar/effect
suite -> existing LLVM lowering. This component is not an installed Notebook. -/
namespace Lemma.Compiler.ControlRenderExport
open Lean Lemma.Core0
def exportFiles (env : Environment) (out : System.FilePath) : IO Unit := do
  if ← out.pathExists then throw <| IO.userError "unused control export required"
  let profile := Profile.user_v0_1
  let roots := #[``Lemma.Courses.ControlRender.renderControls, ``Lemma.Courses.ControlRender.renderIdentity]
  let suite ← IO.ofExcept <| (checkAndLowerActionSuiteForProfile env profile roots).mapError (·.render)
  for source in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let name := ((Lean.privateToUserName? source).getD source).toString
    unless name.startsWith "Lemma.Courses.ControlRender." || name.startsWith "Lemma.Courses.PackageRender.alignedSpanWord" ||
      name.startsWith "Lemma.Courses.PackageRender.packedCellRow" || name.startsWith "Lemma.Courses.PackageRender.glyph" ||
      name.startsWith "Lemma.Ink.Surface.letter" || name == "Lemma.Ink.Surface.framebuffer" || name.startsWith "Lemma.User.Memory." do
      throw <| IO.userError s!"unaccounted control source {name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {symbolPrefix := "lemma_course_control_"}
  let module : LLVM.Module := {
    sourceName := "Lean course-control aligned spans1"
    functions := lowered.functions.map fun f => {f with attributes := f.attributes.push "\"no-jump-tables\"=\"true\""} }
  IO.ofExcept <| LLVM.validateModule module
  let mut rows : Array Json := #[]
  for source in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let some entry := lowered.symbols.find? (fun row => row.source == source)
      | throw <| IO.userError "missing genuine control symbol"
    rows := rows.push <| Json.mkObj [("source",.str source.toString),("symbol",.str entry.llvm)]
  let unit := Json.mkObj [("schema",.str "lemma-course-control-aligned/1"),
    ("contract_version",.str profile.contractVersion),("functions",.arr rows),
    ("roots",.arr (roots.map fun root => .str root.toString)),
    ("execution_ops",.arr (suite.usedExecutionOps.map fun op => .str op.stableId)),
    ("device_ops",.arr (suite.usedDeviceOps.map fun op => .str op.stableId)),
    ("scope",.str "Genuine component only; installed Notebook and CPU/controller qualification separate")]
  IO.FS.createDirAll out
  IO.FS.writeFile (out/"program.ll") module.render
  IO.FS.writeFile (out/"unit.json") (unit.pretty++"\n")
end Lemma.Compiler.ControlRenderExport
open Lean Elab Command
syntax (name := lemmaExportControls) "#lemma_export_controls" : command
elab_rules : command
  | `(#lemma_export_controls) => do
    let some out ← liftIO <| IO.getEnv "LEMMA_CONTROL_OUT" | throwError "LEMMA_CONTROL_OUT requires unused output"
    liftIO <| Lemma.Compiler.ControlRenderExport.exportFiles (← getEnv) out
    logInfo "CONTROL_GENUINE_EXPORT:PASS"
