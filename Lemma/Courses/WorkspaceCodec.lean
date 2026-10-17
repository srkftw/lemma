import Lemma.Courses.PackageWorkspace

/-! Lossless workspace envelope2. The original3712-byte workspace/Doc8 remains
byte-for-byte unchanged in RAM. Eight bitmap words name its464 nonzero words;
all values, including otherwise unused bytes, are retained. Store journal and
barrier semantics are unchanged. Only private disjoint staging is written.
Old workspace1 records remain readable; older software does not read envelope2.
-/
namespace Lemma.Courses.WorkspaceCodec
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

def magic : UInt64 := 0x3243574b504d454c -- LEMPKWC2
def version : UInt64 := 2
def headerBytes : UInt64 := 96
def maximumBytes : UInt64 := 3808

private def separate (source sourceBytes target targetBytes : UInt64) : UInt64 :=
  if source % 8 = 0 then if target % 8 = 0 then
  if source ≤ 0xffffffffffffffff - sourceBytes then
  if target ≤ 0xffffffffffffffff - targetBytes then
  if source + sourceBytes ≤ target then 1 else if target + targetBytes ≤ source then 1 else 0
  else 0 else 0 else 0 else 0

private def read (address offset : UInt64) : Action := Lemma.User.Memory.read64 (address + offset)
private def write (address offset value : UInt64) : Action := Lemma.User.Memory.write64 (address + offset) value

/-- Header classification alone never validates data or warrants publication.
The caller must read the exact declared object and observe its independent EOF.
Raw workspace1 is admitted for migration on the next ordinary user Save. -/
def recordLength (source : UInt64) : Action :=
  if source % 8 = 0 then if source ≤ 0xffffffffffffffff - 32 then
  .bind (read source 0) fun s tag => if s = 0 then
  if tag = PackageWorkspace.magic then .done 0 PackageWorkspace.bytes else
  if tag = magic then
  .bind (read source 8) fun s v => if s = 0 then if v = version then
  .bind (read source 16) fun s raw => if s = 0 then if raw = PackageWorkspace.bytes then
  .bind (read source 24) fun s length => if s = 0 then
  if headerBytes ≤ length then if length ≤ maximumBytes then if length % 8 = 0 then .done 0 length
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done s 0 else .done malformed 0 else .done s 0
  else .done unsupported 0 else .done s 0
  else .done unsupported 0 else .done s 0
  else .done malformed 0 else .done malformed 0

private def clearStep (i _ : UInt32) (acc output _ _ _ : UInt64) : Action :=
  .bind (write output (i.toUInt64 * 8) 0) fun s _ => .done s acc

private def encodeStep (i _ : UInt32) (nonzero source output _ _ : UInt64) : Action :=
  .bind (read source (i.toUInt64 * 8)) fun s value => if s = 0 then
  if value = 0 then .done 0 nonzero else
  let offset := 32 + i.toUInt64 / 64 * 8
  .bind (read output offset) fun s bits => if s = 0 then
  .bind (write output offset (bits ||| ((1 : UInt64) <<< (i.toUInt64 % 64)))) fun s _ => if s = 0 then
  .bind (write output (headerBytes + nonzero * 8) value) fun s _ =>
  if s = 0 then .done 0 (nonzero + 1) else .done s 0
  else .done s 0 else .done s 0 else .done s 0

/-- Source remains private/immutable throughout this Action. The envelope
magic is written last; partial staging never becomes a Saved acknowledgement.
Caller freezes the resulting bytes through the real append and barrier reply. -/
def encode (source output ns page : UInt64) : Action :=
  if separate source PackageWorkspace.bytes output maximumBytes = 1 then
  .bind (PackageWorkspace.validate source ns page) fun s _ => if s = 0 then
  .boundedFoldU64 12 clearStep 12 0 output 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 464 encodeStep 464 0 source output 0 0 fun s count => if s = 0 then
  let length := headerBytes + count * 8
  .bind (write output 8 version) fun s _ => if s = 0 then
  .bind (write output 16 PackageWorkspace.bytes) fun s _ => if s = 0 then
  .bind (write output 24 length) fun s _ => if s = 0 then
  .bind (write output 0 magic) fun s _ => if s = 0 then .done 0 length else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done malformed 0

private def countStep (i _ : UInt32) (acc source _ _ _ : UInt64) : Action :=
  .bind (read source (32 + i.toUInt64 / 64 * 8)) fun s bits => if s = 0 then
  .done 0 (acc + ((bits >>> (i.toUInt64 % 64)) &&& 1)) else .done s 0

private def decodeStep (i _ : UInt32) (consumed source output available _ : UInt64) : Action :=
  .bind (read source (32 + i.toUInt64 / 64 * 8)) fun s bits => if s = 0 then
  if (bits >>> (i.toUInt64 % 64)) &&& 1 = 0 then
    .bind (write output (i.toUInt64 * 8) 0) fun s _ => .done s consumed
  else if consumed < available then
    .bind (read source (headerBytes + consumed * 8)) fun s value => if s = 0 then
    if value = 0 then .done malformed 0 else
    .bind (write output (i.toUInt64 * 8) value) fun s _ => if s = 0 then .done 0 (consumed + 1) else .done s 0
    else .done s 0
  else .done malformed 0 else .done s 0

/-- Full exact-length/bitmap admission precedes output writes. Decompression
and existing complete workspace/Doc8 validation precede caller publication.
Faults retain actual ordered private-staging effects, without rollback claims.
This function does not read a medium, construct evidence or publish live state. -/
def decode (source storedBytes output ns page : UInt64) : Action :=
  if headerBytes ≤ storedBytes then if storedBytes ≤ maximumBytes then
  if separate source storedBytes output PackageWorkspace.bytes = 1 then
  .bind (read source 0) fun s tag => if s = 0 then if tag = magic then
  .bind (recordLength source) fun s expected => if s = 0 then if expected = storedBytes then
  .bind (read source 88) fun s lastBits => if s = 0 then if lastBits >>> 16 = 0 then
  .boundedFoldU64 464 countStep 464 0 source 0 0 0 fun s count => if s = 0 then
  if count = (storedBytes - headerBytes) / 8 then
  .boundedFoldU64 464 decodeStep 464 0 source output count 0 fun s consumed => if s = 0 then
  if consumed = count then
  .bind (PackageWorkspace.validate output ns page) fun s _ => if s = 0 then .done 0 PackageWorkspace.bytes else .done s 0
  else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done unsupported 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0

private def copyDecodedStep (i _ : UInt32) (copied source output _ _ : UInt64) : Action :=
  .bind (read source (i.toUInt64 * 8)) fun s value => if s = 0 then
  .bind (write output (i.toUInt64 * 8) value) fun s _ =>
  if s = 0 then .done 0 (copied + 8) else .done s 0 else .done s 0

/-- Decode/validate completely in private disjoint scratch, then copy all464
words into the caller's private publication staging. Output may replace the
compressed source only after decode no longer needs it. This is not the Store
sector-copy primitive, whose512-byte bound remains unchanged. Live workspace
adoption and any actual journal/barrier acknowledgement remain caller duties. -/
def restore (source storedBytes scratch output ns page : UInt64) : Action :=
  if separate scratch PackageWorkspace.bytes output PackageWorkspace.bytes = 1 then
  .bind (decode source storedBytes scratch ns page) fun s _ => if s = 0 then
  .boundedFoldU64 464 copyDecodedStep 464 0 scratch output 0 0 fun s copied =>
  if s = 0 then if copied = PackageWorkspace.bytes then .done 0 copied else .done malformed 0
  else .done s 0 else .done s 0 else .done malformed 0

end Lemma.Courses.WorkspaceCodec
