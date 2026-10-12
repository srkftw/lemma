import Lemma.Kernel.ServiceEntry
import Lemma.Platform.Silicon.Binding

/-! Trusted development-only lifecycle controls. The input is KernelInput's
distinct diagnostic class, never the ordinary CLI byte stream. Pending restart
depends only on checked full identities and a genuinely delivered live Reply;
it has no Buffer operation, request identifier, banner or test-PC selector. -/
namespace Lemma.Kernel.Development.ServiceEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def phase : UInt64 := Process.control + 56
def targetServer : UInt64 := Process.control + 64
def acceptedReply : UInt64 := Process.control + 72
def expectedCaller : UInt64 := Process.control + 80
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

private def acknowledge (number : UInt64) (status : UInt8) (value subject : UInt64) : Action :=
  .bind (Lemma.Kernel.Console.record 0xf7 number status.toUInt64 value subject) fun s _ =>
  if failed s = true then fatal else .done 0 value

private def clearControl : Action :=
  .bind (Access.write64 phase 0) fun s _ => if failed s = true then fatal else
  .bind (Access.write64 targetServer 0) fun s _ => if failed s = true then fatal else
  .bind (Access.write64 acceptedReply 0) fun s _ => if failed s = true then fatal else
  Access.write64 expectedCaller 0

private def stableKernel : Action :=
  .bind (Access.read64 Process.control) fun s current =>
  if failed s = true then fatal else
  if current = 0 then
  .bind (Access.read64 (Process.control + 8)) fun s root =>
  if failed s = true then fatal else
  .bind (Access.read64 AddressSpace.activeRoot) fun s active =>
  if failed s = true then fatal else
  if active = root then .done 0 0 else fatal
  else fatal

private def cliStep (i _ : UInt32) (acc table _ _ _ : UInt64) : Action :=
  let row := table + i.toUInt64 * Task.stride
  .bind (Access.read64 (row + Task.stateOffset)) fun s state =>
  if failed s = true then fatal else
  if (if Task.runnable ≤ state then if state < Task.dying then true else false else false) = true then
    .bind (Access.read64 (row + Task.imageOffset)) fun s image =>
    if failed s = true then fatal else
    if image = 1 then
      .bind (Access.read64 row) fun s descriptor =>
      if failed s = true then fatal else .done Status.iterationStop descriptor
    else .done 0 acc
  else if Task.dying < state then fatal else .done 0 acc

private def cliDescriptor : Action :=
  .bind Task.table fun s table =>
  if failed s = true then fatal else
  .boundedFoldU64 8 cliStep 8 0 table 0 0 0 fun s cli =>
  if s = Status.iterationStop then
    .bind (Task.lookup cli) fun s _ => if failed s = true then fatal else
    .bind (Capability.requireActive cli) fun s _ =>
    if failed s = true then fatal else .done 0 cli
  else if s = 0 then .done IPCABI.peerDied 0 else fatal

private def replacement : Action :=
  .bind stableKernel fun s _ => if failed s = true then fatal else
  .bind cliDescriptor fun s cli => if failed s = true then .done s 0 else
  .bind Lemma.Kernel.ServiceEntry.serverBudget fun s _ =>
  if failed s = true then .done s 0 else
  .bind Directory.nextEpoch fun s epoch => if failed s = true then .done s 0 else
  .bind (Task.prepareManaged 0 epoch) fun s server =>
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.ServiceEntry.createEndpoint server) fun s endpoint =>
  if failed s = true then Lemma.Kernel.ServiceEntry.abortOne server s else
  .bind (Lemma.Kernel.ServiceEntry.grant server Objects.consoleKey CapabilityABI.consoleType 2) fun s _ =>
  if failed s = true then Lemma.Kernel.ServiceEntry.abortOne server s else
  .bind (Lemma.Kernel.ServiceEntry.grant server endpoint CapabilityABI.endpointType 8) fun s _ =>
  if failed s = true then Lemma.Kernel.ServiceEntry.abortOne server s else
  .bind (Directory.preflightPublish server endpoint epoch) fun s _ =>
  if failed s = true then Lemma.Kernel.ServiceEntry.abortOne server s else
  Lemma.Kernel.ServiceEntry.activatePublished server endpoint epoch cli

private def stopServer : Action :=
  .bind stableKernel fun s _ => if failed s = true then fatal else
  .bind Directory.server fun s server =>
  if s = 0 then
    .bind (Task.lookup server) fun s _ =>
    if s = 0 then
      .bind (Task.terminate server 0 0 0 0) fun s _ =>
      if failed s = true then fatal else Task.reap
    else if s = 74 then Task.reap else fatal
  else if s = IPCABI.peerDied then Task.reap else fatal

private def restart : Action :=
  .bind stopServer fun s _ => if failed s = true then fatal else
  .bind clearControl fun s _ => if failed s = true then fatal else replacement

private def createFault (argument : UInt64) : Action :=
  .bind (Task.prepareManaged 4 argument) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.ServiceEntry.grant descriptor Objects.consoleKey CapabilityABI.consoleType 2) fun s _ =>
  if failed s = true then Lemma.Kernel.ServiceEntry.abortOne descriptor s else
  .bind (Lemma.Kernel.ServiceEntry.grant descriptor Objects.directoryKey CapabilityABI.directoryType 1024) fun s _ =>
  if failed s = true then Lemma.Kernel.ServiceEntry.abortOne descriptor s else
  Task.activateManaged descriptor

private def arm (caller : UInt64) : Action :=
  .bind (Access.read64 phase) fun s state =>
  if failed s = true then fatal else
  if state = 0 then
  .bind Directory.server fun s server =>
  if failed s = true then .done s 0 else
  .bind (Task.lookup server) fun s _ => if failed s = true then .done s 0 else
  .bind (Task.lookup caller) fun s _ => if failed s = true then .done s 0 else
  .bind (Capability.requireActive caller) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.pending caller) fun s pending =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (pending + IPCStorage.stateOffset)) fun s actualState =>
  if failed s = true then fatal else
  .bind (Access.read64 (pending + IPCStorage.transactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  if actualState = IPCStorage.stateIdle then if transaction = 0 then
  .bind (Access.write64 targetServer server) fun s _ => if failed s = true then fatal else
  .bind (Access.write64 acceptedReply 0) fun s _ => if failed s = true then fatal else
  .bind (Access.write64 expectedCaller caller) fun s _ => if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0x301 server caller actualState transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 phase 1) fun s _ => if failed s = true then fatal else .done 0 server
  else .done IPCABI.inFlight 0 else .done IPCABI.inFlight 0
  else .done IPCABI.inFlight 0

def command (number a b c d : UInt64) : Action :=
  if number = 0x31 then
    if b ||| c ||| d = 0 then
      .bind (if a = 0 then Task.queryAll else Task.query a) fun status _ =>
      .bind Frames.remaining fun s remaining =>
      if failed s = true then fatal else acknowledge number status remaining a
    else acknowledge number 16 0 a
  else if number = 0x32 then
    if b ||| c ||| d = 0 then
      .bind (Task.terminate a 0 0 0 0) fun status _ =>
      if status = 50 then fatal else
      .bind Task.reap fun s _ => if failed s = true then fatal else
      acknowledge number status a a
    else acknowledge number 16 0 a
  else if number = 0x33 then
    if c ||| d = 0 then if a = 4 then
      .bind (createFault b) fun status descriptor => acknowledge number status descriptor a
    else acknowledge number 16 0 a else acknowledge number 16 0 a
  else if number = 0x40 then
    if a ||| b ||| c ||| d = 0 then
      .bind restart fun status epoch => acknowledge number status epoch 0
    else acknowledge number 16 0 a
  else if number = 0x41 then
    if b ||| c ||| d = 0 then
      .bind (arm a) fun status server => acknowledge number status server a
    else acknowledge number 16 0 a
  else acknowledge number 17 0 a

private def diagnostic : Action :=
  .bind KernelInput.diagnosticPacket fun s packet =>
  if s = 12 then .done 0 0 else if failed s = true then fatal else
  .bind (Access.read64 packet) fun s number => if failed s = true then fatal else
  .bind (Access.read64 (packet + 8)) fun s a => if failed s = true then fatal else
  .bind (Access.read64 (packet + 16)) fun s b => if failed s = true then fatal else
  .bind (Access.read64 (packet + 24)) fun s c => if failed s = true then fatal else
  .bind (Access.read64 (packet + 32)) fun s d => if failed s = true then fatal else
  .bind KernelInput.consumeDiagnostic fun s _ =>
  if failed s = true then fatal else command number a b c d

private def acceptedStep (i _ : UInt32) (acc base server caller _ : UInt64) : Action :=
  let row := Objects.row base i.toUInt64
  .bind (Objects.get row) fun s state => if failed s = true then fatal else
  if state = Objects.live then
  .bind (Objects.get (row + 16)) fun s kind => if failed s = true then fatal else
  if kind = CapabilityABI.replyType then
  .bind (Objects.get (row + 8)) fun s generation => if failed s = true then fatal else
  let key := generation * Objects.capacity + i.toUInt64
  .bind (Objects.replyFields key) fun s fields => if failed s = true then fatal else
  .bind (Objects.get (fields + 40)) fun s actualCaller => if failed s = true then fatal else
  .bind (Objects.get (fields + 72)) fun s actualServer => if failed s = true then fatal else
  .bind (Objects.get (fields + 80)) fun s actualPhase => if failed s = true then fatal else
  if actualCaller = caller then if actualServer = server then if actualPhase = 2 then
    .done Status.iterationStop key else .done 0 acc else .done 0 acc else .done 0 acc
  else .done 0 acc else .done 0 acc

private def intercept (context server caller key : UInt64) : Action :=
  .bind (Objects.replyFields key) fun s fields => if failed s = true then fatal else
  .bind (Objects.get (fields + 64)) fun s transaction => if failed s = true then fatal else
  .bind (Objects.get (fields + 88)) fun s expires => if failed s = true then fatal else
  .bind (IPCStorage.pending caller) fun s pending => if failed s = true then fatal else
  .bind (Access.read64 (pending + IPCStorage.stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = IPCStorage.stateWaiting then
  .bind (Access.read64 (pending + IPCStorage.operationOffset)) fun s operation => if failed s = true then fatal else
  .bind (Access.read64 (pending + IPCStorage.transactionOffset)) fun s actualTransaction => if failed s = true then fatal else
  .bind (Access.read64 (pending + IPCStorage.replyOffset)) fun s actualReply => if failed s = true then fatal else
  .bind (Access.read64 (pending + IPCStorage.deadlineOffset)) fun s actualExpires => if failed s = true then fatal else
  if operation = IPCStorage.callOperation then if actualTransaction = transaction then
  if actualReply = key then if actualExpires = expires then
  .bind (Task.lookup caller) fun s _ => if failed s = true then fatal else
  .bind (Capability.requireActive caller) fun s _ => if failed s = true then fatal else
  .bind (Access.read64 (context + 256)) fun s pc => if failed s = true then fatal else
  .bind MachineServices.time fun s now => if failed s = true then fatal else
  if now < expires then
  .bind (Lemma.Kernel.Console.record 0x302 server caller key transaction) fun s _ => if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0x303 server pc expires now) fun s _ => if failed s = true then fatal else
  .bind (Access.write64 acceptedReply key) fun s _ => if failed s = true then fatal else
  .bind (Access.write64 phase 2) fun s _ => if failed s = true then fatal else
  .bind (Task.terminate server 0 0 pc key) fun s _ => if failed s = true then fatal else
  Scheduler.returnKernel server 5 pc
  else .done 0 context
  else fatal else fatal else fatal else fatal
  else .done 0 context

private def inspectDelivery (context : UInt64) : Action :=
  .bind (Access.read64 phase) fun s state => if failed s = true then fatal else
  if state = 1 then
  .bind (Access.read64 targetServer) fun s server => if failed s = true then fatal else
  .bind (Access.read64 Process.control) fun s current => if failed s = true then fatal else
  if current = server then
  .bind (AddressSpace.context server) fun s expectedContext => if failed s = true then fatal else
  if context = expectedContext then
  .bind (Access.read64 expectedCaller) fun s caller => if failed s = true then fatal else
  .bind Objects.table fun s table => if failed s = true then fatal else
  .boundedFoldU64 16 acceptedStep 16 0 table server caller 0 fun s key =>
  if s = Status.iterationStop then intercept context server caller key
  else if s = 0 then .done 0 context else fatal
  else .done 0 context else .done 0 context
  else if state = 0 then .done 0 context else fatal

private def completeRestart : Action :=
  .bind (Access.read64 phase) fun s state => if failed s = true then fatal else
  if state = 2 then
  .bind stableKernel fun s _ => if failed s = true then fatal else
  .bind (Access.read64 targetServer) fun s server => if failed s = true then fatal else
  .bind (Access.read64 acceptedReply) fun s key => if failed s = true then fatal else
  .bind replacement fun status epoch =>
  if status = 50 then fatal else
  .bind (Lemma.Kernel.Console.record 0x304 server key status.toUInt64 epoch) fun s _ =>
  if failed s = true then fatal else
  .bind clearControl fun s _ => if failed s = true then fatal else .done 0 epoch
  else if state ≤ 1 then .done 0 0 else fatal

def step : Action :=
  .bind completeRestart fun s _ => if failed s = true then fatal else
  .bind KernelInput.poll fun s _ => if failed s = true then fatal else
  .bind diagnostic fun s _ => if failed s = true then fatal else Scheduler.step

def boot : Action :=
  .bind (Lemma.Kernel.ServiceEntry.initialize 2) fun s _ =>
  if failed s = true then .done s 0 else
  .bind clearControl fun s _ => if failed s = true then fatal else
  .bind Lemma.Kernel.ServiceEntry.construct fun s _ =>
  if failed s = true then .done s 0 else .loop step

/-- CVW has no hypervisor extension: MIDELEG readback is exactly SSIP.
All service construction, scheduling, capability and IPC policy is shared. -/
def siliconBoot : Action :=
  .bind (Lemma.Kernel.ServiceEntry.initializeFor 2 2 Lemma.Platform.Silicon.Binding.boot_timer_probe_ticks) fun s _ =>
  if failed s = true then .done s 0 else
  .bind clearControl fun s _ => if failed s = true then fatal else
  .bind Lemma.Kernel.ServiceEntry.construct fun s _ =>
  if failed s = true then .done s 0 else .loop step

def dispatch (frame cause value : UInt64) : Action :=
  .bind (Scheduler.dispatch frame cause value) fun s context =>
  if failed s = true then fatal else inspectDelivery context

end Lemma.Kernel.Development.ServiceEntry
