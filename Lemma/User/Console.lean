import Lemma.User.Memory
import Lemma.User.Syscall

/-! Bounded binary control records over the ordinary console syscall. The
serializer is compiled in each user ELF. Its scratch page is private to the
calling address space; the kernel receives bytes, not a privileged record API.
-/
namespace Lemma.User.Console
open Lemma.Core0.Memory

def packetAddress : UInt64 := 0x20200
def failure : UInt8 := 95
def digit (n : UInt64) : UInt64 := if n < 10 then n + 48 else n + 87

private def hexStep (i _ : UInt32) (acc address word _ _ : UInt64) : Action :=
  .bind (Memory.write8 (address + i.toUInt64)
    (digit ((word >>> (60 - i.toUInt64 * 4)) &&& 15))) fun s _ =>
  .done s (acc + 1)

private def word (address value : UInt64) : Action :=
  .bind (Memory.write8 address 32) fun s _ =>
  if s = 0 then
    .boundedFoldU64 16 hexStep 16 0 (address + 1) value 0 0 fun s count =>
    if s = 0 then if count = 16 then .done 0 0 else .done failure count
    else .done s 0
  else .done s 0

def prepareRecord (tag a b c d : UInt64) : Action :=
  .bind (Memory.write8 packetAddress 75) fun s _ => if s = 0 then
  .bind (Memory.write8 (packetAddress + 1) 49) fun s _ => if s = 0 then
  .bind (word (packetAddress + 2) tag) fun s _ => if s = 0 then
  .bind (word (packetAddress + 19) a) fun s _ => if s = 0 then
  .bind (word (packetAddress + 36) b) fun s _ => if s = 0 then
  .bind (word (packetAddress + 53) c) fun s _ => if s = 0 then
  .bind (word (packetAddress + 70) d) fun s _ => if s = 0 then
  .bind (Memory.write8 (packetAddress + 87) 10) fun s _ => if s = 0 then
  .done 0 88
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

def record (tag a b c d : UInt64) : Action :=
  .bind (prepareRecord tag a b c d) fun s length =>
  if s = 0 then
    .bind (Syscall.consoleWrite packetAddress length) fun s count =>
    if s = 0 then if count = 88 then .done 0 0 else .done failure count
    else .done s 0
  else .done s 0

end Lemma.User.Console
