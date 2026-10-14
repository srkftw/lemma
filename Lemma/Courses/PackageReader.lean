import Lemma.Courses.PackageTarget
import Lemma.Services.Store.Client

/-! `lemma-course-reader/1`: cooperative, read-only copied Store transactions.
The private128-byte context is endpoint0/outgoing8/incoming16/namespace24/
identity32/edition40/staging48/capacity56/firstRequest64/phase72/pending80/
copied88/length96/requested104/nextRequest112/error120. Packet spans and staging
are disjoint from each other/context. Configuration words0..64 and all spans
remain owned and unchanged for this reader lifetime; only these routines mutate
the state words. Staging cannot be the notebook's active package/document.

Phase0 is ready for one request,1 pending,2 complete raw bytes,3 validated,
4 failed,5 canceled. Each step issues one READ or polls one existing READ and
copies at most128 bytes; it never sleeps or waits. Each of at most256 READs has
the existing30-second IPC ceiling. The caller additionally owns the workflow
deadline and calls cancel when leaving/canceling the reader. No retry occurs.
Full validation is a separate bounded Action: it is not an incremental parser
or a measured responsiveness claim. Success is a read, never Installed/Saved.
Guest context faults terminate with their actual status; the caller discards
the reader and must not infer publication from partially written state. -/
namespace Lemma.Courses.PackageReader
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat
open Lemma.Services.Store
open Lemma.User

def contextBytes : UInt64 := 128
def maximumRequests : UInt64 := 256

private def field (context offset : UInt64) : Action := Memory.read64 (context + offset)
private def put (context offset value : UInt64) : Action := Memory.write64 (context + offset) value
private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def separate (a n b m : UInt64) : UInt64 :=
  if a + n ≤ b then 1 else if b + m ≤ a then 1 else 0

private def spans (context outgoing incoming staging capacity : UInt64) : UInt64 :=
  if (context ||| outgoing ||| incoming ||| staging) &&& 7 = 0 then
  if context ≤ 0xffffffffffffffff - contextBytes then
  if outgoing ≤ 0xffffffffffffffff - 192 then
  if incoming ≤ 0xffffffffffffffff - 256 then
  if staging ≤ 0xffffffffffffffff - capacity then
  if separate context contextBytes outgoing 192 = 1 then
  if separate context contextBytes incoming 256 = 1 then
  if separate context contextBytes staging capacity = 1 then
  if separate outgoing 192 incoming 256 = 1 then
  if separate outgoing 192 staging capacity = 1 then
  if separate incoming 256 staging capacity = 1 then 1 else 0
  else 0 else 0 else 0 else 0 else 0 else 0 else 0 else 0 else 0 else 0

private def configuration (context : UInt64) : Action :=
  if context % 8 = 0 then if context ≤ 0xffffffffffffffff - contextBytes then
  .bind (field context 8) fun s outgoing => if s = 0 then
  .bind (field context 16) fun s incoming => if s = 0 then
  .bind (field context 24) fun s ns => if s = 0 then
  .bind (field context 32) fun s identity => if s = 0 then
  .bind (field context 40) fun s edition => if s = 0 then
  .bind (field context 48) fun s staging => if s = 0 then
  .bind (field context 56) fun s capacity => if s = 0 then
  .bind (field context 64) fun s first => if s = 0 then
  if Protocol.namespaceValid ns = 1 then
  if identity = 0 then .done malformed 0 else if maximumIdentity < identity then .done malformed 0 else
  if edition = 0 then .done malformed 0 else if maximumEdition < edition then .done malformed 0 else
  if capacity < headerBytes then .done resourceLimit 0 else if maximumBytes < capacity then .done resourceLimit 0 else
  if first = 0 then .done malformed 0 else if Format.maximumSequence - maximumRequests < first then .done resourceLimit 0 else
  if spans context outgoing incoming staging capacity = 1 then .done 0 capacity else .done malformed 0
  else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0

private def stop (context status phase : UInt64) : Action :=
  .bind (put context 120 status) fun s _ => if s = 0 then
  .bind (put context 72 phase) fun s _ => if s = 0 then .done status.toUInt8 0 else .done s 0
  else .done s 0

private def clearStep (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (put context (72 + i.toUInt64 * 8) 0) fun s _ => .done s acc

/-- Reuse only a reader without a pending transaction. This does not clear
staging or touch an active selection. Fresh allocated contexts start zero. -/
def start (context : UInt64) : Action :=
  .bind (configuration context) fun s _ => if s = 0 then
  .bind (field context 72) fun s phase => if s = 0 then
  .bind (field context 80) fun s pending => if s = 0 then
  if phase ≤ 5 then if pending = 0 then
  .boundedFoldU64 7 clearStep 7 0 context 0 0 0 fun s _ => if s = 0 then
  .bind (field context 64) fun s first => if s = 0 then put context 112 first else .done s 0
  else .done s 0
  else .done Protocol.busy 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0

private def issue (context count copied request : UInt64) : Action :=
  .bind (field context 0) fun s endpoint => if s = 0 then
  .bind (field context 8) fun s outgoing => if s = 0 then
  .bind (field context 24) fun s ns => if s = 0 then
  .bind (field context 32) fun s identity => if s = 0 then
  .bind (field context 40) fun s edition => if s = 0 then
  .bind (Client.beginCall endpoint outgoing 5 ns (object identity edition) 0 copied count 0 request) fun s pending => if s = 0 then
  if pending = 0 then stop context IPCABI.invalidTransaction.toUInt64 4 else
  .bind (put context 80 pending) fun s _ => if s = 0 then
  .bind (put context 104 count) fun s _ => if s = 0 then put context 72 1 else .done s 0
  else .done s 0
  else stop context s.toUInt64 4
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def beginPiece (context : UInt64) : Action :=
  .bind (field context 80) fun s pending => if s = 0 then
  .bind (field context 88) fun s copied => if s = 0 then
  .bind (field context 96) fun s length => if s = 0 then
  .bind (field context 104) fun s oldCount => if s = 0 then
  .bind (field context 112) fun s request => if s = 0 then
  .bind (field context 64) fun s first => if s = 0 then
  if pending ||| oldCount = 0 then
  if first ≤ request then if request < first + maximumRequests then
  if copied = 0 then if length = 0 then if request = first then issue context 128 0 request
    else stop context malformed.toUInt64 4 else stop context malformed.toUInt64 4
  else if copied % 128 = 0 then if headerBytes ≤ length then if length ≤ maximumBytes then if copied < length then
    if request = first + copied / 128 then issue context (minimum 128 (length - copied)) copied request
    else stop context malformed.toUInt64 4
    else stop context malformed.toUInt64 4 else stop context resourceLimit.toUInt64 4 else stop context malformed.toUInt64 4
    else stop context malformed.toUInt64 4
  else stop context resourceLimit.toUInt64 4 else stop context malformed.toUInt64 4
  else stop context malformed.toUInt64 4
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def accept (context copied count length request incoming staging : UInt64) : Action :=
  .bind (Format.copy (Client.responseData incoming) (staging + copied) count) fun s _ => if s = 0 then
  .bind (if copied = 0 then Memory.read64 (staging + 16) else .done 0 length) fun s total => if s = 0 then
  .bind (field context 56) fun s capacity => if s = 0 then
  if total < headerBytes then stop context malformed.toUInt64 4 else
  if capacity < total then stop context resourceLimit.toUInt64 4 else
  if total < copied + count then stop context malformed.toUInt64 4 else
  .bind (put context 96 total) fun s _ => if s = 0 then
  .bind (put context 88 (copied + count)) fun s _ => if s = 0 then
  .bind (put context 104 0) fun s _ => if s = 0 then
  .bind (put context 112 (request + 1)) fun s _ => if s = 0 then
  .bind (put context 72 (if copied + count = total then 2 else 0)) fun s _ =>
    if s = 0 then .done 0 (copied + count) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else stop context s.toUInt64 4 else stop context s.toUInt64 4 else stop context s.toUInt64 4

private def pollPiece (context : UInt64) : Action :=
  .bind (field context 80) fun s pending => if s = 0 then
  .bind (field context 16) fun s incoming => if s = 0 then
  .bind (field context 24) fun s ns => if s = 0 then
  .bind (field context 32) fun s identity => if s = 0 then
  .bind (field context 40) fun s edition => if s = 0 then
  .bind (field context 48) fun s staging => if s = 0 then
  .bind (field context 88) fun s copied => if s = 0 then
  .bind (field context 96) fun s length => if s = 0 then
  .bind (field context 104) fun s count => if s = 0 then
  .bind (field context 112) fun s request => if s = 0 then
  if pending = 0 then stop context malformed.toUInt64 4 else
  if count = 0 then stop context malformed.toUInt64 4 else if 128 < count then stop context malformed.toUInt64 4 else
  if copied ≤ maximumBytes then if count ≤ maximumBytes - copied then
  .bind (Client.pollCall pending incoming 5 ns (object identity edition) request count) fun s _ =>
  if s = IPCABI.wouldBlock then .done s 0 else
  .bind (put context 80 0) fun cleared _ => if cleared = 0 then
  if s = 0 then
    .bind (Client.responseField incoming 56) fun s actual => if s = 0 then
    if actual = count then accept context copied count length request incoming staging
    else stop context malformed.toUInt64 4 else stop context s.toUInt64 4
  else stop context s.toUInt64 4
  else .done cleared 0
  else stop context resourceLimit.toUInt64 4 else stop context resourceLimit.toUInt64 4
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- One nonblocking phase. Raw completion returns its length but has phase2,
so no caller may publish it as a validated selection. -/
def step (context : UInt64) : Action :=
  .bind (configuration context) fun s _ => if s = 0 then
  .bind (field context 72) fun s phase => if s = 0 then
  if phase = 0 then beginPiece context else if phase = 1 then pollPiece context
  else if phase = 2 then field context 96 else if phase = 3 then field context 96
  else if phase = 4 then .bind (field context 120) fun s error => if s = 0 then .done error.toUInt8 0 else .done s 0
  else if phase = 5 then .done IPCABI.canceled 0 else .done malformed 0
  else .done s 0 else .done s 0

/-- Full canonical decoder/integrity/domain validation before publication.
The complete staging buffer remains immutable after success until discarded.
This Action is bounded to32768 bytes; its cost is not hidden in a fetch step. -/
def finish (context : UInt64) : Action :=
  .bind (configuration context) fun s _ => if s = 0 then
  .bind (field context 72) fun s phase => if s = 0 then
  .bind (field context 80) fun s pending => if s = 0 then
  if phase = 2 then if pending = 0 then
  .bind (field context 48) fun s staging => if s = 0 then
  .bind (field context 96) fun s length => if s = 0 then
  .bind (PackageTarget.validate staging length) fun s _ => if s = 0 then
  .bind (field context 32) fun s identity => if s = 0 then
  .bind (field context 40) fun s edition => if s = 0 then
  .bind (Memory.read64 (staging + 24)) fun s actualIdentity => if s = 0 then
  .bind (Memory.read64 (staging + 32)) fun s actualEdition => if s = 0 then
  if actualIdentity = identity then if actualEdition = edition then
  .bind (put context 72 3) fun s _ => if s = 0 then .done 0 length else .done s 0
  else stop context malformed.toUInt64 4 else stop context malformed.toUInt64 4
  else stop context s.toUInt64 4 else stop context s.toUInt64 4 else stop context s.toUInt64 4
  else stop context s.toUInt64 4 else stop context s.toUInt64 4 else .done s 0 else .done s 0
  else .done Protocol.busy 0 else .done Protocol.busy 0
  else .done s 0 else .done s 0 else .done s 0

/-- Discard a pending READ exactly once, including an already completed reply.
Canceled/raw/validated bytes never become a selected package through this API. -/
def cancel (context : UInt64) : Action :=
  .bind (configuration context) fun s _ => if s = 0 then
  .bind (field context 72) fun s phase => if s = 0 then
  .bind (field context 80) fun s pending => if s = 0 then
  if phase ≤ 5 then
  if pending = 0 then stop context IPCABI.canceled.toUInt64 5 else if phase = 1 then
  .bind (field context 16) fun s incoming => if s = 0 then
  .bind (IPC.cancel pending) fun s _ =>
  if (if s = 0 then (1 : UInt64) else if s = IPCABI.alreadyCompleted then 1 else 0) = 1 then
  .bind (Syscall.call 67 pending incoming IPCABI.maximumPacket 0 0) fun terminal _ =>
  if terminal = IPCABI.wouldBlock then .done IPCABI.invalidTransaction 0 else
  .bind (put context 80 0) fun s _ => if s = 0 then stop context IPCABI.canceled.toUInt64 5 else .done s 0
  else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0

end Lemma.Courses.PackageReader
