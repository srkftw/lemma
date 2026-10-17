import Lean
import Lemma.Compiler.BootExecutedExport
import Lemma.Boot.DevelopmentRecovery
import Lemma.Boot.TrialWatchdog

/-! Genuine ROM export for the explicit public-development-key policy.
The existing structured reset boundary is reused; image selection, MAC,
installation and recovery are all ordinary elaborated Lean declarations. -/
namespace Lemma.Compiler.DevelopmentBootExport
open Lean Lemma.Core0
private def watchdogBindings : Array String := #[
  "Lemma.Platform.Silicon.BindingSafety.power_watchdog_timeout_offset",
  "Lemma.Platform.Silicon.BindingSafety.power_watchdog_command_offset",
  "Lemma.Platform.Silicon.BindingSafety.power_magic_value",
  "Lemma.Platform.Silicon.BindingPower.power_base",
  "Lemma.Platform.Silicon.BindingPower.power_reset_cause_offset"]
private def effects (value : EffectSet) : Json :=
  if value == .empty then .arr #[] else
  let interior := String.ofList (value.render.toList.drop 1 |>.reverse |>.drop 1 |>.reverse)
  .arr ((interior.splitOn ",").toArray.map Json.str)
private def exportPolicy (env : Environment) (directory : System.FilePath) (watchdog : Bool) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "development authentication exporter refuses retained output"
  let profile := if watchdog then Profile.boot_v0_2 else Profile.boot_v0_1
  let root := if watchdog then ``Lemma.Boot.TrialWatchdog.entry else ``Lemma.Boot.DevelopmentRecovery.entry
  let suite ← match checkAndLowerActionSuiteForProfile env profile #[root] with
    | .ok value => pure value | .error error => throw <| IO.userError error.render
  for name in suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name) do
    let name := ((Lean.privateToUserName? name).getD name).toString
    unless name.startsWith "Lemma.Boot.DevelopmentAuthentication." || name.startsWith "Lemma.Boot.DevelopmentRecovery." ||
      name.startsWith "Lemma.Boot.ProductExecuted." || name.startsWith "Lemma.Boot.RecoveryExecuted." ||
      name.startsWith "Lemma.Crypto.SHA256." || name.startsWith "Lemma.Crypto.HMAC256." ||
      name.startsWith "Lemma.Kernel.Memory.Access." || name.startsWith "Lemma.Platform.LemmaSim.IO." ||
      name.startsWith "Lemma.Core0.Memory.Status." ||
      (watchdog && (name.startsWith "Lemma.Boot.TrialWatchdog." ||
        name.startsWith "Lemma.Drivers.PowerSafety." || name.startsWith "Lemma.Drivers.Power." ||
        watchdogBindings.contains name)) do
      throw <| IO.userError s!"unaccounted development ROM dependency {name}"
  let lowered ← IO.ofExcept <| lowerActionSuiteExecution profile suite {symbolPrefix := if watchdog then "lemma_trial_watchdog_auth_boot_" else "lemma_development_auth_boot_"}
  let some entry := lowered.symbols.find? (fun row => row.source == root)
    | throw <| IO.userError "missing actual authenticated entry"
  let module : LLVM.Module := {
    sourceName := if watchdog then "Lemma Product10 public-development-key trial watchdog boot-v1" else "Lemma Product10 public-development-key authenticated boot-v1"
    functions := lowered.functions.map fun f => {f with attributes := f.attributes.push "\"no-jump-tables\"=\"true\""}
    declarations := #[{name := "core0_io_fence",returnType := .void,parameters := #[]}] }
  IO.ofExcept <| LLVM.validateModule module
  let mut functions : Array Json := #[]
  for f in suite.scalarFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing actual ROM scalar"
    functions := functions.push <| Json.mkObj [("source",.str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",.arr #[])]
  for f in suite.actionFunctions do
    let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
      | throw <| IO.userError "missing actual ROM action"
    functions := functions.push <| Json.mkObj [("source",.str f.name.toString),("symbol",.str symbol.llvm),
      ("args",.arr (f.signature.args.map (Json.str ∘ Ty.render))),("effects",effects f.effects)]
  let fields := [("schema_version",(1 : Json)),("contract_version",.str profile.contractVersion),
    ("configuration",.str (if watchdog then "lemmasim-silicon-public-development-trial-watchdog-boot" else "lemmasim-silicon-public-development-auth-boot")),("role",.str "boot"),
    ("hardware_profile",.str "lemma-silicon-dev/0.10.0"),("image_compatibility",toJson Lemma.Boot.ProductExecuted.compatibility.toNat),
    ("root",.str root.toString),("entry_symbol",.str entry.llvm),("rom_base",4096),("rom_bytes",65536),
    ("stack_floor",toJson (0x81fd0000 : Nat)),("stack_top",toJson Lemma.Boot.ProductExecuted.romStackTop.toNat),
    ("authentication",.str "HMAC-SHA-256 with PUBLIC DEVELOPMENT KEY; production identity/anti-rollback OPEN"),
    ("key_id",toJson Lemma.Boot.DevelopmentAuthentication.keyId.toNat),("key_public",.bool true),
    ("tag_format",.str "lemma-development-boot-tag/1"),("recovery_transport",.str "lemma-local-uart-development-auth-recovery/2"),
    ("backend_dispatch",.str "lemma-boot-direct-branches-v1"),("functions",.arr functions),
    ("used_execution_ops",.arr (suite.usedExecutionOps.map (Json.str ∘ (·.stableId)))),
    ("used_device_ops",.arr (suite.usedDeviceOps.map (Json.str ∘ (·.stableId))))]
  let unit := Json.mkObj (if watchdog then fields ++ [
    ("boot_watchdog_contract",.str "lemma-trial-boot-watchdog/1"),
    ("trial_watchdog_clocks",toJson Lemma.Boot.TrialWatchdog.timeoutClocks.toNat)] else fields)
  IO.FS.createDirAll directory
  for (name,contents) in #[("program.ll",module.render),("unit.json",unit.pretty++"\n"),
    ("symbols.txt",lowered.renderSymbolManifest),("startup.S",BootExecutedExport.startup entry.llvm),
    ("link.ld",BootExecutedExport.linker)] do IO.FS.writeFile (directory/name) contents
def exportFiles (env : Environment) (directory : System.FilePath) : IO Unit :=
  exportPolicy env directory false
def exportWatchdogFiles (env : Environment) (directory : System.FilePath) : IO Unit :=
  exportPolicy env directory true
end Lemma.Compiler.DevelopmentBootExport
open Lean Elab Command
syntax (name := lemmaExportDevelopmentAuthBoot) "#lemma_export_development_auth_boot" : command
elab_rules : command
  | `(#lemma_export_development_auth_boot) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_DEVELOPMENT_AUTH_BOOT_OUT"
      | throwError "LEMMA_DEVELOPMENT_AUTH_BOOT_OUT requires unused output"
    liftIO <| Lemma.Compiler.DevelopmentBootExport.exportFiles (← getEnv) output
    logInfo "DEVELOPMENT_AUTH_BOOT_EXPORT:PASS genuine immutable ROM source"

syntax (name := lemmaExportTrialWatchdogAuthBoot) "#lemma_export_trial_watchdog_auth_boot" : command
elab_rules : command
  | `(#lemma_export_trial_watchdog_auth_boot) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_DEVELOPMENT_AUTH_BOOT_OUT"
      | throwError "LEMMA_DEVELOPMENT_AUTH_BOOT_OUT requires unused output"
    liftIO <| Lemma.Compiler.DevelopmentBootExport.exportWatchdogFiles (← getEnv) output
    logInfo "TRIAL_WATCHDOG_AUTH_BOOT_EXPORT:PASS genuine immutable ROM source"
