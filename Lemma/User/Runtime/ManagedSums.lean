import Lemma.User.Runtime.Arena

/-! `lemma-managed-sums-v1` checked payload access. This additive runtime keeps
the existing31-slot arena and record cookie semantics. Sum cookies occupy a
separate encoding: closed type identity in bits8..23, constructor tag in0..7.
Every access validates the real generational arena reference before payload.
-/
namespace Lemma.User.Runtime.ManagedSums
open Lemma.Core0.Memory
open Lemma.User.Runtime

private def validLayout (typeId tag bytes : UInt64) : Bool :=
  if typeId = 0 then false else if 65536 ≤ typeId then false else
  if 8 ≤ tag then false else if bytes < 16 then false else if 64 < bytes then false else
  bytes % 8 = 0

def allocate (typeId tag bytes : UInt64) : Action :=
  if validLayout typeId tag bytes then
  .bind Arena.ensure fun s _ => if s = 0 then
  .bind (Arena.newBytes bytes) fun s handle => if s = 0 then
  .bind (Arena.bytesWriteWord handle 0 ((typeId <<< 8) ||| tag)) fun s _ =>
  if s = 0 then .done 0 handle else
  .bind (Arena.release handle) fun _ _ => .done s 0
  else .done s 0 else .done s 0 else .done Arena.invalid 0

/-- The tag observation is bounded by the actual source constructor catalog.
It never accepts an untyped reference or a legacy record's cookie. -/
def constructorTag (handle typeId count lengths : UInt64) : Action :=
  if typeId = 0 then .done Arena.invalid 0 else if 65536 ≤ typeId then .done Arena.invalid 0 else
  if count < 2 then .done Arena.invalid 0 else if 8 < count then .done Arena.invalid 0 else
  if lengths >>> (count * 4) = 0 then
  .bind (Arena.bytesLength handle) fun s bytes => if s = 0 then
  if bytes < 16 then .done Arena.invalid 0 else if 64 < bytes then .done Arena.invalid 0 else
  if bytes % 8 = 0 then
  .bind (Arena.bytesReadWord handle 0) fun s cookie => if s = 0 then
  if cookie >>> 8 = typeId then
  let tag := cookie &&& 255
  if tag < count then
  if ((lengths >>> (tag * 4)) &&& 15) * 8 = bytes then .done 0 tag else .done Arena.invalid 0
  else .done Arena.invalid 0
  else .done Arena.invalid 0 else .done s 0 else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0

def readField (handle typeId tag bytes offset : UInt64) : Action :=
  if validLayout typeId tag bytes then
  if offset < 8 then .done Arena.invalid 0 else if bytes - 8 < offset then .done Arena.invalid 0 else
  if offset % 8 = 0 then
  .bind (Arena.bytesLength handle) fun s actualBytes => if s = 0 then
  if actualBytes = bytes then
  .bind (Arena.bytesReadWord handle 0) fun s cookie => if s = 0 then
  if cookie = ((typeId <<< 8) ||| tag) then Arena.bytesReadWord handle offset
  else .done Arena.invalid 0 else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done Arena.invalid 0 else .done Arena.invalid 0

def writeField (handle typeId tag bytes offset value : UInt64) : Action :=
  .bind (readField handle typeId tag bytes offset) fun s _ =>
  if s = 0 then Arena.bytesWriteWord handle offset value else .done s 0

end Lemma.User.Runtime.ManagedSums
