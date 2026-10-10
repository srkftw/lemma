import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaSim.MachineServices
import Lemma.Platform.LemmaSim.DeviceService
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Kernel.Scheduler

/-! LemmaSim boot authority and device dispatch. User image0 is the record store,
image1 the notebook; both are separately linked and isolated by existing Sv39.
Only the store receives the raw-block endpoint. The kernel does not interpret
record headers, notebook actions, strokes or display pixels. -/
namespace Lemma.Platform.LemmaSim.NotebookKernel
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory
open Lemma.User
private def fatal : Action := .done 50 0

private def grant (descriptor key rights : UInt64) : Action :=
  Capability.grantBoot descriptor key rights

private def construct (initialization : UInt64) : Action :=
  .bind Process.init fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind Objects.init fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 initialization) fun s notebook => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (DeviceService.configure surface input block) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  Lemma.Kernel.Console.record 0x410 store notebook documents 8192
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal

/-- S policy runs with SIE clear. WFI wakes for an enabled external source even
before a U task is entered. Claim one real PLIC source after each wake/return so
all-blocked services can progress without a status-polling idle loop. -/
private def acceptPending : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (DeviceService.notification source) fun s _ => if s = 0 then
  Lemma.Drivers.PLIC.complete source else fatal else fatal

private def step : Action :=
  .bind acceptPending fun s _ => if s = 0 then
  .bind DeviceService.deferred fun s _ => if s = 0 then Scheduler.step else fatal
  else fatal

private def observedStage (stage : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (Lemma.Kernel.Console.record 0x407 stage status.toUInt64 value 0) fun s _ =>
  if s = 0 then .done status value else .done s 0

private def bootSelected (initialization : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind Descriptor.validate fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validate fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.initialize fun s _ => if s = 0 then
  .bind (construct initialization) fun s _ => if s = 0 then .loop step else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def boot : Action := bootSelected 0
/-- Selected only by the explicit initialize deployment on a newly created raw image. -/
def initializeMedium : Action := bootSelected 1

private def deviceCall (descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surface descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then DeviceService.block descriptor a b c d e else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

def dispatch (frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (DeviceService.notification source) fun s _ => if s = 0 then
    .bind (Lemma.Drivers.PLIC.complete source) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 1 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 1 pc else fatal else fatal else fatal else fatal
    else fatal else fatal else fatal
  else if cause = 8 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    if pc % 4 = 0 then
    .bind (AddressSpace.lookup descriptor pc 4) fun s _ => if s = 0 then
    .bind (Access.read64 (context + 136)) fun s number => if s = 0 then
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else false) = true then
      deviceCall descriptor context pc number
    else Scheduler.call descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else Scheduler.dispatch frame cause value

end Lemma.Platform.LemmaSim.NotebookKernel
