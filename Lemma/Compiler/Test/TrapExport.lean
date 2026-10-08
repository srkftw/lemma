import Lemma.Compiler.Test.DeviceExport
import Lemma.Machine.TrapPrimitives

/-! Closed Gate 7 exporter.  Shared Action metadata is reused structurally;
the new machine/profile/primitive contract is explicit and separately audited. -/

namespace Lemma.Compiler.Test.TrapExport

open Lean Elab Command
open Lemma.Compiler

def suiteId : Nat := 0x76a7494d1d0037c1
def sourceSeed : Nat := 0x4c454d4d41373037
def runtimeSeed : Nat := 0x52554e54494d4537

private def replaceFields (original : Json) (fields : List (String × Json)) : Except String Json := do
  let object ← original.getObj?
  let old := object.toList.filter fun entry => !fields.any (fun field => field.1 == entry.1)
  pure <| Json.mkObj (old ++ fields)

def trapContract : Json := Json.mkObj [
  ("schema_version", 1),
  ("profile", .str "m-mode-sync-trap-v1"),
  ("privileged_spec", .str "RISC-V Privileged Architecture 20240411; Machine ISA 1.13"),
  ("privileged_spec_sha256", .str "538f3b17e1990ffabde30a6b96aaa2a0111afb63c174a6ef02b55a7aeb0e701d"),
  ("frame_bytes", 288), ("call_alignment", 16), ("outgoing_argument_bytes", 16),
  ("integer_registers", 31), ("hart_count", 1), ("nested", .bool false),
  ("cpu_extensions_disabled", .arr #[.str "Smrnmi", .str "Smdbltrp"]),
  ("qemu_feature_normalization", Json.mkObj [
    ("source", .str "target/riscv/tcg/tcg-cpu.c"),
    ("sha256", .str "562e89fd688a921f9d48d718c60af73b51a7effaf5ec0577b67d0b177d99a7b9"),
    ("lines", .str "1630-1646")]),
  ("latch", .str "mscratch=trap-stack-top in foreground; zero during dispatch"),
  ("csr_snapshots", .arr #[.str "mstatus", .str "mepc", .str "mcause", .str "mtval", .str "mie"]),
  ("dispatcher_arguments", .arr #[.str "cause", .str "pc", .str "mstatus", .str "tval", .str "mie",
    .str "ecall-site", .str "ecall-resume", .str "breakpoint-site", .str "breakpoint-resume"]),
  ("authorized_sites", .arr #[
    Json.mkObj [("cause", 11), ("site", .str "__trap_ecall_site"),
      ("resume", .str "__trap_ecall_resume"), ("instruction_bytes", 4)],
    Json.mkObj [("cause", 3), ("site", .str "__trap_breakpoint_site"),
      ("resume", .str "__trap_breakpoint_resume"), ("instruction_bytes", 4)]]),
  ("fatal_status", 18), ("double_fault_status", 19), ("context_mismatch_status", 20),
  ("premises", .arr #[.str "fixed aligned RAM frame/stack accesses do not fault",
    .str "authorized M-mode continuation; MPRV=0; MIE=0 through return",
    .str "no NMI; synchronous faults in latch entry/tail window are not classified exhaustively",
    .str "compiled code uses neither gp nor tp; no relaxation; no floating/vector state"])]

private def machinePrimitives : Json := .arr <| #[
  ("trap-startup", "machine-state", "Lemma.Machine.TrapPrimitives.startup"),
  ("trap-entry-return", "machine-state", "Lemma.Machine.TrapPrimitives.vector"),
  ("trap-register-probes", "sync-trap/context-check", "Lemma.Machine.TrapPrimitives.ecallProbe/breakpointProbe"),
  ("trap-fatal-fixtures", "sync-trap", "Lemma.Machine.TrapPrimitives.unexpectedEcall/illegalInstruction"),
  ("trap-fatal-finishers", "vm-termination-mmio", "Lemma.Machine.TrapPrimitives.fatalDispatch/doubleFault"),
  ("io-fence", "ordered-mmio", "Lemma.Machine.Primitives.ioFence"),
  ("status-test-harness", "action-abi/status-coded-vm-termination", "Lemma.Machine.DeviceHarness.main")
].map fun (identity, effect, implementation) => Json.mkObj [
  ("identity", .str identity), ("effect", .str effect), ("implementation", .str implementation)]

private def renderManifest (suite : Lemma.Core0.CheckedActionSuite)
    (lowered : LoweredActionSuite) (mutation : Lemma.Machine.TrapPrimitives.RestoreMutation) : Except String String := do
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
    ("effects", .arr #[.str "sync-trap", .str "machine-state"]),
    ("arguments", .arr #[]), ("result", .str "u64-context-mask")]
  let manifest ← replaceFields shared [
    ("artifact_category", .str "test-trap-suite"), ("contract_version", .str "core0-v0.6"),
    ("test_abi", .str "lemma-sync-trap-test-v1"),
    ("trap_contract", trapContract), ("used_trap_ops", .arr trapUses),
    ("machine_primitives", machinePrimitives),
    ("restore_mutation", Json.mkObj [("identity", .str mutation.stableId),
      ("production_selectable", .bool false), ("transform_stage", .str "structured-machine-restore"),
      ("match_count", toJson (if mutation == .none then 0 else 1))])]
  pure <| manifest.pretty ++ "\n"

private def abi : Json := Json.mkObj [
  ("schema_version", 1), ("contract_version", .str "core0-v0.6"),
  ("name", .str "lemma-sync-trap-test-v1"), ("byte_order", .str "little-endian"),
  ("ready", .str DeviceABI.readyBanner), ("runtime_fixture_address", .str "0x0000000081000000"),
  ("runtime_fixture_bytes", 24),
  ("runtime_fields", .arr #[.str "seed:u64@0", .str "count:u64@8", .str "scenario:u64@16"]),
  ("maximum_count", 64), ("response_bytes", 24), ("response_magic", .str "LMS6"),
  ("result_ids", .arr #[toJson (0x7101 : Nat), toJson (0x7102 : Nat),
    toJson (0x7103 : Nat), toJson (0x7104 : Nat)]),
  ("fatal_ids", .arr #[toJson (0x7001 : Nat), toJson (0x7002 : Nat),
    toJson (0x7003 : Nat), toJson (0x7004 : Nat), toJson (0x7005 : Nat)]),
  ("context_failure_id", toJson (0x71ff : Nat)),
  ("scenarios", Json.mkObj [("0", .str "control-and-interrupted-fold"),
    ("1", .str "unauthorized-ecall"), ("2", .str "illegal-instruction"),
    ("4", .str "nested-ecall-in-compiled-dispatch")])]

private def exportSuite (env : Environment) (names : Array Name)
    (outputDir : System.FilePath) : IO Unit := do
  unless names == #[`Lemma.Examples.Foundation.Trap.foreground, `Lemma.Examples.Foundation.Trap.dispatch] do
    throw <| IO.userError "Gate 7 exporter requires the fixed foreground and dispatcher source roots"
  let mutationText := (← IO.getEnv "LEMMA_TRAP_RESTORE_MUTATION").getD "0"
  let mutation ← match mutationText with
    | "0" => pure Lemma.Machine.TrapPrimitives.RestoreMutation.none
    | "1" => pure Lemma.Machine.TrapPrimitives.RestoreMutation.restoreS3FromS4
    | _ => throw <| IO.userError "LEMMA_TRAP_RESTORE_MUTATION must be 0 or 1 in this test-only exporter"
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV06 env names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  unless suite.roots.size == 2 && suite.roots[0]!.signature.args.isEmpty &&
      suite.roots[1]!.signature.args == Array.replicate 9 .u64 &&
      suite.usedTrapOps.size == 4 && Lemma.Core0.Trap.Op.all.all suite.usedTrapOps.contains do
    throw <| IO.userError "Gate 7 checked root signatures or closed trap operations differ"
  let preserveCalls := suite.scalarFunctions.map (fun f => f.name) ++ suite.actionFunctions.map (fun f => f.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteV06 suite { preserveCalls }
  let some foreground := lowered.roots[0]?
    | throw <| IO.userError "trap lowering omitted foreground root"
  let some dispatcher := lowered.roots[1]?
    | throw <| IO.userError "trap lowering omitted dispatcher root"
  let startup ← IO.ofExcept <| Lemma.Machine.TrapPrimitives.renderStartup { dispatcher := dispatcher.llvm, mutation }
  let llvmModule : LLVM.Module := {
    sourceName := "Lemma Gate 7 synchronous trap conformance"
    declarations := Lemma.Machine.DeviceHarness.declarations ++ Lemma.Core0.Trap.Op.all.map (fun op =>
      { name := op.llvmSymbol, returnType := .i64, parameters := #[] })
    functions := lowered.functions ++ Lemma.Machine.DeviceHarness.functions Lemma.Machine.deviceLayout foreground
  }
  IO.ofExcept <| LLVM.validateModule llvmModule
  let manifest ← IO.ofExcept <| renderManifest suite lowered mutation
  let linkScript ← IO.ofExcept Lemma.Machine.trapLayout.linkerScript
  let layout ← IO.ofExcept Lemma.Machine.trapLayout.manifestJson
  let deviceContract ← IO.ofExcept Lemma.Machine.deviceLayout.deviceContractJson
  let normalized := (DeviceExport.renderNormalized suite).replace "contract=core0-v0.5\n" "contract=core0-v0.6\n" ++
    String.join (suite.usedTrapOps.toList.map fun op => s!"trap-op={op.stableId}\n")
  IO.FS.createDirAll outputDir
  for (name, contents) in #[
      ("program.ll", llvmModule.render), ("startup.S", startup), ("link.ld", linkScript),
      ("layout.json", layout), ("device-contract.json", deviceContract),
      ("trap-suite-manifest.json", manifest), ("trap-suite-normalized.txt", normalized),
      ("trap-test-abi.json", abi.pretty ++ "\n"), ("symbols.txt", lowered.renderSymbolManifest)] do
    IO.FS.writeFile (outputDir / name) contents

syntax (name := core0ExportTrapSuite) "#core0_export_trap_suite " "[" ident,* "]" : command

elab_rules : command
  | `(#core0_export_trap_suite [$decls:ident,*]) => do
      let mut names := #[]
      for declaration in decls.getElems do
        names := names.push (← resolveGlobalConstNoOverload declaration)
      let some output ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
        | throwError "LEMMA_CORE0_OUT must name the generated-artifact directory"
      liftIO <| exportSuite (← getEnv) names (System.FilePath.mk output)
      logInfo m!"Core0 exported synchronous-trap v0.6 suite to {output}"

end Lemma.Compiler.Test.TrapExport
