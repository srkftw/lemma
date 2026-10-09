import Lemma.Compiler.Test.TimerExport
import Lemma.Machine.TimerPrimitives

/-! Closed Gate 9 exporter for the interactive Core0 monitor image.  Parsing,
dispatch, validation, formatting, buffer work, synchronous traps, and timer
policy all remain in checked Lean source.  The generated machine substrate is
the unchanged clean Gate 8 timer/trap startup. -/

namespace Lemma.Compiler.Test.MonitorExport

open Lean Elab Command
open Lemma.Compiler

def suiteId : Nat := 0x9d2c479b0810f351
def sourceSeed : Nat := 0x4c454d4d41393039
def runtimeSeed : Nat := 0x4d4f4e49544f5231

private def replaceFields (original : Json) (fields : List (String × Json)) : Except String Json := do
  let object ← original.getObj?
  let old := object.toList.filter fun entry => !fields.any (fun field => field.1 == entry.1)
  pure <| Json.mkObj (old ++ fields)

private def strings (values : Array String) : Json := .arr (values.map Json.str)

private def command (id : Nat) (name : String) (length : Nat) (semantics : String) : Json :=
  Json.mkObj [("id", id), ("name", .str name), ("payload_bytes", length),
    ("semantics", .str semantics)]

private def status (code : Nat) (name : String) (alwaysTerminal wireStatus : Bool) : Json :=
  Json.mkObj [("code", code), ("name", .str name),
    ("always_terminal", .bool alwaysTerminal), ("wire_status", .bool wireStatus)]

private def commandCatalog : Json := .arr #[
  command 1 "HELLO" 0 "capability and version tuple",
  command 2 "STATUS" 0 "handled/error/recovery/checksum counters",
  command 3 "EVAL" 32 "bounded scalar evaluation and interrupt-aware mixing",
  command 4 "FILL" 24 "checked fill of the logical user buffer",
  command 5 "CHECKSUM" 16 "checked sum of actual user-buffer bytes",
  command 6 "TRAP_TEST" 8 "authorized ECALL or EBREAK recovery",
  command 7 "TIMER_START" 8 "validated real machine-timer start and probe",
  command 8 "TIMER_STOP" 0 "idempotent timer shutdown and stability check",
  command 9 "TICKS" 16 "critical-section timer statistics or ring access",
  command 10 "EXIT" 0 "timer shutdown, guard validation, response, and clean finish"]

private def statusCatalog : Json := .arr #[
  status 0 "ok" false true,
  status 1 "unknown-region" false true, status 2 "reserved-region" false true,
  status 3 "device-region" false true, status 4 "read-denied" false true,
  status 5 "write-denied" false true, status 6 "width-denied" false true,
  status 7 "bounds-or-index" false true, status 8 "alignment" false true,
  status 9 "session-budget" true true, status 10 "internal-only" true false,
  status 11 "uart-tx-timeout" true true, status 12 "empty-rx-timeout" true true,
  status 13 "uart-line-error" true true,
  status 14 "malformed-header-or-argument" false true,
  status 15 "truncated-input" true true,
  status 16 "length-count-or-active-state" false true,
  status 17 "unsupported-command-selector-or-mode" false true,
  status 18 "unexpected-trap" true false, status 19 "double-fault" true false,
  status 20 "context-guard-or-state-integrity" false true,
  status 21 "required-hardware-event-absent-or-inactive" false true,
  status 22 "invalid-timer-period-or-deadline" false true]

private def helloContract : Json := Json.mkObj [
  ("tag_u64", .str "0x31304e4f4d4d454c"), ("tag_bytes", .str "LEMMON01"),
  ("core0_version", 7), ("machine_profile", 1), ("command_bits", .str "0x3ff")]

private def memoryContract : Json := Json.mkObj [
  ("protocol_scratch", .str "scratch[0..47]"),
  ("user_buffer", .str "scratch[256..4095]"),
  ("user_buffer_logical_bytes", 3840),
  ("boot_initialization", .str "all 3840 user bytes are zeroed"),
  ("timer_state", .str "events[0..127]"),
  ("monitor_stats", strings #["events:u64@128=handledRequests",
    "events:u64@136=recoverableErrors", "events:u64@144=syncRecoveries",
    "events:u64@152=lastWorkChecksum"]),
  ("private_shutdown_witness", .str "events:u64@160=stoppedWorkChecksum"),
  ("timer_guard_offset", 240)]

def monitorContract : Json := Json.mkObj [
  ("schema_version", 1), ("profile", .str "bounded-uart-monitor-v1"),
  ("request", Json.mkObj [
    ("magic", .str "LMQ9"), ("version", 1), ("header_bytes", 16),
    ("maximum_payload_bytes", 32), ("flags", 0), ("request_id_bits", 64),
    ("byte_order", .str "little-endian"),
    ("fields", strings #["magic:u8[4]@0", "version:u8@4", "command:u8@5",
      "length:u8@6", "flags:u8@7", "request-id:u64@8", "payload:u8[length]@16"]) ]),
  ("response", Json.mkObj [
    ("magic", .str "LMS9"), ("version", 1), ("bytes", 48),
    ("payload_bytes", 32), ("flags", 0), ("request_id_bits", 64),
    ("byte_order", .str "little-endian"),
    ("fields", strings #["magic:u8[4]@0", "version:u8@4", "status:u8@5",
      "length:u8@6", "flags:u8@7", "request-id:u64@8", "values:u64[4]@16"]) ]),
  ("ready", .str "LEMMA_MONITOR/1\nREADY\n"),
  ("maximum_handled_requests", 256),
  ("commands", commandCatalog),
  ("statuses", statusCatalog),
  ("framing", Json.mkObj [
    ("bounded_request_order", .str "receive complete payload, increment handledRequests, then validate and dispatch"),
    ("oversize", .str "length>32 terminates status 16 without reply or counter increment"),
    ("invalid_header", .str "status 14 with zero values; continue"),
    ("wrong_known_length", .str "status 16 with zero values; continue"),
    ("unknown_command", .str "status 17 with zero values; continue"),
    ("truncated", .str "missing first byte status 12; partial header or payload status 15") ]),
  ("memory", memoryContract),
  ("hello", helloContract),
  ("eval", Json.mkObj [
    ("selectors", strings #["0=wrapping-add", "1=xor", "2=fixed-mix", "3=mix-until-real-irq-delta"]),
    ("maximum_fixed_quanta", 4096), ("maximum_irq_delta", 256),
    ("mix_steps_per_quantum", 128), ("maximum_irq_quanta", 1000000) ]),
  ("trap_test", Json.mkObj [
    ("modes", strings #["0=authorized-ecall", "1=authorized-ebreak"]),
    ("required_sync_recovery_delta", 1),
    ("timer_interrupts_are_not_sync_recoveries", .bool true) ]),
  ("timer", Json.mkObj [
    ("minimum_period", 10000), ("maximum_period", 1000000),
    ("timer_start_requires_inactive", .bool true),
    ("timer_stop_is_idempotent", .bool true),
    ("ticks_modes", strings #["0=counters", "1=timing", "2=state",
      "3=retained-record-peek", "4=retained-record-pop"]),
    ("foreground_may_call_interrupt_policy", .bool false) ]),
  ("exit", Json.mkObj [
    ("success_status", 0), ("context_failure_status", 20),
    ("successful_exit_is_the_only_ordinary_finish", .bool true) ]),
  ("source_policy_probes", Json.mkObj [
    ("marker", .str "MONITOR_POLICY_PROBES"), ("total", 50),
    ("frontend_lowering", 1)])]

private def resultMeaning : Lemma.Core0.Timer.ResultMeaning → String
  | .time => "time"
  | .zero => "zero"
  | .pendingBit => "pending-bit"
  | .previousGlobalMIE => "previous-global-mie"
  | .probeMask => "probe-mask"

private def timerEffects : Lemma.Core0.Timer.Op → Array String
  | .readTime => #["mmio-read", "io-order", "machine-state", "timer-state"]
  | .setCompare => #["mmio-write", "io-order", "machine-state", "timer-state"]
  | .readPending => #["io-order", "machine-state", "timer-state", "interrupt-state"]
  | .irqSaveDisable | .irqRestore => #["io-order", "machine-state", "interrupt-state"]
  | .setInterrupt | .probe => #["io-order", "machine-state", "timer-state", "interrupt-state"]

private def renderTimerUse (spec : Lemma.Core0.Timer.OpSpec) : Json :=
  let mmio := match spec.mmio? with
    | none => Json.null
    | some access => Json.mkObj [
        ("address", .str (Lemma.Compiler.Format.hexAddr access.address.toNat)),
        ("width_bits", toJson (access.widthBytes * 8)), ("alignment", access.widthBytes),
        ("access", .str access.access.render), ("volatile", .bool true),
        ("fence_before", .bool access.fenceBefore), ("fence_after", .bool access.fenceAfter)]
  Json.mkObj [
    ("stable_id", .str spec.op.stableId), ("source_identity", .str spec.sourceIdentity),
    ("llvm_symbol", .str spec.llvmSymbol),
    ("source_arguments", strings (spec.sourceArguments.map Lemma.Core0.Ty.render)),
    ("machine_arguments", strings (spec.machineArguments.map Lemma.Core0.Ty.render)),
    ("result", .str spec.result.render), ("result_meaning", .str (resultMeaning spec.resultMeaning)),
    ("state_operation", .str spec.stateOperation.render), ("mmio", mmio),
    ("canonical_bool_argument", .bool spec.canonicalBoolArgument),
    ("requires_global_mie_disabled", .bool spec.requiresGlobalMIEDisabled),
    ("fence_before", .bool spec.fenceBefore), ("fence_after", .bool spec.fenceAfter),
    ("effects", strings (timerEffects spec.op))]

private def machinePrimitives : Json := .arr <| #[
  ("timer-startup", "machine-state/timer-state", "Lemma.Machine.TimerPrimitives.startup"),
  ("trap-entry-return", "machine-state/interrupt-state", "Lemma.Machine.TrapPrimitives.vector"),
  ("trap-register-probes", "sync-trap/context-check", "Lemma.Machine.TrapPrimitives.ecallProbe/breakpointProbe"),
  ("trap-fatal-fixtures", "sync-trap", "Lemma.Machine.TrapPrimitives.unexpectedEcall/illegalInstruction"),
  ("trap-fatal-finishers", "vm-termination-mmio", "Lemma.Machine.TrapPrimitives.fatalDispatch/doubleFault"),
  ("timer-mmio", "ordered-64-bit-mmio", "Lemma.Machine.TimerPrimitives.readTime/setCompare"),
  ("timer-csr", "interrupt-state", "Lemma.Machine.TimerPrimitives.readPending/saveDisable/restore/setInterrupt"),
  ("timer-register-probe", "real-interrupt/context-check", "Lemma.Machine.TimerPrimitives.probe"),
  ("io-fence", "ordered-mmio", "Lemma.Machine.Primitives.ioFence"),
  ("status-monitor-harness", "action-abi/status-coded-vm-termination", "Lemma.Machine.DeviceHarness.main")
].map fun (identity, effect, implementation) => Json.mkObj [
  ("identity", .str identity), ("effect", .str effect), ("implementation", .str implementation)]

private def cleanMachineConfiguration : Json := Json.mkObj [
  ("identity", .str "none"), ("production_selectable", .bool false),
  ("transform_stage", .str "none"), ("match_count", 0), ("expected_delta", Json.null)]

private def renderManifest (suite : Lemma.Core0.CheckedActionSuite)
    (lowered : LoweredActionSuite) : Except String String := do
  let config : DeviceABI.Configuration := { suiteId, sourceSeed, runtimeSeed }
  let shared ← DeviceExport.renderManifest suite lowered Lemma.Machine.deviceLayout config
  let shared ← Json.parse shared
  let trapUses := suite.usedTrapOps.map fun op => Json.mkObj [
    ("stable_id", .str op.stableId), ("llvm_symbol", .str op.llvmSymbol),
    ("source_identity", .str (match op with
      | .ecall => "Lemma.Core0.Memory.Action.trapEcall"
      | .breakpoint => "Lemma.Core0.Memory.Action.trapBreakpoint"
      | .unexpectedEcall => "Lemma.Core0.Memory.Action.trapUnexpectedEcall"
      | .illegalInstruction => "Lemma.Core0.Memory.Action.trapIllegalInstruction")),
    ("effects", strings #["sync-trap", "machine-state"]),
    ("arguments", .arr #[]), ("result", .str "u64-context-mask")]
  let timerUses := suite.usedTimerOps.map fun op =>
    match Lemma.Core0.Timer.findSpec? op with
    | some spec => renderTimerUse spec
    | none => Json.null
  let manifest ← replaceFields shared [
    ("artifact_category", .str "test-monitor-image"),
    ("contract_version", .str "core0-v0.7"),
    ("test_abi", .str "lemma-monitor-v1"),
    ("trap_contract", TimerExport.trapContract),
    ("timer_contract", TimerExport.timerContract),
    ("monitor_contract", monitorContract),
    ("used_trap_ops", .arr trapUses), ("used_timer_ops", .arr timerUses),
    ("machine_primitives", machinePrimitives),
    ("timer_mutation", cleanMachineConfiguration)]
  pure <| manifest.pretty ++ "\n"

def abi : Json := Json.mkObj [
  ("schema_version", 1), ("contract_version", .str "core0-v0.7"),
  ("name", .str "lemma-monitor-v1"), ("byte_order", .str "little-endian"),
  ("ready", .str "LEMMA_MONITOR/1\nREADY\n"),
  ("request_magic", .str "LMQ9"), ("request_version", 1),
  ("request_header_bytes", 16), ("maximum_request_payload_bytes", 32),
  ("request_flags", 0), ("request_id_bits", 64),
  ("response_magic", .str "LMS9"), ("response_version", 1),
  ("response_bytes", 48), ("response_payload_bytes", 32),
  ("response_flags", 0), ("response_id_bits", 64),
  ("response_values", 4), ("maximum_handled_requests", 256),
  ("commands", commandCatalog), ("statuses", statusCatalog),
  ("hello", helloContract), ("memory", memoryContract),
  ("monitor_contract", monitorContract)]

private def exportSuite (env : Environment) (names : Array Name)
    (outputDir : System.FilePath) : IO Unit := do
  unless names == #[`Lemma.Examples.Foundation.Monitor.foreground,
      `Lemma.Examples.Foundation.Timer.dispatch] do
    throw <| IO.userError "Gate 9 exporter requires the fixed monitor foreground and timer dispatcher roots"
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV07 env names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  unless suite.roots.size == 2 && suite.roots[0]!.signature.args.isEmpty &&
      suite.roots[1]!.signature.args == Array.replicate 9 .u64 &&
      suite.usedTrapOps.size == 2 && suite.usedTrapOps.contains .ecall &&
      suite.usedTrapOps.contains .breakpoint &&
      suite.usedTimerOps.size == Lemma.Core0.Timer.Op.all.size &&
      Lemma.Core0.Timer.Op.all.all suite.usedTimerOps.contains do
    throw <| IO.userError "Gate 9 checked roots or closed trap/timer operation sets differ"
  let preserveCalls := suite.scalarFunctions.map (fun f => f.name) ++
    suite.actionFunctions.map (fun f => f.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteV07 suite { preserveCalls }
  let some foreground := lowered.roots[0]?
    | throw <| IO.userError "monitor lowering omitted foreground root"
  let some dispatcher := lowered.roots[1]?
    | throw <| IO.userError "monitor lowering omitted timer dispatcher root"
  let startup ← IO.ofExcept <| Lemma.Machine.TimerPrimitives.renderStartup {
    dispatcher := dispatcher.llvm, mutation := .none }
  let trapDeclarations := suite.usedTrapOps.map fun op =>
    ({ name := op.llvmSymbol, returnType := LLVM.Ty.i64, parameters := #[] } : LLVM.Declaration)
  let timerDeclarations := suite.usedTimerOps.map fun op =>
    let parameters := (Lemma.Core0.Timer.findSpec? op).map
      (fun spec => spec.machineArguments.map fun _ => LLVM.Ty.i64) |>.getD #[]
    ({ name := op.llvmSymbol, returnType := LLVM.Ty.i64, parameters } : LLVM.Declaration)
  let llvmModule : LLVM.Module := {
    sourceName := "Lemma Gate 9 interactive monitor"
    declarations := Lemma.Machine.DeviceHarness.declarations ++ trapDeclarations ++ timerDeclarations
    functions := lowered.functions ++
      Lemma.Machine.DeviceHarness.functions Lemma.Machine.deviceLayout foreground
  }
  IO.ofExcept <| LLVM.validateModule llvmModule
  let manifest ← IO.ofExcept <| renderManifest suite lowered
  let linkScript ← IO.ofExcept Lemma.Machine.trapLayout.linkerScript
  let layout ← IO.ofExcept Lemma.Machine.trapLayout.manifestJson
  let deviceContract ← IO.ofExcept Lemma.Machine.deviceLayout.deviceContractJson
  let normalized := (DeviceExport.renderNormalized suite).replace
      "contract=core0-v0.5\n" "contract=core0-v0.7\n" ++
    "monitor-abi=lemma-monitor-v1\n" ++
    String.join (suite.usedTrapOps.toList.map fun op => s!"trap-op={op.stableId}\n") ++
    String.join (suite.usedTimerOps.toList.map fun op => s!"timer-op={op.stableId}\n")
  IO.FS.createDirAll outputDir
  for (name, contents) in #[
      ("program.ll", llvmModule.render), ("startup.S", startup), ("link.ld", linkScript),
      ("layout.json", layout), ("device-contract.json", deviceContract),
      ("monitor-manifest.json", manifest), ("monitor-normalized.txt", normalized),
      ("monitor-abi.json", abi.pretty ++ "\n"), ("symbols.txt", lowered.renderSymbolManifest)] do
    IO.FS.writeFile (outputDir / name) contents

syntax (name := core0ExportMonitorImage) "#core0_export_monitor_image " "[" ident,* "]" : command

elab_rules : command
  | `(#core0_export_monitor_image [$decls:ident,*]) => do
      let mut names := #[]
      for declaration in decls.getElems do
        names := names.push (← resolveGlobalConstNoOverload declaration)
      let some output ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
        | throwError "LEMMA_CORE0_OUT must name the generated-artifact directory"
      liftIO <| exportSuite (← getEnv) names (System.FilePath.mk output)
      logInfo m!"Core0 exported interactive monitor v0.7 image to {output}"

end Lemma.Compiler.Test.MonitorExport
