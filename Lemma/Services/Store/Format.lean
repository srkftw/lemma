import Lemma.User.Memory

/-! Durable record-store v1. These are ordinary elaborated scalar/Action
declarations. Byte buffers and context/index pages are service-owned User
memory; none of the format, checksums, or recovery policy executes on the host.
The little-endian execution profile supplies the byte order of aligned words. -/
namespace Lemma.Services.Store.Format
open Lemma.Core0.Memory

def rootMagic : UInt64 := 0x31544f4f524d4c
def recordMagic : UInt64 := 0x314345524d4c
def commitMagic : UInt64 := 0x3154494d434d4c
def version : UInt64 := 1
def sectorBytes : UInt64 := 512
def maximumPayload : UInt64 := 32768
def firstSegment : UInt64 := 8
def maximumObjects : UInt64 := 1024
def indexRowBytes : UInt64 := 48
def indexBytes : UInt64 := 49152
def maximumSequence : UInt64 := 0x7fffffffffffffff
def malformed : UInt8 := 220
def unformatted : UInt8 := 221
def unsupported : UInt8 := 222
def readOnly : UInt8 := 223
def full : UInt8 := 224
def indexFull : UInt8 := 225
def wrongNamespace : UInt8 := 226
def transportFailed : UInt8 := 227
def wrongPhase : UInt8 := 228
def checksumFailed : UInt8 := 229
def notFound : UInt8 := 230

def payloadSectors (bytes : UInt64) : UInt64 := (bytes + 511) / 512
def recordSectors (bytes : UInt64) : UInt64 := payloadSectors bytes + 2
def segmentLength (capacity : UInt64) : UInt64 := (capacity - firstSegment) / 2
def segmentStart (capacity segment : UInt64) : UInt64 :=
  firstSegment + segment * segmentLength capacity
def capacityValid (capacity : UInt64) : UInt64 :=
  if 4096 ≤ capacity then if capacity ≤ 0x100000000 then 1 else 0 else 0
def kindValid (kind : UInt64) : UInt64 := if kind = 1 then 1 else if kind = 2 then 1 else 0
def recordShape (ns object transaction sequence length kind : UInt64) : UInt64 :=
  if 0 < ns then if 0 < object then if 0 < transaction then
  if 0 < sequence then if sequence ≤ maximumSequence then
  if length ≤ maximumPayload then if kindValid kind = 1 then
    if kind = 2 then if length = 0 then 1 else 0 else 1
  else 0 else 0 else 0 else 0 else 0 else 0 else 0

def hashInitial : UInt64 := 0xcbf29ce484222325
def hashByte (hash byte : UInt64) : UInt64 :=
  (hash ^^^ (byte &&& 255)) * 0x100000001b3
def hashWord (hash word : UInt64) : UInt64 :=
  let h0 := hashByte hash word
  let h1 := hashByte h0 (word >>> 8)
  let h2 := hashByte h1 (word >>> 16)
  let h3 := hashByte h2 (word >>> 24)
  let h4 := hashByte h3 (word >>> 32)
  let h5 := hashByte h4 (word >>> 40)
  let h6 := hashByte h5 (word >>> 48)
  hashByte h6 (word >>> 56)

/-- FNV-1a is corruption detection, not authentication. Header has eleven
specified words; reserved bytes are zero and checked on read. -/
def recordHash (generation ns object transaction sequence length kind payloadHash : UInt64) : UInt64 :=
  let h := hashWord hashInitial recordMagic
  let h := hashWord h version
  let h := hashWord h generation
  let h := hashWord h ns
  let h := hashWord h object
  let h := hashWord h transaction
  let h := hashWord h sequence
  let h := hashWord h length
  let h := hashWord h kind
  let h := hashWord h (payloadSectors length)
  hashWord h payloadHash

def publicationHash (generation ns object transaction sequence length kind payloadHash headerHash : UInt64) : UInt64 :=
  let h := hashWord hashInitial commitMagic
  let h := hashWord h version
  let h := hashWord h generation
  let h := hashWord h ns
  let h := hashWord h object
  let h := hashWord h transaction
  let h := hashWord h sequence
  let h := hashWord h length
  let h := hashWord h kind
  let h := hashWord h payloadHash
  hashWord h headerHash

def rootHash (capacity generation segment count tail sequence : UInt64) : UInt64 :=
  let h := hashWord hashInitial rootMagic
  let h := hashWord h version
  let h := hashWord h generation
  let h := hashWord h capacity
  let h := hashWord h segment
  let h := hashWord h (segmentStart capacity segment)
  let h := hashWord h (segmentLength capacity)
  let h := hashWord h count
  let h := hashWord h tail
  hashWord h sequence

def rootShape (capacity generation segment count tail sequence : UInt64) : UInt64 :=
  if capacityValid capacity = 1 then if 0 < generation then
  if generation ≤ maximumSequence then if segment ≤ 1 then
  if count ≤ maximumObjects then if count * 2 ≤ tail then
  if tail ≤ segmentLength capacity then if sequence ≤ maximumSequence then 1 else 0
  else 0 else 0 else 0 else 0 else 0 else 0 else 0

private def zeroStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write64 (address + i.toUInt64 * 8) 0) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else .done s 0

def clearSector (address : UInt64) : Action :=
  if address % 8 = 0 then if address ≤ 0xffffffffffffffff - 512 then
  .boundedFoldU64 64 zeroStep 64 0 address 0 0 0 fun s count =>
  if s = 0 then if count = 64 then .done 0 0 else .done malformed 0 else .done s 0
  else .done malformed 0 else .done malformed 0

private def hashStep (i _ : UInt32) (hash address _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read8 (address + i.toUInt64)) fun s byte =>
  if s = 0 then .done 0 (hashByte hash byte) else .done s 0

def checksum (address length initial : UInt64) : Action :=
  if length ≤ maximumPayload then if address ≤ 0xffffffffffffffff - length then
  .boundedFoldU64 32768 hashStep length.toUInt32 initial address 0 0 0 fun s hash =>
  .done s hash else .done malformed 0 else .done malformed 0

private def copyStep (i _ : UInt32) (count source target _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read8 (source + i.toUInt64)) fun s byte => if s = 0 then
  .bind (Lemma.User.Memory.write8 (target + i.toUInt64) byte) fun s _ =>
  if s = 0 then .done 0 (count + 1) else .done s 0 else .done s 0
private def copyWordStep (i _ : UInt32) (count source target _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 (source + i.toUInt64 * 8)) fun s word => if s = 0 then
  .bind (Lemma.User.Memory.write64 (target + i.toUInt64 * 8) word) fun s _ =>
  if s = 0 then .done 0 (count + 8) else .done s 0 else .done s 0

def copy (source target bytes : UInt64) : Action :=
  if bytes ≤ 512 then if source ≤ 0xffffffffffffffff - bytes then
  if target ≤ 0xffffffffffffffff - bytes then
  if (source ||| target ||| bytes) &&& 7 = 0 then
    .boundedFoldU64 64 copyWordStep (bytes / 8).toUInt32 0 source target 0 0 fun s copied =>
    if s = 0 then if copied = bytes then .done 0 copied else .done malformed 0 else .done s 0
  else
  .boundedFoldU64 512 copyStep bytes.toUInt32 0 source target 0 0 fun s copied =>
  if s = 0 then if copied = bytes then .done 0 copied else .done malformed 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0

private def reservedStep (i _ : UInt32) (acc address begin _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 (address + begin + i.toUInt64 * 8)) fun s word =>
  if s = 0 then .done 0 (acc ||| word) else .done s 0

def reservedZero (address begin : UInt64) : Action :=
  if begin % 8 = 0 then if begin ≤ 512 then
  .boundedFoldU64 64 reservedStep ((512 - begin) / 8).toUInt32 0 address begin 0 0 fun s nonzero =>
  if s = 0 then if nonzero = 0 then .done 0 0 else .done malformed 0 else .done s 0
  else .done malformed 0 else .done malformed 0

end Lemma.Services.Store.Format
