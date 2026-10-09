import Lemma.Kernel.Entry
import Lemma.Kernel.Memory.Batch

/-! Explicit development image. This privileged frame diagnostic transport is
not imported by the normal kernel. It has no finite session-command budget;
every request and UART poll remains bounded. No target policy is host-filled. -/
namespace Lemma.Kernel.Development.FramesEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Platform.LemmaVM.ConsoleDevice

def failed (s : UInt8) : Bool := if s = 0 then false else true
def wordOffsetStatus (offset : UInt64) : UInt8 :=
  if offset < 4096 then
    if 8 ≤ 4096 - offset then
      if offset % 8 = 0 then 0 else 8
    else 7
  else 7
def frameWord (write owner handle offset value : UInt64) : Action :=
  let status := wordOffsetStatus offset
  if status = 0 then
    .bind (Frames.resolve owner handle) fun s frame =>
    if s = 0 then
      if write = 0 then Access.read64 (frame + offset)
      else Access.write64 (frame + offset) value
    else .done s 0
  else .done status 0

def operation (command a b c d : UInt64) : Action :=
  if command = 0 then Frames.remaining
  else if command = 1 then Frames.allocate a b
  else if command = 2 then Frames.release a b
  else if command = 3 then frameWord 0 a b c 0
  else if command = 4 then frameWord 1 a b c d
  else if command = 5 then Frames.resolve a b
  else if command = 6 then Frames.ownedCount a
  -- Compiler-authority probes exist only in this development configuration.
  else if command = 8 then Access.read64 a
  else if command = 9 then Access.write64 a b
  else if command = 10 then Batch.allocate a b c
  else .done 17 0

def reply (command a b c d : UInt64) : Action :=
  .bind (operation command a b c d) fun status value =>
  .bind Frames.remaining fun s remaining =>
  if s = 0 then
    .bind (Lemma.Kernel.Console.record 0xb0 command status.toUInt64 value remaining) fun s _ =>
    if s = 0 then .done 0 0 else .done s 0
  else .done s 0

private def zeroHeaderStep (i _count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind receiveByte fun s byte =>
  if s = 0 then .done 0 (acc ||| (byte <<< (i.toUInt64 * 8))) else .done s 0

def fields (command : UInt64) : Action :=
  .boundedFoldU64 7 zeroHeaderStep 7 0 0 0 0 0 fun s reserved =>
  if failed s = true then .done 15 0 else
  if reserved = 0 then
    .bind Lemma.Kernel.Console.readWord fun s a =>
    if failed s = true then .done 15 0 else
    .bind Lemma.Kernel.Console.readWord fun s b =>
    if failed s = true then .done 15 0 else
    .bind Lemma.Kernel.Console.readWord fun s c =>
    if failed s = true then .done 15 0 else
    .bind Lemma.Kernel.Console.readWord fun s d =>
    if failed s = true then .done 15 0 else reply command a b c d
  else .done 14 0

def step : Action :=
  .bind receiveByte fun s command =>
  if s = 0 then fields command
  else if s = 12 then .done 0 0 -- empty poll; continuous idle, not a session timeout
  else .done s 0

def boot : Action :=
  .bind Lemma.Kernel.Entry.boot fun s _ =>
  if s = 0 then .loop step else .done s 0
def dispatch (frame cause value : UInt64) : Action :=
  Lemma.Kernel.Entry.dispatch frame cause value

end Lemma.Kernel.Development.FramesEntry
