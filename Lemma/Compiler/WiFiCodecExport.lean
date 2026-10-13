import Lean
import Lemma.Compiler.CFGLower
import Lemma.Platform.RiscV.CounterPrimitives
import Lemma.Platform.RiscV.Development.WiFiCodecPolicy

/-! Genuine, closed development exporter for guest-issued Wi-Fi coding qualification.
The source frontend consumes ordinary elaborated declarations. No test AST,
LLVM algorithm or instruction program is manufactured by this exporter. -/
namespace Lemma.Compiler.WiFiCodecExport
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
  if ← directory.pathExists then throw <| IO.userError "Wi-Fi codec exporter refuses retained output"
  let root := `Lemma.Platform.RiscV.Development.WiFiCodecPolicy.main
  let suite ← match checkAndLowerActionSuiteForProfile env .firmware_v0_2 #[root] with
    | .ok value => pure value | .error e => throw <| IO.userError e.render
  unless suite.contractVersion == "core0-firmware-v0.2" && suite.roots.size == 1 &&
      suite.roots[0]!.source == root && suite.roots[0]!.signature.args.isEmpty &&
      suite.usedLoops.isEmpty && suite.usedDeviceOps.isEmpty do
    throw <| IO.userError "Wi-Fi codec unit escapes its declared source/loop/device closure"
  for f in suite.scalarFunctions do
    let source := ((Lean.privateToUserName? f.name).getD f.name).toString
    unless source.startsWith "Lemma.Platform.RiscV.Development.WiFiCodecPolicy." ||
      source.startsWith "Lemma.Radio.WiFi.Codec." do
      throw <| IO.userError s!"unaccounted Wi-Fi codec scalar source {f.name}"
  for f in suite.actionFunctions do
    let source := ((Lean.privateToUserName? f.name).getD f.name).toString
    unless source.startsWith "Lemma.Platform.RiscV.Development.WiFiCodecPolicy." ||
      source.startsWith "Lemma.Radio.WiFi.Codec." do
      throw <| IO.userError s!"unaccounted Wi-Fi codec action source {f.name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution .firmware_v0_2 suite {
    preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
    symbolPrefix := "lemma_wifi_codec_" }
  let symbolFor (name : Name) : Except String String := do
    let some row := lowered.symbols.find? (fun row => row.source == name)
      | throw s!"missing genuine Wi-Fi codec symbol {name}"
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
    sourceName := "genuine Lean guest-issued Wi-Fi codec policy"
    declarations
    functions := lowered.functions }
  IO.ofExcept <| LLVM.validateModule module
  let mut functions : Array Json := #[]
  for f in suite.scalarFunctions do
    functions := functions.push <| Json.mkObj [("source", .str ((Lean.privateToUserName? f.name).getD f.name).toString),
      ("symbol", .str (← IO.ofExcept <| symbolFor f.name)),
      ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))), ("effects", .arr #[])]
  for f in suite.actionFunctions do
    functions := functions.push <| Json.mkObj [("source", .str ((Lean.privateToUserName? f.name).getD f.name).toString),
      ("symbol", .str (← IO.ofExcept <| symbolFor f.name)),
      ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))), ("effects", effects f.effects)]
  let unit := Json.mkObj [("schema_version", toJson (1 : Nat)),
    ("artifact_category", .str "development-wifi-codec-execution-unit"),
    ("configuration", .str "wifi-codec-development"), ("contract_version", .str suite.contractVersion),
    ("role", .str "firmware"),
    ("roots", .arr #[Json.mkObj [("source", .str root.toString), ("symbol", .str entry), ("args", .arr #[])]]),
    ("functions", .arr functions), ("used_execution_ops", .arr (suite.usedExecutionOps.map executionJson)),
    ("used_device_ops", .arr #[]), ("used_loops", .arr #[])]
  let normalized := String.join (suite.scalarFunctions.toList.map fun f =>
      s!"scalar={f.name}\n" ++ f.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun f =>
      s!"action={f.name};effects={f.effects.render}\n" ++ f.body.renderNormalized ++ "\n")
  -- Reuse the existing structured M-mode diagnostic startup only. No CSR
  -- helpers or foreign algorithm bodies are linked into this pure codec image.
  let lines := Lemma.Platform.RiscV.CounterPrimitives.startup entry
  let startup := String.intercalate "\n" <| [".option push", ".option norelax", ".option norvc",
    ".section .text.start, \"ax\", @progbits", ".balign 4", ".globl _start", ".type _start, @function"] ++
    lines.toList.map Lemma.Machine.Primitives.Line.render ++ [".size _start, . - _start", ".option pop",
      ".section .note.GNU-stack, \"\", @progbits", ""]
  let layout := Lemma.Platform.RiscV.CounterPrimitives.layout
  let link ← IO.ofExcept layout.linkerScript
  let manifest ← IO.ofExcept layout.manifestJson
  IO.FS.createDirAll directory
  for (name, value) in #[("program.ll",module.render), ("unit.json",unit.pretty ++ "\n"),
      ("normalized.txt",normalized), ("symbols.txt",lowered.renderSymbolManifest),
      ("startup.S",startup), ("link.ld",link), ("layout.json",manifest)] do
    IO.FS.writeFile (directory / name) value

syntax (name := lemmaExportWiFiCodec) "#lemma_export_wifi_codec_probe" : command
elab_rules : command
  | `(#lemma_export_wifi_codec_probe) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_WIFI_GUEST_OUTPUT"
      | throwError "LEMMA_WIFI_GUEST_OUTPUT must name a new output directory"
    liftIO <| exportProbe (← getEnv) (System.FilePath.mk output)
    logInfo "WIFI_CODEC_EXPORT:PASS genuine elaboration and checked core0-firmware-v0.2 lowering"

end Lemma.Compiler.WiFiCodecExport
