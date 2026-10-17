import Lean
import Lemma.Boot.RecoveryNext
import Lemma.Compiler.CFGLower
import Lemma.Machine.Primitives

/-! Genuine checked ROM export. The only assembly is the structured reset
boundary and I/O fence, generated through the shared primitive renderer.
Image parsing, integrity, selection and update policy remain ordinary Lean.
-/
namespace Lemma.Compiler.BootNextExport
open Lean Lemma.Core0 Lemma.Machine.Primitives

def profile : Profile := .boot_v0_1
def configuration : String := "lemmasim-silicon-product-next-boot"
def romBase : Nat := 0x1000
def romBytes : Nat := 0x10000
def dtbBase : Nat := 0x87e00000

def resetLines (entry : String) : Array Line := #[
  .label "_reset",
  .instruction (.csrWrite .mie .zero),
  .instruction .maskMachineInterruptEnable,
  .instruction (.csrWrite .satp .zero),
  .instruction (.loadImmediate .sp Lemma.Boot.ProductNext.romStackTop.toNat),
  .instruction (.call entry),
  .instruction (.branchNeZero .a0 ".Lboot_recovery"),
  .instruction (.move .t0 .a1),
  .instruction (.loadImmediate .a0 0),
  .instruction (.loadImmediate .a1 dtbBase),
  .instruction .instructionFence,
  .instruction (.jumpRegisterZero .t0),
  -- A bounded recovery-command campaign may fail/expire. Reset re-enters the
  -- immutable transport; no unvalidated entry address can be used here.
  .label ".Lboot_recovery",
  .instruction .waitForInterrupt,
  .instruction (.jump ".Lboot_recovery")
]
def startup (entry : String) : String := String.intercalate "\n" ([
  ".option norvc", ".option norelax", ".section .text.reset, \"ax\", @progbits",
  ".globl _reset", ".type _reset, @function", ".balign 4"] ++ (resetLines entry).toList.map Line.render ++ [
  ".size _reset, .-_reset",
  ".section .text.io, \"ax\", @progbits", ".globl core0_io_fence", ".type core0_io_fence, @function", ".balign 4",
  (Line.label "core0_io_fence").render,
  (Line.instruction .fenceIO).render, (Line.instruction .return).render,
  ".size core0_io_fence, .-core0_io_fence",
  ".section .note.GNU-stack, \"\", @progbits", ""])

def linker : String := String.intercalate "\n" [
  "OUTPUT_ARCH(riscv)", "ENTRY(_reset)", "PHDRS { rom PT_LOAD FLAGS(5); }", "SECTIONS {",
  s!"  . = {romBase};", "  .text : ALIGN(4) { KEEP(startup.o(.text.reset)) startup.o(.text.io) *(.text .text.*) } :rom",
  "  .rodata : ALIGN(8) { *(.rodata.cst8) } :rom",
  s!"  ASSERT(. <= {romBase+romBytes}, \"immutable boot ROM envelope exceeded\")",
  "  /DISCARD/ : { *(.comment) *(.note.GNU-stack) *(.eh_frame*) }", "}", ""]

private def effectFields (effects : EffectSet) : Json :=
  if effects == EffectSet.empty then .arr #[] else
    .arr <| ((String.ofList (effects.render.toList.drop 1 |>.reverse.drop 1 |>.reverse)).splitOn ",").toArray.map Json.str

def exportFiles (env : Environment) (directory : System.FilePath) : IO Unit := do
  let suite ← match checkAndLowerActionSuiteForProfile env profile #[`Lemma.Boot.RecoveryNext.entry] with
    | .ok suite => pure suite | .error e => throw <| IO.userError e.render
  -- Ordinary LLVM optimization is permitted here. No range, integrity or
  -- metadata guard is removed by the compiler; each is present in checked IR.
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {
    symbolPrefix := "lemma_product_next_boot_" }
  let some entry := lowered.symbols.find? (fun row => row.source == `Lemma.Boot.RecoveryNext.entry)
    | throw <| IO.userError "missing genuine boot entry"
  let module : LLVM.Module := {
    sourceName := "Lemma immutable Product9 boot-v1"
    -- ROM-v1 uses branch dispatch. Prevent llc from introducing unadvertised
    -- indirect jump-table state after the checked direct-control-flow corpus.
    functions := lowered.functions.map fun f => {f with attributes := f.attributes.push "\"no-jump-tables\"=\"true\""}
    declarations := #[{name := "core0_io_fence", returnType := .void, parameters := #[]}] }
  IO.ofExcept <| LLVM.validateModule module
  let mut functions : Array Json := #[]
  for f in suite.scalarFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing scalar boot symbol"
    functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
      ("symbol", .str symbol.llvm), ("args", .arr <| f.signature.args.map (Json.str ∘ Ty.render)),
      ("effects", .arr #[])]
  for f in suite.actionFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing Action boot symbol"
    functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
      ("symbol", .str symbol.llvm), ("args", .arr <| f.signature.args.map (Json.str ∘ Ty.render)),
      ("effects", effectFields f.effects)]
  let manifest := Json.mkObj [
    ("schema_version", 1), ("contract_version", .str profile.contractVersion),
    ("configuration", .str configuration), ("role", .str "boot"),
    ("hardware_profile", .str "lemma-silicon-dev/0.9.0"),
    ("image_compatibility", toJson Lemma.Boot.ProductNext.compatibility.toNat),
    ("root", .str "Lemma.Boot.RecoveryNext.entry"), ("entry_symbol", .str entry.llvm),
    ("rom_base", toJson romBase), ("rom_bytes", toJson romBytes),
    ("stack_floor", toJson (0x81fd0000 : Nat)), ("stack_top", toJson Lemma.Boot.ProductNext.romStackTop.toNat),
    ("integrity", .str "CRC32/ISO-HDLC; no authentication or anti-rollback guarantee"),
    ("recovery_transport", .str "lemma-local-uart-recovery-v1; integrity-only, bounded owner-local transport; authentication OPEN"),
    ("backend_dispatch", .str "lemma-boot-direct-branches-v1"),
    ("functions", .arr functions),
    ("used_execution_ops", .arr <| suite.usedExecutionOps.map fun op => .str op.stableId),
    ("used_device_ops", .arr <| suite.usedDeviceOps.map fun op => .str op.stableId)]
  IO.FS.createDirAll directory
  for (name,contents) in #[("program.ll",module.render),("unit.json",manifest.pretty++"\n"),
      ("symbols.txt",lowered.renderSymbolManifest),("startup.S",startup entry.llvm),("link.ld",linker)] do
    IO.FS.writeFile (directory/name) contents

end Lemma.Compiler.BootNextExport
open Lean Elab Command
syntax (name := lemmaExportProductNextBoot) "#lemma_export_product_next_boot" : command
elab_rules : command
  | `(#lemma_export_product_next_boot) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_PRODUCT_NEXT_BOOT_OUT"
      | throwError "LEMMA_PRODUCT_NEXT_BOOT_OUT must select an unused output directory"
    liftIO <| Lemma.Compiler.BootNextExport.exportFiles (← getEnv) output
    logInfo "PRODUCT_NEXT_BOOT_EXPORT:PASS genuine immutable ROM source and structured boundary"
