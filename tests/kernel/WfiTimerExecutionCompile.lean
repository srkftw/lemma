import Lemma.Compiler.CFGLower
import Lemma.Platform.RiscV.Development.WfiTimerPolicy
import Lemma.Platform.RiscV.Development.WfiTimerFirmware

/-! Genuine admission fixtures, excluded from diagnostic target imports. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
namespace WfiTimerExecutionCompile

def extraWaitOperand : Memory.Action :=
  .platform .waitInterrupt 1 0 0 0 0 0 fun s v => .done s v
def machineCompareFromSupervisor : Memory.Action :=
  .platform .setMachineCompare 1000 0 0 0 0 0 fun s v => .done s v
def deniedUserWait : Memory.Action :=
  .platform .waitInterrupt 0 0 0 0 0 0 fun s v => .done s v
def failed (result : Except α β) : Bool := match result with | .error _ => true | .ok _ => false
private def require (value : Bool) (message : String) : CommandElabM Unit :=
  unless value do throwError message

run_cmd do
  let env ← getEnv
  let kernelRoots := #[`Lemma.Platform.RiscV.Development.WfiTimerPolicy.main,
    `Lemma.Platform.RiscV.Development.WfiTimerPolicy.dispatch]
  let firmwareRoots := #[`Lemma.Platform.RiscV.Development.WfiTimerFirmware.dispatch]
  let kernel ← match checkAndLowerActionSuiteForProfile env .kernel_v0_4 kernelRoots with
    | .ok value => pure value | .error e => throwError e.render
  let firmware ← match checkAndLowerActionSuiteForProfile env .firmware_v0_1 firmwareRoots with
    | .ok value => pure value | .error e => throwError e.render
  require (kernel.contractVersion == "core0-kernel-v0.4" && kernel.usedExecutionOps.size == 5 &&
    firmware.contractVersion == "core0-firmware-v0.1" && firmware.usedExecutionOps.size == 5)
    "WFI source lost its exact existing privilege-operation closure"
  require (kernel.usedDeviceOps.isEmpty && firmware.usedDeviceOps.isEmpty &&
    kernel.usedLoops.isEmpty && firmware.usedLoops.isEmpty) "WFI diagnostic acquired a device/loop grant"
  require (Lemma.Platform.RiscV.Development.WfiTimerPolicy.interval 0 == 8192 &&
    Lemma.Platform.RiscV.Development.WfiTimerPolicy.interval 1 == 1000 &&
    Lemma.Platform.RiscV.Development.WfiTimerPolicy.interval 2 == 1001 &&
    Lemma.Platform.RiscV.Development.WfiTimerPolicy.interval 3 == 4096)
    "diagnostic literal interval corpus changed"
  for profile in #[Profile.firmware_v0_1,.firmware_v0_2,.counter_su_v0_1,.user_v0_1,
      .user_v0_2,.user_v0_3,.user_v0_4,.user_v0_5,.user_v0_6,.user_v0_7,.boot_v0_1] do
    require (failed <| checkAndLowerActionSuiteForProfile env profile kernelRoots)
      "S timer/WFI policy admitted by a different privilege profile"
    require (!Execution.Op.waitInterrupt.admits profile) "WFI operation admission broadened"
  require (failed <| checkAndLowerActionSuiteForProfile env .kernel_v0_4 firmwareRoots)
    "S profile admitted direct M timer primitives"
  require (failed <| checkAndLowerActionSuiteForProfile env .kernel_v0_4 #[`WfiTimerExecutionCompile.extraWaitOperand])
    "unused WFI operand accepted"
  require (failed <| checkAndLowerActionSuiteForProfile env .kernel_v0_4 #[`WfiTimerExecutionCompile.machineCompareFromSupervisor])
    "S direct timer comparator accepted"
  require (failed <| checkAndLowerActionSuiteForProfile env .user_v0_2 #[`WfiTimerExecutionCompile.deniedUserWait])
    "User WFI admitted"
  logInfo "WFI_TIMER_EXECUTION_COMPILE:PASS genuine existing-profile closure/admission; no CPU claim"

end WfiTimerExecutionCompile
