import Lemma.Courses.PackageTarget
import Lemma.Services.Store.Client

/-! Dynamic package loading through the existing guest Store endpoint.
The caller owns a dedicated staging buffer and an80-byte context: endpoint0,
outgoing8(192 bytes), incoming16(256 bytes), namespace24, package identity32,
edition40, staging48, capacity56, first request ID64; word72 is reserved zero.
All spans must be disjoint. Failure leaves only unpublished staging bytes; the
caller keeps its active package/document intact. No host journal parser is used.
This module does not install packages or enforce Store immutability by itself. -/
namespace Lemma.Courses.PackageStore
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat
open Lemma.Services.Store

private def field (context offset : UInt64) : Action := Lemma.User.Memory.read64 (context + offset)
private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def separate (a n b m : UInt64) : UInt64 :=
  if a + n ≤ b then 1 else if b + m ≤ a then 1 else 0

private def contextValid (context outgoing incoming target capacity : UInt64) : UInt64 :=
  if (context ||| outgoing ||| incoming ||| target) &&& 7 = 0 then
  if context ≤ 0xffffffffffffffff - 80 then
  if outgoing ≤ 0xffffffffffffffff - 192 then
  if incoming ≤ 0xffffffffffffffff - 256 then
  if target ≤ 0xffffffffffffffff - capacity then
  if separate context 80 outgoing 192 = 1 then
  if separate context 80 incoming 256 = 1 then
  if separate context 80 target capacity = 1 then
  if separate outgoing 192 incoming 256 = 1 then
  if separate outgoing 192 target capacity = 1 then
  if separate incoming 256 target capacity = 1 then 1 else 0
  else 0 else 0 else 0 else 0 else 0 else 0 else 0 else 0 else 0 else 0

private def readPiece (context offset count requestOffset : UInt64) : Action :=
  .bind (field context 0) fun s endpoint => if s = 0 then
  .bind (field context 8) fun s outgoing => if s = 0 then
  .bind (field context 16) fun s incoming => if s = 0 then
  .bind (field context 24) fun s ns => if s = 0 then
  .bind (field context 32) fun s identity => if s = 0 then
  .bind (field context 40) fun s edition => if s = 0 then
  .bind (field context 48) fun s target => if s = 0 then
  .bind (field context 64) fun s request => if s = 0 then
  .bind (Client.call endpoint outgoing incoming 5 ns (object identity edition) 0 offset count 0 (request + requestOffset))
    fun s _ => if s = 0 then
  .bind (Client.responseField incoming 56) fun s actualCount => if s = 0 then
  if actualCount = count then
  .bind (Format.copy (Client.responseData incoming) (target + offset) count) fun s _ => .done s count
  else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def readStep (i _ : UInt32) (copied context length _ _ : UInt64) : Action :=
  let offset := (i.toUInt64 + 1) * 128
  let count := minimum 128 (length - offset)
  .bind (readPiece context offset count (i.toUInt64 + 1)) fun s bytes =>
  if s = 0 then .done 0 (copied + bytes) else .done s 0

/-- Retrieve actual object bytes by bounded copied IPC, check the complete
canonical package, and require the exact requested identity/edition. Success
means a validated read, never a new Saved acknowledgement. The caller publishes
a resident selection only after this Action succeeds. -/
def load (context : UInt64) : Action :=
  if context % 8 = 0 then if context ≤ 0xffffffffffffffff - 80 then
  .bind (field context 8) fun s outgoing => if s = 0 then
  .bind (field context 16) fun s incoming => if s = 0 then
  .bind (field context 24) fun s ns => if s = 0 then
  .bind (field context 32) fun s identity => if s = 0 then
  .bind (field context 40) fun s edition => if s = 0 then
  .bind (field context 48) fun s target => if s = 0 then
  .bind (field context 56) fun s capacity => if s = 0 then
  .bind (field context 64) fun s request => if s = 0 then
  .bind (field context 72) fun s reserved => if s = 0 then
  if reserved = 0 then if Protocol.namespaceValid ns = 1 then
  if identity = 0 then .done malformed 0 else if maximumIdentity < identity then .done malformed 0 else
  if edition = 0 then .done malformed 0 else if maximumEdition < edition then .done malformed 0 else
  if capacity < headerBytes then .done resourceLimit 0 else if maximumBytes < capacity then .done resourceLimit 0 else
  if request = 0 then .done malformed 0 else if Format.maximumSequence - 256 < request then .done resourceLimit 0 else
  if contextValid context outgoing incoming target capacity = 1 then
  .bind (readPiece context 0 128 0) fun s copied => if s = 0 then
  .bind (Lemma.User.Memory.read64 (target + 16)) fun s length => if s = 0 then
  if length < headerBytes then .done malformed 0 else if capacity < length then .done resourceLimit 0 else
  .boundedFoldU64 255 readStep ((length - 128 + 127) / 128).toUInt32 copied context length 0 0 fun s actual => if s = 0 then
  if actual = length then
  .bind (PackageTarget.validate target length) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.read64 (target + 24)) fun s actualIdentity => if s = 0 then
  .bind (Lemma.User.Memory.read64 (target + 32)) fun s actualEdition => if s = 0 then
  if actualIdentity = identity then if actualEdition = edition then .done 0 length else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0

end Lemma.Courses.PackageStore
