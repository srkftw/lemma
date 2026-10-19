import Lemma.Platform.LemmaSim.TrialWatchdogKernel
import Lemma.Platform.Silicon.BindingIntegrated

/-! Integrated15 composes the existing Product10 isolated authorities, actual
boot-health/watchdog policy, Multimodal14 services and Notebook21 user image.
No user has access to boot context, NV registers or direct sensor MMIO. The
optional raw endpoints remain polled through syscall69; IRQ19 stays masked
until a separately admitted interrupt-driven service consumes it. -/
namespace Lemma.Platform.LemmaSim.IntegratedKernel
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Kernel

private def failed (s : UInt8) : Bool := if s = 0 then false else true
private def invalid : UInt8 := 51

/-- Recover the handle from its live slot, then use the existing generation,
owner, purpose and pin checks. This is only a boot-time table capability borrow. -/
private def ownedTable (owner physical : UInt64) : Action :=
  .bind Frames.runtimeCount fun s count => if failed s = true then .done s 0 else
  if count = 8192 then
  if Frames.pool ≤ physical then if physical ≤ Frames.expandedPoolLimit - 4096 then
  if physical % 4096 = 0 then
  let index := (physical - Frames.pool) / 4096
  .bind (Access.read64 (Frames.records + index * 32 + 24)) fun s generation => if failed s = true then .done s 0 else
  if 0 < generation then if generation ≤ Frames.maxGeneration then
  let handle := generation * count + index
  .bind (Frames.resolvePurpose owner handle Frames.tablePurpose) fun s resolved => if failed s = true then .done s 0 else
  .bind (Frames.mappingCount owner handle) fun s pins => if failed s = true then .done s 0 else
  if resolved = physical then if pins = 1 then .done 0 physical else .done invalid 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0

private def nonleaf (owner value : UInt64) : Action :=
  let physical := value >>> 10 <<< 12
  if value = (physical >>> 12 <<< 10 ||| 1) then ownedTable owner physical else .done invalid 0

def installRoot (owner root : UInt64) : Action :=
  .bind (ownedTable owner root) fun s _ => if failed s = true then .done s 0 else
  .bind (Access.read64 root) fun s first => if failed s = true then .done s 0 else
  .bind (nonleaf owner first) fun s middle => if failed s = true then .done s 0 else
  .bind (Access.read64 (middle + 128 * 8)) fun s second => if failed s = true then .done s 0 else
  .bind (nonleaf owner second) fun s low => if failed s = true then .done s 0 else
  if root = middle then .done invalid 0 else if root = low then .done invalid 0 else if middle = low then .done invalid 0 else
  .bind (Access.read64 (low + 20 * 8)) fun s old0 => if failed s = true then .done s 0 else
  .bind (Access.read64 (low + 21 * 8)) fun s old1 => if failed s = true then .done s 0 else
  let leaf0 : UInt64 := (0x10014000 : UInt64) >>> 12 <<< 10 ||| 0xc7
  let leaf1 : UInt64 := (0x10015000 : UInt64) >>> 12 <<< 10 ||| 0xc7
  if old0 = 0 then if old1 = 0 then
  .bind (Access.write64 (low + 20 * 8) leaf0) fun s _ => if failed s = true then .done s 0 else
  Access.write64 (low + 21 * 8) leaf1
  else .done invalid 0 else .done invalid 0

private def taskAliases (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Lemma.Kernel.Objects.registryDescriptor i.toUInt64) fun s descriptor => if failed s = true then .done s 0 else
  .bind (AddressSpace.owner descriptor) fun s owner => if failed s = true then .done s 0 else
  .bind (AddressSpace.root descriptor) fun s root => if failed s = true then .done s 0 else
  .bind (installRoot owner root) fun s _ => .done s acc

private def configureAliases : Action :=
  .bind (Access.read64 (Process.control + 8)) fun s root => if failed s = true then .done s 0 else
  .bind (installRoot Frames.kernelOwner root) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 4 taskAliases 4 0 0 0 0 0 fun s _ => if failed s = true then .done s 0 else
  AddressSpace.flushCurrent

private def startupAuthority : Action :=
  .bind MachineServices.validateSilicon fun s _ => if failed s = true then .done s 0 else
  .bind (Access.read64 0x804e01e0) fun s nv => if failed s = true then .done s 0 else
  .bind (Access.read64 0x804e01e8) fun s config0 => if failed s = true then .done s 0 else
  .bind (Access.read64 0x804e01f0) fun s mm => if failed s = true then .done s 0 else
  .bind (Access.read64 0x804e01f8) fun s config1 => if failed s = true then .done s 0 else
  if nv = 0x0400487f then if mm = 0x040053ff then
  if config0 = 0x1b1b then if config1 = 0x1b1b then .done 0 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0

private def step : Action :=
  .bind NotebookKernel.stepIntegratedAuthorities fun s reason => if failed s = true then .done s 0 else
  .bind TrialWatchdogKernel.confirmHealthy fun s _ => .done s reason

/-- The ROM supplies image/context and the MAC-bound Product10 compatibility
DTB. The new converter endpoint must independently pass real MMIO discovery. -/
def boot : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if failed s = true then .done s 0 else
  .bind BootInfo.validate fun s _ => if failed s = true then .done s 0 else
  .bind Descriptor.validateSiliconProductExecuted fun s _ => if failed s = true then .done s 0 else
  .bind startupAuthority fun s _ => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.Multimodal.discover fun s _ => if failed s = true then .done s 0 else
  .bind Frames.init fun s _ => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.PLIC.initializePower fun s _ => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if failed s = true then .done s 0 else
  .bind NotebookKernel.prepareIntegratedAuthorities fun s _ => if failed s = true then .done s 0 else
  .bind configureAliases fun s _ => if failed s = true then .done s 0 else
  .bind (Access.read64 (PowerControl.stateBase + 8)) fun s key => if failed s = true then .done s 0 else
  .bind (MultimodalService.configure key) fun s _ => if failed s = true then .done s 0 else
  .bind (Access.write64 TrialWatchdogKernel.completed 0) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0x47c 15 8 9 0) fun s _ => if failed s = true then .done s 0 else
  .loop step

/-- Only syscall69 is delegated to the maintained Multimodal14 gate. Paper3,
blocking IPC, power, boot-health and isolation retain Product10 handling. -/
def dispatch (frame cause value : UInt64) : Action :=
  .bind (if cause = 8 then
    .bind (Access.read64 (frame + 136)) fun s number => if failed s = true then .done s 0 else
    if number = 69 then NotebookKernel.dispatchMultimodalBulk frame cause value
    else NotebookKernel.dispatchProductExecutedBulk frame cause value
    else NotebookKernel.dispatchProductExecutedBulk frame cause value) fun s result =>
  if failed s = true then .done s result else
  .bind TrialWatchdogKernel.confirmHealthy fun s _ => .done s result

end Lemma.Platform.LemmaSim.IntegratedKernel
