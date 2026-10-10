import Lemma.Kernel.Development.TasksEntry
import Lemma.Kernel.IPC

/-! Closed IPC development boot policy. Four independently compiled images
receive explicit grants while constructing, then become runnable. Ordinary IPC
knows neither these image roles nor diagnostic commands. -/
namespace Lemma.Kernel.Development.IPCEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def primaryKeyOffset : UInt64 := 160
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

private def grant (descriptor key kind rights : UInt64) : Action :=
  .bind (Capability.grantBoot descriptor key rights) fun s handle =>
  if s = 255 then fatal else
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0xb1 descriptor handle kind rights) fun s _ =>
  if failed s = true then fatal else .done 0 handle

private def abortOne (descriptor : UInt64) (status : UInt8) : Action :=
  .bind (Task.abort descriptor) fun s _ =>
  if failed s = true then fatal else .done status 0
private def abortTwo (first second : UInt64) (status : UInt8) : Action :=
  .bind (Task.abort second) fun s _ =>
  if failed s = true then fatal else abortOne first status
private def abortThree (first second third : UInt64) (status : UInt8) : Action :=
  .bind (Task.abort third) fun s _ =>
  if failed s = true then fatal else abortTwo first second status
private def abortFour (first second third fourth : UInt64) (status : UInt8) : Action :=
  .bind (Objects.table) fun s base =>
  if failed s = true then fatal else
  .bind (Objects.put (base + primaryKeyOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.abort fourth) fun s _ =>
  if failed s = true then fatal else abortThree first second third status

private def initialGrants (server clientA clientB primary probe inbox : UInt64) : Action :=
  .bind (grant server Objects.consoleKey CapabilityABI.consoleType 34) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant server primary CapabilityABI.endpointType 8) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant clientA Objects.consoleKey CapabilityABI.consoleType 34) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant clientA primary CapabilityABI.endpointType 20) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant clientA probe CapabilityABI.endpointType 124) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant clientA Objects.managementKey CapabilityABI.managementType 928) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant clientA inbox CapabilityABI.endpointType 4) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant clientB Objects.consoleKey CapabilityABI.consoleType 34) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant clientB primary CapabilityABI.endpointType 20) fun s _ =>
  if failed s = true then .done s 0 else
  grant clientB inbox CapabilityABI.endpointType 8

private def activate (server clientA clientB busy : UInt64) : Action :=
  .bind (Task.activateManaged server) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.activateManaged clientA) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.activateManaged clientB) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.activateManaged busy) fun s _ =>
  if failed s = true then fatal else .done 0 4

private def createEndpoint (owner : UInt64) : Action :=
  .bind (Objects.createEndpoint owner) fun s key =>
  if failed s = true then .done s 0 else
  .bind Frames.remaining fun s remaining =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xb4 owner key remaining 0) fun s _ =>
  if failed s = true then fatal else .done 0 key

private def configure (server clientA clientB busy : UInt64) : Action :=
  .bind (Objects.configureManagement clientA clientB) fun s _ =>
  if failed s = true then abortFour server clientA clientB busy s else
  .bind (createEndpoint server) fun s primary =>
  if failed s = true then abortFour server clientA clientB busy s else
  .bind (createEndpoint clientA) fun s probe =>
  if failed s = true then abortFour server clientA clientB busy s else
  .bind (createEndpoint clientB) fun s inbox =>
  if failed s = true then abortFour server clientA clientB busy s else
  .bind Objects.table fun s base =>
  if failed s = true then fatal else
  .bind (Objects.put (base + primaryKeyOffset) primary) fun s _ =>
  if failed s = true then fatal else
  .bind (initialGrants server clientA clientB primary probe inbox) fun s _ =>
  if failed s = true then abortFour server clientA clientB busy s else
  activate server clientA clientB busy

private def launch : Action :=
  .bind TasksEntry.readLaunchWithFourth fun s packet =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (packet + 8)) fun s a =>
  if failed s = true then fatal else
  .bind (Access.read64 (packet + 16)) fun s b =>
  if failed s = true then fatal else
  .bind (Access.read64 (packet + 24)) fun s c =>
  if failed s = true then fatal else
  .bind (Access.read64 (packet + 32)) fun s d =>
  if failed s = true then fatal else
  .bind (Task.prepareManaged 0 a) fun s server =>
  if failed s = true then .done s 0 else
  .bind (Task.prepareManaged 1 b) fun s clientA =>
  if failed s = true then abortOne server s else
  .bind (Task.prepareManaged 2 c) fun s clientB =>
  if failed s = true then abortTwo server clientA s else
  .bind (Task.prepareManaged 3 d) fun s busy =>
  if failed s = true then abortThree server clientA clientB s else
  configure server clientA clientB busy

/-- This retained value is a full object generation key, not a saved physical
pointer. Revalidation also excludes a withdrawn/dying owner task. -/
private def retainedPrimary : Action :=
  .bind Objects.table fun s base =>
  if failed s = true then fatal else
  .bind (Objects.get (base + primaryKeyOffset)) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
  .bind (Objects.get (object + 40)) fun s owner =>
  if failed s = true then fatal else
  .bind (Capability.requireActive owner) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Task.lookup owner) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else .done 0 key
  else .done CapabilityABI.wrongType 0

private def createFault (argument : UInt64) : Action :=
  .bind retainedPrimary fun s primary =>
  if failed s = true then .done s 0 else
  .bind (Task.prepareManaged 4 argument) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (grant descriptor Objects.consoleKey CapabilityABI.consoleType 34) fun s _ =>
  if failed s = true then abortOne descriptor s else
  .bind (grant descriptor primary CapabilityABI.endpointType 20) fun s _ =>
  if failed s = true then abortOne descriptor s else Task.activateManaged descriptor

def command (number a b c d : UInt64) : Action :=
  if number = 0x33 then
    if c ||| d = 0 then
      if a = 4 then
        .bind (createFault b) fun s id => TasksEntry.acknowledge number s id a
      else TasksEntry.acknowledge number 81 0 a
    else TasksEntry.acknowledge number 16 0 a
  else TasksEntry.command number a b c d

private def packet : Action :=
  .bind TasksEntry.readPacket fun s address =>
  if failed s = true then fatal else
  .bind (Access.read64 address) fun s header =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 8)) fun s a =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 16)) fun s b =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 24)) fun s c =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 32)) fun s d =>
  if failed s = true then fatal else
  .bind TasksEntry.resetPacket fun s _ =>
  if failed s = true then fatal else
  if header >>> 8 = 0 then command (header &&& 255) a b c d
  else TasksEntry.acknowledge (header &&& 255) 16 0 a

def poll : Action :=
  .bind TasksEntry.pollBytes fun s length =>
  if failed s = true then fatal else
  if length = 40 then packet else .done 0 0
def step : Action :=
  .bind poll fun s _ =>
  if failed s = true then fatal else Scheduler.step

def boot : Action :=
  .bind Lemma.Kernel.Entry.bootServices fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 0x80400010) fun s stage =>
  if failed s = true then fatal else
  if stage = 1 then
  .bind Process.init fun s _ =>
  if failed s = true then fatal else
  .bind Task.init fun s _ =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xf0 1 Task.capacity Task.stride Scheduler.quantum) fun s _ =>
  if failed s = true then fatal else
  .bind Objects.init fun s _ =>
  if failed s = true then .done s 0 else
  .bind Frames.remaining fun s baseline =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xb0 1 Capability.capacity Objects.capacity baseline) fun s _ =>
  if failed s = true then fatal else
  .bind launch fun s _ =>
  if failed s = true then .done s 0 else .loop step
  else fatal

def dispatch (frame cause value : UInt64) : Action :=
  Scheduler.dispatch frame cause value

end Lemma.Kernel.Development.IPCEntry
