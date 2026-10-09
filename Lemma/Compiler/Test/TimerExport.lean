import Lemma.Compiler.Test.TrapExport
import Lemma.Machine.TimerPrimitives

/-! Closed Gate 8 exporter for the pinned QEMU machine timer.  Shared Action,
RAM, UART, and synchronous-trap metadata are reused structurally, while the
asynchronous timer contract and test-only machine mutations remain explicit. -/

namespace Lemma.Compiler.Test.TimerExport

open Lean Elab Command
open Lemma.Compiler

def suiteId : Nat := 0x7d18a8491d0038c1
def sourceSeed : Nat := 0x4c454d4d41383038
def runtimeSeed : Nat := 0x52554e54494d4538

private def replaceFields (original : Json) (fields : List (String × Json)) : Except String Json := do
  let object ← original.getObj?
  let old := object.toList.filter fun entry => !fields.any (fun field => field.1 == entry.1)
  pure <| Json.mkObj (old ++ fields)

private def strings (values : Array String) : Json := .arr (values.map Json.str)

def trapContract : Json := Json.mkObj [
  ("schema_version", 1),
  ("profile", .str "m-mode-timer-trap-v1"),
  ("privileged_spec", .str "RISC-V Privileged Architecture 20240411; Machine ISA 1.13"),
  ("privileged_spec_sha256", .str "538f3b17e1990ffabde30a6b96aaa2a0111afb63c174a6ef02b55a7aeb0e701d"),
  ("frame_bytes", 288), ("call_alignment", 16), ("outgoing_argument_bytes", 16),
  ("integer_registers", 31), ("hart_count", 1), ("nested", .bool false),
  ("cpu_extensions_disabled", strings #["Smrnmi", "Smdbltrp"]),
  ("qemu_feature_normalization", Json.mkObj [
    ("source", .str "target/riscv/tcg/tcg-cpu.c"),
    ("sha256", .str "562e89fd688a921f9d48d718c60af73b51a7effaf5ec0577b67d0b177d99a7b9"),
    ("lines", .str "1630-1646")]),
  ("latch", .str "mscratch=trap-stack-top in foreground; zero during dispatch"),
  ("csr_snapshots", strings #["mstatus", "mepc", "mcause", "mtval", "mie"]),
  ("dispatcher_arguments", strings #["cause", "pc", "mstatus", "tval", "mie",
    "ecall-site", "ecall-resume", "breakpoint-site", "breakpoint-resume"]),
  ("authorized_sync_sites", .arr #[
    Json.mkObj [("cause", 11), ("site", .str "__trap_ecall_site"),
      ("resume", .str "__trap_ecall_resume"), ("instruction_bytes", 4)],
    Json.mkObj [("cause", 3), ("site", .str "__trap_breakpoint_site"),
      ("resume", .str "__trap_breakpoint_resume"), ("instruction_bytes", 4)]]),
  ("timer_interrupt", Json.mkObj [
    ("cause", .str "0x8000000000000007"),
    ("resume", .str "interrupted-pc-unchanged-after-compiled-policy"),
    ("entry_mstatus", .str "MPIE=1,MIE=0,MPRV=0,MPP=M"),
    ("entry_mie", .str "MTIE-only")]),
  ("fatal_status", 18), ("double_fault_status", 19), ("context_mismatch_status", 20),
  ("missing_interrupt_status", 21), ("invalid_deadline_status", 22),
  ("premises", strings #[
    "fixed aligned RAM frame/stack accesses do not fault",
    "single hart; no NMI; non-nested software latch",
    "timer return preserves the interrupted PC; synchronous return uses only approved sites",
    "compiled code uses neither gp nor tp; no relaxation; no floating/vector state"])]

def timerContract : Json := Json.mkObj [
  ("schema_version", 1), ("profile", .str "qemu-virt-machine-timer-v1"),
  ("qemu_version", .str "11.1.1"),
  ("qemu_revision", .str "c3d48b7d1e89604920e5b81b91140c2ad39a1943"),
  ("qemu_source_archive_sha256", .str "079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482"),
  ("hart_count", 1), ("timebase_frequency_hz", 10000000),
  ("mtime", Json.mkObj [("address", .str "0x000000000200bff8"),
    ("width_bits", 64), ("alignment", 8), ("access", .str "read")]),
  ("mtimecmp", Json.mkObj [("address", .str "0x0000000002004000"),
    ("width_bits", 64), ("alignment", 8), ("access", .str "write"),
    ("boot_value", .str "0xffffffffffffffff")]),
  ("interrupt", Json.mkObj [("cause", 7), ("class", .str "machine-timer"),
    ("mip_bit", 7), ("mie_bit", 7), ("global_mstatus_bit", 3),
    ("controller", .str "CPU-local ACLINT MTIMER presented by the QEMU virt CLINT node; not PLIC")]),
  ("maximum_period", 1000000), ("maximum_goal", 512),
  ("deadline_domain", .str "0..0x7fffffffffffffff with checked nonwrapping addition"),
  ("event_ring", Json.mkObj [("region", .str "events"), ("capacity", 16),
    ("record_bytes", 32), ("fields", strings #["sequence", "time", "pc", "cause"]),
    ("overflow", .str "counted-drop")]),
  ("synchronization", .str "single-hart global-MIE save/disable/restore critical sections with checked volatile RAM and full fences"),
  ("qemu_sources", .arr #[
    Json.mkObj [("path", .str "hw/riscv/virt.c"),
      ("sha256", .str "ab1ef03005e1a94c25f6a8c7e1ddb7c44393802a7db13410c5c97603a1ea4920"),
      ("lines", .str "85-90,600-602,623-633,1384-1392")],
    Json.mkObj [("path", .str "include/hw/intc/riscv_aclint.h"),
      ("sha256", .str "6bd7dac8694d4d8012f1036c00d6b1e9e746d3d7635fc0380d100026e01f7d39"),
      ("lines", .str "74-80")],
    Json.mkObj [("path", .str "hw/intc/riscv_aclint.c"),
      ("sha256", .str "0b2ba0e01c110141df685e16b1ce98383646f95ec426c92b23ab3313a6cb1b89"),
      ("lines", .str "51-60,63-119,125-130,138-167,192-202,266-277,323-336,374-419")],
    Json.mkObj [("path", .str "target/riscv/tcg/cpu_helper.c"),
      ("sha256", .str "172bd47c98c1ea9da48e95e3add0f3b3ac923a4e8a743ab3b785b098f90e4416"),
      ("lines", .str "351-372,553-590,2310-2347")],
    Json.mkObj [("path", .str "target/riscv/tcg/csr.c"),
      ("sha256", .str "631294ef82387021c1a40d2125b636b4097a9350a2bc50d299ff38d5aa856360"),
      ("lines", .str "1814-1819,2292-2308,3776-3813")]])]

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
  ("status-test-harness", "action-abi/status-coded-vm-termination", "Lemma.Machine.DeviceHarness.main")
].map fun (identity, effect, implementation) => Json.mkObj [
  ("identity", .str identity), ("effect", .str effect), ("implementation", .str implementation)]

private def mutationManifest (mutation : Lemma.Machine.TimerPrimitives.Mutation) : Json :=
  let (stage, delta) := match mutation with
    | .none => ("none", Json.null)
    | .restoreS3FromS4 => ("structured-machine-restore", Json.mkObj [
        ("function", .str "core0_trap_vector"), ("before", .str "ld s3, 144(sp)"),
        ("after", .str "ld s3, 152(sp)")])
    | .disableArming => ("structured-machine-timer-arming", Json.mkObj [
        ("function", .str "core0_timer_set_compare"), ("before", .str "sd a0, 0(t0)"),
        ("after", .str "sd t1, 0(t0)")])
  Json.mkObj [("identity", .str mutation.stableId), ("production_selectable", .bool false),
    ("transform_stage", .str stage), ("match_count", if mutation == .none then 0 else 1),
    ("expected_delta", delta)]

private def renderManifest (suite : Lemma.Core0.CheckedActionSuite)
    (lowered : LoweredActionSuite) (mutation : Lemma.Machine.TimerPrimitives.Mutation) : Except String String := do
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
    ("artifact_category", .str "test-timer-suite"), ("contract_version", .str "core0-v0.7"),
    ("test_abi", .str "lemma-timer-test-v1"), ("trap_contract", trapContract),
    ("timer_contract", timerContract), ("used_trap_ops", .arr trapUses),
    ("used_timer_ops", .arr timerUses), ("machine_primitives", machinePrimitives),
    ("timer_mutation", mutationManifest mutation)]
  pure <| manifest.pretty ++ "\n"

private def abi : Json := Json.mkObj [
  ("schema_version", 1), ("contract_version", .str "core0-v0.7"),
  ("name", .str "lemma-timer-test-v1"), ("byte_order", .str "little-endian"),
  ("ready", .str DeviceABI.readyBanner),
  ("runtime_fixture_address", .str "0x0000000081000000"), ("runtime_fixture_bytes", 32),
  ("runtime_fields", strings #["seed:u64@0", "goal:u64@8", "period:u64@16", "scenario:u64@24"]),
  ("maximum_goal", 512), ("maximum_period", 1000000), ("response_bytes", 24),
  ("response_magic", .str "LMS6"), ("response_version", 1),
  ("fixed_stat_frames", 24),
  ("stat_ids", .arr ((List.range 24).toArray.map fun index => toJson (0x8101 + index))),
  ("stat_fields", strings #["checksum", "completed-outer-quanta", "hardware-irq-count",
    "ring-head", "ring-tail", "ring-overflow", "skipped-periods", "spurious-entries",
    "maximum-catch-up-steps", "context-mask", "pending-witness", "shutdown-count-before",
    "shutdown-count-after", "guard-mask", "last-consumed-sequence", "last-consumed-time",
    "last-isr-time", "deadline", "real-read-time", "real-pending", "last-ring-sequence",
    "last-ring-time", "last-ring-pc", "last-ring-cause"]),
  ("ring_dump", Json.mkObj [("base_id", 0x8200), ("maximum_records", 16),
    ("frames_per_record", 4), ("maximum_frames", 64),
    ("fields", strings #["sequence", "time", "pc", "cause"]),
    ("record_id", .str "0x8200 + slot*4 + field-index")]),
  ("maximum_total_frames", 88),
  ("failure", Json.mkObj [("id", 0x81ff), ("context_status", 20),
    ("context_value", .str "register/canary mask"), ("missing_interrupt_status", 21),
    ("missing_interrupt_value", .str "observed hardware IRQ count")]),
  ("invalid_deadline_status", 22),
  ("scenarios", Json.mkObj [("0", .str "overflow"), ("1", .str "masked-pending"),
    ("2", .str "forced-catch-up"), ("3", .str "shutdown"),
    ("4", .str "interleaved-ring")])]

private def exportSuite (env : Environment) (names : Array Name)
    (outputDir : System.FilePath) : IO Unit := do
  unless names == #[`Lemma.Examples.Foundation.Timer.foreground,
      `Lemma.Examples.Foundation.Timer.dispatch] do
    throw <| IO.userError "Gate 8 exporter requires the fixed timer foreground and dispatcher roots"
  let mutationText := (← IO.getEnv "LEMMA_TIMER_MUTATION").getD "0"
  let mutation ← match mutationText with
    | "0" => pure Lemma.Machine.TimerPrimitives.Mutation.none
    | "1" => pure Lemma.Machine.TimerPrimitives.Mutation.restoreS3FromS4
    | "2" => pure Lemma.Machine.TimerPrimitives.Mutation.disableArming
    | _ => throw <| IO.userError "LEMMA_TIMER_MUTATION must be 0, 1, or 2 in this test-only exporter"
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV07 env names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  unless suite.roots.size == 2 && suite.roots[0]!.signature.args.isEmpty &&
      suite.roots[1]!.signature.args == Array.replicate 9 .u64 &&
      suite.usedTimerOps.size == Lemma.Core0.Timer.Op.all.size &&
      Lemma.Core0.Timer.Op.all.all suite.usedTimerOps.contains do
    throw <| IO.userError "Gate 8 checked root signatures or closed timer operations differ"
  let preserveCalls := suite.scalarFunctions.map (fun f => f.name) ++
    suite.actionFunctions.map (fun f => f.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteV07 suite { preserveCalls }
  let some foreground := lowered.roots[0]?
    | throw <| IO.userError "timer lowering omitted foreground root"
  let some dispatcher := lowered.roots[1]?
    | throw <| IO.userError "timer lowering omitted dispatcher root"
  let startup ← IO.ofExcept <| Lemma.Machine.TimerPrimitives.renderStartup {
    dispatcher := dispatcher.llvm, mutation }
  let trapDeclarations := suite.usedTrapOps.map fun op =>
    ({ name := op.llvmSymbol, returnType := LLVM.Ty.i64, parameters := #[] } : LLVM.Declaration)
  let timerDeclarations := suite.usedTimerOps.map fun op =>
    let parameters := (Lemma.Core0.Timer.findSpec? op).map
      (fun spec => spec.machineArguments.map fun _ => LLVM.Ty.i64) |>.getD #[]
    ({ name := op.llvmSymbol, returnType := LLVM.Ty.i64, parameters } : LLVM.Declaration)
  let llvmModule : LLVM.Module := {
    sourceName := "Lemma Gate 8 machine timer and interrupt conformance"
    declarations := Lemma.Machine.DeviceHarness.declarations ++ trapDeclarations ++ timerDeclarations
    functions := lowered.functions ++
      Lemma.Machine.DeviceHarness.functions Lemma.Machine.deviceLayout foreground
  }
  IO.ofExcept <| LLVM.validateModule llvmModule
  let manifest ← IO.ofExcept <| renderManifest suite lowered mutation
  let linkScript ← IO.ofExcept Lemma.Machine.trapLayout.linkerScript
  let layout ← IO.ofExcept Lemma.Machine.trapLayout.manifestJson
  let deviceContract ← IO.ofExcept Lemma.Machine.deviceLayout.deviceContractJson
  let normalized := (DeviceExport.renderNormalized suite).replace
      "contract=core0-v0.5\n" "contract=core0-v0.7\n" ++
    String.join (suite.usedTrapOps.toList.map fun op => s!"trap-op={op.stableId}\n") ++
    String.join (suite.usedTimerOps.toList.map fun op => s!"timer-op={op.stableId}\n")
  IO.FS.createDirAll outputDir
  for (name, contents) in #[
      ("program.ll", llvmModule.render), ("startup.S", startup), ("link.ld", linkScript),
      ("layout.json", layout), ("device-contract.json", deviceContract),
      ("timer-suite-manifest.json", manifest), ("timer-suite-normalized.txt", normalized),
      ("timer-test-abi.json", abi.pretty ++ "\n"), ("symbols.txt", lowered.renderSymbolManifest)] do
    IO.FS.writeFile (outputDir / name) contents

syntax (name := core0ExportTimerSuite) "#core0_export_timer_suite " "[" ident,* "]" : command

elab_rules : command
  | `(#core0_export_timer_suite [$decls:ident,*]) => do
      let mut names := #[]
      for declaration in decls.getElems do
        names := names.push (← resolveGlobalConstNoOverload declaration)
      let some output ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
        | throwError "LEMMA_CORE0_OUT must name the generated-artifact directory"
      liftIO <| exportSuite (← getEnv) names (System.FilePath.mk output)
      logInfo m!"Core0 exported machine-timer v0.7 suite to {output}"

end Lemma.Compiler.Test.TimerExport
