import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.Format
import Lemma.Compiler.Test.DeviceABI
import Lemma.Machine.DeviceHarness
import Lemma.Machine.DeviceLayout
import Lemma.Machine.Primitives

/-! Fixed exporter for the genuine `core0-v0.5` compiled UART session. -/

namespace Lemma.Compiler.Test.DeviceExport

open Lean Elab Command
open Lemma.Compiler
open Lemma.Compiler.Test.DeviceABI

private def quoted (value : String) : String :=
  "\"" ++ Lemma.Compiler.Format.escapeJson value ++ "\""

private def jsonArray (values : List String) : String :=
  "[" ++ String.intercalate "," values ++ "]"

private def renderScalarSignature (signature : Lemma.Core0.Signature) : String :=
  let args := signature.args.toList.map (quoted ∘ Lemma.Core0.Ty.render)
  "{\"args\":" ++ jsonArray args ++
    ",\"result\":" ++ quoted signature.result.render ++ "}"

private def renderActionSignature (signature : Lemma.Core0.ActionSignature) : String :=
  let args := signature.args.toList.map (quoted ∘ Lemma.Core0.Ty.render)
  "{\"args\":" ++ jsonArray args ++ "}"

private def effectNames (effects : Lemma.Core0.EffectSet) : List String :=
  (if effects.checkedAccess then ["checked-access"] else []) ++
  (if effects.ramRead then ["fixed-ram-read"] else []) ++
  (if effects.ramWrite then ["fixed-ram-write"] else []) ++
  (if effects.mmioRead then ["mmio-read"] else []) ++
  (if effects.mmioWrite then ["mmio-write"] else []) ++
  (if effects.ioOrder then ["io-order"] else []) ++
  (if effects.syncTrap then ["sync-trap"] else []) ++
  (if effects.machineState then ["machine-state"] else [])

def renderEffects (effects : Lemma.Core0.EffectSet) : String :=
  jsonArray (effectNames effects |>.map quoted)

private def renderPrimitive (stableId : String) : String :=
  let candidates := Lemma.Core0.primitiveAllowlistV05.toList.filter
    (fun spec => spec.stableId == stableId)
  let leanIdentities := candidates.map (quoted ∘ (fun spec => spec.leanDecl.toString))
  let signature := candidates.head?.map (renderScalarSignature ∘ (fun spec => spec.signature))
    |>.getD "null"
  "{" ++
    "\"stable_id\":" ++ quoted stableId ++ "," ++
    "\"lean_identities\":" ++ jsonArray leanIdentities ++ "," ++
    "\"signature\":" ++ signature ++ "," ++
    "\"effect\":\"pure\"}"

private def memorySourceIdentity (use : Lemma.Core0.MemoryOpUse) : String :=
  if use.range then
    match use.access with
    | .read => "Lemma.Core0.Memory.Action.checkReadRange"
    | .write => "Lemma.Core0.Memory.Action.checkWriteRange"
  else
    let constructor := match use.access with
      | .read => "load"
      | .write => "store"
    let suffix := use.width?.map Lemma.Core0.Memory.Width.render |>.getD "?"
    "Lemma.Core0.Memory.Action." ++ constructor ++ suffix

private def renderMemoryUse (use : Lemma.Core0.MemoryOpUse) : String :=
  let effect := if use.range then "checked-access" else match use.access with
    | .read => "fixed-ram-read"
    | .write => "fixed-ram-write"
  let width := use.width?.map (toString ∘ Lemma.Core0.Memory.Width.bits) |>.getD "null"
  "{" ++
    "\"stable_id\":" ++ quoted use.stableId ++ "," ++
    "\"source_identity\":" ++ quoted (memorySourceIdentity use) ++ "," ++
    "\"access\":" ++ quoted use.access.render ++ "," ++
    "\"width\":" ++ width ++ "," ++
    "\"range\":" ++ toString use.range ++ "," ++
    "\"effect\":" ++ quoted effect ++ "}"

private def sideEffectName : Lemma.Core0.Device.SideEffect → String
  | .observeLineStatus => "observe-line-status-and-clear-BI-OE"
  | .consumeReceiveByte => "consume-rx-fifo-byte-and-update-DR"
  | .transmitByte => "transmit-byte-and-clear-THRE-TEMT"
  | .enableAndResetFifos => "enable-fifo-and-clear-rx-tx"

private def deviceSourceIdentity : Lemma.Core0.Device.Op → String
  | .uartReadStatus => "Lemma.Core0.Memory.Action.uartReadStatus"
  | .uartReadByte => "Lemma.Core0.Memory.Action.uartReadByte"
  | .uartWriteByte => "Lemma.Core0.Memory.Action.uartWriteByte"
  | .uartEnableAndResetFifo => "Lemma.Core0.Memory.Action.uartEnableAndResetFifo"

private def renderDeviceUse (op : Lemma.Core0.Device.Op)
    (spec : Lemma.Core0.Device.OpSpec) : String :=
  let fixedWrite := spec.fixedWriteValue?.map (toString ∘ UInt8.toNat) |>.getD "null"
  "{" ++
    "\"stable_id\":" ++ quoted op.stableId ++ "," ++
    "\"source_identity\":" ++ quoted (deviceSourceIdentity op) ++ "," ++
    "\"access\":" ++ quoted spec.access.render ++ "," ++
    "\"base\":" ++ quoted (Lemma.Compiler.Format.hexAddr spec.base.toNat) ++ "," ++
    "\"offset\":" ++ toString spec.offset.toNat ++ "," ++
    "\"address\":" ++ quoted
      (Lemma.Compiler.Format.hexAddr (spec.base.toNat + spec.offset.toNat)) ++ "," ++
    "\"width_bits\":8,\"alignment\":1,\"volatile\":true," ++
    "\"fence_before\":" ++ toString spec.fenceBefore ++ "," ++
    "\"fence_after\":" ++ toString spec.fenceAfter ++ "," ++
    "\"fixed_write_value\":" ++ fixedWrite ++ "," ++
    "\"side_effect\":" ++ quoted (sideEffectName spec.sideEffect) ++ "}"

private def renderActionIteration (site : Lemma.Core0.ActionIterationUse) : String :=
  "{" ++
    "\"stable_id\":" ++ quoted site.stableId ++ "," ++
    "\"source_identity\":\"Lemma.Core0.Memory.Action.boundedFoldU64\"," ++
    "\"static_budget\":" ++ toString site.budget ++ "," ++
    "\"callback\":" ++ quoted site.callback.toString ++ "," ++
    "\"maximum_budget\":1000000," ++
    "\"counter\":{\"type\":\"u32\",\"order\":\"ascending-zero-based\"}," ++
    "\"accumulator\":\"u64\",\"contexts\":4," ++
    "\"outcome\":\"checked-result-v1\"," ++
    "\"exhaustion\":{\"status\":9,\"value\":\"initial\",\"callbacks\":0}}"

def renderManifest (suite : Lemma.Core0.CheckedActionSuite)
    (lowered : LoweredActionSuite) (layout : Lemma.Machine.DeviceLayout)
    (config : Configuration) : Except String String := do
  let memoryContract ← layout.memory.memoryContractJson
  let deviceContract ← layout.deviceContractJson
  let roots := lowered.roots.toList.map fun root =>
    "{" ++
      "\"root_id\":" ++ toString root.id ++ "," ++
      "\"source\":" ++ quoted root.source.toString ++ "," ++
      "\"llvm\":" ++ quoted root.llvm ++ "," ++
      "\"signature\":" ++ renderActionSignature root.signature ++ "}"
  let scalarFunctions := suite.scalarFunctions.toList.map fun function =>
    let symbol := lowered.symbols.find? (fun candidate => candidate.source == function.name)
      |>.map (fun candidate => candidate.llvm) |>.getD "<missing>"
    "{" ++
      "\"source\":" ++ quoted function.name.toString ++ "," ++
      "\"llvm\":" ++ quoted symbol ++ "," ++
      "\"signature\":" ++ renderScalarSignature function.signature ++ "," ++
      "\"dependencies\":" ++ jsonArray
        (function.dependencies.toList.map (quoted ∘ Name.toString)) ++ "," ++
      "\"body\":" ++ quoted function.body.renderNormalized ++ "," ++
      "\"noinline\":true}"
  let actionFunctions := suite.actionFunctions.toList.map fun function =>
    let symbol := lowered.symbols.find? (fun candidate => candidate.source == function.name)
      |>.map (fun candidate => candidate.llvm) |>.getD "<missing>"
    "{" ++
      "\"source\":" ++ quoted function.name.toString ++ "," ++
      "\"llvm\":" ++ quoted symbol ++ "," ++
      "\"signature\":" ++ renderActionSignature function.signature ++ "," ++
      "\"scalar_dependencies\":" ++ jsonArray
        (function.scalarDependencies.toList.map (quoted ∘ Name.toString)) ++ "," ++
      "\"action_dependencies\":" ++ jsonArray
        (function.actionDependencies.toList.map (quoted ∘ Name.toString)) ++ "," ++
      "\"direct_effects\":" ++ renderEffects function.directEffects ++ "," ++
      "\"transitive_effects\":" ++ renderEffects function.effects ++ "," ++
      "\"body\":" ++ quoted function.body.renderNormalized ++ "," ++
      "\"noinline\":true}"
  let mut deviceUses : List String := []
  for operation in suite.usedDeviceOps do
    let some spec := Lemma.Core0.Device.findSpec? operation
      | throw s!"device suite contains uncatalogued operation `{operation.stableId}`"
    deviceUses := deviceUses ++ [renderDeviceUse operation spec]
  let memoryUses := suite.usedMemoryOps.qsort (fun left right => left.stableId < right.stableId)
  let primitives := suite.usedPrimitives.toList.map renderPrimitive
  let iterations := suite.usedActionIterations.toList.map renderActionIteration
  pure <| String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"artifact_category\": \"test-device-suite\",",
    "  \"contract_version\": \"core0-v0.5\",",
    "  \"test_abi\": \"lemma-device-session-v1\",",
    "  \"suite_id\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.suiteId) ++ ",",
    "  \"source_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.sourceSeed) ++ ",",
    "  \"runtime_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.runtimeSeed) ++ ",",
    "  \"checked_result\": {\"logical_status\":\"u8\",\"logical_value\":\"u64\"," ++
      "\"llvm\":\"{ i64, i64 }\",\"rv64\":\"a0=status-zero-extended,a1=value\"," ++
      "\"status_high_bits_zero\":true},",
    "  \"memory_contract\": " ++ memoryContract ++ ",",
    "  \"device_contract\": " ++ deviceContract ++ ",",
    "  \"roots\": " ++ jsonArray roots ++ ",",
    "  \"scalar_functions\": " ++ jsonArray scalarFunctions ++ ",",
    "  \"action_functions\": " ++ jsonArray actionFunctions ++ ",",
    "  \"used_primitives\": " ++ jsonArray primitives ++ ",",
    "  \"used_memory_ops\": " ++ jsonArray (memoryUses.toList.map renderMemoryUse) ++ ",",
    "  \"used_device_ops\": " ++ jsonArray deviceUses ++ ",",
    "  \"action_iterations\": " ++ jsonArray iterations ++ ",",
    "  \"machine_primitives\": [",
    "    {\"identity\":\"startup\",\"effect\":\"machine-state\",\"implementation\":\"Lemma.Machine.Primitives.startup\"},",
    "    {\"identity\":\"io-fence\",\"effect\":\"ordered-mmio\",\"implementation\":\"Lemma.Machine.Primitives.ioFence\"},",
    "    {\"identity\":\"device-test-harness\",\"effect\":\"action-abi/status-coded-vm-termination\",\"implementation\":\"Lemma.Machine.DeviceHarness.main\"},",
    "    {\"identity\":\"sifive-test\",\"effect\":\"vm-termination-mmio\",\"implementation\":\"Lemma.Machine.DeviceHarness.successBlock/failureBlock\"}",
    "  ]",
    "}", ""
  ]

def renderNormalized (suite : Lemma.Core0.CheckedActionSuite) : String :=
  let roots := suite.roots.toList.map fun root =>
    s!"root={root.id};source={root.source};signature={renderActionSignature root.signature}\n"
  let scalars := suite.scalarFunctions.toList.map fun function =>
    s!"scalar={function.name};body={function.body.renderNormalized}\n"
  let actions := suite.actionFunctions.toList.map fun function =>
    s!"action={function.name};direct={function.directEffects.render};" ++
      s!"transitive={function.effects.render};body={function.body.renderNormalized}\n"
  let memory := suite.usedMemoryOps.toList.map fun use =>
    s!"memory-op={use.stableId}\n"
  let devices := suite.usedDeviceOps.toList.map fun op =>
    s!"device-op={op.stableId}\n"
  let iterations := suite.usedActionIterations.toList.map fun site =>
    s!"action-iteration={site.stableId};budget={site.budget};callback={site.callback}\n"
  "contract=core0-v0.5\n" ++ String.join roots ++ String.join scalars ++
    String.join actions ++ String.join memory ++ String.join devices ++ String.join iterations

private def renderABI (config : Configuration) : String :=
  String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"contract_version\": \"core0-v0.5\",",
    "  \"name\": \"lemma-device-session-v1\",",
    "  \"byte_order\": \"little-endian\",",
    "  \"ready\": \"LEMMA_DEVICE/1\\nREADY\\n\",",
    "  \"requests_per_session\": 2,",
    "  \"poll_budget\": 1000000,",
    "  \"request\": {\"bytes\":\"16-byte-header + payload\",\"maximum_payload_bytes\":16,\"magic_bytes\":\"4c4d5136\",\"magic_u32\":\"0x36514d4c\",\"fields\":[\"magic:u32@0\",\"version:u8@4\",\"command:u8@5\",\"length:u8@6\",\"flags:u8@7\",\"request_id:u64@8\"]},",
    "  \"response\": {\"bytes\":24,\"magic_bytes\":\"4c4d5336\",\"magic_u32\":\"0x36534d4c\",\"fields\":[\"magic:u32@0\",\"version:u8@4\",\"status:u8@5\",\"length:u8@6=8\",\"flags:u8@7=0\",\"request_id:u64@8\",\"value:u64@16\"]},",
    "  \"commands\": [{\"code\":1,\"name\":\"add64\",\"payload_bytes\":16},{\"code\":2,\"name\":\"xor64\",\"payload_bytes\":16},{\"code\":3,\"name\":\"branch\",\"payload_bytes\":1,\"false_ram_marker\":\"scratch+64=0x5a\",\"true_uart_marker\":165},{\"code\":4,\"name\":\"tx-stress\",\"payload_bytes\":4,\"maximum_count\":65535,\"byte\":85}],",
    "  \"statuses\": [{\"code\":0,\"name\":\"ok\"},{\"code\":10,\"name\":\"poll-again-internal\",\"public\":false},{\"code\":11,\"name\":\"tx-timeout\"},{\"code\":12,\"name\":\"rx-timeout\"},{\"code\":13,\"name\":\"line-error\"},{\"code\":14,\"name\":\"malformed-frame\"},{\"code\":15,\"name\":\"truncated-frame\"},{\"code\":16,\"name\":\"invalid-length\"},{\"code\":17,\"name\":\"unsupported-command\"}],",
    "  \"terminal_rules\": {\"no_first_byte\":12,\"partial_header_or_payload\":15,\"unsupported_command_responds_and_continues\":true,\"internal_status_must_not_escape\":10},",
    "  \"suite_id\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.suiteId) ++ ",",
    "  \"source_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.sourceSeed) ++ ",",
    "  \"runtime_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.runtimeSeed),
    "}", ""
  ]

private def parseEnvNat (name : String) : IO Nat := do
  let some text ← IO.getEnv name
    | throw <| IO.userError s!"{name} must be set for the device-suite exporter"
  let some value := text.toNat?
    | throw <| IO.userError s!"{name} must be a decimal natural number"
  unless value < 2 ^ 64 do throw <| IO.userError s!"{name} exceeds UInt64"
  pure value

private def exportSuite (env : Environment) (names : Array Name)
    (outputDir : System.FilePath) : IO Unit := do
  unless names.size == 1 do
    throw <| IO.userError s!"the fixed Gate 6 suite requires one root, got {names.size}"
  let config : Configuration := {
    suiteId := ← parseEnvNat "LEMMA_DEVICE_SUITE_ID"
    sourceSeed := ← parseEnvNat "LEMMA_DEVICE_SOURCE_SEED"
    runtimeSeed := ← parseEnvNat "LEMMA_DEVICE_RUNTIME_SEED"
  }
  match config.validate with
  | .ok () => pure ()
  | .error message => throw <| IO.userError message
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV05 env names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  unless suite.roots.size == 1 && suite.roots[0]!.signature.args.isEmpty do
    throw <| IO.userError "the Gate 6 device root must have the zero-argument Action ABI"
  unless suite.usedDeviceOps.size == 4 &&
      Lemma.Core0.Device.opCatalog.all (fun spec => suite.usedDeviceOps.contains spec.op) do
    throw <| IO.userError "the Gate 6 device closure does not use all four UART operations"
  let preserveCalls := suite.scalarFunctions.map (fun function => function.name) ++
    suite.actionFunctions.map (fun function => function.name)
  let lowered ← match lowerActionSuiteV05 suite { preserveCalls } with
    | .ok lowered => pure lowered
    | .error message => throw <| IO.userError s!"device suite LLVM lowering failed: {message}"
  let some loweredRoot := lowered.roots[0]?
    | throw <| IO.userError "device lowering omitted its single checked root"
  let layout := Lemma.Machine.deviceLayout
  let linkScript ← match layout.linkerScript with
    | .ok script => pure script
    | .error message => throw <| IO.userError message
  let machineLayout ← match layout.machineManifestJson with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let deviceContract ← match layout.deviceContractJson with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let manifest ← match renderManifest suite lowered layout config with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let llvmModule : LLVM.Module := {
    sourceName := "Lemma Gate 6 compiled UART device session"
    declarations := Lemma.Machine.DeviceHarness.declarations
    functions := lowered.functions ++
      Lemma.Machine.DeviceHarness.functions layout loweredRoot
  }
  match LLVM.validateModule llvmModule with
  | .ok () => pure ()
  | .error message => throw <| IO.userError message
  IO.FS.createDirAll outputDir
  IO.FS.writeFile (outputDir / "program.ll") llvmModule.render
  IO.FS.writeFile (outputDir / "startup.S") Lemma.Machine.Primitives.renderStartup
  IO.FS.writeFile (outputDir / "link.ld") linkScript
  IO.FS.writeFile (outputDir / "layout.json") machineLayout
  IO.FS.writeFile (outputDir / "device-contract.json") deviceContract
  IO.FS.writeFile (outputDir / "device-suite-manifest.json") manifest
  IO.FS.writeFile (outputDir / "device-suite-normalized.txt") (renderNormalized suite)
  IO.FS.writeFile (outputDir / "device-test-abi.json") (renderABI config)
  IO.FS.writeFile (outputDir / "symbols.txt") lowered.renderSymbolManifest

syntax (name := core0ExportDeviceSuite)
  "#core0_export_device_suite " "[" ident,* "]" : command

elab_rules : command
  | `(#core0_export_device_suite [$decls:ident,*]) => do
      let mut names : Array Name := #[]
      for declaration in decls.getElems do
        names := names.push (← resolveGlobalConstNoOverload declaration)
      let some output ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
        | throwError "LEMMA_CORE0_OUT must name the generated-artifact directory"
      let env ← getEnv
      liftIO <| exportSuite env names (System.FilePath.mk output)
      logInfo m!"Core0 exported compiled-device v0.5 suite with {names.size} root to {output}"

end Lemma.Compiler.Test.DeviceExport
