import Lemma.User.Runtime.Arena

/-! Bounded ordinary ByteArray runtime for the additive User-v0.4 bridge.
Real process-owned Arena allocation, lifetime and reference counts are authoritative. -/
namespace Lemma.User.Runtime.ManagedBytes
open Lemma.Core0.Memory Lemma.User.Runtime

def maximum : UInt64 := 48
def cookie : UInt64 := 0x3159544252414d4c

/-- Only small scalar Naturals are admitted by this version. No bignum helper
or hidden boxed Nat runtime is substituted for upstream IR. -/
def natural (value : UInt64) : Action :=
  if maximum < value then .done Arena.invalid 0 else .done 0 value

private def allocate (length : UInt64) : Action :=
  if maximum < length then .done Arena.invalid 0 else
  .bind Arena.ensure fun s _ => if s = 0 then
  .bind (Arena.newBytes 64) fun s handle => if s = 0 then
  .bind (Arena.bytesWriteWord handle 0 cookie) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 8 length) fun s _ =>
  if s = 0 then .done 0 handle else
  .bind (Arena.release handle) fun _ _ => .done s 0
  else .bind (Arena.release handle) fun _ _ => .done s 0
  else .done s 0 else .done s 0

def emptyWithCapacity (capacity : UInt64) : Action :=
  if maximum < capacity then .done Arena.invalid 0 else allocate 0

/-- Full object layout validation precedes every byte observation. -/
def size (handle : UInt64) : Action :=
  .bind (Arena.bytesLength handle) fun s bytes => if s = 0 then
  if bytes = 64 then
  .bind (Arena.bytesReadWord handle 0) fun s actualCookie => if s = 0 then
  if actualCookie = cookie then
  .bind (Arena.bytesReadWord handle 8) fun s length => if s = 0 then
  if length ≤ maximum then .done 0 length else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done Arena.invalid 0 else .done s 0

def get (handle index : UInt64) : Action :=
  .bind (size handle) fun s length => if s = 0 then
  if index < length then Arena.bytesGet handle (16 + index)
  else .done Arena.invalid 0 else .done s 0

private def copyStep (i _ : UInt32) (acc source target length _ : UInt64) : Action :=
  if i.toUInt64 < length then
  .bind (Arena.bytesGet source (16 + i.toUInt64)) fun s byte => if s = 0 then
  .bind (Arena.bytesSet target (16 + i.toUInt64) byte) fun s _ => .done s acc
  else .done s 0 else .done 0 acc

/-- Copy-on-write always creates a distinct generational object, then consumes
one source reference. This avoids changing any aliased source, even if shared.
The fixed 48-byte payload and at most one new slot bound allocation/copy work.
On failure, owned input and any unpublished output are reclaimed. -/
private def changed (handle index byte copyLength length : UInt64) : Action :=
  .bind (allocate length) fun s output => if s = 0 then
  .boundedFoldU64 48 copyStep 48 0 handle output copyLength 0 fun s _ => if s = 0 then
  .bind (Arena.bytesSet output (16 + index) byte) fun s _ => if s = 0 then
  .bind (Arena.release handle) fun s _ =>
  if s = 0 then .done 0 output else
  .bind (Arena.release output) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ =>
    .bind (Arena.release handle) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ =>
    .bind (Arena.release handle) fun _ _ => .done s 0
  else .bind (Arena.release handle) fun _ _ => .done s 0

def push (handle byte : UInt64) : Action :=
  .bind (size handle) fun s length => if s = 0 then
  if 255 < byte then .bind (Arena.release handle) fun _ _ => .done Arena.invalid 0 else
  if length = maximum then .bind (Arena.release handle) fun _ _ => .done Arena.exhausted 0 else
  changed handle length byte length (length + 1)
  else .bind (Arena.release handle) fun _ _ => .done s 0

/-- Upstream set! leaves an out-of-bounds array unchanged. An admitted index48
can exercise that behavior; unsupported larger Nat values are rejected earlier. -/
def set (handle index byte : UInt64) : Action :=
  .bind (size handle) fun s length => if s = 0 then
  if 255 < byte then .bind (Arena.release handle) fun _ _ => .done Arena.invalid 0 else
  if index < length then changed handle index byte length length else .done 0 handle
  else .bind (Arena.release handle) fun _ _ => .done s 0

def retain (handle : UInt64) : Action :=
  .bind (size handle) fun s _ => if s = 0 then Arena.retain handle else .done s 0

end Lemma.User.Runtime.ManagedBytes
