import Lemma.Kernel.Development.TasksEntry
import Lemma.Kernel.Development.Pressure

/-! Separate, quarantined four-image lifecycle entry. The production Task and
Scheduler policies do not know image names or adversarial startup cases. This
entry adds checked physical reuse observations and the trusted quota-pressure
command; the three-image scheduling entry retains its original wire protocol. -/
namespace Lemma.Kernel.Development.FaultEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

/-- Observation is before the first user dispatch. Both byte addresses and
the private owner come from the checked live address-space descriptor. -/
def observeCreation (descriptor : UInt64) : Action :=
  .bind (Task.lookup descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (AddressSpace.lookup descriptor 0x20000 1) fun s data =>
  if failed s = true then fatal else
  .bind (AddressSpace.lookup descriptor 0x3fffc020 1) fun s stack =>
  if failed s = true then fatal else
  .bind (AddressSpace.owner descriptor) fun s owner =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xfe descriptor data stack owner) fun s _ =>
  if failed s = true then fatal else .done 0 descriptor

def create (image argument : UInt64) : Action :=
  .bind (Task.create image argument) fun s descriptor =>
  if failed s = true then .done s 0 else observeCreation descriptor

private def launch : Action :=
  .bind TasksEntry.readLaunch fun s address =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (address + 8)) fun s a =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 16)) fun s b =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 24)) fun s c =>
  if failed s = true then fatal else
  .bind (create 0 a) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (create 1 b) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (create 2 c) fun s _ => .done s 3

def command (number a b c d : UInt64) : Action :=
  if number = 0x33 then
    if c ||| d = 0 then
      .bind (create a b) fun s id => TasksEntry.acknowledge number s id a
    else TasksEntry.acknowledge number 16 0 a
  else if number = 0x34 then
    if c ||| d = 0 then
      .bind (Pressure.run a b) fun s value => TasksEntry.acknowledge number s value a
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
    .bind launch fun s _ =>
    if failed s = true then .done s 0 else .loop step
  else fatal

def dispatch (frame cause value : UInt64) : Action :=
  Scheduler.dispatch frame cause value

end Lemma.Kernel.Development.FaultEntry
