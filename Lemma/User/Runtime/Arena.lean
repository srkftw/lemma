import Lemma.User.Memory
import Lemma.User.Syscall

/-! Bounded owned-page object runtime foundation. The additive managed-records
bridge uses real generational slots for checked ordinary scalar structures.
General inductives, closures and a general managed heap remain unsupported. -/
namespace Lemma.User.Runtime.Arena
open Lemma.Core0.Memory
open Lemma.User

def control : UInt64 := 0x20e00
def page : UInt64 := 0x400000
def capacity : UInt64 := 31
def maximumGeneration : UInt64 := 0x07ffffffffffffff
def boxTag : UInt64 := 1
def bytesTag : UInt64 := 2
def invalid : UInt8 := 236
def exhausted : UInt8 := 237
def cancelled : UInt8 := 238
def lifetime : UInt8 := 239

private def slotAddress (slot : UInt64) : UInt64 := page + 128 + slot * 128

private def initStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (slotAddress i.toUInt64 + 8) 1) fun s _ => .done s acc

private def initializePage : Action :=
  .boundedFoldU64 31 initStep 31 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (Memory.write64 page 0x31414e4552414d4c) fun s _ => if s = 0 then
  .bind (Memory.write64 (page + 8) 1) fun s _ => if s = 0 then
  .bind (Memory.write64 (control + 8) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (control + 16) 0) fun s _ => if s = 0 then
  Memory.write64 control 1 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0

/-- Kernel allocation zeroes and maps a genuinely owned page. A destroyed
arena is terminal in this process, so old generations can never become valid
through a new zeroed page at the same VA. Kernel process death releases it. -/
def create : Action :=
  .bind (Memory.read64 control) fun s phase => if s = 0 then
  if phase = 0 then
  .bind (Syscall.allocatePage page) fun s actual => if s = 0 then
  if actual = page then
  .bind initializePage fun s _ => if s = 0 then .done 0 page else
  .bind (Syscall.releasePage page) fun cleanup _ =>
  if cleanup = 0 then .done s 0 else .done cleanup 0
  else .done lifetime 0 else .done s 0 else .done lifetime 0 else .done s 0

private def live : Action :=
  .bind (Memory.read64 control) fun s phase => if s = 0 then
  if phase = 1 then
  .bind (Memory.read64 page) fun s magic => if s = 0 then
  if magic = 0x31414e4552414d4c then
  .bind (Memory.read64 (page + 8)) fun s version => if s = 0 then
  if version = 1 then .done 0 page else .done lifetime 0 else .done s 0
  else .done lifetime 0 else .done s 0 else .done lifetime 0 else .done s 0

private def ready : Action :=
  .bind live fun s _ => if s = 0 then
  .bind (Memory.read64 (control + 8)) fun s flag => if s = 0 then
  if flag = 0 then .done 0 page else if flag = 1 then .done cancelled 0 else .done lifetime 0 else .done s 0 else .done s 0

/-- Reuse this process's live arena without allocating another owned page. -/
def ensure : Action :=
  .bind (Memory.read64 control) fun s phase => if s = 0 then
  if phase = 0 then create else if phase = 1 then ready else .done lifetime 0 else .done s 0

private def findStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.read64 (slotAddress i.toUInt64)) fun s state => if s = 0 then
  if state = 0 then .done Status.iterationStop i.toUInt64 else
  if state = 1 then .done 0 acc else if state = 2 then .done 0 acc else .done lifetime 0
  else .done s 0

private def zeroPayloadStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (address + 64 + i.toUInt64 * 8) 0) fun s _ => .done s acc

private def allocate (tag length : UInt64) : Action :=
  .bind ready fun s _ => if s = 0 then
  .bind (Memory.read64 (control + 16)) fun s count => if s = 0 then
  if capacity < count then .done lifetime 0 else if capacity = count then .done exhausted 0 else
  .boundedFoldU64 31 findStep 31 0 0 0 0 0 fun s slot =>
  if s = Status.iterationStop then
  let address := slotAddress slot
  .bind (Memory.read64 (address + 8)) fun s generation => if s = 0 then
  if generation = 0 then .done lifetime 0 else if maximumGeneration < generation then .done lifetime 0 else
  .boundedFoldU64 8 zeroPayloadStep 8 0 address 0 0 0 fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 16) 1) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 24) tag) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 32) length) fun s _ => if s = 0 then
  .bind (Memory.write64 address 1) fun s _ => if s = 0 then
  .bind (Memory.write64 (control + 16) (count + 1)) fun s _ =>
  if s = 0 then .done 0 ((generation <<< 5) ||| slot) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else if s = 0 then .done exhausted 0 else .done s 0
  else .done s 0 else .done s 0

/-- Handle validation precedes all payload access. It is process local: the
hardware translation and the owned page supply actual memory isolation. -/
private def resolve (handle tag : UInt64) : Action :=
  .bind live fun s _ => if s = 0 then
  let slot := handle &&& 31
  let generation := handle >>> 5
  if generation = 0 then .done invalid 0 else if capacity ≤ slot then .done invalid 0 else
  let address := slotAddress slot
  .bind (Memory.read64 address) fun s state => if s = 0 then
  if state = 1 then
  .bind (Memory.read64 (address + 8)) fun s actual => if s = 0 then
  if actual = generation then
  .bind (Memory.read64 (address + 16)) fun s references => if s = 0 then
  if references = 0 then .done lifetime 0 else if 65535 < references then .done lifetime 0 else
  .bind (Memory.read64 (address + 24)) fun s actualTag => if s = 0 then
  .bind (Memory.read64 (address + 32)) fun s length => if s = 0 then
  if actualTag = boxTag then if length = 8 then if tag = 0 then .done 0 address else
    if tag = boxTag then .done 0 address else .done invalid 0 else .done lifetime 0
  else if actualTag = bytesTag then if length ≤ 64 then if tag = 0 then .done 0 address else
    if tag = bytesTag then .done 0 address else .done invalid 0 else .done lifetime 0
  else .done lifetime 0
  else .done s 0 else .done s 0 else .done s 0 else .done invalid 0 else .done s 0
  else .done invalid 0 else .done s 0 else .done s 0

def newBox (value : UInt64) : Action :=
  .bind (allocate boxTag 8) fun s handle => if s = 0 then
  .bind (Memory.write64 (slotAddress (handle &&& 31) + 64) value) fun s _ =>
  if s = 0 then .done 0 handle else .done s 0 else .done s 0

def newBytes (length : UInt64) : Action :=
  if 64 < length then .done invalid 0 else allocate bytesTag length

def boxGet (handle : UInt64) : Action :=
  .bind ready fun s _ => if s = 0 then
  .bind (resolve handle boxTag) fun s address => if s = 0 then
  Memory.read64 (address + 64) else .done s 0 else .done s 0

def boxSet (handle value : UInt64) : Action :=
  .bind ready fun s _ => if s = 0 then
  .bind (resolve handle boxTag) fun s address => if s = 0 then
  Memory.write64 (address + 64) value else .done s 0 else .done s 0

private def bytesAddress (handle index : UInt64) : Action :=
  .bind ready fun s _ => if s = 0 then
  .bind (resolve handle bytesTag) fun s address => if s = 0 then
  .bind (Memory.read64 (address + 32)) fun s length => if s = 0 then
  if 64 < length then .done lifetime 0 else if index < length then .done 0 (address + 64 + index)
  else .done invalid 0 else .done s 0 else .done s 0 else .done s 0

def bytesGet (handle index : UInt64) : Action :=
  .bind (bytesAddress handle index) fun s address => if s = 0 then Memory.read8 address else .done s 0

def bytesSet (handle index value : UInt64) : Action :=
  if 255 < value then .done invalid 0 else
  .bind (bytesAddress handle index) fun s address => if s = 0 then Memory.write8 address value else .done s 0

def bytesLength (handle : UInt64) : Action :=
  .bind ready fun s _ => if s = 0 then
  .bind (resolve handle bytesTag) fun s address => if s = 0 then
  .bind (Memory.read64 (address + 32)) fun s length => if s = 0 then
  if 64 < length then .done lifetime 0 else .done 0 length else .done s 0 else .done s 0 else .done s 0

private def wordAddress (handle offset : UInt64) : Action :=
  if offset % 8 = 0 then
  .bind ready fun s _ => if s = 0 then
  .bind (resolve handle bytesTag) fun s address => if s = 0 then
  .bind (Memory.read64 (address + 32)) fun s length => if s = 0 then
  if 64 < length then .done lifetime 0 else if offset ≤ length then
    if 8 ≤ length - offset then .done 0 (address + 64 + offset) else .done invalid 0
  else .done invalid 0 else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0

def bytesReadWord (handle offset : UInt64) : Action :=
  .bind (wordAddress handle offset) fun s address => if s = 0 then Memory.read64 address else .done s 0

def bytesWriteWord (handle offset value : UInt64) : Action :=
  .bind (wordAddress handle offset) fun s address => if s = 0 then Memory.write64 address value else .done s 0

def retain (handle : UInt64) : Action :=
  .bind ready fun s _ => if s = 0 then
  .bind (resolve handle 0) fun s address => if s = 0 then
  .bind (Memory.read64 (address + 16)) fun s references => if s = 0 then
  if references < 65535 then
  .bind (Memory.write64 (address + 16) (references + 1)) fun s _ => .done s handle
  else .done lifetime 0 else .done s 0 else .done s 0 else .done s 0

private def clearStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (address + 16 + i.toUInt64 * 8) 0) fun s _ => .done s acc

/-- Release remains available after cancellation. Final release clears both
payload and object metadata before the slot becomes reusable. -/
def release (handle : UInt64) : Action :=
  .bind (resolve handle 0) fun s address => if s = 0 then
  .bind (Memory.read64 (address + 16)) fun s references => if s = 0 then
  if 1 < references then Memory.write64 (address + 16) (references - 1) else
  .bind (Memory.read64 (address + 8)) fun s generation => if s = 0 then
  .bind (Memory.read64 (control + 16)) fun s count => if s = 0 then
  if count = 0 then .done lifetime 0 else
  .boundedFoldU64 14 clearStep 14 0 address 0 0 0 fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 8) (if generation < maximumGeneration then generation + 1 else generation)) fun s _ => if s = 0 then
  .bind (Memory.write64 address (if generation < maximumGeneration then 0 else 2)) fun s _ => if s = 0 then
  Memory.write64 (control + 16) (count - 1) else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

def cancel : Action :=
  .bind live fun s _ => if s = 0 then Memory.write64 (control + 8) 1 else .done s 0

def destroy : Action :=
  .bind live fun s _ => if s = 0 then
  .bind (Memory.read64 (control + 16)) fun s count => if s = 0 then
  if count = 0 then
  .bind (Syscall.releasePage page) fun s _ => if s = 0 then Memory.write64 control 2 else .done s 0
  else .done lifetime 0 else .done s 0 else .done s 0

end Lemma.User.Runtime.Arena
