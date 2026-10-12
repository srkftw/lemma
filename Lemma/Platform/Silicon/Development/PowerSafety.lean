import Lemma.Drivers.PowerSafety
import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaSim.MachineServices
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Kernel.Console

/-! Explicit development guest drives the real Power-v2 MMIO path. It arms the
watchdog then deliberately stops making progress in WFI. No host reset is
requested. On a watchdog/supply restart it reports the actual retained cause. -/
namespace Lemma.Platform.Silicon.Development.PowerSafety
open Lemma.Core0.Memory
private def fatal : Action := .done 255 0
private def waitStep : Action :=
  -- The private timer call clears an older SSIP notification before WFI.
  -- A distant wake deadline cannot satisfy this much shorter watchdog.
  .bind (Lemma.Kernel.MachineServices.rearmRelative 10000000) fun s _ => if s = 0 then
  Lemma.Kernel.MachineServices.wait else fatal

def boot : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind Lemma.Kernel.BootInfo.validate fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.Descriptor.validateSiliconSafety fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun s _ => if s = 0 then
  .bind Lemma.Drivers.PowerSafety.initialize fun s cause => if s = 0 then
  .bind Lemma.Drivers.PowerSafety.resetEpoch fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x445 cause epoch 0 0) fun s _ => if s = 0 then
  if cause = 1 then
    .bind (Lemma.Drivers.PowerSafety.arm 100000) fun s _ => if s = 0 then
    .loop waitStep else fatal
  else .loop waitStep
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

def dispatch (_frame _cause _value : UInt64) : Action := fatal
end Lemma.Platform.Silicon.Development.PowerSafety
