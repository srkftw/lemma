import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.Format
import Lemma.Compiler.DeploymentCatalog
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
open DeploymentCatalog

private def roleProfile (role : String) : Except String Profile :=
  match role with
  | "firmware" => .ok .firmware_v0_1
  | "kernel" => .ok .kernel_v0_2
  | "user" => .ok .user_v0_1
  | _ => .error "production role must be firmware, kernel, or user"

private def readConfiguration : IO String := do
  let some configuration ← IO.getEnv "LEMMA_KERNEL_CONFIGURATION"
    | throw <| IO.userError "LEMMA_KERNEL_CONFIGURATION must select an admitted exact configuration"
  unless configuration == "normal" || configuration == "frames-development" ||
      configuration == "machine-origin-development" || configuration == "user-isolation-development" ||
      configuration == "user-csr-development" || configuration == "user-nx-development" ||
      configuration == "user-kernel-fetch-development" || configuration == "user-misaligned-development" ||
      configuration == "user-syscall-development" || isMultiImageConfiguration configuration do
    throw <| IO.userError "LEMMA_KERNEL_CONFIGURATION must select an admitted exact configuration"
  pure configuration

/-- The startup probe is selected only by its exact quarantined configuration,
not by an independent environment switch or by a supplied instruction list. -/
private def startupCase (configuration : String) : Lemma.Platform.RiscV.ExecutionPrimitives.StartupCase :=
  if configuration == "machine-origin-development" then .machineOriginProbe else .normal

private def userStartupCase (configuration : String) : Lemma.Platform.RiscV.ExecutionPrimitives.UserStartupCase :=
  if configuration == "user-csr-development" then .supervisorCsr
  else if configuration == "user-nx-development" then .executeData
  else if configuration == "user-kernel-fetch-development" then .executeKernel
  else if configuration == "user-misaligned-development" then .executeMisaligned else .none

private def requiresSupervisor (configuration : String) : Bool :=
  configuration == "user-isolation-development" || configuration == "user-csr-development" ||
    configuration == "user-nx-development" || configuration == "user-kernel-fetch-development" ||
    configuration == "user-misaligned-development" || configuration == "user-syscall-development" ||
    isMultiImageConfiguration configuration

private def unitCategory (configuration role : String) : String :=
  (if configuration == "normal" || configuration == "service-normal" then
    "production-" else "development-") ++ role ++ "-unit"

private def rootIdentities (configuration role : String) : Array String :=
  match role with
  | "firmware" => #["Lemma.Platform.RiscV.Firmware.dispatch"]
  | "kernel" => if configuration == "frames-development" then
      #["Lemma.Kernel.Development.FramesEntry.boot", "Lemma.Kernel.Development.FramesEntry.dispatch"]
    else if configuration == "user-isolation-development" then
      #["Lemma.Kernel.Development.IsolationEntry.boot", "Lemma.Kernel.Development.IsolationEntry.dispatch"]
    else if configuration == "tasks-development" then
      #["Lemma.Kernel.Development.TasksEntry.boot", "Lemma.Kernel.Development.TasksEntry.dispatch"]
    else if configuration == "tasks-fault-development" then
      #["Lemma.Kernel.Development.FaultEntry.boot", "Lemma.Kernel.Development.FaultEntry.dispatch"]
    else if configuration == "capabilities-development" then
      #["Lemma.Kernel.Development.CapsEntry.boot", "Lemma.Kernel.Development.CapsEntry.dispatch"]
    else if configuration == "ipc-development" then
      #["Lemma.Kernel.Development.IPCEntry.boot", "Lemma.Kernel.Development.IPCEntry.dispatch"]
    else if configuration == "service-normal" then
      #["Lemma.Kernel.ServiceEntry.boot", "Lemma.Kernel.ServiceEntry.dispatch"]
    else if configuration == "service-development" then
      #["Lemma.Kernel.Development.ServiceEntry.boot", "Lemma.Kernel.Development.ServiceEntry.dispatch"]
    else #["Lemma.Kernel.Entry.boot", "Lemma.Kernel.Entry.dispatch"]
  | "user" => if configuration == "user-isolation-development" then
      #["Lemma.User.Development.Isolation.main"]
    else if configuration == "user-syscall-development" then
      #["Lemma.User.Development.Syscall.main"] else #["Lemma.User.Entry.main"]
  | _ => #[]

private def rootArguments (role : String) : Array (Array Ty) :=
  match role with
  | "firmware" => #[#[.u64, .u64, .u64]]
  | "kernel" => #[#[], #[.u64, .u64, .u64]]
  | "user" => #[#[.u64]]
  | _ => #[]

private def developmentModules (configuration role : String) (image? : Option UserImageSpec := none) : Array String :=
  if let some image := image? then
    if image.moduleName.toString.startsWith "Lemma.User.Development." then #[image.moduleName.toString]
    else #[]
  else if configuration == "tasks-development" && role == "kernel" then
    #["Lemma.Kernel.Development.TasksEntry"]
  else if configuration == "tasks-fault-development" && role == "kernel" then
    #["Lemma.Kernel.Development.FaultEntry", "Lemma.Kernel.Development.TasksEntry",
      "Lemma.Kernel.Development.Pressure"]
  else if configuration == "capabilities-development" && role == "kernel" then
    #["Lemma.Kernel.Development.CapsEntry", "Lemma.Kernel.Development.CapAlias",
      "Lemma.Kernel.Development.TasksEntry", "Lemma.Kernel.Development.CapabilityGeneration"]
  else if configuration == "ipc-development" && role == "kernel" then
    #["Lemma.Kernel.Development.IPCEntry", "Lemma.Kernel.Development.TasksEntry"]
  else if configuration == "service-development" && role == "kernel" then
    #["Lemma.Kernel.Development.ServiceEntry"]
  else if configuration == "frames-development" && role == "kernel" then
    #["Lemma.Kernel.Development.FramesEntry"]
  else if configuration == "user-isolation-development" && role == "kernel" then
    #["Lemma.Kernel.Development.IsolationEntry"]
  else if configuration == "user-isolation-development" && role == "user" then
    #["Lemma.User.Development.Isolation"]
  else if configuration == "user-syscall-development" && role == "user" then
    #["Lemma.User.Development.Syscall"]
  else #[]

private def developmentName (name : Name) : Bool :=
  let source := (Lean.privateToUserName? name).getD name |>.toString
  source.startsWith "Lemma.Kernel.Development." || source.startsWith "Lemma.User.Development."

private def allowedDevelopmentSource (configuration role : String) (name : Name)
    (image? : Option UserImageSpec := none) : Bool :=
  if !developmentName name then true else
    (developmentModules configuration role image?).any fun scope =>
      ((Lean.privateToUserName? name).getD name |>.toString).startsWith (scope ++ ".")

private def validateSelectedRoots (configuration role : String) (names : Array Name)
    (image? : Option UserImageSpec := none) : Except String Unit := do
  if let some image := image? then
    unless role == "user" && (← imageFor configuration image.key) == image do
      throw "user image identity differs from the closed selected deployment"
    let _ ← validateSelection configuration image.key names
  else if isMultiImageConfiguration configuration && role == "user" then
    throw "multiimage users require the closed per-image export command"
  else unless names.map Name.toString == rootIdentities configuration role do
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

private def managedPolicyFields (configuration : String) : List (String × Json) :=
  ((managedPolicyFor configuration).map fun policy => [("managed_policy", Json.str policy)]).getD []

private def imageBootRoleFields (image? : Option UserImageSpec) : List (String × Json) :=
  ((image?.bind (·.bootRole?)).map fun role => [("boot_role", Json.str role.stableId)]).getD []

private def managedUserSource (configuration role : String) (name : Name) : Bool :=
  if (managedPolicyFor configuration).isNone || role != "user" then true else
    let source := (Lean.privateToUserName? name).getD name |>.toString
    !source.startsWith "Lemma.Kernel." && !source.startsWith "Lemma.Compiler."

/-- Application/service executable modules are independent linkage roots, not
shared libraries. Gate J may import only the selected executable namespace. -/
private def serviceExecutableSource (source : String) : Bool :=
  source.startsWith "Lemma.Applications." || source == "Lemma.Services.Buffer.Server" ||
    source.startsWith "Lemma.Services.Buffer.Server." || source == "Lemma.User.Development.BufferFault" ||
    source.startsWith "Lemma.User.Development.BufferFault."

private def selectedExecutableSource (configuration role source : String)
    (image? : Option UserImageSpec) : Bool :=
  if configuration != "service-normal" && configuration != "service-development" then true
  else if !serviceExecutableSource source then true
  else if role != "user" then false
  else image?.any fun image => source == image.moduleName.toString ||
    source.startsWith (image.moduleName.toString ++ ".")

private def rootSymbol (lowered : LoweredActionSuite) (name : Name) : Except String String := do
  let some symbol := lowered.symbols.find? (fun symbol => symbol.source == name)
    | throw s!"production lowering omitted source `{name}`"
  pure symbol.llvm

private def deviceSourceIdentity : Device.Op → String
  | .uartReadStatus => "Lemma.Core0.Memory.Action.uartReadStatus"
  | .uartReadByte => "Lemma.Core0.Memory.Action.uartReadByte"
  | .uartWriteByte => "Lemma.Core0.Memory.Action.uartWriteByte"
  | .uartEnableAndResetFifo => "Lemma.Core0.Memory.Action.uartEnableAndResetFifo"
  | .uartEnableAndResetFifo14 => "Lemma.Core0.Memory.Action.uartEnableAndResetFifo14"

private def deviceLoweringId : Device.Op → String
  | .uartReadStatus => "uart.lsr.read8"
  | .uartReadByte => "uart.rbr.read8"
  | .uartWriteByte => "uart.thr.write8"
  | .uartEnableAndResetFifo => "uart.fcr.enable-reset"
  | .uartEnableAndResetFifo14 => "uart.fcr.enable-reset-trigger14"

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
          | .uartEnableAndResetFifo14 site, .uartEnableAndResetFifo14 => some site
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
    (lowered : LoweredActionSuite) (image? : Option UserImageSpec := none) : Except String Json := do
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
  let imageFields := match image? with
    | none => []
    | some image => [("image_key", Json.str image.key), ("image_id", toJson image.id)] ++
      (if configuration == "tasks-fault-development" || (managedPolicyFor configuration).isSome then
        [("startup_case", Json.str image.startupCase.stableId)] else []) ++ imageBootRoleFields image?
  pure <| Json.mkObj ([("schema_version", toJson (if image?.isSome then (2 : Nat) else 1)), ("artifact_category", .str (unitCategory configuration role)),
    ("configuration", .str configuration),
    ("contract_version", .str suite.contractVersion), ("role", .str role), ("roots", .arr roots),
    ("functions", .arr functions), ("used_execution_ops", .arr (suite.usedExecutionOps.map executionJson)),
    ("used_device_ops", .arr devices), ("used_loops", .arr (suite.usedLoops.map fun use =>
      Json.mkObj [("stable_id", .str use.stableId), ("callback", .str use.callback.toString)]))] ++ imageFields ++ managedPolicyFields configuration)

private def loopJson (use : ActionLoopUse) : Json :=
  Json.mkObj [("stable_id", .str use.stableId), ("callback", .str use.callback.toString)]

private def normalized (configuration role : String) (suite : CheckedActionSuite)
    (image? : Option UserImageSpec := none) : String :=
  s!"configuration={configuration}\nrole={role}\ncontract={suite.contractVersion}\n" ++
    (((managedPolicyFor configuration).map fun policy => s!"managed_policy={policy}\n").getD "") ++
    ((image?.map (fun image => s!"image_key={image.key}\nimage_id={image.id}\n" ++
      (if configuration == "tasks-fault-development" || (managedPolicyFor configuration).isSome then
        s!"startup_case={image.startupCase.stableId}\n" else "") ++
      ((image.bootRole?.map fun role => s!"boot_role={role.stableId}\n").getD ""))).getD "") ++
    String.join (suite.scalarFunctions.toList.map fun function =>
      s!"scalar={function.name};args={repr function.signature.args};result={function.signature.result.render}\n" ++
        function.body.renderNormalized ++ "\n") ++
    String.join (suite.actionFunctions.toList.map fun function =>
      s!"action={function.name};args={repr function.signature.args};effects={function.effects.render}\n" ++
        function.body.renderNormalized ++ "\n") ++
    String.join (suite.usedExecutionOps.toList.map fun spec => "execution=" ++ (executionJson spec).compress ++ "\n") ++
    String.join (suite.usedDeviceOps.toList.map fun operation => s!"device={operation.stableId}\n") ++
    String.join (suite.usedLoops.toList.map fun use => "loop=" ++ (loopJson use).compress ++ "\n")

private def validateRoots (configuration role : String) (suite : CheckedActionSuite)
    (image? : Option UserImageSpec := none) : Except String Unit := do
  validateSelectedRoots configuration role (suite.roots.map (·.source)) image?
  unless suite.roots.map (·.signature.args) == rootArguments role do
    throw s!"{configuration} {role} signatures differ from the admitted entry/dispatch ABI"

private def exportUnit (env : Environment) (configuration role : String) (names : Array Name)
    (directory : System.FilePath) (image? : Option UserImageSpec := none) : IO Unit := do
  let profile ← IO.ofExcept (roleProfile role)
  IO.ofExcept <| validateSelectedRoots configuration role names image?
  for imported in env.header.moduleNames do
    unless selectedExecutableSource configuration role imported.toString image? do
      throw <| IO.userError s!"{configuration} {role} imports sibling executable module `{imported}`"
    if (configuration == "tasks-fault-development" || (managedPolicyFor configuration).isSome) &&
        (imported.toString == "Lemma.Compiler.Test" || imported.toString.startsWith "Lemma.Compiler.Test.") then
      throw <| IO.userError s!"{configuration} {role} imports forbidden compiler test module `{imported}`"
    if developmentName imported then
      unless (developmentModules configuration role image?).contains imported.toString do
        throw <| IO.userError s!"{configuration} {role} imports forbidden development module `{imported}`"
  let suite ← match checkAndLowerActionSuiteForProfile env profile names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  IO.ofExcept (validateRoots configuration role suite image?)
  for function in suite.scalarFunctions do
    unless productionName function.name && allowedDevelopmentSource configuration role function.name image? &&
        managedUserSource configuration role function.name &&
        selectedExecutableSource configuration role ((Lean.privateToUserName? function.name).getD function.name).toString image? do
      throw <| IO.userError s!"forbidden reachable source `{function.name}` for {configuration} {role}"
  for function in suite.actionFunctions do
    unless productionName function.name && allowedDevelopmentSource configuration role function.name image? &&
        managedUserSource configuration role function.name &&
        selectedExecutableSource configuration role ((Lean.privateToUserName? function.name).getD function.name).toString image? do
      throw <| IO.userError s!"forbidden reachable source `{function.name}` for {configuration} {role}"
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {
    preserveCalls := preserved, symbolPrefix := image?.map (·.symbolPrefix) |>.getD ("lemma_" ++ role ++ "_") }
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
  let manifest ← IO.ofExcept <| unitManifest configuration role suite lowered image?
  IO.FS.createDirAll directory
  for (filename, contents) in #[("program.ll", module.render), ("unit.json", manifest.pretty ++ "\n"),
      ("normalized.txt", normalized configuration role suite image?), ("symbols.txt", lowered.renderSymbolManifest)] do
    IO.FS.writeFile (directory / filename) contents

private def layoutJson (configuration : String)
    (image? : Option UserImageSpec := none) : Json := Json.mkObj ([
  ("configuration", .str configuration),
  ("startup_case", .str (startupCase configuration).stableId),
  ("user_startup_case", .str (image?.map (·.startupCase) |>.getD (userStartupCase configuration)).stableId),
  ("schema_version", 1), ("contract_version", .str "lemma-kernel-layout-v1"),
  ("ram_base", toJson Layout.ramBase), ("ram_limit", toJson Layout.ramLimit),
  ("frame_bytes", toJson Layout.frameBytes), ("frame_count", toJson Layout.frameCount),
  ("task_kernel_stack_pages", toJson Layout.taskKernelStackPages),
  ("task_kernel_stack_bytes", toJson Layout.taskKernelStackBytes),
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
    ("stack_base", toJson Layout.userStackBase), ("stack_pages", toJson Layout.userStackPages)])] ++
    managedPolicyFields configuration ++ imageBootRoleFields image?)

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

private def userLinker (directory : String := "user") : String := String.intercalate "\n" [
  "OUTPUT_ARCH(riscv)", "ENTRY(_user_start)", "PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }", "SECTIONS {",
  s!"  . = {Layout.userTextBase};", "  .text : ALIGN(4096) { " ++ directory ++ "/startup.o(.text.user_start) *(.text .text.* .rodata .rodata.*) } :text",
  s!"  ASSERT(. <= {Layout.userTextLimit}, \"user text envelope exceeded\")",
  s!"  . = {Layout.userDataBase};", "  .data : ALIGN(4096) { *(.data .data.* .sdata .sdata.*) } :data",
  "  __user_data_file_end = .;", "  .bss (NOLOAD) : ALIGN(8) { *(.bss .bss.* .sbss .sbss.*) *(COMMON)",
  s!"    . = MAX(., ABSOLUTE({Layout.userDataBase + Layout.userDataBytes})); } :data",
  s!"  ASSERT(. <= {Layout.userDataBase + Layout.userDataBytes}, \"user data/BSS envelope exceeded\")",
  "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }", "}", ""]

private def packageContract (configuration : String) : Json := Json.mkObj [
  ("configuration", .str configuration),
  ("startup_case", .str (startupCase configuration).stableId),
  ("user_startup_case", .str (userStartupCase configuration).stableId),
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
    (index : Nat) (image? : Option UserImageSpec := none) : IO String := do
  let unitDirectory := directory / (image?.map (·.directory) |>.getD role)
  let contents ← IO.FS.readFile (unitDirectory / "unit.json")
  let manifest ← IO.ofExcept <| Json.parse contents
  let actualRole ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "role").getStr?
  let actualConfiguration ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "configuration").getStr?
  let contract ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "contract_version").getStr?
  let category ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "artifact_category").getStr?
  let version ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "schema_version").getNat?
  let profile ← IO.ofExcept <| roleProfile role
  unless actualRole == role && actualConfiguration == configuration &&
      contract == profile.contractVersion && version == (if image?.isSome then 2 else 1) &&
      category == unitCategory configuration role do
    throw <| IO.userError "boot export rejected inconsistent unit configuration/identity"
  if let some policy := managedPolicyFor configuration then
    unless jsonFieldEquals manifest "managed_policy" (.str policy) do
      throw <| IO.userError "boot export rejected a crossing managed policy"
  if let some image := image? then
    IO.ofExcept <| validateSelectedRoots configuration role #[image.root] image?
    unless jsonFieldEquals manifest "image_key" (.str image.key) &&
        jsonFieldEquals manifest "image_id" (toJson image.id) do
      throw <| IO.userError "boot export rejected a crossing user image identity"
    if configuration == "tasks-fault-development" || (managedPolicyFor configuration).isSome then
      unless jsonFieldEquals manifest "startup_case" (.str image.startupCase.stableId) do
        throw <| IO.userError "boot export rejected a crossing user startup authority"
    if let some role := image.bootRole? then
      unless jsonFieldEquals manifest "boot_role" (.str role.stableId) do
        throw <| IO.userError "boot export rejected a crossing managed boot role"
  let roots ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "roots").getArr?
  let functions ← IO.ofExcept <| (← IO.ofExcept <| manifest.getObjVal? "functions").getArr?
  let expectedSources := image?.map (fun image => #[image.root.toString]) |>.getD (rootIdentities configuration role)
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
    unless symbol.startsWith (image?.map (·.symbolPrefix) |>.getD ("lemma_" ++ role ++ "_")) && !symbols.contains symbol do
      throw <| IO.userError "boot export rejected a role-crossing or duplicate entry symbol"
    symbols := symbols.push symbol
  let some symbol := symbols[index]? | throw <| IO.userError s!"boot export omitted {role} entry {index}"
  pure symbol

private def userSymbolsJson (image : UserImageSpec) : Json := .arr
  ((Lemma.Platform.RiscV.ExecutionPrimitives.userPrimitiveCatalog image.startupCase).map fun (symbol, privilege, effect) =>
    Json.mkObj [("symbol", .str symbol), ("privilege", .str privilege), ("effect", .str effect)])

private def userImageCatalog (configuration : String) (image : UserImageSpec) : Json := Json.mkObj ([
  ("schema_version", 1), ("contract_version", .str "lemma-user-execution-v1"),
  ("configuration", .str configuration), ("image_key", .str image.key), ("image_id", toJson image.id),
  ("startup_case", .str image.startupCase.stableId), ("symbols", userSymbolsJson image)] ++
  managedPolicyFields configuration ++ imageBootRoleFields (some image))

private def exportUserFiles (directory : System.FilePath) (configuration : String)
    (image : UserImageSpec) : IO Unit := do
  let user ← readRootSymbol directory configuration "user" 0 (some image)
  let startup ← IO.ofExcept <| Lemma.Platform.RiscV.ExecutionPrimitives.renderUserStartup user image.startupCase
  let target := directory / image.directory
  for (filename, contents) in #[("startup.S", startup), ("link.ld", userLinker image.directory),
      ("layout.json", (layoutJson configuration (some image)).pretty ++ "\n"),
      ("primitive-catalog.json", (userImageCatalog configuration image).pretty ++ "\n")] do
    IO.FS.writeFile (target / filename) contents

private def multiPackageContract (configuration : String) (images : Array UserImageSpec) : Json :=
  Json.mkObj ([("schema_version", 2), ("contract_version", .str "lemma-boot-package-v1"),
    ("configuration", .str configuration), ("startup_case", .str "normal"), ("user_startup_case", .str "none"),
    ("magic", toJson (0x31474b50414d454c : Nat)), ("version", 1), ("image_count", toJson images.size),
    ("header_bytes", 32), ("descriptor_bytes", 96), ("offset_encoding", .str "generated-label-differences"),
    ("images", .arr (images.map fun image => Json.mkObj ([
      ("key", .str image.key), ("id", toJson image.id), ("entry", toJson Layout.userTextBase),
      ("text_va", toJson Layout.userTextBase), ("text_capacity", toJson (Layout.userTextLimit - Layout.userTextBase)),
      ("data_va", toJson Layout.userDataBase), ("data_mem_bytes", toJson Layout.userDataBytes),
      ("stack_va", toJson Layout.userStackBase), ("stack_pages", toJson Layout.userStackPages), ("flags", 0)] ++
      imageBootRoleFields (some image))))] ++ managedPolicyFields configuration)

/-- Data-only package construction. Sizes/offsets are assembler label
differences over the actual separately linked bytes, never predicted values. -/
private def multiPackageData (images : Array UserImageSpec) : String := Id.run do
  let mut lines := #[".section .boot_package, \"a\", @progbits", ".balign 8", ".globl lemma_boot_package",
    "lemma_boot_package:", "  .quad 0x31474b50414d454c", "  .quad 1", s!"  .quad {images.size}",
    "  .quad .Llemma_package_end - lemma_boot_package"]
  for image in images do
    let label := ".Llemma_package_" ++ image.key
    lines := lines ++ #[s!"  .quad {image.id}", s!"  .quad {Layout.userTextBase}", s!"  .quad {Layout.userTextBase}",
      s!"  .quad {label}_text - lemma_boot_package", s!"  .quad {label}_text_end - {label}_text",
      s!"  .quad {Layout.userDataBase}", s!"  .quad {label}_data - lemma_boot_package",
      s!"  .quad {label}_data_end - {label}_data", s!"  .quad {Layout.userDataBytes}",
      s!"  .quad {Layout.userStackBase}", s!"  .quad {Layout.userStackPages}", "  .quad 0"]
  for image in images do
    let label := ".Llemma_package_" ++ image.key
    lines := lines ++ #[".balign 8", label ++ "_text:", s!"  .incbin \"{image.directory}/text.bin\"",
      label ++ "_text_end:", ".balign 8", label ++ "_data:", s!"  .incbin \"{image.directory}/data.bin\"",
      label ++ "_data_end:"]
  lines := lines ++ #[".Llemma_package_end:", ".section .note.GNU-stack, \"\", @progbits", ""]
  return String.intercalate "\n" lines.toList

private def exportBootFiles (directory : System.FilePath) (configuration : String)
    (stage : Lemma.Platform.RiscV.ExecutionPrimitives.Stage) : IO Unit := do
  if configuration == "machine-origin-development" && stage != .bootstrapM then
    throw <| IO.userError "machine-origin-development requires bootstrap-m stage"
  if requiresSupervisor configuration && stage != .supervisor then
    throw <| IO.userError s!"{configuration} requires supervisor stage"
  unless Layout.valid do throw <| IO.userError "authoritative boot layout is invalid"
  let firmware ← readRootSymbol directory configuration "firmware" 0
  let kernel ← readRootSymbol directory configuration "kernel" 0
  let dispatcher ← readRootSymbol directory configuration "kernel" 1
  let config : Lemma.Platform.RiscV.ExecutionPrimitives.Configuration := {
    stage, startupCase := startupCase configuration, userStartupCase := userStartupCase configuration,
    kernelMain := kernel, firmwareDispatcher := firmware, supervisorDispatcher := dispatcher }
  let startup ← IO.ofExcept <| Lemma.Platform.RiscV.ExecutionPrimitives.renderStartup config
  if isMultiImageConfiguration configuration then
    let images ← IO.ofExcept <| imagesFor configuration
    IO.ofExcept <| validateImages configuration images
    for image in images do exportUserFiles directory configuration image
    let catalog := Json.mkObj ([("schema_version", 2), ("contract_version", .str "lemma-execution-v1"),
      ("configuration", .str configuration), ("stage", .str stage.stableId),
      ("startup_case", .str config.startupCase.stableId), ("user_startup_case", .str config.userStartupCase.stableId),
      ("symbols", .arr ((Lemma.Platform.RiscV.ExecutionPrimitives.primitiveCatalog config).map fun (symbol, privilege, effect) =>
        Json.mkObj [("symbol", .str symbol), ("privilege", .str privilege), ("effect", .str effect)])),
      ("user_images", .arr (images.map fun image => Json.mkObj ([
        ("key", .str image.key), ("id", toJson image.id),
        ("startup_case", .str image.startupCase.stableId), ("symbols", userSymbolsJson image)] ++
        imageBootRoleFields (some image))))] ++ managedPolicyFields configuration)
    for (filename, contents) in #[("startup.S", startup), ("link.ld", bootLinker),
        ("layout.json", (layoutJson configuration).pretty ++ "\n"), ("primitive-catalog.json", catalog.pretty ++ "\n"),
        ("boot-package.S", multiPackageData images), ("package-contract.json", (multiPackageContract configuration images).pretty ++ "\n"),
        ("user-image-catalog.json", (← IO.ofExcept <| catalogJson configuration).pretty ++ "\n")] do
      IO.FS.writeFile (directory / filename) contents
    return
  let user ← readRootSymbol directory configuration "user" 0
  let userStartup ← IO.ofExcept <| Lemma.Platform.RiscV.ExecutionPrimitives.renderUserStartup user config.userStartupCase
  let catalog := Json.mkObj [("schema_version", 1), ("contract_version", .str "lemma-execution-v1"),
    ("configuration", .str configuration), ("stage", .str stage.stableId),
    ("startup_case", .str config.startupCase.stableId),
    ("user_startup_case", .str config.userStartupCase.stableId), ("symbols", .arr
      ((Lemma.Platform.RiscV.ExecutionPrimitives.primitiveCatalog config).map fun (symbol, privilege, effect) =>
        Json.mkObj [("symbol", .str symbol), ("privilege", .str privilege), ("effect", .str effect)])),
    ("user_symbols", .arr
      ((Lemma.Platform.RiscV.ExecutionPrimitives.userPrimitiveCatalog config.userStartupCase).map fun (symbol, privilege, effect) =>
        Json.mkObj [("symbol", .str symbol), ("privilege", .str privilege), ("effect", .str effect)]))]
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

syntax (name := lemmaExportUserCatalog) "#lemma_export_user_catalog" : command

elab_rules : command
  | `(#lemma_export_user_catalog) => do
      let some output ← liftIO <| IO.getEnv "LEMMA_KERNEL_OUT"
        | throwError "LEMMA_KERNEL_OUT must name the deployment directory"
      let configuration ← liftIO readConfiguration
      let catalog ← match catalogJson configuration with
        | .ok catalog => pure catalog
        | .error error => throwError error
      liftIO do
        IO.FS.createDirAll output
        IO.FS.writeFile (System.FilePath.mk output / "user-image-catalog.json") (catalog.pretty ++ "\n")
      logInfo m!"Lemma exported the closed {configuration} user image catalog"

syntax (name := lemmaExportUserImage) "#lemma_export_user_image " str "[" ident,* "]" : command

elab_rules : command
  | `(#lemma_export_user_image $key:str [$decls:ident,*]) => do
      let some key := key.raw.isStrLit? | throwError "user image key must be a literal string"
      let mut names := #[]
      for declaration in decls.getElems do names := names.push (← resolveGlobalConstNoOverload declaration)
      let configuration ← liftIO readConfiguration
      let image ← match validateSelection configuration key names with
        | .ok image => pure image
        | .error error => throwError error
      let some output ← liftIO <| IO.getEnv "LEMMA_KERNEL_OUT"
        | throwError "LEMMA_KERNEL_OUT must name the deployment directory"
      liftIO <| exportUnit (← getEnv) configuration "user" names (System.FilePath.mk output / image.directory) (some image)
      logInfo m!"Lemma exported the genuine {configuration} user image {key}"

syntax (name := lemmaExportUserFiles) "#lemma_export_user_files " str : command

elab_rules : command
  | `(#lemma_export_user_files $key:str) => do
      let some key := key.raw.isStrLit? | throwError "user image key must be a literal string"
      let configuration ← liftIO readConfiguration
      let image ← match imageFor configuration key with
        | .ok image => pure image
        | .error error => throwError error
      let some output ← liftIO <| IO.getEnv "LEMMA_KERNEL_OUT"
        | throwError "LEMMA_KERNEL_OUT must name the deployment directory"
      liftIO <| exportUserFiles (System.FilePath.mk output) configuration image
      logInfo m!"Lemma exported independent user startup/layout files for {key}"

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
