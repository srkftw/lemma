import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.Format
import Lemma.Platform.RiscV.ExecutionPrimitives

/-! Production export commands. Each unit comes from genuine elaborated Lean
roots under an explicit privilege profile; no test harness is appended. Boot
packaging emits data descriptors and the separately linked user bytes, never
allocator, loading, scheduling, authority or service policy. -/

namespace Lemma.Compiler.KernelExport

open Lean Elab Command
open Lemma.Core0
open Lemma.Compiler
open Lemma.Platform.LemmaVM

private def roleProfile (role : String) : Except String Profile :=
  match role with
  | "firmware" => .ok .firmware_v0_1
  | "kernel" => .ok .kernel_v0_1
  | "user" => .ok .user_v0_1
  | _ => .error "production role must be firmware, kernel, or user"

private def readConfiguration : IO String := do
  let some configuration ← IO.getEnv "LEMMA_KERNEL_CONFIGURATION"
    | throw <| IO.userError "LEMMA_KERNEL_CONFIGURATION must be normal, frames-development, or machine-origin-development"
  unless configuration == "normal" || configuration == "frames-development" ||
      configuration == "machine-origin-development" do
    throw <| IO.userError "LEMMA_KERNEL_CONFIGURATION must be normal, frames-development, or machine-origin-development"
  pure configuration

/-- The startup probe is selected only by its exact quarantined configuration,
not by an independent environment switch or by a supplied instruction list. -/
private def startupCase (configuration : String) : Lemma.Platform.RiscV.ExecutionPrimitives.StartupCase :=
  if configuration == "machine-origin-development" then .machineOriginProbe else .normal

private def unitCategory (configuration role : String) : String :=
  (if configuration == "normal" then "production-" else "development-") ++ role ++ "-unit"

private def rootIdentities (configuration role : String) : Array String :=
  match role with
  | "firmware" => #["Lemma.Platform.RiscV.Firmware.dispatch"]
  | "kernel" => if configuration == "frames-development" then
      #["Lemma.Kernel.Development.FramesEntry.boot", "Lemma.Kernel.Development.FramesEntry.dispatch"]
    else #["Lemma.Kernel.Entry.boot", "Lemma.Kernel.Entry.dispatch"]
  | "user" => #["Lemma.User.Entry.main"]
  | _ => #[]

private def rootArguments (role : String) : Array (Array Ty) :=
  match role with
  | "firmware" => #[#[.u64, .u64, .u64]]
  | "kernel" => #[#[], #[.u64, .u64, .u64]]
  | "user" => #[#[.u64]]
  | _ => #[]

private def allowsDevelopment (configuration role : String) : Bool :=
  configuration == "frames-development" && role == "kernel"

private def developmentName (name : Name) : Bool :=
  let source := (Lean.privateToUserName? name).getD name |>.toString
  source.startsWith "Lemma.Kernel.Development."

private def validateSelectedRoots (configuration role : String) (names : Array Name) : Except String Unit := do
  unless names.map Name.toString == rootIdentities configuration role do
    throw s!"{configuration} {role} roots differ from the fixed selected entry identities"

private def argumentsJson (arguments : Array Ty) : Json :=
  .arr (arguments.map (Json.str ∘ Ty.render))

private def effectsJson (effects : EffectSet) : Json :=
  if effects == .empty then .arr #[] else
    let names := String.ofList (effects.render.toList.drop 1 |>.reverse.drop 1 |>.reverse)
    .arr ((names.splitOn ",").toArray.map Json.str)

private def productionName (name : Name) : Bool :=
  let value := name.toString
  let lower := value.toLower
  let source := (Lean.privateToUserName? name).getD name |>.toString
  source.startsWith "Lemma." && (lower.splitOn ".examples.").length == 1 &&
    !lower.startsWith "examples." && (lower.splitOn ".compiler.test.").length == 1 &&
    (lower.splitOn "mutation").length == 1 && (lower.splitOn "mutant").length == 1

private def rootSymbol (lowered : LoweredActionSuite) (name : Name) : Except String String := do
  let some symbol := lowered.symbols.find? (fun symbol => symbol.source == name)
    | throw s!"production lowering omitted source `{name}`"
  pure symbol.llvm

private def deviceSourceIdentity : Device.Op → String
  | .uartReadStatus => "Lemma.Core0.Memory.Action.uartReadStatus"
  | .uartReadByte => "Lemma.Core0.Memory.Action.uartReadByte"
  | .uartWriteByte => "Lemma.Core0.Memory.Action.uartWriteByte"
  | .uartEnableAndResetFifo => "Lemma.Core0.Memory.Action.uartEnableAndResetFifo"

private def deviceLoweringId : Device.Op → String
  | .uartReadStatus => "uart.lsr.read8"
  | .uartReadByte => "uart.rbr.read8"
  | .uartWriteByte => "uart.thr.write8"
  | .uartEnableAndResetFifo => "uart.fcr.enable-reset"

private def deviceSites (lowered : LoweredActionSuite) (operation : Device.Op) : Array Json := Id.run do
  let mut sites := #[]
  for function in lowered.functions do
    for block in function.blocks do
      for instruction in block.instructions do
        let site? := match instruction, operation with
          | .uartRead8 _ site .lsr, .uartReadStatus => some site
          | .uartRead8 _ site .rbr, .uartReadByte => some site
          | .uartWrite8 site _, .uartWriteByte => some site
          | .uartEnableAndResetFifo site, .uartEnableAndResetFifo => some site
          | _, _ => none
        if let some site := site? then
          sites := sites.push <| Json.mkObj [("site", toJson site), ("symbol", .str function.name)]
  return sites

private def executionJson (spec : Execution.OpSpec) : Json := Json.mkObj [
  ("stable_id", .str spec.stableId), ("source_identity", .str spec.sourceIdentity.toString),
  ("primitive_symbol", spec.primitiveSymbol?.map Json.str |>.getD Json.null),
  ("arguments", argumentsJson spec.machineArguments),
  ("returnkind", .str (if spec.resultKind == .checked then "checked" else "word"))]

private def deviceJson (lowered : LoweredActionSuite) (operation : Device.Op) : Except String Json := do
  let some spec := Device.findSpec? operation | throw "missing closed production device contract"
  pure <| Json.mkObj [
    ("stable_id", .str operation.stableId), ("source_identity", .str (deviceSourceIdentity operation)),
    ("lowering_id", .str (deviceLoweringId operation)), ("base", toJson spec.base.toNat),
    ("offset", toJson spec.offset.toNat), ("width_bytes", toJson spec.widthBytes),
    ("access", .str spec.access.render),
    ("fixed_value", spec.fixedWriteValue?.map (toJson ∘ UInt8.toNat) |>.getD Json.null),
    ("volatile", .bool true), ("fence_before", .bool spec.fenceBefore),
    ("fence_after", .bool spec.fenceAfter), ("sites", .arr (deviceSites lowered operation))]

private def unitManifest (configuration role : String) (suite : CheckedActionSuite)
    (lowered : LoweredActionSuite) : Except String Json := do
  let mut roots := #[]
  for root in suite.roots do
    roots := roots.push <| Json.mkObj [("id", toJson root.id), ("source", .str root.source.toString),
      ("symbol", .str (← rootSymbol lowered root.source)), ("args", argumentsJson root.signature.args)]
  let mut functions := #[]
  for function in suite.scalarFunctions do
    functions := functions.push <| Json.mkObj [("source", .str function.name.toString),
      ("symbol", .str (← rootSymbol lowered function.name)),
      ("args", argumentsJson function.signature.args), ("effects", .arr #[])]
  for function in suite.actionFunctions do
    functions := functions.push <| Json.mkObj [("source", .str function.name.toString),
      ("symbol", .str (← rootSymbol lowered function.name)),
      ("args", argumentsJson function.signature.args), ("effects", effectsJson function.effects)]
  let mut devices := #[]
  for operation in suite.usedDeviceOps do devices := devices.push (← deviceJson lowered operation)
  pure <| Json.mkObj [("schema_version", 1), ("artifact_category", .str (unitCategory configuration role)),
    ("configuration", .str configuration),
    ("contract_version", .str suite.contractVersion), ("role", .str role), ("roots", .arr roots),
    ("functions", .arr functions), ("used_execution_ops", .arr (suite.usedExecutionOps.map executionJson)),
    ("used_device_ops", .arr devices), ("used_loops", .arr (suite.usedLoops.map fun use =>
      Json.mkObj [("stable_id", .str use.stableId), ("callback", .str use.callback.toString)]))]

private def loopJson (use : ActionLoopUse) : Json :=
  Json.mkObj [("stable_id", .str use.stableId), ("callback", .str use.callback.toString)]

private def normalized (configuration role : String) (suite : CheckedActionSuite) : String :=
  s!"configuration={configuration}\nrole={role}\ncontract={suite.contractVersion}\n" ++
    String.join (suite.scalarFunctions.toList.map fun function =>
      s!"scalar={function.name};args={repr function.signature.args};result={function.signature.result.render}\n" ++
        function.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun function =>
      s!"action={function.name};args={repr function.signature.args};effects={function.effects.render}\n" ++
        function.body.renderNormalized ++ "\n") ++
    String.join (suite.usedExecutionOps.toList.map fun spec => "execution=" ++ (executionJson spec).compress ++ "\n") ++
    String.join (suite.usedDeviceOps.toList.map fun operation => s!"device={operation.stableId}\n") ++
    String.join (suite.usedLoops.toList.map fun use => "loop=" ++ (loopJson use).compress ++ "\n")

private def validateRoots (configuration role : String) (suite : CheckedActionSuite) : Except String Unit := do
  validateSelectedRoots configuration role (suite.roots.map (·.source))
  unless suite.roots.map (·.signature.args) == rootArguments role do
    throw s!"{configuration} {role} signatures differ from the admitted entry/dispatch ABI"

private def exportUnit (env : Environment) (configuration role : String) (names : Array Name)
    (directory : System.FilePath) : IO Unit := do
  let profile ← IO.ofExcept (roleProfile role)
  IO.ofExcept <| validateSelectedRoots configuration role names
  unless allowsDevelopment configuration role do
    for imported in env.header.moduleNames do
      if developmentName imported then
        throw <| IO.userError s!"{configuration} {role} imports forbidden development module `{imported}`"
  let suite ← match checkAndLowerActionSuiteForProfile env profile names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  IO.ofExcept (validateRoots configuration role suite)
  for function in suite.scalarFunctions do
    unless productionName function.name &&
        (allowsDevelopment configuration role || !developmentName function.name) do
      throw <| IO.userError s!"forbidden reachable source `{function.name}` for {configuration} {role}"
  for function in suite.actionFunctions do
    unless productionName function.name &&
        (allowsDevelopment configuration role || !developmentName function.name) do
      throw <| IO.userError s!"forbidden reachable source `{function.name}` for {configuration} {role}"
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {
    preserveCalls := preserved, symbolPrefix := "lemma_" ++ role ++ "_" }
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map llvmTy }
  if !suite.usedDeviceOps.isEmpty then
    declarations := declarations.push { name := "core0_io_fence", returnType := .void, parameters := #[] }
  let module : LLVM.Module := {
    sourceName := "Lemma " ++ configuration ++ " " ++ role
    declarations
    functions := lowered.functions }
  IO.ofExcept <| LLVM.validateModule module
  let manifest ← IO.ofExcept <| unitManifest configuration role suite lowered
  IO.FS.createDirAll directory
  for (filename, contents) in #[("program.ll", module.render), ("unit.json", manifest.pretty ++ "\n"),
      ("normalized.txt", normalized configuration role suite), ("symbols.txt", lowered.renderSymbolManifest)] do
    IO.FS.writeFile (directory / filename) contents

private def layoutJson (configuration : String) : Json := Json.mkObj [
  ("configuration", .str configuration),
  ("startup_case", .str (startupCase configuration).stableId),
  ("schema_version", 1), ("contract_version", .str "lemma-kernel-layout-v1"),
  ("ram_base", toJson Layout.ramBase), ("ram_limit", toJson Layout.ramLimit),
  ("frame_bytes", toJson Layout.frameBytes), ("frame_count", toJson Layout.frameCount),
  ("context", Json.mkObj [
    ("bytes", toJson Lemma.Platform.RiscV.ExecutionPrimitives.contextBytes),
    ("kernel_resume_base", toJson Layout.kernelResumeContext),
    ("boot_stack_floor", toJson Layout.bootStackFloor),
    ("pc_offset", toJson Lemma.Platform.RiscV.ExecutionPrimitives.savedPcOffset),
    ("status_offset", toJson Lemma.Platform.RiscV.ExecutionPrimitives.savedStatusOffset),
    ("translation_offset", toJson Lemma.Platform.RiscV.ExecutionPrimitives.savedTranslationOrEnableOffset),
    ("scratch_offset", toJson Lemma.Platform.RiscV.ExecutionPrimitives.savedKernelStackOffset)]),
  ("intervals", .arr (Layout.intervals.map fun interval => Json.mkObj [
    ("name", .str interval.name), ("base", toJson interval.base), ("limit", toJson interval.limit),
    ("purpose", .str interval.purpose)])),
  ("user", Json.mkObj [("text_base", toJson Layout.userTextBase), ("text_limit", toJson Layout.userTextLimit),
    ("data_base", toJson Layout.userDataBase), ("data_bytes", toJson Layout.userDataBytes),
    ("stack_base", toJson Layout.userStackBase), ("stack_pages", toJson Layout.userStackPages)])]

private def bootLinker : String := String.intercalate "\n" [
  "OUTPUT_ARCH(riscv)", "ENTRY(_start)", "PHDRS { firmware PT_LOAD FLAGS(5); supervisor PT_LOAD FLAGS(5); storage PT_LOAD FLAGS(6); package PT_LOAD FLAGS(4); }",
  "SECTIONS {", s!"  . = {Layout.firmwareBase};",
  "  .firmware : ALIGN(4096) { startup.o(.text.firmware) *firmware/program.o(.text .text.* .rodata .rodata.*) } :firmware",
  s!"  ASSERT(. <= {Layout.firmwareLimit}, \"firmware envelope exceeded\")",
  s!"  . = {Layout.supervisorBase};",
  "  .text : ALIGN(4096) { startup.o(.text.platform) *kernel/program.o(.text .text.* .rodata .rodata.*) } :supervisor",
  s!"  ASSERT(. <= {Layout.supervisorLimit}, \"supervisor envelope exceeded\")",
  s!"  . = {Layout.metadataBase};", "  __bss_start = .;",
  "  .kernel_storage (NOLOAD) : ALIGN(64) { __boot_hartid = .; . += 8; __boot_dtb = .; . += 8; . += 112; } :storage",
  "  __bss_end = .;", s!"  ASSERT(__bss_end <= {Layout.metadataBase + 0x1000}, \"boot metadata envelope exceeded\")",
  s!"  . = {Layout.packageBase};", "  .boot_package : ALIGN(4096) { KEEP(boot-package.o(.boot_package)) } :package",
  s!"  ASSERT(. <= {Layout.packageLimit}, \"boot package envelope exceeded\")",
  "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }", "}", ""]

private def userLinker : String := String.intercalate "\n" [
  "OUTPUT_ARCH(riscv)", "ENTRY(_user_start)", "PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }", "SECTIONS {",
  s!"  . = {Layout.userTextBase};", "  .text : ALIGN(4096) { user/startup.o(.text.user_start) *(.text .text.* .rodata .rodata.*) } :text",
  s!"  ASSERT(. <= {Layout.userTextLimit}, \"user text envelope exceeded\")",
  s!"  . = {Layout.userDataBase};", "  .data : ALIGN(4096) { *(.data .data.* .sdata .sdata.*) } :data",
  "  __user_data_file_end = .;", "  .bss (NOLOAD) : ALIGN(8) { *(.bss .bss.* .sbss .sbss.*) *(COMMON)",
  s!"    . = MAX(., ABSOLUTE({Layout.userDataBase + Layout.userDataBytes})); } :data",
  s!"  ASSERT(. <= {Layout.userDataBase + Layout.userDataBytes}, \"user data/BSS envelope exceeded\")",
  "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }", "}", ""]

private def packageContract (configuration : String) : Json := Json.mkObj [
  ("configuration", .str configuration),
  ("startup_case", .str (startupCase configuration).stableId),
  ("schema_version", 1), ("contract_version", .str "lemma-boot-package-v1"),
  ("magic", toJson (0x31474b50414d454c : Nat)), ("version", 1), ("image_count", 1),
  ("header_bytes", 32), ("descriptor_bytes", 96), ("offset_encoding", .str "generated-label-differences"),
  ("image", Json.mkObj [("id", 1), ("entry", toJson Layout.userTextBase), ("text_va", toJson Layout.userTextBase),
    ("text_capacity", toJson (Layout.userTextLimit - Layout.userTextBase)), ("data_va", toJson Layout.userDataBase),
    ("data_mem_bytes", toJson Layout.userDataBytes), ("stack_va", toJson Layout.userStackBase),
    ("stack_pages", toJson Layout.userStackPages), ("flags", 0)])]

private def packageData : String := String.intercalate "\n" [
  ".section .boot_package, \"a\", @progbits", ".balign 8", ".globl lemma_boot_package", "lemma_boot_package:",
  "  .quad 0x31474b50414d454c", "  .quad 1", "  .quad 1", "  .quad .Llemma_package_end - lemma_boot_package",
  "  .quad 1", s!"  .quad {Layout.userTextBase}", s!"  .quad {Layout.userTextBase}",
  "  .quad .Llemma_package_text - lemma_boot_package", "  .quad .Llemma_package_text_end - .Llemma_package_text",
  s!"  .quad {Layout.userDataBase}", "  .quad .Llemma_package_data - lemma_boot_package",
  "  .quad .Llemma_package_data_end - .Llemma_package_data", s!"  .quad {Layout.userDataBytes}",
  s!"  .quad {Layout.userStackBase}", s!"  .quad {Layout.userStackPages}", "  .quad 0",
  ".Llemma_package_text:", "  .incbin \"user-text.bin\"", ".Llemma_package_text_end:", ".balign 8",
  ".Llemma_package_data:", "  .incbin \"user-data.bin\"", ".Llemma_package_data_end:", ".Llemma_package_end:",
  ".section .note.GNU-stack, \"\", @progbits", ""]

private def jsonFieldEquals (object : Json) (field : String) (expected : Json) : Bool :=
  match object.getObjVal? field with
  | .ok actual => actual == expected
  | .error _ => false

private def readRootSymbol (directory : System.FilePath) (configuration role : String)
    (index : Nat) : IO String := do
  let contents ← IO.FS.readFile (directory / role / "unit.json")
  let manifest ← IO.ofExcept <| Json.parse contents
  let actualRole ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "role").getStr?
  let actualConfiguration ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "configuration").getStr?
  let contract ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "contract_version").getStr?
  let category ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "artifact_category").getStr?
  let version ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "schema_version").getNat?
  let profile ← IO.ofExcept <| roleProfile role
  unless actualRole == role && actualConfiguration == configuration &&
      contract == profile.contractVersion && version == 1 && category == unitCategory configuration role do
    throw <| IO.userError "boot export rejected inconsistent unit configuration/identity"
  let roots ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "roots").getArr?
  let functions ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "functions").getArr?
  let expectedSources := rootIdentities configuration role
  let expectedArguments := rootArguments role
  unless roots.size == expectedSources.size do
    throw <| IO.userError "boot export rejected unexpected root count"
  let mut symbols : Array String := #[]
  for h : rootIndex in [:roots.size] do
    let root := roots[rootIndex]
    let source ← IO.ofExcept <| (← IO.ofExcept <| root.getObjVal? "source").getStr?
    let id ← IO.ofExcept <| (← IO.ofExcept <| root.getObjVal? "id").getNat?
    let arguments ← IO.ofExcept <| root.getObjVal? "args"
    let symbol ← IO.ofExcept <| (← IO.ofExcept <| root.getObjVal? "symbol").getStr?
    unless source == expectedSources[rootIndex]! && id == rootIndex + 1 &&
        arguments == argumentsJson expectedArguments[rootIndex]! do
      throw <| IO.userError "boot export rejected a non-selected entry source/signature"
    unless functions.any (fun function =>
        jsonFieldEquals function "source" (.str source) &&
        jsonFieldEquals function "symbol" (.str symbol) &&
        jsonFieldEquals function "args" arguments) do
      throw <| IO.userError "boot export rejected a root/function symbol or signature mismatch"
    IO.ofExcept <| validateSymbolPrefix symbol
    unless symbol.startsWith ("lemma_" ++ role ++ "_") && !symbols.contains symbol do
      throw <| IO.userError "boot export rejected a role-crossing or duplicate entry symbol"
    symbols := symbols.push symbol
  let some symbol := symbols[index]? | throw <| IO.userError s!"boot export omitted {role} entry {index}"
  pure symbol

private def exportBootFiles (directory : System.FilePath) (configuration : String)
    (stage : Lemma.Platform.RiscV.ExecutionPrimitives.Stage) : IO Unit := do
  if configuration == "machine-origin-development" && stage != .bootstrapM then
    throw <| IO.userError "machine-origin-development requires bootstrap-m stage"
  unless Layout.valid do throw <| IO.userError "authoritative boot layout is invalid"
  let firmware ← readRootSymbol directory configuration "firmware" 0
  let kernel ← readRootSymbol directory configuration "kernel" 0
  let dispatcher ← readRootSymbol directory configuration "kernel" 1
  let user ← readRootSymbol directory configuration "user" 0
  let config : Lemma.Platform.RiscV.ExecutionPrimitives.Configuration := {
    stage, startupCase := startupCase configuration,
    kernelMain := kernel, firmwareDispatcher := firmware, supervisorDispatcher := dispatcher }
  let startup ← IO.ofExcept <| Lemma.Platform.RiscV.ExecutionPrimitives.renderStartup config
  let userStartup ← IO.ofExcept <| Lemma.Platform.RiscV.ExecutionPrimitives.renderUserStartup user
  let catalog := Json.mkObj [("schema_version", 1), ("contract_version", .str "lemma-execution-v1"),
    ("configuration", .str configuration), ("stage", .str stage.stableId),
    ("startup_case", .str config.startupCase.stableId), ("symbols", .arr
      ((Lemma.Platform.RiscV.ExecutionPrimitives.primitiveCatalog config).map fun (symbol, privilege, effect) =>
        Json.mkObj [("symbol", .str symbol), ("privilege", .str privilege), ("effect", .str effect)])),
    ("user_symbols", .arr #[Json.mkObj [("symbol", .str "_user_start"), ("privilege", .str "U"), ("effect", .str "user-entry/exit")],
      Json.mkObj [("symbol", .str "lemma_exec_syscall"), ("privilege", .str "U"), ("effect", .str "user-syscall")]])]
  for (filename, contents) in #[("startup.S", startup), ("user-startup.S", userStartup),
      ("link.ld", bootLinker), ("user-link.ld", userLinker), ("layout.json", (layoutJson configuration).pretty ++ "\n"),
      ("primitive-catalog.json", catalog.pretty ++ "\n"), ("boot-package.S", packageData),
      ("package-contract.json", (packageContract configuration).pretty ++ "\n")] do
    IO.FS.writeFile (directory / filename) contents

syntax (name := lemmaExportUnit) "#lemma_export_unit " str "[" ident,* "]" : command

elab_rules : command
  | `(#lemma_export_unit $role:str [$decls:ident,*]) => do
      let some role := role.raw.isStrLit? | throwError "production role must be a literal string"
      let mut names := #[]
      for declaration in decls.getElems do names := names.push (← resolveGlobalConstNoOverload declaration)
      let some output ← liftIO <| IO.getEnv "LEMMA_KERNEL_OUT"
        | throwError "LEMMA_KERNEL_OUT must name the generated production unit directory"
      let configuration ← liftIO readConfiguration
      liftIO <| exportUnit (← getEnv) configuration role names (System.FilePath.mk output)
      logInfo m!"Lemma exported {configuration} {role} unit to {output}"

syntax (name := lemmaExportBootFiles) "#lemma_export_boot_files" : command

elab_rules : command
  | `(#lemma_export_boot_files) => do
      let some output ← liftIO <| IO.getEnv "LEMMA_KERNEL_OUT"
        | throwError "LEMMA_KERNEL_OUT must name the generated boot directory"
      let some stage ← liftIO <| IO.getEnv "LEMMA_KERNEL_STAGE"
        | throwError "LEMMA_KERNEL_STAGE must be bootstrap-m or supervisor"
      let stage ← match stage with
        | "bootstrap-m" => pure Lemma.Platform.RiscV.ExecutionPrimitives.Stage.bootstrapM
        | "supervisor" => pure Lemma.Platform.RiscV.ExecutionPrimitives.Stage.supervisor
        | _ => throwError "LEMMA_KERNEL_STAGE must be bootstrap-m or supervisor"
      let configuration ← liftIO readConfiguration
      liftIO <| exportBootFiles (System.FilePath.mk output) configuration stage
      logInfo m!"Lemma exported {configuration} {stage.stableId} boot files to {output}"

end Lemma.Compiler.KernelExport
