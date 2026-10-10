import Lemma.Kernel.Development.TasksEntry
import Lemma.Kernel.Development.CapAlias
import Lemma.Kernel.Development.CapabilityGeneration

/-! Closed development capability boot policy. Kernel-held grants are installed
while each task is building; only fully configured instances are activated.
The package contains independently compiled user images. Image selection here
is explicit boot/test policy, not a scheduler or capability-lookup decision. -/
namespace Lemma.Kernel.Development.CapsEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

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

private def initialGrants (tester peer endpoint : UInt64) : Action :=
  .bind (grant tester Objects.consoleKey Lemma.User.CapabilityABI.consoleType 34) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant tester Objects.managementKey Lemma.User.CapabilityABI.managementType 928) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant tester endpoint Lemma.User.CapabilityABI.endpointType 124) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant peer Objects.consoleKey Lemma.User.CapabilityABI.consoleType 34) fun s _ =>
  if failed s = true then .done s 0 else
  grant peer endpoint Lemma.User.CapabilityABI.endpointType 36

private def seedEndpoint : Action :=
  .bind CapabilityGeneration.seedOneFree fun s index =>
  if s = 255 then fatal else
  if failed s = true then .done s 0 else
  .bind CapabilityGeneration.seedResult fun s tuple =>
  if failed s = true then fatal else
  .bind (Access.read64 tuple) fun s actualIndex =>
  if failed s = true then fatal else
  .bind (Access.read64 (tuple + 8)) fun s old =>
  if failed s = true then fatal else
  .bind (Access.read64 (tuple + 16)) fun s generation =>
  if failed s = true then fatal else
  .bind (Access.read64 (tuple + 24)) fun s state =>
  if failed s = true then fatal else
  if actualIndex = index then
    .bind (Lemma.Kernel.Console.record 0xb5 index old generation state) fun s _ =>
    if failed s = true then fatal else .done 0 index
  else fatal

private def configure (tester peer busy : UInt64) : Action :=
  .bind (Objects.configureManagement tester peer) fun s _ =>
  if failed s = true then abortThree tester peer busy s else
  .bind seedEndpoint fun s slot =>
  if failed s = true then abortThree tester peer busy s else
  .bind (Objects.createEndpoint tester) fun s endpoint =>
  if failed s = true then abortThree tester peer busy s else
  if Objects.keyIndex endpoint = slot then
  if Objects.keyGeneration endpoint = Objects.maxGeneration then
  .bind Frames.remaining fun s remaining =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xb4 tester endpoint remaining 0) fun s _ =>
  if failed s = true then fatal else
  .bind (initialGrants tester peer endpoint) fun s _ =>
  if failed s = true then abortThree tester peer busy s else
  .bind (Task.activateManaged tester) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.activateManaged peer) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.activateManaged busy) fun s _ =>
  if failed s = true then fatal else .done 0 3
  else fatal else fatal

private def launch : Action :=
  .bind TasksEntry.readLaunch fun s packet =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (packet + 8)) fun s a =>
  if failed s = true then fatal else
  .bind (Access.read64 (packet + 16)) fun s b =>
  if failed s = true then fatal else
  .bind (Access.read64 (packet + 24)) fun s c =>
  if failed s = true then fatal else
  .bind (Task.prepareManaged 0 a) fun s tester =>
  if failed s = true then .done s 0 else
  .bind (Task.prepareManaged 1 b) fun s peer =>
  if failed s = true then abortOne tester s else
  .bind (Task.prepareManaged 2 c) fun s busy =>
  if failed s = true then abortTwo tester peer s else configure tester peer busy

private def createTamper (argument : UInt64) : Action :=
  .bind (Task.prepareManaged 3 argument) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (grant descriptor Objects.consoleKey Lemma.User.CapabilityABI.consoleType 2) fun s _ =>
  if failed s = true then abortOne descriptor s else
  .bind (CapAlias.install descriptor) fun s _ =>
  if failed s = true then abortOne descriptor s else Task.activateManaged descriptor

def command (number a b c d : UInt64) : Action :=
  if number = 0x33 then
    if c ||| d = 0 then
      if a = 3 then
        .bind (createTamper b) fun s id => TasksEntry.acknowledge number s id a
      else TasksEntry.acknowledge number 81 0 a
    else TasksEntry.acknowledge number 16 0 a
  else if number = 0x36 then
    if a ||| b ||| c ||| d = 0 then
      .bind Objects.nextSerial fun s before =>
      if failed s = true then TasksEntry.acknowledge number s 0 a else
      .bind CapabilityGeneration.advance fun s after =>
      if failed s = true then TasksEntry.acknowledge number s 0 a else
      .bind (Lemma.Kernel.Console.record 0xb3 before after Objects.maxSerial 0) fun s _ =>
      if failed s = true then fatal else TasksEntry.acknowledge number 0 after a
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
    .bind (Lemma.Kernel.Console.record 0xb0 1 16 Objects.capacity baseline) fun s _ =>
    if failed s = true then fatal else
    .bind launch fun s _ =>
    if failed s = true then .done s 0 else .loop step
  else fatal

def dispatch (frame cause value : UInt64) : Action :=
  Scheduler.dispatch frame cause value

end Lemma.Kernel.Development.CapsEntry
