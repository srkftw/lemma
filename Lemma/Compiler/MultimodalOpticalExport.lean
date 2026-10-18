import Lean
import Lemma.Compiler.CFGLower
import Lemma.Machine.Primitives
import Lemma.Multimodal.OpticalDerivedProbe

namespace Lemma.Compiler.MultimodalOpticalExport
open Lean Lemma.Core0 Lemma.Machine.Primitives
private def startup (entry : String) : String :=
  let lines : Array Line := #[.label "_reset",.instruction (.csrWrite .mie .zero),
    .instruction .maskMachineInterruptEnable,.instruction (.csrWrite .satp .zero),
    .instruction (.loadImmediate .sp 0x81fb0000),.instruction (.call entry),
    .label ".Lderived_halt",.instruction .waitForInterrupt,.instruction (.jump ".Lderived_halt")]
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
  " ASSERT(. <= 0x80020000, \"derived component executable envelope exceeded\")",
  " /DISCARD/ : { *(.comment) *(.note.GNU-stack) *(.eh_frame*) }","}",""]
def exportFiles (env : Environment) (directory : System.FilePath) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "derived exporter requires unused output"
  let profile := Profile.boot_v0_1
  let suite ← match checkAndLowerActionSuiteForProfile env profile #[``Lemma.Multimodal.OpticalDerivedProbe.entry] with
    | .ok value => pure value | .error error => throw <| IO.userError error.render
  for op in suite.usedExecutionOps do
    unless op.sourceIdentity == ``Execution.Op.physicalRead8 || op.sourceIdentity == ``Execution.Op.physicalRead64 ||
      op.sourceIdentity == ``Execution.Op.physicalWrite8 || op.sourceIdentity == ``Execution.Op.physicalWrite64 do
      throw <| IO.userError s!"unaccounted derived execution operation {op.sourceIdentity}"
  for op in suite.usedDeviceOps do
    unless op.stableId == "uart.read-status" || op.stableId == "uart.write-byte" || op.stableId == "uart.enable-reset-fifo" do
      throw <| IO.userError s!"unaccounted derived device operation {op.stableId}"
  for name in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let name := ((Lean.privateToUserName? name).getD name).toString
    unless name.startsWith "Lemma.Multimodal.OpticalDerived" || name.startsWith "Lemma.Kernel.Memory.Access." ||
      name.startsWith "Lemma.Boot.RecoveryExecuted.transmit" || name == "Lemma.Core0.Memory.Status.iterationStop" ||
      name == "Lemma.Core0.Memory.Status.txTimeout" do
      throw <| IO.userError s!"unaccounted derived source dependency {name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {symbolPrefix := "lemma_derived_"}
  let some entry := lowered.symbols.find? (fun row => row.source == ``Lemma.Multimodal.OpticalDerivedProbe.entry)
    | throw <| IO.userError "missing actual derived entry"
  let module : LLVM.Module := {
    sourceName := "Lemma bounded synthetic optical geometry ordinary Lean RV64 workload"
    functions := lowered.functions.map fun f => {f with attributes := f.attributes.push "\"no-jump-tables\"=\"true\""}
    declarations := #[{name := "core0_io_fence",returnType := .void,parameters := #[]}] }
  IO.ofExcept <| LLVM.validateModule module
  let mut functions : Array Json := #[]
  for f in suite.scalarFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing actual derived scalar"
    functions := functions.push <| Json.mkObj [("source",.str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",.str "{}")]
  for f in suite.actionFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing actual derived action"
    functions := functions.push <| Json.mkObj [("source",.str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",.str f.effects.render)]
  let unit := Json.mkObj [("schema",.str "lemma-optical-derived-rv64-component/1"),("contract_version",.str profile.contractVersion),
    ("root",.str "Lemma.Multimodal.OpticalDerivedProbe.entry"),("entry_symbol",.str entry.llvm),("functions",.arr functions),
    ("used_execution_ops",.arr (suite.usedExecutionOps.map (Json.str ∘ (·.stableId)))),
    ("used_device_ops",.arr (suite.usedDeviceOps.map (Json.str ∘ (·.stableId)))),
    ("scope",.str "Freestanding known-answer execution; authenticated ROM selection not implied")]
  IO.FS.createDirAll directory
  for (name,contents) in #[("program.ll",module.render),("unit.json",unit.pretty++"\n"),
      ("symbols.txt",lowered.renderSymbolManifest),("startup.S",startup entry.llvm),("link.ld",linker)] do
    IO.FS.writeFile (directory/name) contents
end Lemma.Compiler.MultimodalOpticalExport
open Lean Elab Command
syntax (name := lemmaExportMultimodalCrypto) "#lemma_export_multimodal_optical" : command
elab_rules : command
  | `(#lemma_export_multimodal_optical) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_MULTIMODAL_OPTICAL_OUT"
      | throwError "LEMMA_MULTIMODAL_OPTICAL_OUT requires an unused output"
    liftIO <| Lemma.Compiler.MultimodalOpticalExport.exportFiles (← getEnv) output
    logInfo "MULTIMODAL_OPTICAL_EXPORT:PASS genuine checked ordinary source"
