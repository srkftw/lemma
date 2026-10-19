import Lemma.Platform.LemmaSim.MultimodalService
import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaSim.MachineServices
import Lemma.Platform.LemmaSim.DeviceService
import Lemma.Platform.LemmaSim.PowerControl
import Lemma.Platform.LemmaSim.BootHealth
import Lemma.Platform.LemmaSim.BootHealthExecuted
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Kernel.Scheduler

/-! LemmaSim boot authority and device dispatch. Images 0 and 1 are the record
store and notebook. The canonical arithmetic deployment also links image 2 as
an isolated checker; historical deployments retain their two-image contract.
Only the store receives the raw-block endpoint. The kernel does not interpret
record headers, notebook actions, strokes or display pixels. -/
namespace Lemma.Platform.LemmaSim.NotebookKernel

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true
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

private def construct (initialization isolation binding arithmeticMode : UInt64) : Action :=
  .bind Process.init fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (if binding = 3 then Objects.initArithmetic else Objects.init) fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 (if binding = 3 then initialization + 2 else initialization)) fun s notebook => if s = 0 then
  .bind (if binding = 3 then Task.prepareManaged 2 arithmeticMode else .done 0 0) fun s arithmetic => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (if binding = 3 then Objects.createEndpoint notebook else .done 0 0) fun s power => if s = 0 then
  .bind (if binding = 3 then Objects.createEndpoint arithmetic else .done 0 0) fun s checking => if s = 0 then
  .bind (DeviceService.configure surface input block) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (if binding = 3 then grant notebook power CapabilityABI.endpointCall else .done 0 0) fun s _ => if s = 0 then
  .bind (if binding = 3 then
    .bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal
    else .done 0 0) fun s _ => if s = 0 then
  .bind (PowerControl.configure (if binding = 3 then 1 else 0) power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (if binding = 3 then Task.activateManaged arithmetic else .done 0 0) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents (if binding = 1 then Lemma.Platform.Silicon.Binding.frame_count else 8192)) fun s _ => if s = 0 then
  configureIsolation isolation documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

/-- S policy runs with SIE clear. WFI wakes for an enabled external source even
before a U task is entered. Claim one real PLIC source after each wake/return so
all-blocked services can progress without a status-polling idle loop. -/
private def acceptPending : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (if source = 14 then PowerControl.notification else DeviceService.notification source) fun s _ => if s = 0 then
  Lemma.Drivers.PLIC.completePower source else fatal else fatal

private def step : Action :=
  .bind acceptPending fun s _ => if s = 0 then
  .bind DeviceService.deferred fun s _ => if s = 0 then
  .bind Scheduler.step fun s reason => if s = 0 then
  .bind observeReaped fun s _ => if s = 0 then .done 0 reason else fatal else fatal else fatal
  else fatal

private def powerStep : Action :=
  .bind acceptPending fun s _ => if s = 0 then
  .bind DeviceService.deferred fun s _ => if s = 0 then
  .bind PowerControl.step fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind Scheduler.step fun s reason => if s = 0 then
  .bind observeReaped fun s _ => if s = 0 then .done 0 reason else fatal else fatal else fatal else fatal else fatal

private def observedStage (stage : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (Lemma.Kernel.Console.record 0x407 stage status.toUInt64 value 0) fun s _ =>
  if s = 0 then .done status value else .done s 0

private def bootSelected (initialization isolation binding arithmeticMode : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (if binding = 3 then Descriptor.validateSiliconPower else if binding = 1 then Descriptor.validateSilicon else if binding = 2 then Descriptor.validateSiliconFull else Descriptor.validate) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind (if binding = 0 then Lemma.Platform.LemmaSim.MachineServices.validate else Lemma.Platform.LemmaSim.MachineServices.validateSilicon) fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (if binding = 3 then Lemma.Drivers.PLIC.initializePower else Lemma.Drivers.PLIC.initialize) fun s _ => if s = 0 then
  .bind (construct initialization isolation binding arithmeticMode) fun s _ => if s = 0 then if binding = 3 then .loop powerStep else .loop step else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def boot : Action := bootSelected 0 0 0 0
/-- Selected only by the explicit initialize deployment on a newly created raw image. -/
def initializeMedium : Action := bootSelected 1 0 0 0

/-- The only deployment that admits the third isolated ordinary-client fixture. -/
def isolationBoot : Action := bootSelected 0 1 0 0

/-- Silicon selects the declared discovery, bounded frame supply and CSR WARL expectations. -/
def siliconBoot : Action := bootSelected 0 0 1 0
def siliconInitializeMedium : Action := bootSelected 1 0 1 0
def siliconFullBoot : Action := bootSelected 0 0 2 0
def siliconFullInitializeMedium : Action := bootSelected 1 0 2 0
def siliconPowerBoot : Action := bootSelected 0 0 3 0
def siliconPowerInitializeMedium : Action := bootSelected 1 0 3 0
def arithmeticOOMBoot : Action := bootSelected 0 0 3 1
def arithmeticFaultBoot : Action := bootSelected 0 0 3 2
def arithmeticStallBoot : Action := bootSelected 0 0 3 3

/-- Bounded development entry exercising the same compiled power policy without
constructing notebook User images. Actual notebook authority remains separate. -/
def siliconPowerProbe : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun s _ => if s = 0 then
  .bind Descriptor.validateSiliconPower fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun s _ => if s = 0 then
  .bind (PowerControl.configure 1 0) fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.initializePower fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x443 1 0 0 0) fun s _ => if s = 0 then
  .loop PowerControl.step else fatal else fatal else fatal else fatal else fatal else fatal else fatal

/-- Invoked only after dispatch has captured and validated the actual User trap.
Its named-device authority and scheduling result are also exercised independently. -/
def deviceCall (descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surface descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then DeviceService.block descriptor a b c d e else
    if number = 68 then PowerControl.call descriptor a b c d e else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

def dispatch (frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCall descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    .bind (observeFault cause) fun s _ => if s = 0 then
    Scheduler.dispatch frame cause value else fatal

private def constructModern (initialization binding : UInt64) : Action :=
  .bind (if binding = 7 then AddressSpace.configureProduct 7 else .done 0 0) fun s _ => if s = 0 then
  .bind (if binding = 7 then Process.initProduct else Process.init) fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (Objects.initArithmetic) fun s _ => if s = 0 then
  .bind (if binding = 7 then Task.prepareManagedProduct 0 initialization else Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (if binding = 7 then Task.prepareManagedProduct 1 (initialization + 2) else Task.prepareManaged 1 (initialization + 2)) fun s notebook => if s = 0 then
  .bind (if binding = 7 then Task.prepareManagedProduct 2 0 else Task.prepareManaged 2 0) fun s arithmetic => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind ((if binding = 6 then DeviceService.configureUSB surface input block else DeviceService.configure surface input block)) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (.bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (if binding = 7 then BootHealth.configure store notebook else .done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def acceptPendingModern (binding : UInt64) : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (if source = 14 then PowerControl.notification else
    if binding = 6 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
  if binding = 6 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source
  else fatal else fatal

private def modernStep (binding : UInt64) : Action :=
  .bind (acceptPendingModern binding) fun s _ => if s = 0 then
  .bind (if binding = 6 then DeviceService.deferredUSB else DeviceService.deferred) fun s _ => if s = 0 then
  .bind (if binding = 6 then PowerControl.stepUSB else PowerControl.step) fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind (if binding = 7 then BootHealth.step else .done 0 0) fun s _ => if s = 0 then Scheduler.step else fatal
  else fatal else fatal else fatal

private def modernUSBStep : Action := modernStep 6
private def modernProductStep : Action := modernStep 7

private def bootModern (initialization binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBinding binding) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (if binding = 6 then Lemma.Drivers.PLIC.initializeUSB else Lemma.Drivers.PLIC.initializePower) fun s _ => if s = 0 then
  .bind (if binding = 6 then Lemma.USB.Block.initialize else Lemma.Drivers.VirtIOBlock.initialize) fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructModern initialization binding) fun s _ => if s = 0 then
  if binding = 6 then .loop modernUSBStep else .loop modernProductStep
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconUSBBoot : Action := bootModern 0 6
def siliconUSBInitializeMedium : Action := bootModern 1 6
def siliconProductBoot : Action := bootModern 0 7

private def deviceCallModern (binding descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surface descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then (if binding = 6 then DeviceService.blockUSB descriptor a b c d e else DeviceService.block descriptor a b c d e) else
    if number = 68 then (if binding = 6 then PowerControl.callUSB descriptor a b c d e else PowerControl.call descriptor a b c d e) else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

private def dispatchModern (binding frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else if binding = 6 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (if binding = 6 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallModern binding descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    Scheduler.dispatch frame cause value

def dispatchUSB (frame cause value : UInt64) : Action := dispatchModern 6 frame cause value
def dispatchProduct (frame cause value : UInt64) : Action := dispatchModern 7 frame cause value

/-- Explicit Surface-v2 dispatcher; legacy dispatch retains its device entry. -/
def deviceCallBulk (descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2 descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then DeviceService.block descriptor a b c d e else
    if number = 68 then PowerControl.call descriptor a b c d e else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

/-- Captured context is exactly base+2048. Capture validates frame/stack/AS
before copying only36 disjoint saved-context words; PC lookup and device
arguments read metadata without mutation. The borrow ends before syscallReply
or scheduling and never becomes cross-entry authority. -/
private def deviceCallBulkAt (descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2At descriptor (context - AddressSpace.userContextOffset) a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then DeviceService.block descriptor a b c d e else
    if number = 68 then PowerControl.call descriptor a b c d e else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

def dispatchBulk (frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 1 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 1 pc else fatal else fatal else fatal else fatal
    else fatal else fatal else fatal
  else if cause = 8 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    if pc % 4 = 0 then
    .bind (AddressSpace.lookupAt (context - AddressSpace.userContextOffset) pc 4) fun s _ => if s = 0 then
    .bind (Access.read64 (context + 136)) fun s number => if s = 0 then
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallBulkAt descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    .bind (observeFault cause) fun s _ => if s = 0 then
    Scheduler.dispatch frame cause value else fatal


private def deviceCallModernBulk (binding descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2 descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then (if binding = 6 then DeviceService.blockUSB descriptor a b c d e else DeviceService.block descriptor a b c d e) else
    if number = 68 then (if binding = 6 then PowerControl.callUSB descriptor a b c d e else PowerControl.call descriptor a b c d e) else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

private def dispatchModernBulk (binding frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else if binding = 6 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (if binding = 6 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallModernBulk binding descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    Scheduler.dispatch frame cause value


/-- Product7 Surface-v2 uses the same validated modern privilege/device path. -/
def dispatchProductBulk (frame cause value : UInt64) : Action := dispatchModernBulk 7 frame cause value

/-- USB6 Surface-v2 is an explicit software selection over the same device path. -/
def dispatchUSBBulk (frame cause value : UInt64) : Action := dispatchModernBulk 6 frame cause value

private def constructModernNext (initialization binding : UInt64) : Action :=
  .bind (if binding = 9 then AddressSpace.configureProductNext 9 else .done 0 0) fun s _ => if s = 0 then
  .bind (if binding = 9 then Process.initProduct else Process.init) fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (Objects.initArithmetic) fun s _ => if s = 0 then
  .bind (if binding = 9 then Task.prepareManagedProduct 0 initialization else Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (if binding = 9 then Task.prepareManagedProduct 1 (initialization + 2) else Task.prepareManaged 1 (initialization + 2)) fun s notebook => if s = 0 then
  .bind (if binding = 9 then Task.prepareManagedProduct 2 0 else Task.prepareManaged 2 0) fun s arithmetic => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind ((if binding = 8 then DeviceService.configureUSB surface input block else DeviceService.configure surface input block)) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (.bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (if binding = 9 then BootHealth.configure store notebook else .done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def acceptPendingModernNext (binding : UInt64) : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (if source = 14 then PowerControl.notification else
    if binding = 8 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
  if binding = 8 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source
  else fatal else fatal

private def modernNextStep (binding : UInt64) : Action :=
  .bind (acceptPendingModernNext binding) fun s _ => if s = 0 then
  .bind (if binding = 8 then DeviceService.deferredUSB else DeviceService.deferred) fun s _ => if s = 0 then
  .bind (if binding = 8 then PowerControl.stepUSB else PowerControl.step) fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind (if binding = 9 then BootHealth.step else .done 0 0) fun s _ => if s = 0 then Scheduler.step else fatal
  else fatal else fatal else fatal

private def modernUSBNextStep : Action := modernNextStep 8
private def modernProductNextStep : Action := modernNextStep 9

private def bootModernNext (initialization binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingNext binding) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (if binding = 8 then Lemma.Drivers.PLIC.initializeUSB else Lemma.Drivers.PLIC.initializePower) fun s _ => if s = 0 then
  .bind (if binding = 8 then Lemma.USB.Block.initialize else Lemma.Drivers.VirtIOBlock.initialize) fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeNext fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructModernNext initialization binding) fun s _ => if s = 0 then
  if binding = 8 then .loop modernUSBNextStep else .loop modernProductNextStep
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconUSBNextBoot : Action := bootModernNext 0 8
def siliconUSBNextInitializeMedium : Action := bootModernNext 1 8
def siliconProductNextBoot : Action := bootModernNext 0 9


private def deviceCallModernNextBulk (binding descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2Next descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then (if binding = 8 then DeviceService.blockUSB descriptor a b c d e else DeviceService.block descriptor a b c d e) else
    if number = 68 then (if binding = 8 then PowerControl.callUSB descriptor a b c d e else PowerControl.call descriptor a b c d e) else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

private def dispatchModernNextBulk (binding frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else if binding = 8 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (if binding = 8 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallModernNextBulk binding descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    Scheduler.dispatch frame cause value



/-- Paper-v2 successors retain Kernel6/7 privilege/device semantics while
selecting the disjoint staging interface after actual discovery validation. -/
def dispatchUSBNextBulk (frame cause value : UInt64) : Action := dispatchModernNextBulk 8 frame cause value
def dispatchProductNextBulk (frame cause value : UInt64) : Action := dispatchModernNextBulk 9 frame cause value

private def constructModernExecuted (initialization binding : UInt64) : Action :=
  .bind (if binding = 10 then AddressSpace.configureProductExecuted 10 else .done 0 0) fun s _ => if s = 0 then
  .bind (if binding = 10 then Process.initProduct else Process.init) fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (Objects.initArithmetic) fun s _ => if s = 0 then
  .bind (if binding = 10 then Task.prepareManagedProduct 0 initialization else Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (if binding = 10 then Task.prepareManagedProduct 1 (initialization + 2) else Task.prepareManaged 1 (initialization + 2)) fun s notebook => if s = 0 then
  .bind (if binding = 10 then Task.prepareManagedProduct 2 0 else Task.prepareManaged 2 0) fun s arithmetic => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind ((if binding = 8 then DeviceService.configureUSB surface input block else DeviceService.configure surface input block)) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (.bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (if binding = 10 then BootHealthExecuted.configure store notebook else .done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def acceptPendingModernExecuted (binding : UInt64) : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (if source = 14 then PowerControl.notification else
    if binding = 8 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
  if binding = 8 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source
  else fatal else fatal

private def modernExecutedStep (binding : UInt64) : Action :=
  .bind (acceptPendingModernExecuted binding) fun s _ => if s = 0 then
  .bind (if binding = 8 then DeviceService.deferredUSB else DeviceService.deferred) fun s _ => if s = 0 then
  .bind (if binding = 8 then PowerControl.stepUSB else PowerControl.step) fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind (if binding = 10 then BootHealthExecuted.step else .done 0 0) fun s _ => if s = 0 then Scheduler.step else fatal
  else fatal else fatal else fatal

private def modernUSBExecutedStep : Action := modernExecutedStep 8
private def modernProductExecutedStep : Action := modernExecutedStep 10

private def bootModernExecuted (initialization binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingExecuted binding) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (if binding = 8 then Lemma.Drivers.PLIC.initializeUSB else Lemma.Drivers.PLIC.initializePower) fun s _ => if s = 0 then
  .bind (if binding = 8 then Lemma.USB.Block.initialize else Lemma.Drivers.VirtIOBlock.initialize) fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructModernExecuted initialization binding) fun s _ => if s = 0 then
  if binding = 8 then .loop modernUSBExecutedStep else .loop modernProductExecutedStep
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconProductExecutedBoot : Action := bootModernExecuted 0 10


private def deviceCallModernExecutedBulk (binding descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2Next descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then (if binding = 8 then DeviceService.blockUSB descriptor a b c d e else DeviceService.block descriptor a b c d e) else
    if number = 68 then (if binding = 8 then PowerControl.callUSB descriptor a b c d e else PowerControl.call descriptor a b c d e) else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

private def dispatchModernExecutedBulk (binding frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else if binding = 8 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (if binding = 8 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallModernExecutedBulk binding descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    Scheduler.dispatch frame cause value



/-- Paper-v2 successors retain Kernel6/7 privilege/device semantics while
selecting the disjoint staging interface after actual discovery validation. -/
def dispatchProductExecutedBulk (frame cause value : UInt64) : Action := dispatchModernExecutedBulk 10 frame cause value


private def constructWire (initialization binding : UInt64) : Action :=
  .bind (.done 0 0) fun s _ => if s = 0 then
  .bind (Process.init) fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (Objects.initArithmetic) fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 (initialization + 2)) fun s notebook => if s = 0 then
  .bind (Task.prepareManaged 2 0) fun s arithmetic => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind ((if binding = 11 then DeviceService.configureUSB surface input block else DeviceService.configure surface input block)) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (.bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (.done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def acceptPendingWire (binding : UInt64) : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (if source = 14 then PowerControl.notification else
    if binding = 11 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
  if binding = 11 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source
  else fatal else fatal

private def wireStep (binding : UInt64) : Action :=
  .bind (acceptPendingWire binding) fun s _ => if s = 0 then
  .bind (if binding = 11 then DeviceService.deferredUSB else DeviceService.deferred) fun s _ => if s = 0 then
  .bind (if binding = 11 then PowerControl.stepUSB else PowerControl.step) fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind (.done 0 0) fun s _ => if s = 0 then Scheduler.step else fatal
  else fatal else fatal else fatal

private def wireUSBStep : Action := wireStep 11

private def bootWire (initialization binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingWire binding) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (if binding = 11 then Lemma.Drivers.PLIC.initializeUSB else Lemma.Drivers.PLIC.initializePower) fun s _ => if s = 0 then
  .bind (if binding = 11 then Lemma.USB.Block.initialize else Lemma.Drivers.VirtIOBlock.initialize) fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructWire initialization binding) fun s _ => if s = 0 then
  .loop wireUSBStep
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconUSBWireBoot : Action := bootWire 0 11
def siliconUSBWireInitializeMedium : Action := bootWire 1 11


private def deviceCallWireBulk (binding descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2Next descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then (if binding = 11 then DeviceService.blockUSB descriptor a b c d e else DeviceService.block descriptor a b c d e) else
    if number = 68 then (if binding = 11 then PowerControl.callUSB descriptor a b c d e else PowerControl.call descriptor a b c d e) else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

private def dispatchWireBulk (binding frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else if binding = 11 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (if binding = 11 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallWireBulk binding descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    Scheduler.dispatch frame cause value



/-- Paper-v2 successors retain Kernel6/7 privilege/device semantics while
selecting the disjoint staging interface after actual discovery validation. -/
def dispatchUSBWireBulk (frame cause value : UInt64) : Action := dispatchWireBulk 11 frame cause value

-- Clocked13 retains exact K6 authority and separately validates PHY/CDC binding.
private def constructClocked (initialization binding : UInt64) : Action :=
  .bind (.done 0 0) fun s _ => if s = 0 then
  .bind (Process.init) fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (Objects.initArithmetic) fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 (initialization + 2)) fun s notebook => if s = 0 then
  .bind (Task.prepareManaged 2 0) fun s arithmetic => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind ((if binding = 13 then DeviceService.configureUSB surface input block else DeviceService.configure surface input block)) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (.bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (.done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def acceptPendingClocked (binding : UInt64) : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (if source = 14 then PowerControl.notification else
    if binding = 13 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
  if binding = 13 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source
  else fatal else fatal

private def clockedStep (binding : UInt64) : Action :=
  .bind (acceptPendingClocked binding) fun s _ => if s = 0 then
  .bind (if binding = 13 then DeviceService.deferredUSB else DeviceService.deferred) fun s _ => if s = 0 then
  .bind (if binding = 13 then PowerControl.stepUSB else PowerControl.step) fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind (.done 0 0) fun s _ => if s = 0 then Scheduler.step else fatal
  else fatal else fatal else fatal

private def clockedUSBStep : Action := clockedStep 13

private def bootClocked (initialization binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingClocked binding) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (if binding = 13 then Lemma.Drivers.PLIC.initializeUSB else Lemma.Drivers.PLIC.initializePower) fun s _ => if s = 0 then
  .bind (if binding = 13 then Lemma.USB.Block.initialize else Lemma.Drivers.VirtIOBlock.initialize) fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructClocked initialization binding) fun s _ => if s = 0 then
  .loop clockedUSBStep
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconUSBClockedBoot : Action := bootClocked 0 13
def siliconUSBClockedInitializeMedium : Action := bootClocked 1 13


private def deviceCallClockedBulk (binding descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2Next descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then (if binding = 13 then DeviceService.blockUSB descriptor a b c d e else DeviceService.block descriptor a b c d e) else
    if number = 68 then (if binding = 13 then PowerControl.callUSB descriptor a b c d e else PowerControl.call descriptor a b c d e) else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

private def dispatchClockedBulk (binding frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else if binding = 13 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (if binding = 13 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallClockedBulk binding descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    Scheduler.dispatch frame cause value



/-- Paper-v2 successors retain Kernel6/7 privilege/device semantics while
selecting the disjoint staging interface after actual discovery validation. -/
def dispatchUSBClockedBulk (frame cause value : UInt64) : Action := dispatchClockedBulk 13 frame cause value

/-- Versioned course installer authority. Existing boot wrappers are preserved.
Only these roots prepare image3 and grant Console Read/Write plus Store Call. -/
private def constructCourse (initialization isolation binding arithmeticMode : UInt64) : Action :=
  .bind Process.init fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (if binding = 3 then Objects.initArithmetic else Objects.init) fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 (if binding = 3 then initialization + 2 else initialization)) fun s notebook => if s = 0 then
  .bind (if binding = 3 then Task.prepareManaged 2 arithmeticMode else .done 0 0) fun s arithmetic => if s = 0 then
  .bind (Task.prepareManaged 3 initialization) fun s installer => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (if binding = 3 then Objects.createEndpoint notebook else .done 0 0) fun s power => if s = 0 then
  .bind (if binding = 3 then Objects.createEndpoint arithmetic else .done 0 0) fun s checking => if s = 0 then
  .bind (DeviceService.configure surface input block) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (if binding = 3 then grant notebook power CapabilityABI.endpointCall else .done 0 0) fun s _ => if s = 0 then
  .bind (if binding = 3 then
    .bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal
    else .done 0 0) fun s _ => if s = 0 then
  .bind (grant installer Objects.consoleKey (CapabilityABI.consoleRead ||| CapabilityABI.consoleWrite)) fun s _ => if s = 0 then
  .bind (grant installer documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (PowerControl.configure (if binding = 3 then 1 else 0) power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (if binding = 3 then Task.activateManaged arithmetic else .done 0 0) fun s _ => if s = 0 then
  .bind (Task.activateManaged installer) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents (if binding = 1 then Lemma.Platform.Silicon.Binding.frame_count else 8192)) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x4b4 installer documents 0 0) fun s _ => if s = 0 then
  configureIsolation isolation documents
  else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def bootCourseSelected (initialization isolation binding arithmeticMode : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (if binding = 3 then Descriptor.validateSiliconPower else if binding = 1 then Descriptor.validateSilicon else if binding = 2 then Descriptor.validateSiliconFull else Descriptor.validate) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind (if binding = 0 then Lemma.Platform.LemmaSim.MachineServices.validate else Lemma.Platform.LemmaSim.MachineServices.validateSilicon) fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (if binding = 3 then Lemma.Drivers.PLIC.initializePower else Lemma.Drivers.PLIC.initialize) fun s _ => if s = 0 then
  .bind (constructCourse initialization isolation binding arithmeticMode) fun s _ => if s = 0 then if binding = 3 then .loop powerStep else .loop step else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconCourseBoot : Action := bootCourseSelected 0 0 3 0
def siliconCourseInitializeMedium : Action := bootCourseSelected 1 0 3 0

/-- Distinct images select new User startup/library roots; device/boot policy
and the original four-role initialization/grants are unchanged. -/
def siliconCourseAwaitBoot : Action := bootCourseSelected 0 0 3 0
def siliconCourseAwaitInitializeMedium : Action := bootCourseSelected 1 0 3 0

/-- Closed software selectors reuse canonical digital boot/power policy. -/
def siliconClosureBoot : Action := bootSelected 0 0 3 0
def siliconClosureInitializeMedium : Action := bootSelected 1 0 3 0
def siliconClosureOOMBoot : Action := bootSelected 0 0 3 1
def siliconClosureFaultBoot : Action := bootSelected 0 0 3 2

/-! Additive recovery software on the unchanged Clocked13 hardware. Only these
roots select the owned frame/epoch controls and shadow-remount user service. -/
private def constructRecovery (initialization binding : UInt64) : Action :=
  .bind (.done 0 0) fun s _ => if s = 0 then
  .bind (Process.init) fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (Objects.initArithmetic) fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 (initialization + 2)) fun s notebook => if s = 0 then
  .bind (Task.prepareManaged 2 0) fun s arithmetic => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind ((if binding = 13 then DeviceService.configureUSBRecovery surface input block else DeviceService.configure surface input block)) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (.bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (.done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def acceptPendingRecovery (binding : UInt64) : Action :=
  .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
  if source = 0 then .done 0 0 else
  .bind (if source = 14 then PowerControl.notification else
    if binding = 13 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
  if binding = 13 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source
  else fatal else fatal

private def recoveryStep (binding : UInt64) : Action :=
  .bind (acceptPendingRecovery binding) fun s _ => if s = 0 then
  .bind (if binding = 13 then DeviceService.deferredUSBRecovery else DeviceService.deferred) fun s _ => if s = 0 then
  .bind (if binding = 13 then PowerControl.stepUSB else PowerControl.step) fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind (.done 0 0) fun s _ => if s = 0 then Scheduler.step else fatal
  else fatal else fatal else fatal

private def recoveryUSBStep : Action := recoveryStep 13

private def bootRecovery (initialization binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingClocked binding) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (if binding = 13 then Lemma.Drivers.PLIC.initializeUSB else Lemma.Drivers.PLIC.initializePower) fun s _ => if s = 0 then
  .bind (if binding = 13 then Lemma.USB.Block.initializeRecovery else Lemma.Drivers.VirtIOBlock.initialize) fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructRecovery initialization binding) fun s _ => if s = 0 then
  .loop recoveryUSBStep
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconUSBRecoveryBoot : Action := bootRecovery 0 13
def siliconUSBRecoveryInitializeMedium : Action := bootRecovery 1 13


private def deviceCallRecoveryBulk (binding descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2Next descriptor a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then (if binding = 13 then DeviceService.blockUSBRecovery descriptor a b c d e else DeviceService.block descriptor a b c d e) else
    if number = 68 then (if binding = 13 then PowerControl.callUSB descriptor a b c d e else PowerControl.call descriptor a b c d e) else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

private def dispatchRecoveryBulk (binding frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else if binding = 13 then DeviceService.notificationUSB source else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (if binding = 13 then Lemma.Drivers.PLIC.completeUSB source else Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
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
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else false) = true then
      deviceCallRecoveryBulk binding descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    Scheduler.dispatch frame cause value



/-- Paper-v2 successors retain Kernel6/7 privilege/device semantics while
selecting the disjoint staging interface after actual discovery validation. -/
def dispatchUSBRecoveryBulk (frame cause value : UInt64) : Action := dispatchRecoveryBulk 13 frame cause value



/-- Software-only Closure recovery selection. The exact existing K6 constructor,
USB recovery loop and grants remain the same hardware13 boundary. -/
def siliconUSBClosureRecoveryBoot : Action := bootRecovery 0 13
def siliconUSBClosureRecoveryInitializeMedium : Action := bootRecovery 1 13
def dispatchUSBClosureRecoveryBulk (frame cause value : UInt64) : Action :=
  dispatchRecoveryBulk 13 frame cause value

private def powerStepEntryV2 : Action :=
  .bind acceptPending fun s _ => if s = 0 then
  .bind DeviceService.deferred fun s _ => if s = 0 then
  .bind PowerControl.step fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind Scheduler.stepEntryV2 fun s reason => if s = 0 then
  .bind observeReaped fun s _ => if s = 0 then .done 0 reason else fatal else fatal else fatal else fatal else fatal

private def bootSelectedEntryV2 (initialization isolation binding arithmeticMode : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (if binding = 3 then Descriptor.validateSiliconPower else if binding = 1 then Descriptor.validateSilicon else if binding = 2 then Descriptor.validateSiliconFull else Descriptor.validate) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind (if binding = 0 then Lemma.Platform.LemmaSim.MachineServices.validate else Lemma.Platform.LemmaSim.MachineServices.validateSilicon) fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (if binding = 3 then Lemma.Drivers.PLIC.initializePower else Lemma.Drivers.PLIC.initialize) fun s _ => if s = 0 then
  .bind (construct initialization isolation binding arithmeticMode) fun s _ => if s = 0 then if binding = 3 then .loop powerStepEntryV2 else .loop step else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconClosureEntry2Boot : Action := bootSelectedEntryV2 0 0 3 0
def siliconClosureEntry2InitializeMedium : Action := bootSelectedEntryV2 1 0 3 0

/-- The package/closure notebook keeps the existing four-role constructor and
installer capability grants. Only the new software roots select the checked
entry-context borrow; historical course boot loops remain unchanged. -/
private def bootCourseSelectedEntryV2 (initialization isolation binding arithmeticMode : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (if binding = 3 then Descriptor.validateSiliconPower else if binding = 1 then Descriptor.validateSilicon else if binding = 2 then Descriptor.validateSiliconFull else Descriptor.validate) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind (if binding = 0 then Lemma.Platform.LemmaSim.MachineServices.validate else Lemma.Platform.LemmaSim.MachineServices.validateSilicon) fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (if binding = 3 then Lemma.Drivers.PLIC.initializePower else Lemma.Drivers.PLIC.initialize) fun s _ => if s = 0 then
  .bind (constructCourse initialization isolation binding arithmeticMode) fun s _ => if s = 0 then
    if binding = 3 then .loop powerStepEntryV2 else .loop step else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconPackageClosureEntry2Boot : Action := bootCourseSelectedEntryV2 0 0 3 0
def siliconPackageClosureEntry2InitializeMedium : Action := bootCourseSelectedEntryV2 1 0 3 0


/-- Four isolated roles on the existing Clocked13/Kernel6 recovery hardware.
Only the installer receives Console input; only Store receives the block grant.
The same controller, power policy, checker and exact USB dispatch remain shared.
This software selection grants no Product/NV or authentication authority. -/
private def constructPackageRecovery (initialization : UInt64) : Action :=
  .bind Process.init fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (Objects.initArithmetic) fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 (initialization + 2)) fun s notebook => if s = 0 then
  .bind (Task.prepareManaged 2 0) fun s arithmetic => if s = 0 then
  .bind (Task.prepareManaged 3 initialization) fun s installer => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind (DeviceService.configureUSBRecovery surface input block) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (
    .bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal
    ) fun s _ => if s = 0 then
  .bind (grant installer Objects.consoleKey (CapabilityABI.consoleRead ||| CapabilityABI.consoleWrite)) fun s _ => if s = 0 then
  .bind (grant installer documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged installer) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x4b4 installer documents 0 0) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def bootPackageRecovery (initialization : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingClocked 13) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (Lemma.Drivers.PLIC.initializeUSB) fun s _ => if s = 0 then
  .bind (Lemma.USB.Block.initializeRecovery) fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructPackageRecovery initialization) fun s _ => if s = 0 then
  .loop recoveryUSBStep
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconUSBPackageRecoveryBoot : Action := bootPackageRecovery 0
def siliconUSBPackageRecoveryInitializeMedium : Action := bootPackageRecovery 1
def dispatchUSBPackageRecoveryBulk (frame cause value : UInt64) : Action :=
  dispatchRecoveryBulk 13 frame cause value

/-- Product10 course software prepares all four real isolated images through
the product address-space/loader path. Ordinary boot never formats the Store.
Only the installer receives Console Read; neither User receives the NV alias.
Historical three-role Product10 and four-role preload roots remain unchanged. -/
private def constructProductCourseReader : Action :=
  .bind (AddressSpace.configureProductExecuted 10) fun s _ => if s = 0 then
  .bind Process.initProduct fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind Objects.initArithmetic fun s _ => if s = 0 then
  .bind (Task.prepareManagedProduct 0 0) fun s store => if s = 0 then
  .bind (Task.prepareManagedProduct 1 2) fun s notebook => if s = 0 then
  .bind (Task.prepareManagedProduct 2 0) fun s arithmetic => if s = 0 then
  .bind (Task.prepareManagedProduct 3 0) fun s installer => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s power => if s = 0 then
  .bind (Objects.createEndpoint arithmetic) fun s checking => if s = 0 then
  .bind (DeviceService.configure surface input block) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook power CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant installer Objects.consoleKey (CapabilityABI.consoleRead ||| CapabilityABI.consoleWrite)) fun s _ => if s = 0 then
  .bind (grant installer documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (PowerControl.configureSafety 1 power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (Task.activateManaged arithmetic) fun s _ => if s = 0 then
  .bind (Task.activateManaged installer) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (BootHealthExecuted.configure store notebook) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents 8192) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x4b4 installer documents 0 0) fun s _ => if s = 0 then
  configureIsolation 0 documents
  else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal

private def productCourseReaderStep : Action :=
  .bind (acceptPendingModernExecuted 10) fun s _ => if s = 0 then
  .bind DeviceService.deferred fun s _ => if s = 0 then
  .bind PowerControl.step fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else
  .bind BootHealthExecuted.step fun s _ => if s = 0 then
  .bind Scheduler.stepEntryV2 fun s reason => if s = 0 then
  .bind observeReaped fun s _ => if s = 0 then .done 0 reason
  else fatal else fatal else fatal else fatal else fatal else fatal

/-- Closed Product10 successor for Reader18/Closure7 plus the owned installer.
ROM supplies image/context/discovery through NV transactions. This definition
does not itself qualify a linked deployment or any boot/update observation. -/
def siliconProductCourseReaderBoot : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingExecuted 10) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.initializePower fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind constructProductCourseReader fun s _ => if s = 0 then
  .loop productCourseReaderStep
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0


/-- Same Clocked13 recovery and four-role constructor; entry authority is
borrowed only inside the existing checked Scheduler EntryV2 Action. The old
recovery roots keep their exact callback and source bodies. -/
private def packageRecoveryEntry2Step : Action :=
  .bind (acceptPendingRecovery 13) fun s _ => if s = 0 then
  .bind DeviceService.deferredUSBRecovery fun s _ => if s = 0 then
  .bind PowerControl.stepUSB fun s suspended => if s = 0 then
  if suspended = 1 then .done 0 0 else Scheduler.stepEntryV2
  else fatal else fatal else fatal

private def bootPackageRecoveryEntry2 (initialization : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind (Descriptor.validateBindingClocked 13) fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.initializeUSB fun s _ => if s = 0 then
  .bind Lemma.USB.Block.initializeRecovery fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initializeExecuted fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind (constructPackageRecovery initialization) fun s _ => if s = 0 then
  .loop packageRecoveryEntry2Step
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconUSBPackageRecoveryEntry2Boot : Action := bootPackageRecoveryEntry2 0
def siliconUSBPackageRecoveryEntry2InitializeMedium : Action := bootPackageRecoveryEntry2 1


private def deviceCallMultimodalAt (descriptor context pc number : UInt64) : Action :=
  .bind (Access.read64 (context + 80)) fun s a => if s = 0 then
  .bind (Access.read64 (context + 88)) fun s b => if s = 0 then
  .bind (Access.read64 (context + 96)) fun s c => if s = 0 then
  .bind (Access.read64 (context + 104)) fun s d => if s = 0 then
  .bind (Access.read64 (context + 112)) fun s e => if s = 0 then
  .bind (if number = 64 then DeviceService.surfaceV2At descriptor (context - AddressSpace.userContextOffset) a b c d e else
    if number = 65 then DeviceService.input descriptor a b c d e else
    if number = 66 then DeviceService.block descriptor a b c d e else
    if number = 69 then MultimodalService.call descriptor a b c d e else
    if number = 68 then PowerControl.call descriptor a b c d e else
    if d ||| e = 0 then IPC.tryCallWait descriptor a b c else .done 16 0) fun status result =>
  if status = DeviceService.waitStatus then
    .bind MachineServices.time fun s now => if s = 0 then
    if 0xffffffffffffffff - 10000000 < now then fatal else
    .bind (Process.syscallReply context pc 174 0) fun s _ => if s = 0 then
    .bind (Task.sleep descriptor (now + 10000000) pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 3 pc else fatal else fatal else fatal
  else if status = 255 then fatal else
  if number = 68 then if b = 1 then if status = 0 then
    .bind (Process.syscallReply context pc status result) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 2 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 2 pc else fatal else fatal
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else Process.syscallReply context pc status result
  else fatal else fatal else fatal else fatal else fatal

def dispatchMultimodalBulk (frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    .bind Lemma.Drivers.PLIC.claim fun s source => if s = 0 then
    .bind (if source = 14 then PowerControl.notification else DeviceService.notification source) fun s _ => if s = 0 then
    .bind (Lemma.Drivers.PLIC.completePower source) fun s _ => if s = 0 then
    .bind (Task.ready descriptor 1 pc) fun s _ => if s = 0 then
    Scheduler.returnKernel descriptor 1 pc else fatal else fatal else fatal else fatal
    else fatal else fatal else fatal
  else if cause = 8 then
    .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
    .bind (Task.capture descriptor frame) fun s context => if s = 0 then
    .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
    if pc % 4 = 0 then
    .bind (AddressSpace.lookupAt (context - AddressSpace.userContextOffset) pc 4) fun s _ => if s = 0 then
    .bind (Access.read64 (context + 136)) fun s number => if s = 0 then
    if (if number = 64 then true else if number = 65 then true else if number = 66 then true else if number = 67 then true else if number = 68 then true else if number = 69 then true else false) = true then
      deviceCallMultimodalAt descriptor context pc number
    else Scheduler.callWithIPCLimit IPCABI.lemmaSimMaximumTicks descriptor context pc
    else fatal else fatal else fatal else fatal else fatal else fatal
  else
    .bind (observeFault cause) fun s _ => if s = 0 then
    Scheduler.dispatch frame cause value else fatal

/-- Converter14 construction: the same four original authorities, with
explicit supervisor-only aliases in each fixed task root before activation. -/
private def constructCourseMultimodal (initialization : UInt64) : Action :=
  let binding : UInt64 := 3
  let arithmeticMode : UInt64 := 0
  let isolation : UInt64 := 0
  .bind Process.initMultimodal fun s _ => if s = 0 then
  .bind Task.init fun s _ => if s = 0 then
  .bind (if binding = 3 then Objects.initArithmetic else Objects.init) fun s _ => if s = 0 then
  .bind (Task.prepareManaged 0 initialization) fun s store => if s = 0 then
  .bind (Task.prepareManaged 1 (if binding = 3 then initialization + 2 else initialization)) fun s notebook => if s = 0 then
  .bind (if binding = 3 then Task.prepareManaged 2 arithmeticMode else .done 0 0) fun s arithmetic => if s = 0 then
  .bind (Task.prepareManaged 3 initialization) fun s installer => if s = 0 then
  .bind (AddressSpace.addMultimodalAliases store) fun s _ => if s = 0 then
  .bind (AddressSpace.addMultimodalAliases notebook) fun s _ => if s = 0 then
  .bind (AddressSpace.addMultimodalAliases arithmetic) fun s _ => if s = 0 then
  .bind (AddressSpace.addMultimodalAliases installer) fun s _ => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s surface => if s = 0 then
  .bind (Objects.createEndpoint notebook) fun s input => if s = 0 then
  .bind (Objects.createEndpoint store) fun s block => if s = 0 then
  .bind (Objects.createEndpoint store) fun s documents => if s = 0 then
  .bind (if binding = 3 then Objects.createEndpoint notebook else .done 0 0) fun s power => if s = 0 then
  .bind (if binding = 3 then Objects.createEndpoint arithmetic else .done 0 0) fun s checking => if s = 0 then
  .bind (DeviceService.configure surface input block) fun s _ => if s = 0 then
  .bind (grant store block CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant store documents CapabilityABI.endpointReceive) fun s _ => if s = 0 then
  .bind (grant store Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (grant notebook surface CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook input CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (grant notebook Objects.consoleKey CapabilityABI.consoleWrite) fun s _ => if s = 0 then
  .bind (if binding = 3 then grant notebook power CapabilityABI.endpointCall else .done 0 0) fun s _ => if s = 0 then
  .bind (if binding = 3 then
    .bind (grant notebook checking CapabilityABI.endpointCall) fun s _ => if s = 0 then
    .bind (grant arithmetic checking CapabilityABI.endpointReceive) fun s _ => if s = 0 then
    grant arithmetic Objects.consoleKey CapabilityABI.consoleWrite else fatal else fatal
    else .done 0 0) fun s _ => if s = 0 then
  .bind (grant installer Objects.consoleKey (CapabilityABI.consoleRead ||| CapabilityABI.consoleWrite)) fun s _ => if s = 0 then
  .bind (grant installer documents CapabilityABI.endpointCall) fun s _ => if s = 0 then
  .bind (PowerControl.configure (if binding = 3 then 1 else 0) power) fun s _ => if s = 0 then
  .bind (Task.activateManaged store) fun s _ => if s = 0 then
  .bind (if binding = 3 then Task.activateManaged arithmetic else .done 0 0) fun s _ => if s = 0 then
  .bind (Task.activateManaged installer) fun s _ => if s = 0 then
  .bind (Task.activateManaged notebook) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x410 store notebook documents (if binding = 1 then Lemma.Platform.Silicon.Binding.frame_count else 8192)) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x4b4 installer documents 0 0) fun s _ => if s = 0 then
  configureIsolation isolation documents
  else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal

private def bootMultimodal (initialization : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind Descriptor.validateSiliconMultimodal fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateMultimodal fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.initializePower fun s _ => if s = 0 then
  .bind (constructCourseMultimodal initialization) fun s _ => if s = 0 then
    .bind (Access.read64 (PowerControl.stateBase + 8)) fun s key => if mmFailed s = true then .done s 0 else
    .bind (MultimodalService.configure key) fun s _ => if mmFailed s = true then .done s 0 else
    .loop powerStepEntryV2 else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconMultimodalBoot : Action := bootMultimodal 0
def siliconMultimodalInitializeMedium : Action := bootMultimodal 1

/-- Exact owner-local parameterized development boot: grant the existing
isolated checker Call endpoint to the sole course UART consumer before the
first User instruction. Registry role and initial capability counts are checked;
no Store, display, sensor or checking-result authority is added. -/
private def grantParameterizedInstaller : Action :=
  .bind (Objects.registryDescriptor 1) fun s notebook => if s = 0 then
  .bind (Task.lookup notebook) fun s notebookRow => if s = 0 then
  .bind (Access.read64 (notebookRow + Task.imageOffset)) fun s notebookImage => if s = 0 then
  if notebookImage = 1 then
  .bind (Capability.bootGrant notebook 5) fun s checkingHandle => if s = 0 then
  .bind (Capability.lookup notebook checkingHandle CapabilityABI.endpointType CapabilityABI.endpointCall) fun s checking => if s = 0 then
  .bind (Objects.registryDescriptor 3) fun s installer => if s = 0 then
  .bind (Task.lookup installer) fun s installerRow => if s = 0 then
  .bind (Access.read64 (installerRow + Task.imageOffset)) fun s installerImage => if s = 0 then
  if installerImage = 3 then
  .bind (Capability.entryCount installer) fun s before => if s = 0 then
  if before = 2 then
  .bind (Capability.grantDiscovered installer checking) fun s handle => if s = 0 then
  .bind (Capability.entryCount installer) fun s after => if s = 0 then
  if after = 3 then Lemma.Kernel.Console.record 0x72e installer checking handle after else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal

private def bootMultimodalParameterized (initialization : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind BootInfo.validate fun status value =>
  .bind (observedStage 1 status value) fun s _ => if s = 0 then
  .bind Descriptor.validateSiliconMultimodal fun status value =>
  .bind (observedStage 2 status value) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateMultimodal fun status value =>
  .bind (observedStage 3 status value) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if s = 0 then
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if s = 0 then
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.initializePower fun s _ => if s = 0 then
  .bind (constructCourseMultimodal initialization) fun s _ => if s = 0 then
    .bind grantParameterizedInstaller fun s _ => if mmFailed s = true then .done s 0 else
    .bind (Access.read64 (PowerControl.stateBase + 8)) fun s key => if mmFailed s = true then .done s 0 else
    .bind (MultimodalService.configure key) fun s _ => if mmFailed s = true then .done s 0 else
    .loop powerStepEntryV2 else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def siliconMultimodalParameterizedBoot : Action := bootMultimodalParameterized 0
def siliconMultimodalParameterizedInitializeMedium : Action := bootMultimodalParameterized 1

/-- Integrated15 composes the maintained Product10 four-role authorities and
scheduler step; their original constructors and legacy roots remain unchanged. -/
def prepareIntegratedAuthorities : Action :=
  .bind constructProductCourseReader fun s _ => if mmFailed s = true then .done s 0 else
  grantParameterizedInstaller
def stepIntegratedAuthorities : Action := productCourseReaderStep

end Lemma.Platform.LemmaSim.NotebookKernel
