import Lemma.Kernel.Entry
import Lemma.Kernel.Scheduler

/-! Explicit privileged development boot policy and control transport. User
programs are separate package images, never imports of this kernel. After one
preboot launch packet, partial control packets are polled without blocking the
scheduler. Query/kill/create are not user management grants. -/
namespace Lemma.Kernel.Development.TasksEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

/-- Shared preboot transport reads exactly one five-word launch packet. It
validates the fixed header before either development entry constructs tasks. -/
def readLaunch : Action :=
  .bind Lemma.Kernel.Console.readWord fun s header =>
  if failed s = true then .done 15 0 else
  .bind Lemma.Kernel.Console.readWord fun s a =>
  if failed s = true then .done 15 0 else
  .bind Lemma.Kernel.Console.readWord fun s b =>
  if failed s = true then .done 15 0 else
  .bind Lemma.Kernel.Console.readWord fun s c =>
  if failed s = true then .done 15 0 else
  .bind Lemma.Kernel.Console.readWord fun s d =>
  if failed s = true then .done 15 0 else
  if header = 0x30 then
    if d = 0 then
      .bind (Access.write64 Task.packetBase header) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (Task.packetBase + 8) a) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (Task.packetBase + 16) b) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (Task.packetBase + 24) c) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (Task.packetBase + 32) d) fun s _ =>
      if failed s = true then fatal else .done 0 Task.packetBase
    else .done 16 0
  else .done 16 0

private def launch : Action :=
  .bind readLaunch fun s address =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (address + 8)) fun s a =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 16)) fun s b =>
  if failed s = true then fatal else
  .bind (Access.read64 (address + 24)) fun s c =>
  if failed s = true then fatal else
  .bind (Task.create 0 a) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Task.create 1 b) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Task.create 2 c) fun s _ => .done s 3

def acknowledge (command : UInt64) (status : UInt8) (value argument : UInt64) : Action :=
  if status = 50 then fatal else
  .bind (Lemma.Kernel.Console.record 0xf7 command status.toUInt64 value argument) fun s _ =>
  if failed s = true then fatal else .done 0 0

def command (number a b c d : UInt64) : Action :=
  if number = 0x31 then
    if b ||| c ||| d = 0 then
      .bind (if a = 0 then Task.queryAll else Task.query a) fun s _ =>
      if failed s = true then acknowledge number s 0 a else
      .bind Frames.remaining fun s remaining =>
      if failed s = true then fatal else acknowledge number 0 remaining a
    else acknowledge number 16 0 a
  else if number = 0x32 then
    if c ||| d = 0 then
      -- A control termination is explicitly distinguished from a hardware
      -- exception. Reaping occurs on the next boot-stack scheduler step.
      .bind (Task.terminate a 0x100 b 0 0) fun s id =>
      acknowledge number s id a
    else acknowledge number 16 0 a
  else if number = 0x33 then
    if c ||| d = 0 then
      .bind (Task.create a b) fun s id => acknowledge number s id a
    else acknowledge number 16 0 a
  else acknowledge number 17 0 a

/-- A completed packet stays in the fixed supervisor buffer until the selected
entry reads its scalar fields and resets the retained byte count. -/
def readPacket : Action :=
  .bind (Access.read64 Task.packetLength) fun s count =>
  if failed s = true then fatal else
  if count = 40 then .done 0 Task.packetBase else fatal

def resetPacket : Action := Access.write64 Task.packetLength 0

private def packet : Action :=
  .bind readPacket fun s address =>
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
  .bind resetPacket fun s _ =>
  if failed s = true then fatal else
  if header >>> 8 = 0 then command (header &&& 255) a b c d
  else acknowledge (header &&& 255) 16 0 a

private def pollStep (_i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  if acc = 40 then .done Status.iterationStop acc else
  if 40 < acc then fatal else
  .bind (Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep 0 0 0 0 0 0 0) fun s byte =>
  if s = Status.iterationStop then
    .bind (Access.write8 (Task.packetBase + acc) byte) fun s _ =>
    if failed s = true then fatal else .done 0 (acc + 1)
  else if s = 0 then .done Status.iterationStop acc else fatal

/-- At most forty nonblocking polls per scheduling return. A short packet is
retained in supervisor storage; it cannot strand runnable tasks waiting on UART. -/
def pollBytes : Action :=
  .bind (Access.read64 Task.packetLength) fun s count =>
  if failed s = true then fatal else
  if 40 < count then fatal else
  .boundedFoldU64 40 pollStep 40 count 0 0 0 0 fun s length =>
  if (if s = 0 then true else if s = Status.iterationStop then true else false) = true then
    .bind (Access.write64 Task.packetLength length) fun s _ =>
    if failed s = true then fatal else
    .done 0 length
  else fatal

def poll : Action :=
  .bind pollBytes fun s length =>
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

end Lemma.Kernel.Development.TasksEntry
