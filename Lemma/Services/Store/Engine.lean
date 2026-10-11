import Lemma.Services.Store.Codec
import Lemma.Services.Store.Index

/-! One-request-at-a-time durable record engine. `operation/sector/buffer` is a
guest-to-guest transport adapter contract, never a host application callback.
Only a capability-authorized store worker may execute its requests. The block
adapter calls complete after real completion, retaining the bounce-page pins.
This module contains the transaction/recovery state machine, not the adapter.

Context: 4096 private bytes, one 512-byte transport buffer, two independently
allocated index spans for checkpoint. All spans must already be mapped writable
to the store; wrappers preflight complete spans before entering these routines.
See docs/contracts/004-store-v1.md for fields and admitted crash semantics. -/
namespace Lemma.Services.Store.Engine
open Lemma.Core0.Memory
open Format

def field (context offset : UInt64) : Action := Lemma.User.Memory.read64 (context + offset)
def put (context offset value : UInt64) : Action := Lemma.User.Memory.write64 (context + offset) value

/-- One validated record and one immutable private body sector. Neither span
 is the kernel DMA bounce or the reusable transport buffer. -/
def invalidateReadCache (context : UInt64) : Action :=
  .bind (put context 376 0) fun s _ => if s = 0 then put context 432 0 else .done s 0

def request (context operation phase sector : UInt64) : Action :=
  .bind (if operation = 1 then .done 0 0 else invalidateReadCache context) fun s _ => if s = 0 then
  .bind (put context 16 sector) fun s _ => if s = 0 then
  .bind (put context 8 phase) fun s _ => if s = 0 then
  .bind (put context 0 operation) fun s _ => .done s operation
  else .done s 0 else .done s 0 else .done s 0

def failure (context : UInt64) (status : UInt8) : Action :=
  .bind (invalidateReadCache context) fun s _ => if s = 0 then
  .bind (put context 336 1) fun s _ => if s = 0 then
  .bind (put context 32 status.toUInt64) fun s _ => if s = 0 then
  .bind (put context 8 0) fun s _ => if s = 0 then
  .bind (put context 0 0) fun s _ => if s = 0 then .done status 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- A rejected client range ends this request without making the medium
read-only. Structural media corruption uses failure instead. -/
def rejected (context : UInt64) (status : UInt8) : Action :=
  .bind (put context 32 status.toUInt64) fun s _ => if s = 0 then
  .bind (put context 8 0) fun s _ => if s = 0 then
  .bind (put context 0 0) fun s _ => if s = 0 then .done status 0 else .done s 0
  else .done s 0 else .done s 0

def ready (context : UInt64) : Action :=
  .bind (put context 32 0) fun s _ => if s = 0 then
  .bind (put context 8 0) fun s _ => if s = 0 then
  .bind (put context 0 0) fun s _ => .done s 0
  else .done s 0 else .done s 0

private def contextClearStep (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (put context (i.toUInt64 * 8) 0) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else .done s 0

def mountStart (context buffer index capacity : UInt64) : Action :=
  if capacityValid capacity = 1 then
  if context % 8 = 0 then if buffer % 8 = 0 then if index % 8 = 0 then
  if context ≤ 0xffffffffffffffff - 4096 then
  if buffer ≤ 0xffffffffffffffff - 512 then
  .boundedFoldU64 512 contextClearStep 512 0 context 0 0 0 fun s count =>
  if s = 0 then if count = 512 then
  .bind (Index.clear index) fun s _ => if s = 0 then
  .bind (put context 24 buffer) fun s _ => if s = 0 then
  .bind (put context 48 capacity) fun s _ => if s = 0 then
  .bind (put context 104 index) fun s _ => if s = 0 then
  request context 1 1 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0

private def nextHeader (context : UInt64) : Action :=
  .bind (field context 72) fun s start => if s = 0 then
  .bind (field context 80) fun s length => if s = 0 then
  .bind (field context 88) fun s tail => if s = 0 then
  .bind (field context 224) fun s remaining => if s = 0 then
  if tail < length then request context 1 3 (start + tail)
  else if remaining = 0 then ready context else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def rootCompareStep (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (field context (512 + i.toUInt64 * 8)) fun s left => if s = 0 then
  .bind (field context (576 + i.toUInt64 * 8)) fun s right =>
  if s = 0 then .done 0 (acc ||| (left ^^^ right)) else .done s 0 else .done s 0

private def selectRoot (context : UInt64) : Action :=
  .bind (field context 512) fun s g0 => if s = 0 then
  .bind (field context 576) fun s g1 => if s = 0 then
  .bind (field context 552) fun s h0 => if s = 0 then
  .bind (field context 616) fun s h1 => if s = 0 then
  if g0 = 0 then if g1 = 0 then failure context unformatted else
    .done 0 576
  else if g1 = 0 then .done 0 512 else
  if g0 = g1 then if h0 = h1 then
    .boundedFoldU64 6 rootCompareStep 6 0 context 0 0 0 fun s difference =>
    if s = 0 then if difference = 0 then .done 0 512 else failure context malformed else .done s 0
  else failure context malformed
  else .done 0 (if g0 < g1 then 576 else 512)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def rootSelected (context candidate : UInt64) : Action :=
  .bind (field context 48) fun s capacity => if s = 0 then
  .bind (Lemma.User.Memory.read64 candidate) fun s generation => if s = 0 then
  .bind (Lemma.User.Memory.read64 (candidate + 8)) fun s segment => if s = 0 then
  .bind (Lemma.User.Memory.read64 (candidate + 16)) fun s count => if s = 0 then
  .bind (Lemma.User.Memory.read64 (candidate + 24)) fun s tail => if s = 0 then
  .bind (Lemma.User.Memory.read64 (candidate + 32)) fun s sequence => if s = 0 then
  .bind (put context 56 generation) fun s _ => if s = 0 then
  .bind (put context 64 segment) fun s _ => if s = 0 then
  .bind (put context 72 (segmentStart capacity segment)) fun s _ => if s = 0 then
  .bind (put context 80 (segmentLength capacity)) fun s _ => if s = 0 then
  .bind (put context 96 sequence) fun s _ => if s = 0 then
  .bind (put context 40 sequence) fun s _ => if s = 0 then
  .bind (put context 216 count) fun s _ => if s = 0 then
  .bind (put context 224 count) fun s _ => if s = 0 then
  .bind (put context 232 tail) fun s _ => if s = 0 then
  .bind (put context 248 (if candidate = context + 576 then 1 else 0)) fun s _ => if s = 0 then
  nextHeader context
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def rootCompleted (context phase : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 48) fun s capacity => if s = 0 then
  .bind (Codec.readRoot buffer capacity (context + (if phase = 1 then 512 else 576))) fun status _ =>
  if status = 0 then
    if phase = 1 then request context 1 2 1 else
    .bind (selectRoot context) fun status candidate =>
    if status = 0 then rootSelected context (context + candidate) else .done status 0
  else failure context status
  else .done s 0 else .done s 0

private def incompleteTail (context : UInt64) : Action :=
  .bind (field context 224) fun s remaining =>
  if s = 0 then if remaining = 0 then ready context else failure context checksumFailed
  else .done s 0

private def recordFields (context buffer : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 (buffer + 24)) fun s ns => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 32)) fun s object => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 40)) fun s transaction => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 48)) fun s sequence => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 56)) fun s bytes => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 64)) fun s kind => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 72)) fun s sectors => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 80)) fun s hash => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 88)) fun s headerHash => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 96)) fun s inverse => if s = 0 then
  .bind (field context 56) fun s generation => if s = 0 then
  if recordShape ns object transaction sequence bytes kind = 1 then
  if sectors = payloadSectors bytes then
  if headerHash = recordHash generation ns object transaction sequence bytes kind hash then
  if inverse = ~~~headerHash then
  .bind (reservedZero buffer 104) fun s _ => if s = 0 then
  .bind (put context 120 bytes) fun s _ => if s = 0 then
  .bind (put context 128 ns) fun s _ => if s = 0 then
  .bind (put context 136 object) fun s _ => if s = 0 then
  .bind (put context 144 transaction) fun s _ => if s = 0 then
  .bind (put context 152 sequence) fun s _ => if s = 0 then
  .bind (put context 160 kind) fun s _ => if s = 0 then
  .bind (put context 168 hash) fun s _ => if s = 0 then
  .bind (put context 176 headerHash) fun s _ => if s = 0 then
  .bind (put context 192 0) fun s _ => if s = 0 then
  .bind (put context 208 hashInitial) fun s _ => .done s bytes
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0

private def scanBodyOrCommit (context : UInt64) : Action :=
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 184) fun s first => if s = 0 then
  .bind (field context 192) fun s progressed => if s = 0 then
  if progressed < payloadSectors bytes then request context 1 4 (first + 1 + progressed)
  else request context 1 5 (first + 1 + payloadSectors bytes)
  else .done s 0 else .done s 0 else .done s 0

private def scanSequenceValid (remaining sequence previous : UInt64) : UInt64 :=
  if remaining = 0 then if sequence = previous + 1 then 1 else 0
  else if sequence ≤ previous then 1 else 0

private def headerCompleted (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (Lemma.User.Memory.read64 buffer) fun s magic => if s = 0 then
  if magic = recordMagic then
  .bind (Lemma.User.Memory.read64 (buffer + 8)) fun s ver => if s = 0 then
  if ver = version then
  .bind (Lemma.User.Memory.read64 (buffer + 16)) fun s gen => if s = 0 then
  .bind (field context 56) fun s generation => if s = 0 then
  if gen = generation then
  .bind (recordFields context buffer) fun parsed bytes =>
  if parsed = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 96) fun s previous => if s = 0 then
  .bind (field context 224) fun s remaining => if s = 0 then
  .bind (field context 88) fun s tail => if s = 0 then
  .bind (field context 80) fun s length => if s = 0 then
  .bind (field context 72) fun s start => if s = 0 then
  if scanSequenceValid remaining sequence previous = 1 then
  if recordSectors bytes ≤ length - tail then
  .bind (put context 184 (start + tail)) fun s _ =>
  if s = 0 then scanBodyOrCommit context else .done s 0
  else incompleteTail context else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else incompleteTail context
  else incompleteTail context else .done s 0 else .done s 0
  else failure context unsupported else .done s 0
  else incompleteTail context else .done s 0 else .done s 0

private def bodyCompleted (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 192) fun s progressed => if s = 0 then
  .bind (field context 208) fun s hash => if s = 0 then
  let count := if 512 < bytes - progressed * 512 then 512 else bytes - progressed * 512
  .bind (checksum buffer count hash) fun s hash => if s = 0 then
  .bind (put context 208 hash) fun s _ => if s = 0 then
  .bind (put context 192 (progressed + 1)) fun s _ =>
  if s = 0 then scanBodyOrCommit context else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def expectedPublication (context : UInt64) : Action :=
  .bind (field context 56) fun s generation => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 144) fun s transaction => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 160) fun s kind => if s = 0 then
  .bind (field context 168) fun s hash => if s = 0 then
  Codec.publication (context + 1024) generation ns object transaction sequence bytes kind hash
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def compareStep (i _ : UInt32) (acc actual expected _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 (actual + i.toUInt64 * 8)) fun s a => if s = 0 then
  .bind (Lemma.User.Memory.read64 (expected + i.toUInt64 * 8)) fun s e =>
  if s = 0 then .done 0 (acc ||| (a ^^^ e)) else .done s 0 else .done s 0

private def publishIndex (context : UInt64) : Action :=
  .bind (field context 104) fun s index => if s = 0 then
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 184) fun s first => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 160) fun s kind => if s = 0 then
  .bind (Index.find index ns object) fun s slot => if s = 0 then
  .bind (Lemma.User.Memory.read64 (Index.row index slot)) fun s previousNs => if s = 0 then
  .bind (Lemma.User.Memory.read64 (Index.row index slot + 32)) fun s previousSequence => if s = 0 then
  if previousNs = 0 then Index.publish index slot ns object first (recordSectors bytes) sequence kind
  else if previousSequence < sequence then Index.publish index slot ns object first (recordSectors bytes) sequence kind
  else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def publicationCompleted (context : UInt64) : Action :=
  .bind (field context 168) fun s expectedHash => if s = 0 then
  .bind (field context 208) fun s observedHash => if s = 0 then
  if expectedHash = observedHash then
  .bind (expectedPublication context) fun s _ => if s = 0 then
  .bind (field context 24) fun s buffer => if s = 0 then
  .boundedFoldU64 64 compareStep 64 0 buffer (context + 1024) 0 0 fun s difference =>
  if s = 0 then if difference = 0 then
  .bind (publishIndex context) fun s _ => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 88) fun s tail => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 224) fun s remaining => if s = 0 then
  .bind (field context 232) fun s checkpointTail => if s = 0 then
  let nextTail := tail + recordSectors bytes
  .bind (put context 88 nextTail) fun s _ => if s = 0 then
  if remaining = 0 then
  .bind (put context 96 sequence) fun s _ => if s = 0 then
  .bind (put context 40 sequence) fun s _ => if s = 0 then nextHeader context else .done s 0
  else .done s 0
  else .bind (put context 224 (remaining - 1)) fun s _ => if s = 0 then
    if remaining = 1 then if nextTail = checkpointTail then nextHeader context else failure context malformed
    else if nextTail < checkpointTail then nextHeader context else failure context malformed
  else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else incompleteTail context else .done s 0
  else .done s 0 else .done s 0
  else incompleteTail context else .done s 0 else .done s 0

private def appendHeader (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 56) fun s generation => if s = 0 then
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 144) fun s transaction => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 160) fun s kind => if s = 0 then
  .bind (field context 168) fun s hash => if s = 0 then
  .bind (field context 184) fun s first => if s = 0 then
  .bind (Codec.record buffer generation ns object transaction sequence bytes kind hash) fun s headerHash => if s = 0 then
  .bind (put context 176 headerHash) fun s _ => if s = 0 then request context 2 16 first else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def appendStart (context ns object transaction payload bytes kind : UInt64) : Action :=
  .bind (field context 0) fun s operation => if s = 0 then
  .bind (field context 336) fun s blocked => if s = 0 then
  .bind (field context 56) fun s generation => if s = 0 then
  .bind (field context 96) fun s previous => if s = 0 then
  .bind (field context 88) fun s tail => if s = 0 then
  .bind (field context 80) fun s length => if s = 0 then
  .bind (field context 72) fun s start => if s = 0 then
  .bind (field context 104) fun s index => if s = 0 then
  if operation = 0 then if blocked = 0 then if 0 < generation then
  if previous < maximumSequence then
  if recordShape ns object transaction (previous + 1) bytes kind = 1 then
  if tail ≤ length then if recordSectors bytes + 1 ≤ length - tail then
  .bind (Index.find index ns object) fun s slot => if s = 0 then
  .bind (checksum payload bytes hashInitial) fun s hash => if s = 0 then
  .bind (put context 112 payload) fun s _ => if s = 0 then
  .bind (put context 120 bytes) fun s _ => if s = 0 then
  .bind (put context 128 ns) fun s _ => if s = 0 then
  .bind (put context 136 object) fun s _ => if s = 0 then
  .bind (put context 144 transaction) fun s _ => if s = 0 then
  .bind (put context 152 (previous + 1)) fun s _ => if s = 0 then
  .bind (put context 160 kind) fun s _ => if s = 0 then
  .bind (put context 168 hash) fun s _ => if s = 0 then
  .bind (put context 184 (start + tail)) fun s _ => if s = 0 then
  .bind (put context 192 0) fun s _ => if s = 0 then
  .bind (put context 240 slot) fun s _ => if s = 0 then appendHeader context else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0
  else .done full 0 else .done malformed 0 else .done malformed 0
  else .done full 0 else .done unformatted 0 else .done readOnly 0 else .done wrongPhase 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def appendBodyOrSentinel (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 112) fun s payload => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 184) fun s first => if s = 0 then
  .bind (field context 192) fun s progressed => if s = 0 then
  .bind (clearSector buffer) fun s _ => if s = 0 then
  if progressed < payloadSectors bytes then
    let count := if 512 < bytes - progressed * 512 then 512 else bytes - progressed * 512
    .bind (copy (payload + progressed * 512) buffer count) fun s _ =>
    if s = 0 then request context 2 17 (first + 1 + progressed) else .done s 0
  else request context 2 18 (first + recordSectors bytes)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def appendPublication (context : UInt64) : Action :=
  .bind (expectedPublication context) fun s _ => if s = 0 then
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 184) fun s first => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (copy (context + 1024) buffer 512) fun s _ =>
  if s = 0 then request context 2 20 (first + 1 + payloadSectors bytes) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def acknowledged (context : UInt64) : Action :=
  .bind (publishIndex context) fun s _ => if s = 0 then
  .bind (field context 88) fun s tail => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (put context 88 (tail + recordSectors bytes)) fun s _ => if s = 0 then
  .bind (put context 96 sequence) fun s _ => if s = 0 then
  .bind (put context 40 sequence) fun s _ => if s = 0 then ready context else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Explicit destructive initialization. A launcher may use it only for a
new/verified-empty image or after separately recorded destructive user intent.
Mount never calls it, including when both root slots are damaged. -/
def formatStart (context buffer index capacity : UInt64) : Action :=
  .bind (mountStart context buffer index capacity) fun s _ => if s = 0 then
  .bind (put context 56 1) fun s _ => if s = 0 then
  .bind (put context 72 firstSegment) fun s _ => if s = 0 then
  .bind (put context 80 (segmentLength capacity)) fun s _ => if s = 0 then
  .bind (clearSector buffer) fun s _ =>
  if s = 0 then request context 2 64 firstSegment else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def formatRoot (context slot : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 48) fun s capacity => if s = 0 then
  .bind (Codec.root buffer capacity 1 0 0 0 0) fun s _ =>
  if s = 0 then request context 2 (if slot = 0 then 66 else 68) slot else .done s 0
  else .done s 0 else .done s 0

private def checkpointFindStep (i _ : UInt32) (_ index start _ _ : UInt64) : Action :=
  let slot := start + i.toUInt64
  .bind (Lemma.User.Memory.read64 (Index.row index slot)) fun s ns =>
  if s = 0 then if ns = 0 then .done 0 0 else .done 10 (slot + 1) else .done s 0

private def checkpointNext (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 104) fun s index => if s = 0 then
  .bind (field context 264) fun s cursor => if s = 0 then
  .bind (field context 272) fun s tail => if s = 0 then
  .bind (field context 280) fun s start => if s = 0 then
  .bind (field context 80) fun s length => if s = 0 then
  if cursor ≤ 1024 then
  .boundedFoldU64 1024 checkpointFindStep (1024 - cursor).toUInt32 0 index cursor 0 0 fun s found =>
  if (if s = 10 then (0 : UInt8) else s) = 0 then if found = 0 then
  .bind (clearSector buffer) fun s _ =>
  if s = 0 then request context 2 37 (start + tail) else .done s 0
  else
  let slot := found - 1
  .bind (Lemma.User.Memory.read64 (Index.row index slot + 16)) fun s source => if s = 0 then
  .bind (Lemma.User.Memory.read64 (Index.row index slot + 24)) fun s sectors => if s = 0 then
  if 2 ≤ sectors then if sectors ≤ 66 then
  if sectors + 1 ≤ length - tail then
  .bind (put context 264 (slot + 1)) fun s _ => if s = 0 then
  .bind (put context 312 0) fun s _ => if s = 0 then
  .bind (put context 320 source) fun s _ => if s = 0 then
  .bind (put context 328 sectors) fun s _ =>
  if s = 0 then request context 1 32 source else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else failure context full else failure context malformed else failure context malformed
  else .done s 0 else .done s 0
  else .done s 0 else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Copy only latest object revisions (including deletion tombstones) to the
inactive segment. Original stroke objects remain independently retained.
The active root/index/acknowledged sequence stay unchanged until root flush.
Each source and destination sector still traverses the real guest block path. -/
def checkpointStart (context nextIndex : UInt64) : Action :=
  .bind (field context 0) fun s operation => if s = 0 then
  .bind (field context 336) fun s blocked => if s = 0 then
  .bind (field context 48) fun s capacity => if s = 0 then
  .bind (field context 56) fun s generation => if s = 0 then
  .bind (field context 64) fun s segment => if s = 0 then
  .bind (field context 104) fun s currentIndex => if s = 0 then
  if operation = 0 then if blocked = 0 then if 0 < generation then
  if generation < maximumSequence then if nextIndex = currentIndex then .done malformed 0 else
  .bind (invalidateReadCache context) fun s _ => if s = 0 then
  .bind (Index.clear nextIndex) fun s _ => if s = 0 then
  .bind (put context 256 nextIndex) fun s _ => if s = 0 then
  .bind (put context 264 0) fun s _ => if s = 0 then
  .bind (put context 272 0) fun s _ => if s = 0 then
  .bind (put context 280 (segmentStart capacity (1 - segment))) fun s _ => if s = 0 then
  .bind (put context 288 (generation + 1)) fun s _ => if s = 0 then
  .bind (put context 296 (1 - segment)) fun s _ => if s = 0 then
  .bind (put context 304 0) fun s _ => if s = 0 then checkpointNext context else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done full 0 else .done unformatted 0 else .done readOnly 0 else .done wrongPhase 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def checkpointHeader (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (Lemma.User.Memory.read64 buffer) fun s magic => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 8)) fun s ver => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 16)) fun s gen => if s = 0 then
  .bind (field context 56) fun s expectedGen => if s = 0 then
  if magic = recordMagic then if ver = version then if gen = expectedGen then
  .bind (recordFields context buffer) fun s bytes => if s = 0 then
  .bind (field context 328) fun s sectors => if s = 0 then
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 144) fun s transaction => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 160) fun s kind => if s = 0 then
  .bind (field context 168) fun s hash => if s = 0 then
  .bind (field context 272) fun s tail => if s = 0 then
  .bind (field context 280) fun s start => if s = 0 then
  .bind (field context 288) fun s generation => if s = 0 then
  if sectors = recordSectors bytes then
  .bind (Codec.record buffer generation ns object transaction sequence bytes kind hash) fun s _ =>
  if s = 0 then request context 2 33 (start + tail) else .done s 0
  else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else failure context malformed else failure context unsupported else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Namespace-filtered latest-object lookup. Namespace authorization comes from
the kernel-stamped IPC grant; it must be checked before calling this function.
Tombstones and absent rows are explicit notFound. The returned address is
service-private index metadata and must never be sent as a client pointer. -/
def lookup (context ns object : UInt64) : Action :=
  .bind (field context 104) fun s index => if s = 0 then
  .bind (Index.find index ns object) fun s slot => if s = 0 then
  let address := Index.row index slot
  .bind (Lemma.User.Memory.read64 address) fun s observedNs => if s = 0 then
  .bind (Lemma.User.Memory.read64 (address + 8)) fun s observedObject => if s = 0 then
  .bind (Lemma.User.Memory.read64 (address + 40)) fun s kind => if s = 0 then
  if observedNs = ns then if observedObject = object then
    if kind = 1 then .done 0 address else .done notFound 0
  else .done notFound 0 else .done notFound 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Enumerate latest records belonging to one already authorized namespace.
Returns the next slot+1, zero at end. Callers use lookup/readStart to read data.
This is bounded by the index, not the total historical journal length. -/
private def enumerateStep (i _ : UInt32) (_ index ns start _ : UInt64) : Action :=
  let slot := start + i.toUInt64
  .bind (Lemma.User.Memory.read64 (Index.row index slot)) fun s observedNs => if s = 0 then
  .bind (Lemma.User.Memory.read64 (Index.row index slot + 40)) fun s kind =>
  if s = 0 then if observedNs = ns then if kind = 1 then .done 10 (slot + 1) else .done 0 0
  else .done 0 0 else .done s 0 else .done s 0

def enumerate (context ns cursor : UInt64) : Action :=
  if 0 < ns then if cursor ≤ maximumObjects then
  .bind (field context 104) fun s index => if s = 0 then
  .boundedFoldU64 1024 enumerateStep (maximumObjects - cursor).toUInt32 0 index ns cursor 0 fun s next =>
  if s = 10 then .done 0 next else .done s next else .done s 0
  else .done malformed 0 else .done malformed 0

private def cachedBody (context : UInt64) : Action :=
  .bind (field context 184) fun s source => if s = 0 then
  .bind (field context 112) fun s output => if s = 0 then
  .bind (field context 344) fun s offset => if s = 0 then
  .bind (field context 352) fun s count => if s = 0 then
  .bind (field context 360) fun s copied => if s = 0 then
  let begin := (offset + copied) % 512
  let bytes := if count - copied < 512 - begin then count - copied else 512 - begin
  .bind (copy (context + 2048 + begin) (output + copied) bytes) fun s _ => if s = 0 then
  let next := copied + bytes
  .bind (put context 360 next) fun s _ => if s = 0 then
  if next = count then ready context
  else if next < count then request context 1 81 (source + 1 + (offset + next) / 512)
  else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

private def readNext (context : UInt64) : Action :=
  .bind (field context 184) fun s source => if s = 0 then
  .bind (field context 344) fun s offset => if s = 0 then
  .bind (field context 352) fun s count => if s = 0 then
  .bind (field context 360) fun s copied => if s = 0 then
  if copied = count then ready context else if copied < count then
  .bind (field context 432) fun s valid => if s = 0 then
  .bind (field context 440) fun s cached => if s = 0 then
  let sector := source + 1 + (offset + copied) / 512
  if valid = 1 then if cached = sector then cachedBody context else request context 1 81 sector
  else request context 1 81 sector
  else .done s 0 else .done s 0 else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def readRange (context bytes : UInt64) : Action :=
  .bind (field context 344) fun s offset => if s = 0 then
  .bind (field context 352) fun s count => if s = 0 then
  if bytes ≤ maximumPayload then if offset ≤ bytes then
  .bind (put context 352 (if count ≤ bytes - offset then count else bytes - offset)) fun s _ =>
  if s = 0 then readNext context else .done s 0
  else rejected context malformed else failure context malformed
  else .done s 0 else .done s 0

private def readCacheMatches (context ns object source sequence generation : UInt64) : Action :=
  .bind (field context 376) fun s valid => if s = 0 then
  .bind (field context 384) fun s cachedNs => if s = 0 then
  .bind (field context 392) fun s cachedObject => if s = 0 then
  .bind (field context 400) fun s cachedSequence => if s = 0 then
  .bind (field context 408) fun s cachedGeneration => if s = 0 then
  .bind (field context 416) fun s cachedSource =>
  if s = 0 then
    if valid = 1 then if cachedNs = ns then if cachedObject = object then
    if cachedSequence = sequence then if cachedGeneration = generation then
    if cachedSource = source then .done 0 1 else .done 0 0 else .done 0 0
    else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Every RPC revalidates the latest namespace-filtered index tuple. A matching
private header/body window avoids duplicate sector I/O; it cannot publish data
from a replaced object or a previous checkpoint generation. -/
def readStart (context ns object offset count output : UInt64) : Action :=
  .bind (field context 0) fun s operation => if s = 0 then
  if operation = 0 then if count ≤ maximumPayload then
  .bind (lookup context ns object) fun s address => if s = 0 then
  .bind (Lemma.User.Memory.read64 (address + 16)) fun s source => if s = 0 then
  .bind (Lemma.User.Memory.read64 (address + 32)) fun s sequence => if s = 0 then
  .bind (field context 56) fun s generation => if s = 0 then
  .bind (put context 112 output) fun s _ => if s = 0 then
  .bind (put context 184 source) fun s _ => if s = 0 then
  .bind (put context 344 offset) fun s _ => if s = 0 then
  .bind (put context 352 count) fun s _ => if s = 0 then
  .bind (put context 360 0) fun s _ => if s = 0 then
  .bind (put context 368 sequence) fun s _ => if s = 0 then
  .bind (put context 448 ns) fun s _ => if s = 0 then
  .bind (put context 456 object) fun s _ => if s = 0 then
  .bind (readCacheMatches context ns object source sequence generation) fun s hit => if s = 0 then
  if hit = 1 then
    .bind (field context 424) fun s bytes => if s = 0 then readRange context bytes else .done s 0
  else
    .bind (invalidateReadCache context) fun s _ => if s = 0 then request context 1 80 source else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done wrongPhase 0 else .done s 0

private def rememberHeader (context bytes : UInt64) : Action :=
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 56) fun s generation => if s = 0 then
  .bind (field context 184) fun s source => if s = 0 then
  .bind (put context 384 ns) fun s _ => if s = 0 then
  .bind (put context 392 object) fun s _ => if s = 0 then
  .bind (put context 400 sequence) fun s _ => if s = 0 then
  .bind (put context 408 generation) fun s _ => if s = 0 then
  .bind (put context 416 source) fun s _ => if s = 0 then
  .bind (put context 424 bytes) fun s _ => if s = 0 then
  .bind (put context 376 1) fun s _ => if s = 0 then readRange context bytes else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def readHeader (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (Lemma.User.Memory.read64 buffer) fun s magic => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 8)) fun s ver => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 16)) fun s gen => if s = 0 then
  .bind (field context 56) fun s expectedGen => if s = 0 then
  if magic = recordMagic then if ver = version then if gen = expectedGen then
  .bind (recordFields context buffer) fun s bytes => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 368) fun s expected => if s = 0 then
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 448) fun s expectedNs => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 456) fun s expectedObject => if s = 0 then
  .bind (field context 160) fun s kind => if s = 0 then
  if sequence = expected then if ns = expectedNs then if object = expectedObject then if kind = 1 then
  rememberHeader context bytes
  else failure context malformed else failure context malformed else failure context malformed else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else failure context malformed else failure context unsupported else failure context malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def readBody (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 16) fun s sector => if s = 0 then
  .bind (put context 432 0) fun s _ => if s = 0 then
  .bind (copy buffer (context + 2048) 512) fun s _ => if s = 0 then
  .bind (put context 440 sector) fun s _ => if s = 0 then
  .bind (put context 432 1) fun s _ => if s = 0 then cachedBody context else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def checkpointPublication (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 144) fun s transaction => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 160) fun s kind => if s = 0 then
  .bind (field context 168) fun s hash => if s = 0 then
  .bind (field context 208) fun s observed => if s = 0 then
  .bind (field context 272) fun s tail => if s = 0 then
  .bind (field context 280) fun s start => if s = 0 then
  .bind (field context 288) fun s generation => if s = 0 then
  if observed = hash then
  .bind (Codec.publication buffer generation ns object transaction sequence bytes kind hash) fun s _ =>
  if s = 0 then request context 2 36 (start + tail + 1 + payloadSectors bytes) else .done s 0
  else failure context checksumFailed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def checkpointBody (context : UInt64) : Action :=
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 312) fun s progressed => if s = 0 then
  .bind (field context 320) fun s source => if s = 0 then
  if progressed < payloadSectors bytes then request context 1 34 (source + 1 + progressed)
  else checkpointPublication context
  else .done s 0 else .done s 0 else .done s 0

private def checkpointBodyRead (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 120) fun s bytes => if s = 0 then
  .bind (field context 312) fun s progressed => if s = 0 then
  .bind (field context 208) fun s hash => if s = 0 then
  .bind (field context 272) fun s tail => if s = 0 then
  .bind (field context 280) fun s start => if s = 0 then
  let count := if 512 < bytes - progressed * 512 then 512 else bytes - progressed * 512
  .bind (checksum buffer count hash) fun s hash => if s = 0 then
  .bind (put context 208 hash) fun s _ =>
  if s = 0 then request context 2 35 (start + tail + 1 + progressed) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def checkpointRecordDone (context : UInt64) : Action :=
  .bind (field context 256) fun s index => if s = 0 then
  .bind (field context 128) fun s ns => if s = 0 then
  .bind (field context 136) fun s object => if s = 0 then
  .bind (field context 152) fun s sequence => if s = 0 then
  .bind (field context 160) fun s kind => if s = 0 then
  .bind (field context 272) fun s tail => if s = 0 then
  .bind (field context 280) fun s start => if s = 0 then
  .bind (field context 304) fun s count => if s = 0 then
  .bind (field context 328) fun s sectors => if s = 0 then
  .bind (Index.find index ns object) fun s slot => if s = 0 then
  .bind (Index.publish index slot ns object (start + tail) sectors sequence kind) fun s _ => if s = 0 then
  .bind (put context 272 (tail + sectors)) fun s _ => if s = 0 then
  .bind (put context 304 (count + 1)) fun s _ =>
  if s = 0 then checkpointNext context else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def checkpointRoot (context : UInt64) : Action :=
  .bind (field context 24) fun s buffer => if s = 0 then
  .bind (field context 48) fun s capacity => if s = 0 then
  .bind (field context 96) fun s sequence => if s = 0 then
  .bind (field context 248) fun s slot => if s = 0 then
  .bind (field context 272) fun s tail => if s = 0 then
  .bind (field context 288) fun s generation => if s = 0 then
  .bind (field context 296) fun s segment => if s = 0 then
  .bind (field context 304) fun s count => if s = 0 then
  .bind (Codec.root buffer capacity generation segment count tail sequence) fun s _ =>
  if s = 0 then request context 2 39 (1 - slot) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def checkpointSwitched (context : UInt64) : Action :=
  .bind (field context 104) fun s previousIndex => if s = 0 then
  .bind (field context 248) fun s previousSlot => if s = 0 then
  .bind (field context 256) fun s index => if s = 0 then
  .bind (field context 272) fun s tail => if s = 0 then
  .bind (field context 280) fun s start => if s = 0 then
  .bind (field context 288) fun s generation => if s = 0 then
  .bind (field context 296) fun s segment => if s = 0 then
  .bind (put context 56 generation) fun s _ => if s = 0 then
  .bind (put context 64 segment) fun s _ => if s = 0 then
  .bind (put context 72 start) fun s _ => if s = 0 then
  .bind (put context 88 tail) fun s _ => if s = 0 then
  .bind (put context 104 index) fun s _ => if s = 0 then
  .bind (put context 248 (1 - previousSlot)) fun s _ => if s = 0 then
  .bind (put context 256 previousIndex) fun s _ => if s = 0 then ready context else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Called exactly once per matching outstanding request. A flush succeeds only
when the block adapter has observed the actual device's negotiated flush result.
No field or index exposing the new acknowledged sequence changes before phase21. -/
def complete (context : UInt64) (status : UInt8) : Action :=
  .bind (field context 0) fun s operation => if s = 0 then
  .bind (field context 8) fun s phase => if s = 0 then
  if operation = 0 then .done wrongPhase 0 else
  if status = 0 then
    if phase = 1 then rootCompleted context phase else
    if phase = 2 then rootCompleted context phase else
    if phase = 3 then headerCompleted context else
    if phase = 4 then bodyCompleted context else
    if phase = 5 then publicationCompleted context else
    if phase = 16 then appendBodyOrSentinel context else
    if phase = 17 then
      .bind (field context 192) fun s progressed => if s = 0 then
      .bind (put context 192 (progressed + 1)) fun s _ =>
      if s = 0 then appendBodyOrSentinel context else .done s 0 else .done s 0
    else if phase = 18 then request context 3 19 0 else
    if phase = 19 then appendPublication context else
    if phase = 20 then request context 3 21 0 else
    if phase = 21 then acknowledged context else
    if phase = 32 then checkpointHeader context else
    if phase = 33 then checkpointBody context else
    if phase = 34 then checkpointBodyRead context else
    if phase = 35 then
      .bind (field context 312) fun s progressed => if s = 0 then
      .bind (put context 312 (progressed + 1)) fun s _ =>
      if s = 0 then checkpointBody context else .done s 0 else .done s 0
    else if phase = 36 then checkpointRecordDone context else
    if phase = 37 then request context 3 38 0 else
    if phase = 38 then checkpointRoot context else
    if phase = 39 then request context 3 40 0 else
    if phase = 40 then checkpointSwitched context else
    if phase = 64 then request context 3 65 0 else
    if phase = 65 then formatRoot context 0 else
    if phase = 66 then request context 3 67 0 else
    if phase = 67 then formatRoot context 1 else
    if phase = 68 then request context 3 69 0 else
    if phase = 69 then ready context else
    if phase = 80 then readHeader context else
    if phase = 81 then readBody context else failure context wrongPhase
  else failure context transportFailed
  else .done s 0 else .done s 0

end Lemma.Services.Store.Engine
