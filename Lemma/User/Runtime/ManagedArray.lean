import Lemma.User.Runtime.Arena

/-! The bounded ordinary Array UInt64 runtime. Arrays own scalar-box roots;
the old scalar/bytes Arena remains the slot allocator, never the graph collector.
Only this module's typed release may consume an array graph root. -/
namespace Lemma.User.Runtime.ManagedArray
open Lemma.Core0.Memory Lemma.User.Runtime Lemma.User

def maximum : UInt64 := 6
def cookie : UInt64 := 0x31595252414d4c

def natural (value : UInt64) : Action :=
  if maximum < value then .done Arena.invalid 0 else .done 0 value

private def address (handle : UInt64) : UInt64 :=
  Arena.page + 128 + (handle &&& 31) * 128

/-- Cleanup has the same cancellation-independent authority as Arena.release.
Every header field relevant to an object access is checked before returning its
address; source values never supply raw addresses to this helper. -/
private def rawObject (handle tag length : UInt64) : Action :=
  .bind (Memory.read64 Arena.control) fun s phase => if s = 0 then
  if phase = 1 then
  .bind (Memory.read64 Arena.page) fun s magic => if s = 0 then
  if magic = 0x31414e4552414d4c then
  .bind (Memory.read64 (Arena.page + 8)) fun s version => if s = 0 then
  if version = 1 then
  .bind (Memory.read64 (Arena.control + 16)) fun s count => if s = 0 then
  if count = 0 then .done Arena.lifetime 0 else
  if Arena.capacity < count then .done Arena.lifetime 0 else
  let slot := handle &&& 31
  let generation := handle >>> 5
  if generation = 0 then .done Arena.invalid 0 else
  if Arena.maximumGeneration < generation then .done Arena.invalid 0 else
  if Arena.capacity ≤ slot then .done Arena.invalid 0 else
  let location := address handle
  .bind (Memory.read64 location) fun s state => if s = 0 then
  if state = 1 then
  .bind (Memory.read64 (location + 8)) fun s actualGeneration => if s = 0 then
  if actualGeneration = generation then
  .bind (Memory.read64 (location + 16)) fun s references => if s = 0 then
  if references = 0 then .done Arena.lifetime 0 else
  if 65535 < references then .done Arena.lifetime 0 else
  .bind (Memory.read64 (location + 24)) fun s actualTag => if s = 0 then
  .bind (Memory.read64 (location + 32)) fun s actualLength => if s = 0 then
  if actualTag = tag then if actualLength = length then .done 0 location
  else .done Arena.invalid 0 else .done Arena.invalid 0
  else .done s 0 else .done s 0 else .done s 0 else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done s 0
  else .done Arena.lifetime 0 else .done s 0
  else .done Arena.lifetime 0 else .done s 0
  else .done Arena.lifetime 0 else .done s 0

private def rawSize (handle : UInt64) : Action :=
  .bind (rawObject handle Arena.bytesTag 64) fun s location => if s = 0 then
  .bind (Memory.read64 (location + 64)) fun s actualCookie => if s = 0 then
  if actualCookie = cookie then
  .bind (Memory.read64 (location + 72)) fun s length => if s = 0 then
  if length ≤ maximum then .done 0 length else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0 else .done s 0 else .done s 0

private def validateChildStep (i _ : UInt32) (acc handle length _ _ : UInt64) : Action :=
  if i.toUInt64 < length then
  .bind (Memory.read64 (address handle + 80 + i.toUInt64 * 8)) fun s child => if s = 0 then
  .bind (rawObject child Arena.boxTag 8) fun s _ => .done s acc
  else .done s 0 else .done 0 acc

private def releaseChildStep (i _ : UInt32) (first handle length _ _ : UInt64) : Action :=
  if i.toUInt64 < length then
  .bind (Memory.read64 (address handle + 80 + i.toUInt64 * 8)) fun s child =>
  if s = 0 then
    .bind (Arena.release child) fun s _ =>
      .done 0 (if first = 0 then s.toUInt64 else first)
  else .done 0 (if first = 0 then s.toUInt64 else first)
  else .done 0 first

/-- Shared graph roots decrement only the parent. Final roots preflight every
child, release every boxed element, then let the allocator clear and regenerate
the parent slot. No scalar value can be confused with a child object handle. -/
def release (handle : UInt64) : Action :=
  .bind (rawSize handle) fun s length => if s = 0 then
  .bind (Memory.read64 (address handle + 16)) fun s references => if s = 0 then
  if 1 < references then Arena.release handle else
  .boundedFoldU64 6 validateChildStep 6 0 handle length 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 6 releaseChildStep 6 0 handle length 0 0 fun s first => if s = 0 then
  if first = 0 then Arena.release handle else .done first.toUInt8 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def allocate : Action :=
  .bind Arena.ensure fun s _ => if s = 0 then
  .bind (Arena.newBytes 64) fun s handle => if s = 0 then
  .bind (Arena.bytesWriteWord handle 0 cookie) fun s _ =>
  if s = 0 then .done 0 handle else
    .bind (Arena.release handle) fun _ _ => .done s 0
  else .done s 0 else .done s 0

def emptyWithCapacity (capacity : UInt64) : Action :=
  if maximum < capacity then .done Arena.invalid 0 else allocate

def box (value : UInt64) : Action :=
  .bind Arena.ensure fun s _ => if s = 0 then Arena.newBox value else .done s 0

def unbox (handle : UInt64) : Action := Arena.boxGet handle

def size (handle : UInt64) : Action :=
  .bind (Arena.bytesLength handle) fun s bytes => if s = 0 then
  if bytes = 64 then rawSize handle else .done Arena.invalid 0 else .done s 0

/-- This is the selected controlled-panic boundary: a failed ordinary get!
produces status236 and never an apparently successful mathematical default. -/
def getBorrowed (handle index : UInt64) : Action :=
  .bind (size handle) fun s length => if s = 0 then
  if index < length then
  .bind (Arena.bytesReadWord handle (16 + index * 8)) fun s child => if s = 0 then
  .bind (Arena.boxGet child) fun s _ => if s = 0 then .done 0 child else .done s 0
  else .done s 0 else .done Arena.invalid 0 else .done s 0

def retain (handle : UInt64) : Action :=
  .bind (size handle) fun s _ => if s = 0 then Arena.retain handle else .done s 0

private def cleanup (status : UInt8) (source output element transferred : UInt64) : Action :=
  .bind (release output) fun _ _ =>
  .bind (release source) fun _ _ =>
  if transferred = 0 then .bind (Arena.release element) fun _ _ => .done status 0
  else .done status 0

private def copyStep (i _ : UInt32) (transferred source output index element : UInt64) : Action :=
  let location := i.toUInt64
  if location = index then
    .bind (Arena.bytesWriteWord output (16 + location * 8) element) fun s _ => if s = 0 then
    .bind (Arena.bytesWriteWord output 8 (location + 1)) fun s _ =>
      .done s (if s = 0 then 1 else transferred)
    else .done s transferred
  else
    .bind (getBorrowed source location) fun s child => if s = 0 then
    .bind (Arena.retain child) fun s _ => if s = 0 then
    .bind (Arena.bytesWriteWord output (16 + location * 8) child) fun s _ => if s = 0 then
    .bind (Arena.bytesWriteWord output 8 (location + 1)) fun s _ =>
    if s = 0 then .done 0 transferred else
      .bind (Arena.release child) fun _ _ => .done s transferred
    else .bind (Arena.release child) fun _ _ => .done s transferred
    else .done s transferred else .done s transferred

/-- A valid update allocates a distinct parent and actually retains its copied
boxed children. The new element transfers its one reference to the new parent.
One old parent reference is consumed only after constructing the complete copy.
Resource/cancellation failures attempt all unpublished/owned cleanup. A memory
fault can defeat rollback and is preserved as failure, never verified evidence. -/
private def changed (handle index element length : UInt64) : Action :=
  .bind allocate fun s output => if s = 0 then
  .boundedFoldU64 6 copyStep length.toUInt32 0 handle output index element fun s transferred =>
  if s = 0 then
    .bind (release handle) fun s _ => if s = 0 then .done 0 output else
      .bind (release output) fun _ _ => .done s 0
  else cleanup s handle output element transferred
  else .bind (release handle) fun _ _ =>
    .bind (Arena.release element) fun _ _ => .done s 0

private def rejectInputs (status : UInt8) (handle element : UInt64) : Action :=
  .bind (release handle) fun _ _ =>
  .bind (Arena.release element) fun _ _ => .done status 0

def push (handle element : UInt64) : Action :=
  .bind (size handle) fun s length => if s = 0 then
  .bind (Arena.boxGet element) fun s _ => if s = 0 then
  if length = maximum then rejectInputs Arena.exhausted handle element
  else changed handle length element (length + 1)
  else rejectInputs s handle element else rejectInputs s handle element

/-- Both upstream array ! externs invoke panic outside their bounds. This
freestanding profile selects controlled-panic236: consume the owned source
root and replacement box, preserve other aliases, and publish no result. -/
def set (handle index element : UInt64) : Action :=
  .bind (size handle) fun s length => if s = 0 then
  .bind (Arena.boxGet element) fun s _ => if s = 0 then
  if index < length then changed handle index element length
  else rejectInputs Arena.invalid handle element
  else rejectInputs s handle element else rejectInputs s handle element

end Lemma.User.Runtime.ManagedArray
