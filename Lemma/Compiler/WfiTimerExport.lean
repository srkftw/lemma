import Lean
import Lemma.Compiler.CFGLower
import Lemma.Platform.RiscV.ExecutionPrimitives
import Lemma.Platform.RiscV.Development.WfiTimerPolicy
import Lemma.Platform.RiscV.Development.WfiTimerFirmware

/-! Dedicated source-derived diagnostic exporter. Both privilege units use
existing profiles. Startup comes only from the unchanged structured renderer. -/
namespace Lemma.Compiler.WfiTimerExport
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
open Lemma.Platform.LemmaVM

private def effects (value : EffectSet) : Json :=
  if value == .empty then .arr #[] else
    let interior := String.ofList (value.render.toList.drop 1 |>.reverse |>.drop 1 |>.reverse)
    .arr ((interior.splitOn ",").toArray.map Json.str)

private def operationJson (spec : Execution.OpSpec) : Json := Json.mkObj [
  ("stable_id", .str spec.stableId), ("source_identity", .str spec.sourceIdentity.toString),
  ("primitive_symbol", spec.primitiveSymbol?.map Json.str |>.getD .null),
  ("arguments", .arr (spec.machineArguments.map (Json.str ∘ Ty.render))),
  ("source_arguments", .arr (spec.sourceArguments.map (Json.str ∘ Ty.render))),
  ("meaningful_arguments", toJson spec.meaningfulArguments),
  ("result", .str spec.result.render),
  ("returnkind", .str (if spec.resultKind == .checked then "checked" else "word")),
  ("width_bytes", spec.widthBytes?.map toJson |>.getD .null),
  ("write", .bool spec.write), ("physical", .bool spec.physical)]

private def emitUnit (env : Environment) (directory : System.FilePath)
    (profile : Profile) (role : String) (roots : Array Name) : IO LoweredActionSuite := do
  let suite ← match checkAndLowerActionSuiteForProfile env profile roots with
    | .ok value => pure value | .error e => throw <| IO.userError e.render
  unless suite.contractVersion == profile.contractVersion && suite.roots.size == roots.size &&
      suite.usedLoops.isEmpty && suite.usedDeviceOps.isEmpty &&
      suite.usedTimerOps.isEmpty && suite.usedTrapOps.isEmpty do
    throw <| IO.userError "WFI diagnostic escapes its existing execution profile"
  for f in suite.scalarFunctions do
    let isStop := f.name == `Lemma.Core0.Memory.Status.iterationStop &&
      f.signature.args.isEmpty && f.signature.result == .u8 && f.body == .lit .u8 10
    unless isStop || f.name.toString.startsWith "Lemma.Platform.RiscV.Development.WfiTimer" ||
        (role == "firmware" && f.name.toString.startsWith "Lemma.Platform.RiscV.Firmware.") do
      throw <| IO.userError s!"unaccounted WFI scalar source {f.name}"
  for f in suite.actionFunctions do
    unless f.name.toString.startsWith "Lemma.Platform.RiscV.Development.WfiTimer" ||
        (role == "firmware" && f.name.toString.startsWith "Lemma.Platform.RiscV.Firmware.") do
      throw <| IO.userError s!"unaccounted WFI Action source {f.name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {
    preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
    symbolPrefix := if role == "firmware" then "lemma_wfi_m_" else "lemma_wfi_s_" }
  let symbolFor (name : Name) : Except String String := do
    let some row := lowered.symbols.find? (fun row => row.source == name)
      | throw s!"missing source-derived WFI symbol {name}"
    pure row.llvm
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {
    sourceName := s!"genuine Lean WFI {role} diagnostic"
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
    ("artifact_category", .str "development-wfi-timer-execution-unit"),
    ("configuration", .str "wfi-timer-development-v1"),
    ("contract_version", .str suite.contractVersion), ("role", .str role),
    ("roots", .arr (← suite.roots.mapM fun r => do pure <| Json.mkObj [
      ("source", .str r.source.toString), ("symbol", .str (← IO.ofExcept <| symbolFor r.source)),
      ("args", .arr (r.signature.args.map (Json.str ∘ Ty.render)))])),
    ("functions", .arr functions),
    ("used_execution_ops", .arr (suite.usedExecutionOps.map operationJson)),
    ("used_device_ops", .arr #[]), ("used_loops", .arr #[])]
  let normalized := String.join (suite.scalarFunctions.toList.map fun f =>
      s!"scalar={f.name}\n" ++ f.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun f =>
      s!"action={f.name};effects={f.effects.render}\n" ++ f.body.renderNormalized ++ "\n")
  IO.FS.createDirAll directory
  for (name, value) in #[("program.ll",module.render), ("unit.json",unit.pretty ++ "\n"),
      ("normalized.txt",normalized), ("symbols.txt",lowered.renderSymbolManifest)] do
    IO.FS.writeFile (directory / name) value
  pure lowered

private def exportProbe (env : Environment) (directory : System.FilePath) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "WFI exporter refuses retained output"
  let kernel ← emitUnit env (directory / "kernel") .kernel_v0_4 "kernel" #[
    `Lemma.Platform.RiscV.Development.WfiTimerPolicy.main,
    `Lemma.Platform.RiscV.Development.WfiTimerPolicy.dispatch]
  let firmware ← emitUnit env (directory / "firmware") .firmware_v0_1 "firmware" #[
    `Lemma.Platform.RiscV.Development.WfiTimerFirmware.dispatch]
  let symbolFor (lowered : LoweredActionSuite) (name : Name) : Except String String := do
    let some row := lowered.symbols.find? (fun row => row.source == name)
      | throw s!"missing source-derived WFI root {name}"
    pure row.llvm
  let config : Lemma.Platform.RiscV.ExecutionPrimitives.Configuration := {
    stage := .supervisor
    lemmasim := true
    kernelMain := ← IO.ofExcept <| symbolFor kernel `Lemma.Platform.RiscV.Development.WfiTimerPolicy.main
    supervisorDispatcher := ← IO.ofExcept <| symbolFor kernel `Lemma.Platform.RiscV.Development.WfiTimerPolicy.dispatch
    firmwareDispatcher := ← IO.ofExcept <| symbolFor firmware `Lemma.Platform.RiscV.Development.WfiTimerFirmware.dispatch }
  let startup ← IO.ofExcept <| Lemma.Platform.RiscV.ExecutionPrimitives.renderStartup config
  let linker := String.intercalate "\n" [
    "OUTPUT_ARCH(riscv)", "ENTRY(_start)",
    "PHDRS { firmware PT_LOAD FLAGS(5); supervisor PT_LOAD FLAGS(5); storage PT_LOAD FLAGS(6); }",
    "SECTIONS {", s!"  . = {Layout.firmwareBase};",
    "  .firmware : ALIGN(4096) { startup.o(.text.firmware) firmware/program.o(.text .text.* .rodata .rodata.*) } :firmware",
    s!"  ASSERT(. <= {Layout.firmwareLimit}, \"firmware envelope exceeded\")",
    s!"  . = {Layout.supervisorBase};",
    "  .text : ALIGN(4096) { startup.o(.text.platform) kernel/program.o(.text .text.* .rodata .rodata.*) } :supervisor",
    s!"  ASSERT(. <= {Layout.supervisorLimit}, \"supervisor envelope exceeded\")",
    s!"  . = {Layout.metadataBase};", "  __bss_start = .;",
    "  .kernel_storage (NOLOAD) : ALIGN(64) { __boot_hartid = .; . += 8; __boot_dtb = .; . += 120; } :storage",
    "  __bss_end = .;", s!"  ASSERT(__bss_end == {Layout.metadataBase + 128}, \"boot clear interval differs\")",
    "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }", "}", ""]
  let primitives := Lemma.Platform.RiscV.ExecutionPrimitives.primitiveCatalog config
  let layout := Json.mkObj [("schema_version", toJson (1 : Nat)),
    ("contract_version", .str "lemma-wfi-timer-diagnostic-v1"),
    ("record_base", toJson (0x80410000 : Nat)), ("record_bytes", toJson (32768 : Nat)),
    ("trace_base", toJson (0x80101000 : Nat)), ("trace_bytes", toJson (256 : Nat)),
    ("boot_clear_base", toJson Layout.metadataBase), ("boot_clear_bytes", toJson (128 : Nat)),
    ("primitives", .arr (primitives.map fun (name, privilege, effect) => Json.mkObj [
      ("symbol", .str name), ("privilege", .str privilege), ("effect", .str effect)]))]
  for (name, value) in #[("startup.S",startup), ("link.ld",linker), ("layout.json",layout.pretty ++ "\n")] do
    IO.FS.writeFile (directory / name) value

syntax (name := lemmaExportWfiTimer) "#lemma_export_wfi_timer_probe" : command
elab_rules : command
  | `(#lemma_export_wfi_timer_probe) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_WFI_TIMER_OUTPUT"
      | throwError "LEMMA_WFI_TIMER_OUTPUT must name a new output directory"
    liftIO <| exportProbe (← getEnv) (System.FilePath.mk output)
    logInfo "WFI_TIMER_EXPORT:PASS genuine existing-profile elaboration and checked lowering"

end Lemma.Compiler.WfiTimerExport
