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

/-- Kernel-only observation cells for the closed third-client deployment. No
User mapping or grant exposes these cells. Other deployments explicitly clear
selection, and never publish fixture observations. -/
private def isolationState : UInt64 := 0x80400f00
private def isolatedGet (offset : UInt64) : Action := Access.read64 (isolationState + offset)
private def isolatedPut (offset value : UInt64) : Action := Access.write64 (isolationState + offset) value
private def bad (status : UInt8) : Bool := if status = 0 then false else true

private def observeDMA (phase : UInt64) : Action :=
  .bind (Access.read64 Lemma.Drivers.VirtIOBlock.state) fun s handle =>
  if bad s = true then fatal else
  .bind (Access.read64 (Lemma.Drivers.VirtIOBlock.state + 8)) fun s base =>
  if bad s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s resolved =>
  if bad s = true then fatal else
  if resolved = base then
  .bind (Frames.purpose 1 handle) fun s purpose =>
  if bad s = true then fatal else
  .bind (Frames.mappingCount 1 handle) fun s mappings =>
  if bad s = true then fatal else
  .bind (Access.read64 (Lemma.Drivers.VirtIOBlock.state + 40)) fun s pending =>
  if bad s = true then fatal else
  .bind Frames.remaining fun s remaining =>
  if bad s = true then fatal else
  .bind (if phase = 0 then
      .bind (isolatedPut 16 handle) fun s _ => if s = 0 then isolatedPut 24 base else fatal
    else
      .bind (isolatedGet 16) fun s originalHandle => if s = 0 then
      .bind (isolatedGet 24) fun s originalBase => if s = 0 then
      if originalHandle = handle then if originalBase = base then .done 0 0 else fatal else fatal
      else fatal else fatal) fun s _ =>
  if bad s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0x433 phase handle base pending) fun s _ =>
  if bad s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0x434 phase purpose mappings remaining) fun s _ =>
  if bad s = true then fatal else
  .bind MachineServices.time fun s now =>
  if bad s = true then fatal else
  Lemma.Kernel.Console.record 0x436 phase now pending 0
  else fatal

private def configureIsolation (enabled documents : UInt64) : Action :=
  .bind (isolatedPut 0 0) fun s _ => if s = 0 then
  .bind (isolatedPut 8 0) fun s _ => if s = 0 then
  if enabled = 0 then .done 0 0 else if enabled = 1 then
  .bind (Task.prepareManaged 2 0) fun s client => if s = 0 then
  .bind (grant client documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant client Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (Task.activateManaged client) fun s _ => if s = 0 then
  .bind (isolatedPut 0 client) fun s _ => if s = 0 then observeDMA 0 else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def observeReaped : Action :=
  .bind (isolatedGet 8) fun s phase => if s = 0 then
  if phase = 1 then
  .bind (isolatedGet 0) fun s client => if s = 0 then
  .bind (Task.lookup client) fun status _ =>
  if status = 74 then
    .bind (observeDMA 2) fun s _ => if s = 0 then isolatedPut 8 2 else fatal
  else if status = 0 then .done 0 0 else fatal
  else fatal else .done 0 0 else fatal

private def observeFault (cause : UInt64) : Action :=
  if cause = 13 then
  .bind (isolatedGet 0) fun s client => if s = 0 then
  if client = 0 then .done 0 0 else
  .bind (Access.read64 Process.control) fun s current => if s = 0 then
  if current = client then
    .bind (observeDMA 1) fun s _ => if s = 0 then isolatedPut 8 1 else fatal
  else .done 0 0 else fatal else fatal
  else .done 0 0

private def construct (initialization isolation binding : UInt64) : Action :=
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
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents (if binding = 1 then Lemma.Platform.Silicon.Binding.frame_count else 8192)) fun s _ => if s = 0 then
  configureIsolation isolation documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal

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
  .bind DeviceService.deferred fun s _ => if s = 0 then
  .bind Scheduler.step fun s reason => if s = 0 then
  .bind observeReaped fun s _ => if s = 0 then .done 0 reason else fatal else fatal else fatal
  else fatal

private def observedStage (stage : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (Lemma.Kernel.Console.record 0x407 stage status.toUInt64 value 0) fun s _ =>
  if s = 0 then .done status value else .done s 0

private def bootSelected (initialization isolation binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (if binding = 1 then Descriptor.validateSilicon else Descriptor.validate) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind (if binding = 1 then Lemma.Platform.LemmaSim.MachineServices.validateSilicon else Lemma.Platform.LemmaSim.MachineServices.validate) fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.initialize fun s _ => if s = 0 then
  .bind (construct initialization isolation binding) fun s _ => if s = 0 then .loop step else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def boot : Action := bootSelected 0 0 0
/-- Selected only by the explicit initialize deployment on a newly created raw image. -/
def initializeMedium : Action := bootSelected 1 0 0

/-- The only deployment that admits the third isolated ordinary-client fixture. -/
def isolationBoot : Action := bootSelected 0 1 0

/-- Silicon selects the declared discovery, bounded frame supply and CSR WARL expectations. -/
def siliconBoot : Action := bootSelected 0 0 1
def siliconInitializeMedium : Action := bootSelected 1 0 1

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
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    .bind (observeFault cause) fun s _ => if s = 0 then
    Scheduler.dispatch frame cause value else fatal

end Lemma.Platform.LemmaSim.NotebookKernel
