import Lemma.User.CapabilityConsole

/-! School wire S1. This is a bounded presentation of already committed guest
bytes, not a document format or an admission acknowledgement. Each write stays
inside the existing 256-byte Console capability limit. -/
namespace Lemma.Courses.SchoolStream
open Lemma.Core0.Memory Lemma.User

def maximumPayload : UInt64 := 96
def packet : UInt64 := Console.packetAddress
private def malformed : UInt8 := 240

private def wordStep (i _ : UInt32) (acc address value _ _ : UInt64) : Action :=
  .bind (Memory.write8 (address+i.toUInt64)
    (Console.digit ((value >>> (60-i.toUInt64*4)) &&& 15))) fun s _ =>
  .done s (acc+1)

private def word (address value : UInt64) : Action :=
  .boundedFoldU64 16 wordStep 16 0 address value 0 0 fun s count =>
  if s = 0 then if count = 16 then .done 0 0 else .done malformed count
  else .done s 0

private def byteStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (Memory.read8 (source+i.toUInt64)) fun s value => if s = 0 then
  .bind (Memory.write8 (target+i.toUInt64*2) (Console.digit (value >>> 4))) fun s _ => if s = 0 then
  .bind (Memory.write8 (target+i.toUInt64*2+1) (Console.digit (value &&& 15))) fun s _ =>
  .done s (acc+1) else .done s acc else .done s acc

/-- Preparation has no UART effects. The header contains the exact queue and
low48-bit offset/high16-bit count, followed by exactly count bytes as hex. -/
def prepare (queue offset source count : UInt64) : Action :=
  if queue >>> 48 = 0x5351 then if 0 < (queue &&& 0x0000ffffffffffff) then
  if offset < 262144 then if 0 < count then if count ≤ maximumPayload then
  if count ≤ 262144-offset then
  .bind (Memory.write8 packet 83) fun s _ => if s = 0 then
  .bind (Memory.write8 (packet+1) 49) fun s _ => if s = 0 then
  .bind (Memory.write8 (packet+2) 32) fun s _ => if s = 0 then
  .bind (word (packet+3) queue) fun s _ => if s = 0 then
  .bind (Memory.write8 (packet+19) 32) fun s _ => if s = 0 then
  .bind (word (packet+20) (offset ||| (count <<< 48))) fun s _ => if s = 0 then
  .bind (Memory.write8 (packet+36) 32) fun s _ => if s = 0 then
  .boundedFoldU64 96 byteStep count.toUInt32 0 source (packet+37) 0 0 fun s copied =>
  if s = 0 then if copied = count then
  .bind (Memory.write8 (packet+37+count*2) 10) fun s _ =>
  if s = 0 then .done 0 (38+count*2) else .done s 0
  else .done malformed copied else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0

def send (console queue offset source count : UInt64) : Action :=
  .bind (prepare queue offset source count) fun s length => if s = 0 then
  .bind (Capability.consoleWrite console packet length) fun s actual =>
  if s = 0 then if actual = length then .done 0 count else .done Console.failure actual
  else .done s actual else .done s 0


private def shiftStartStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.read8 (packet+87-i.toUInt64)) fun s value => if s = 0 then
  .bind (Memory.write8 (packet+88-i.toUInt64) value) fun s _ =>
  .done s (acc+1) else .done s acc

/-- A fresh stream starts on a fresh line even after an irreversible partial
previous write. The boundary and ordinary K1 start share one bounded write.
No partial frame counts as payload; only a later complete start resynchronizes.
-/
def start (console queue sequence total ns : UInt64) : Action :=
  .bind (Console.prepareRecord 0x72e queue sequence total ns) fun s length => if s = 0 then
  if length = 88 then
  .boundedFoldU64 88 shiftStartStep 88 0 0 0 0 0 fun s shifted => if s = 0 then
  if shifted = 88 then
  .bind (Memory.write8 packet 10) fun s _ => if s = 0 then
  .bind (Capability.consoleWrite console packet 89) fun s actual =>
  if s = 0 then if actual = 89 then .done 0 0 else .done Console.failure actual
  else .done s actual else .done s 0
  else .done malformed shifted else .done s 0
  else .done malformed length else .done s 0

end Lemma.Courses.SchoolStream
