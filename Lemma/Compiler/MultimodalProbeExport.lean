import Lean
import Lemma.Compiler.CFGLower
import Lemma.Machine.Primitives
import Lemma.Multimodal.ControllerProbe

namespace Lemma.Compiler.MultimodalProbeExport
open Lean Lemma.Core0 Lemma.Machine.Primitives
private def startup (entry : String) : String :=
  let lines : Array Line := #[.label "_reset",.instruction (.csrWrite .mie .zero),
    .instruction .maskMachineInterruptEnable,.instruction (.csrWrite .satp .zero),
    .instruction (.loadImmediate .sp 0x81fb0000),.instruction (.call entry),
    .label ".Lcrypto_halt",.instruction .waitForInterrupt,.instruction (.jump ".Lcrypto_halt")]
  String.intercalate "\n" ([".option norvc",".option norelax",".section .text.reset, \"ax\", @progbits",
    ".globl _reset",".type _reset, @function",".balign 4"] ++ lines.toList.map Line.render ++
    [".size _reset, .-_reset",".section .text.io, \"ax\", @progbits",".globl core0_io_fence",
      ".type core0_io_fence, @function",".balign 4",(Line.label "core0_io_fence").render,
      (Line.instruction .fenceIO).render,(Line.instruction .return).render,
      ".size core0_io_fence, .-core0_io_fence",".section .note.GNU-stack, \"\", @progbits",""])
private def linker : String := String.intercalate "\n" [
  "OUTPUT_ARCH(riscv)","ENTRY(_reset)","PHDRS { code PT_LOAD FLAGS(5); }","SECTIONS {",
  " . = 0x80000000;"," .text : ALIGN(4) { KEEP(startup.o(.text.reset)) startup.o(.text.io) *(.text .text.*) } :code",
  " .rodata : ALIGN(8) { *(.rodata.cst8) } :code",
  " ASSERT(. <= 0x80010000, \"crypto component executable envelope exceeded\")",
  " /DISCARD/ : { *(.comment) *(.note.GNU-stack) *(.eh_frame*) }","}",""]
def exportFiles (env : Environment) (directory : System.FilePath) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "crypto exporter requires unused output"
  let profile := Profile.kernel_v0_9
  let suite ← match checkAndLowerActionSuiteForProfile env profile #[``Lemma.Multimodal.ControllerProbe.entry] with
    | .ok value => pure value | .error error => throw <| IO.userError error.render
  for op in suite.usedExecutionOps do
    unless op.stableId == "execution.physical-read64" || op.stableId == "execution.physical-write64" ||
      op.stableId == "lemmasim.device-read64" || op.stableId == "lemmasim.device-write64" do
      throw <| IO.userError s!"unaccounted multimodal probe operation {op.stableId}"
  for name in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let name := ((Lean.privateToUserName? name).getD name).toString
    unless name.startsWith "Lemma.Multimodal.ControllerProbe." || name.startsWith "Lemma.Drivers.Multimodal." ||
      name.startsWith "Lemma.Platform.Silicon.BindingMultimodal." || name.startsWith "Lemma.Platform.LemmaSim.IO." ||
      name.startsWith "Lemma.Kernel.Memory.Access." || name.startsWith "Lemma.Boot.RecoveryExecuted.transmit" ||
      name == "Lemma.Core0.Memory.Status.iterationStop" || name == "Lemma.Core0.Memory.Status.txTimeout" do
      throw <| IO.userError s!"unaccounted multimodal probe source {name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {symbolPrefix := "lemma_multimodal_probe_"}
  let some entry := lowered.symbols.find? (fun row => row.source == ``Lemma.Multimodal.ControllerProbe.entry)
    | throw <| IO.userError "missing actual crypto entry"
  let module : LLVM.Module := {
    sourceName := "Lemma genuinely elaborated RV64 converter/PCM workload"
    functions := lowered.functions.map fun f => {f with attributes := f.attributes.push "\"no-jump-tables\"=\"true\""}
    declarations := #[{name := "core0_io_fence",returnType := .void,parameters := #[]}] }
  IO.ofExcept <| LLVM.validateModule module
  let mut functions : Array Json := #[]
  for f in suite.scalarFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing actual crypto scalar"
    functions := functions.push <| Json.mkObj [("source",.str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",.str "{}")]
  for f in suite.actionFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing actual crypto action"
    functions := functions.push <| Json.mkObj [("source",.str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",.str f.effects.render)]
  let unit := Json.mkObj [("schema",.str "lemma-multimodal-controller-rv64-component/1"),("contract_version",.str profile.contractVersion),
    ("root",.str "Lemma.Multimodal.ControllerProbe.entry"),("entry_symbol",.str entry.llvm),("functions",.arr functions),
    ("used_execution_ops",.arr (suite.usedExecutionOps.map (Json.str ∘ (·.stableId)))),
    ("used_device_ops",.arr (suite.usedDeviceOps.map (Json.str ∘ (·.stableId)))),
    ("scope",.str "Converter component only; full workbook and complete raw sensor acceptance remain separate")]
  IO.FS.createDirAll directory
  for (name,contents) in #[("program.ll",module.render),("unit.json",unit.pretty++"\n"),
      ("symbols.txt",lowered.renderSymbolManifest),("startup.S",startup entry.llvm),("link.ld",linker)] do
    IO.FS.writeFile (directory/name) contents
end Lemma.Compiler.MultimodalProbeExport
open Lean Elab Command
syntax (name := lemmaExportMultimodalProbe) "#lemma_export_multimodal_probe" : command
elab_rules : command
  | `(#lemma_export_multimodal_probe) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_MULTIMODAL_PROBE_OUT"
      | throwError "LEMMA_MULTIMODAL_PROBE_OUT requires an unused output"
    liftIO <| Lemma.Compiler.MultimodalProbeExport.exportFiles (← getEnv) output
    logInfo "MULTIMODAL_PROBE_EXPORT:PASS genuine checked ordinary source"
