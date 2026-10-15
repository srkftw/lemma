import Lean
import Lemma.Compiler.CFGLower
import Lemma.Applications.Notebook

/-! Actual declarations, checked existing User1 effects and LLVM lowering.
This compiler component does not establish RV64 or notebook acceptance. -/
open Lean Elab Command Lemma.Core0 Lemma.Compiler
def exportDirtySurface (env : Environment) : IO Unit := do
  let roots := #[`Lemma.Ink.Surface.uploadIndexedBulk, `Lemma.Applications.Notebook.pumpRefreshBatched]
  let suite ← IO.ofExcept <| (checkAndLowerActionSuiteForProfile env .user_v0_1 roots).mapError (·.render)
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution .user_v0_1 suite {symbolPrefix := "lemma_dirty_surface_"}
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      unless name == "lemma_exec_syscall" && spec.resultKind == .checked &&
          spec.machineArguments == #[.u64,.u64,.u64,.u64,.u64,.u64] do
        throw <| IO.userError "unaccounted dirty component external primitive"
      declarations := declarations.push {
        name := name
        returnType := .checkedResult
        parameters := spec.machineArguments.map (fun _ => .i64) }
  let module : LLVM.Module := {
    sourceName := "Genuine Lean dirty tile batch1"
    functions := lowered.functions
    declarations := declarations }
  IO.ofExcept <| LLVM.validateModule module
  let some out ← IO.getEnv "LEMMA_DIRTY_OUT" | throw <| IO.userError "LEMMA_DIRTY_OUT requires unused output"
  let path : System.FilePath := out
  if ← path.pathExists then throw <| IO.userError "retain existing dirty component export"
  let allowed := #["execution.virtual-read8", "execution.virtual-read64",
    "execution.virtual-write8", "execution.virtual-write64", "execution.syscall"]
  for op in suite.usedExecutionOps do
    unless allowed.contains op.stableId do throw <| IO.userError s!"undeclared dirty execution effect {op.stableId}"
  unless suite.usedDeviceOps.isEmpty do throw <| IO.userError "dirty guest acquired a hardware effect"
  let mut rows : Array Json := #[]
  for source in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let some symbol := lowered.symbols.find? (fun row => row.source == source)
      | throw <| IO.userError "missing actual dirty source symbol"
    rows := rows.push <| Json.mkObj [("source",.str source.toString),("symbol",.str symbol.llvm)]
  IO.FS.createDirAll path
  IO.FS.writeFile (path/"program.ll") module.render
  IO.FS.writeFile (path/"unit.json") <| (Json.mkObj [
    ("schema",.str "lemma-dirty-surface-component/1"),
    ("profile",.str Profile.user_v0_1.contractVersion),("functions",.arr rows),
    ("roots",.arr (roots.map fun root => .str root.toString)),
    ("scope",.str "Genuine checked Lean/LLVM component only; whole ordinary audits/execution pending")]).pretty++"\n"
  IO.println s!"DIRTY_SURFACE_GENUINE_LOWER:PASS {lowered.functions.size} functions"
run_cmd liftIO <| exportDirtySurface (← getEnv)
