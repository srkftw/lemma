import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.User.Development.ClosureProcess
import Lemma.Kernel.Development.ClosureKernel
import Lemma.Platform.RiscV.Firmware
import Lemma.Platform.RiscV.ExecutionPrimitives

/-! Quarantined closure qualification exporter. Software uses genuine source
checking; startup instructions use the existing Lean structured machine boundary.
Linker/package text is declarative layout/data. Production registries are untouched. -/
namespace Lemma.Compiler.ClosureExport
open Lean Elab Command Lemma.Core0 Lemma.Compiler Lemma.Platform.LemmaVM

private def emitUnit (env : Environment) (directory : System.FilePath) (profile : Profile)
    (role : String) (roots : Array Name) : IO (Array String) := do
  let suite ← match checkAndLowerActionSuiteForProfile env profile roots with
    | .ok value => pure value | .error error => throw <| IO.userError error.render
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {
    preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
    inlineLiteralConstants := true,inlinePrimitiveWrappers := role == "kernel",
    inlineUserWordWrappers := role == "user",symbolPrefix := "closure_probe_"++role++"_"}
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map llvmTy}
  if !suite.usedDeviceOps.isEmpty || suite.usedExecutionOps.any (·.operation.isDevice) then
    declarations := declarations.push {name := "core0_io_fence",returnType := .void,parameters := #[]}
  let module : LLVM.Module := {
    sourceName := "isolated source-derived bounded closure qualification "++role
    declarations,functions := lowered.functions}
  IO.ofExcept <| LLVM.validateModule module
  let symbol (source : Name) : Except String String := do
    let some row := lowered.symbols.find? (·.source == source) | throw "compiled source symbol absent"
    pure row.llvm
  let mut rows : Array Json := #[]
  for f in suite.scalarFunctions do
    rows := rows.push <| Json.mkObj [("source",toJson f.name.toString),("symbol",toJson (← IO.ofExcept <| symbol f.name)),
      ("args",toJson (f.signature.args.map Ty.render)),("effects",toJson "pure")]
  for f in suite.actionFunctions do
    rows := rows.push <| Json.mkObj [("source",toJson f.name.toString),("symbol",toJson (← IO.ofExcept <| symbol f.name)),
      ("args",toJson (f.signature.args.map Ty.render)),("effects",toJson f.effects.render)]
  let entries ← roots.mapM fun source => do
    pure <| Json.mkObj [("source",toJson source.toString),("symbol",toJson (← IO.ofExcept <| symbol source))]
  let unit := Json.mkObj [("schema_version",toJson (1 : Nat)),("artifact_category",toJson "development-closure-qualification-unit"),
    ("contract_version",toJson profile.contractVersion),("role",toJson role),("roots",Json.arr entries),
    ("functions",Json.arr rows),("used_execution_ops",Json.arr (suite.usedExecutionOps.map fun s => Json.mkObj [
      ("stable_id",toJson s.stableId),("source_identity",toJson s.sourceIdentity.toString),
      ("primitive_symbol",s.primitiveSymbol?.map Json.str |>.getD .null)]))]
  IO.FS.createDirAll directory
  IO.FS.writeFile (directory/"program.ll") module.render
  IO.FS.writeFile (directory/"symbols.txt") lowered.renderSymbolManifest
  IO.FS.writeFile (directory/"unit.json") (unit.pretty++"\n")
  IO.ofExcept <| roots.mapM symbol

private def bootLinker : String := String.intercalate "\n" [
  "OUTPUT_ARCH(riscv)", "ENTRY(_start)", "PHDRS { firmware PT_LOAD FLAGS(5); supervisor PT_LOAD FLAGS(5); storage PT_LOAD FLAGS(6); package PT_LOAD FLAGS(4); }",
  "SECTIONS {", s!"  . = {Layout.firmwareBase};",
  "  .firmware : ALIGN(4096) { startup.o(.text.firmware) *firmware/program.o(.text .text.* .rodata .rodata.*) } :firmware",
  s!"  ASSERT(. <= {Layout.firmwareLimit}, \"firmware envelope exceeded\")",
  s!"  . = {Layout.supervisorBase};",
  "  .text : ALIGN(4096) { startup.o(.text.platform) *kernel/program.o(.text .text.* .rodata .rodata.*) } :supervisor",
  s!"  ASSERT(. <= {Layout.supervisorLimit}, \"supervisor envelope exceeded\")",
  s!"  . = {Layout.metadataBase};", "  __bss_start = .;",
  "  .kernel_storage (NOLOAD) : ALIGN(64) { __boot_hartid = .; . += 8; __boot_dtb = .; . += 8; . += " ++
    toString (Layout.metadataLimit - Layout.metadataBase - 16) ++ "; } :storage",
  "  __bss_end = .;", s!"  ASSERT(__bss_end == {Layout.metadataLimit}, \"boot metadata envelope differs\")",
  s!"  . = {Layout.packageBase};", "  .boot_package : ALIGN(4096) { KEEP(boot-package.o(.boot_package)) } :package",
  s!"  ASSERT(. <= {Layout.packageLimit}, \"boot package envelope exceeded\")",
  "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }", "}", ""]

private def userLinker (directory : String := "user") : String := String.intercalate "\n" [
  "OUTPUT_ARCH(riscv)", "ENTRY(_user_start)", "PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }", "SECTIONS {",
  s!"  . = {(0x1000000)};", "  .text : ALIGN(4096) { " ++ directory ++ "/startup.o(.text.user_start) *(.text .text.* .rodata .rodata.*) } :text",
  s!"  ASSERT(. <= {(0x1080000)}, \"user text envelope exceeded\")",
  s!"  . = {Layout.userDataBase};", "  .data : ALIGN(4096) { *(.data .data.* .sdata .sdata.*) } :data",
  "  __user_data_file_end = .;", "  .bss (NOLOAD) : ALIGN(8) { *(.bss .bss.* .sbss .sbss.*) *(COMMON)",
  s!"    . = MAX(., ABSOLUTE({Layout.userDataBase + Layout.userDataBytes})); } :data",
  s!"  ASSERT(. <= {Layout.userDataBase + Layout.userDataBytes}, \"user data/BSS envelope exceeded\")",
  "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }", "}", ""]

private def packageData : String := String.intercalate "\n" [
  ".section .boot_package, \"a\", @progbits", ".balign 8", ".globl lemma_boot_package", "lemma_boot_package:",
  "  .quad 0x31474b50414d454c", "  .quad 2", "  .quad 1", "  .quad .Llemma_package_end - lemma_boot_package",
  "  .quad 1", s!"  .quad {(0x1000000)}", s!"  .quad {(0x1000000)}",
  "  .quad .Llemma_package_text - lemma_boot_package", "  .quad .Llemma_package_text_end - .Llemma_package_text",
  s!"  .quad {Layout.userDataBase}", "  .quad .Llemma_package_data - lemma_boot_package",
  "  .quad .Llemma_package_data_end - .Llemma_package_data", s!"  .quad {Layout.userDataBytes}",
  s!"  .quad {0x3fffa000}", s!"  .quad {4}", "  .quad 0",
  ".Llemma_package_text:", "  .incbin \"user-text.bin\"", ".Llemma_package_text_end:", ".balign 8",
  ".Llemma_package_data:", "  .incbin \"user-data.bin\"", ".Llemma_package_data_end:", ".Llemma_package_end:",
  ".section .note.GNU-stack, \"\", @progbits", ""]

syntax (name := lemmaExportClosureProbe) "#lemma_export_closure_probe" : command
elab_rules : command
  | `(#lemma_export_closure_probe) => do
    liftTermElabM do
      Compiler.compile #[``Lemma.User.ClosureExamples.selected,``Lemma.User.ClosureExamples.fourCaptures,``Lemma.User.ClosureExamples.lambdaEntry,``Lemma.User.ClosureExamples.sharedCaptures]
      let env ← getEnv
      let some output ← IO.getEnv "LEMMA_CLOSURE_PROBE_OUT" | throwError "LEMMA_CLOSURE_PROBE_OUT required"
      let directory := System.FilePath.mk output
      unless !(← directory.pathExists) do throwError "Retained closure probe output exists"
      IO.FS.createDirAll directory
      let firmware ← emitUnit env (directory/"firmware") .firmware_v0_1 "firmware"
        #[``Lemma.Platform.RiscV.Firmware.dispatch]
      let kernel ← emitUnit env (directory/"kernel") .kernel_v0_2 "kernel"
        #[``Lemma.Kernel.Development.ClosureKernel.boot,``Lemma.Kernel.Development.ClosureKernel.dispatch]
      let user ← emitUnit env (directory/"user") .user_v0_7 "user"
        #[``Lemma.User.Development.ClosureProcess.entry]
      let config : Lemma.Platform.RiscV.ExecutionPrimitives.Configuration := {
        stage := .supervisor,kernelMain := kernel[0]!,firmwareDispatcher := firmware[0]!,supervisorDispatcher := kernel[1]!}
      let startup ← match Lemma.Platform.RiscV.ExecutionPrimitives.renderStartup config with
        | .ok s => pure s | .error error => throwError error
      let userStartup ← match Lemma.Platform.RiscV.ExecutionPrimitives.renderUserStartup user[0]! with
        | .ok s => pure s | .error error => throwError error
      for (name,contents) in #[("startup.S",startup),("link.ld",bootLinker),("boot-package.S",packageData),
          ("user/startup.S",userStartup),("user/link.ld",userLinker)] do
        IO.FS.writeFile (directory/name) contents
      let programs ← #[``Lemma.User.ClosureExamples.selected,``Lemma.User.ClosureExamples.fourCaptures,``Lemma.User.ClosureExamples.lambdaEntry,``Lemma.User.ClosureExamples.sharedCaptures].mapM fun root => do
        let program ← match ManagedClosureIR.buildProgram env root with
          | .ok p => pure p | .error error => throwError error
        let sources ← program.sourceNames.mapM fun name => do
          let some ci := env.find? name | throwError "source type absent"
          let some ir := IR.findEnvDecl env name | throwError "genuine source IR absent"
          pure <| Json.mkObj [("source",toJson name.toString),("source_type",toJson (← PrettyPrinter.ppExpr ci.type).pretty),
            ("genuine_ir",toJson (IR.formatDecl ir).pretty)]
        let adapters ← program.targets.mapM fun t => do
          let some ir := IR.findEnvDecl env t.adapter | throwError "genuine adapter IR absent"
          pure <| Json.mkObj [("adapter",toJson t.adapter.toString),("owner",toJson t.source.toString),
            ("captures",toJson t.captures),("genuine_ir",toJson (IR.formatDecl ir).pretty)]
        pure <| Json.mkObj [("root",toJson root.toString),("sources",Json.arr sources),("adapters",Json.arr adapters)]
      let metadata := Json.mkObj [("contract",toJson "lemma-managed-closure-v1"),("profile",toJson "core0-user-v0.7"),
        ("compiler_revision",toJson "5045d0056413266e57c625dcd7c365b10e377c52"),
        ("genuine_ir",Json.arr programs),("maximum_captures",toJson (4 : Nat)),("maximum_targets",toJson (8 : Nat)),
        ("slots",toJson (31 : Nat)),("cookie",toJson Lemma.User.Runtime.ManagedClosure.cookie),
        ("qualification_scope",toJson "separately linked isolated U process; no production mathematical authority")]
      IO.FS.writeFile (directory/"closure.json") (metadata.pretty++"\n")
      logInfo "CLOSURE_PROBE_EXPORT:PASS genuine source-derived checked firmware/S-kernel/User7 units"
end Lemma.Compiler.ClosureExport
