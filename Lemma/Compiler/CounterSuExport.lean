import Lean
import Lemma.Compiler.CFGLower
import Lemma.Platform.RiscV.CounterSuPrimitives
import Lemma.Platform.RiscV.Development.CounterSuPolicy

/-! Genuine, closed development exporter for guest-issued CSR qualification.
The source frontend consumes ordinary elaborated declarations. No test AST,
LLVM algorithm or instruction program is manufactured by this exporter. -/
namespace Lemma.Compiler.CounterSuExport
open Lean Elab Command
open Lemma.Core0
open Lemma.Compiler

private def effects (value : EffectSet) : Json :=
  if value == .empty then .arr #[] else
    let interior := String.ofList (value.render.toList.drop 1 |>.reverse |>.drop 1 |>.reverse)
    .arr ((interior.splitOn ",").toArray.map Json.str)

private def executionJson (spec : Execution.OpSpec) : Json := Json.mkObj [
  ("stable_id", .str spec.stableId), ("source_identity", .str spec.sourceIdentity.toString),
  ("primitive_symbol", spec.primitiveSymbol?.map Json.str |>.getD .null),
  ("arguments", .arr (spec.machineArguments.map (Json.str ∘ Ty.render))),
  ("source_arguments", .arr (spec.sourceArguments.map (Json.str ∘ Ty.render))),
  ("meaningful_arguments", toJson spec.meaningfulArguments),
  ("result", .str spec.result.render),
  ("returnkind", .str (if spec.resultKind == .checked then "checked" else "word")),
  ("width_bytes", spec.widthBytes?.map toJson |>.getD .null),
  ("write", .bool spec.write), ("physical", .bool spec.physical)]

private def exportProbe (env : Environment) (directory : System.FilePath) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "counter exporter refuses retained output"
  let root := `Lemma.Platform.RiscV.Development.CounterSuPolicy.main
  let probe := `Lemma.Platform.RiscV.Development.CounterSuPolicy.probe
  let trap := `Lemma.Platform.RiscV.Development.CounterSuPolicy.trap
  let suite ← match checkAndLowerActionSuiteForProfile env .counter_su_v0_1 #[root, probe, trap] with
    | .ok value => pure value | .error e => throw <| IO.userError e.render
  unless suite.contractVersion == "core0-counter-su-v0.1" && suite.roots.size == 3 &&
      suite.roots[0]!.source == root && suite.roots[0]!.signature.args.isEmpty &&
      suite.roots[1]!.source == probe && suite.roots[1]!.signature.args == #[.u64,.u64] &&
      suite.roots[2]!.source == trap && suite.roots[2]!.signature.args == #[.u64,.u64,.u64] &&
      suite.usedLoops.isEmpty && suite.usedDeviceOps.isEmpty do
    throw <| IO.userError "counter unit escapes its declared source/loop/device closure"
  for f in suite.scalarFunctions do
    unless f.name.toString.startsWith "Lemma.Platform.RiscV.Development.CounterSuPolicy." do
      throw <| IO.userError s!"unaccounted counter scalar source {f.name}"
  for f in suite.actionFunctions do
    unless f.name.toString.startsWith "Lemma.Platform.RiscV.Development.CounterSuPolicy." do
      throw <| IO.userError s!"unaccounted counter action source {f.name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution .counter_su_v0_1 suite {
    preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
    symbolPrefix := "lemma_counter_su_" }
  let symbolFor (name : Name) : Except String String := do
    let some row := lowered.symbols.find? (fun row => row.source == name)
      | throw s!"missing genuine counter symbol {name}"
    pure row.llvm
  let entry ← IO.ofExcept <| symbolFor root
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := .i64
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := "genuine Lean guest-issued counter policy"
    declarations
    functions := lowered.functions }
  IO.ofExcept <| LLVM.validateModule module
  let mut functions : Array Json := #[]
  for f in suite.scalarFunctions do
    functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
      ("symbol", .str (← IO.ofExcept <| symbolFor f.name)),
      ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))), ("effects", .arr #[])]
  for f in suite.actionFunctions do
    functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
      ("symbol", .str (← IO.ofExcept <| symbolFor f.name)),
      ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))), ("effects", effects f.effects)]
  let unit := Json.mkObj [("schema_version", toJson (1 : Nat)),
    ("artifact_category", .str "development-counter-su-execution-unit"),
    ("configuration", .str "counter-su-csr-development"), ("contract_version", .str suite.contractVersion),
    ("role", .str "firmware"),
    ("roots", .arr (← suite.roots.mapM fun r => do pure <| Json.mkObj [
      ("source", .str r.source.toString), ("symbol", .str (← IO.ofExcept <| symbolFor r.source)),
      ("args", .arr (r.signature.args.map (Json.str ∘ Ty.render)))])),
    ("functions", .arr functions), ("used_execution_ops", .arr (suite.usedExecutionOps.map executionJson)),
    ("used_device_ops", .arr #[]), ("used_loops", .arr #[])]
  let normalized := String.join (suite.scalarFunctions.toList.map fun f =>
      s!"scalar={f.name}\n" ++ f.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun f =>
      s!"action={f.name};effects={f.effects.render}\n" ++ f.body.renderNormalized ++ "\n")
  let startup ← IO.ofExcept <| Lemma.Platform.RiscV.CounterSuPrimitives.render entry (← IO.ofExcept <| symbolFor probe) (← IO.ofExcept <| symbolFor trap)
  let layout := Lemma.Platform.RiscV.CounterSuPrimitives.layout
  let link ← IO.ofExcept layout.linkerScript
  let manifest ← IO.ofExcept layout.manifestJson
  IO.FS.createDirAll directory
  for (name, value) in #[("program.ll",module.render), ("unit.json",unit.pretty ++ "\n"),
      ("normalized.txt",normalized), ("symbols.txt",lowered.renderSymbolManifest),
      ("startup.S",startup), ("link.ld",link), ("layout.json",manifest)] do
    IO.FS.writeFile (directory / name) value

syntax (name := lemmaExportCounterSu) "#lemma_export_counter_su_probe" : command
elab_rules : command
  | `(#lemma_export_counter_su_probe) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_COUNTER_SU_OUTPUT"
      | throwError "LEMMA_COUNTER_SU_OUTPUT must name a new output directory"
    liftIO <| exportProbe (← getEnv) (System.FilePath.mk output)
    logInfo "COUNTER_SU_EXPORT:PASS genuine elaboration and checked core0-counter-su-v0.1 lowering"

end Lemma.Compiler.CounterSuExport
