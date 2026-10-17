import Lemma.Courses.PackageFormat
import Lemma.User.Memory

/-! Guest course-package decoder. Every read is an ordinary checked User
access. Validation is observational: no allocation, write, checker invocation,
document change or storage completion occurs. A selection is a borrowed address
inside the caller's complete, unchanged private package buffer. It must not be
retained across a mutation of that buffer. -/
namespace Lemma.Courses.PackageTarget
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

private def word (address offset : UInt64) : Action := Lemma.User.Memory.read64 (address + offset)

private def crcStep (i _ : UInt32) (state address _ _ _ : UInt64) : Action :=
  let offset := i.toUInt64
  if 80 ≤ offset then if offset < 96 then .done 0 (crcByte state 0) else
    .bind (Lemma.User.Memory.read8 (address + offset)) fun s byte =>
    if s = 0 then .done 0 (crcByte state byte) else .done s 0
  else
    .bind (Lemma.User.Memory.read8 (address + offset)) fun s byte =>
    if s = 0 then .done 0 (crcByte state byte) else .done s 0

private def textStep (i _ : UInt32) (cursor address offset _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read8 (address + offset + i.toUInt64)) fun s byte =>
  if s = 0 then if textByteValid byte = 1 then .done 0 cursor else .done unsupported 0 else .done s 0

private def validateSpan (address bytes descriptor cursor required : UInt64) : Action :=
  let offset := spanOffset descriptor
  let length := spanLength descriptor
  if offset = cursor then
  if maximumFieldBytes < length then .done resourceLimit 0 else
  if length = 0 then if required = 1 then .done malformed 0 else .done 0 cursor else
  if offset ≤ bytes then if length ≤ bytes - offset then
    .boundedFoldU64 512 textStep length.toUInt32 (cursor + length) address offset 0 0 fun s next => .done s next
  else .done malformed 0 else .done malformed 0
  else .done malformed 0

private def headerTextStep (i _ : UInt32) (cursor address bytes _ _ : UInt64) : Action :=
  .bind (word address (96 + i.toUInt64 * 8)) fun s descriptor =>
  if s = 0 then validateSpan address bytes descriptor cursor 1 else .done s 0

private def entryTextStep (i _ : UInt32) (cursor address bytes entry kind : UInt64) : Action :=
  let field := i.toUInt64
  .bind (word entry (112 + field * 8)) fun s descriptor => if s = 0 then
  let required := if field = 0 then (1 : UInt64) else if field = 1 then 1 else if field = 6 then 1 else
    if kind = 3 then if field = 4 then 1 else 0 else 0
  validateSpan address bytes descriptor cursor required else .done s 0

private def reservedStep (i _ : UInt32) (cursor entry _ _ _ : UInt64) : Action :=
  let offset := if i < 4 then 80 + i.toUInt64 * 8 else 176 + (i.toUInt64 - 4) * 8
  .bind (word entry offset) fun s value =>
  if s = 0 then if value = 0 then .done 0 cursor else .done malformed 0 else .done s 0

private def validateEntry (address bytes ordinal cursor : UInt64) : Action :=
  let entry := address + headerBytes + ordinal * entryBytes
  .bind (word entry 0) fun s identity => if s = 0 then
  if identity = ordinal + 1 then
  .bind (word entry 8) fun s kind => if s = 0 then
  .bind (word entry 16) fun s goal => if s = 0 then
  .bind (word entry 24) fun s checker => if s = 0 then
  .bind (word entry 32) fun s domain => if s = 0 then
  .bind (word entry 40) fun s assumptions => if s = 0 then
  .bind (word entry 48) fun s logical => if s = 0 then
  .bind (word entry 56) fun s pedagogical => if s = 0 then
  .bind (word entry 64) fun s anchor => if s = 0 then
  .bind (word entry 72) fun s budget => if s = 0 then
  let reference := referenceStatus kind goal checker domain assumptions budget
  if reference = 0 then
  if prerequisitesValid logical ordinal = 1 then if prerequisitesValid pedagogical ordinal = 1 then
  if anchor = identity then
  .boundedFoldU64 6 reservedStep 6 cursor entry 0 0 0 fun s next => if s = 0 then
  .boundedFoldU64 8 entryTextStep 8 next address bytes entry kind fun s finalCursor => .done s finalCursor
  else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done reference 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0

private def entryStep (i _ : UInt32) (cursor address bytes _ _ : UInt64) : Action :=
  validateEntry address bytes i.toUInt64 cursor

private def validateBody (address bytes count textOffset expected : UInt64) : Action :=
  .boundedFoldU64 32768 crcStep bytes.toUInt32 0xffffffff address 0 0 0 fun s state => if s = 0 then
  if (state ^^^ 0xffffffff) = expected then
  .boundedFoldU64 4 headerTextStep 4 textOffset address bytes 0 0 fun s cursor => if s = 0 then
  .boundedFoldU64 16 entryStep count.toUInt32 cursor address bytes 0 0 fun s finalCursor => if s = 0 then
  if finalCursor = bytes then .done 0 count else .done malformed 0
  else .done s 0 else .done s 0
  else .done integrityFailure 0 else .done s 0

/-- Validate the full canonical image before selection. Error precedence is
arguments, magic/version, header shape/resources, CRC, text/entry order. An
unknown mandatory version/reference remains Unsupported. Every real access
failure keeps its original status and terminates the read prefix. -/
def validate (address bytes : UInt64) : Action :=
  if bytes < headerBytes then .done malformed 0 else
  if maximumBytes < bytes then .done resourceLimit 0 else
  if address % 8 = 0 then if address ≤ 0xffffffffffffffff - bytes then
  .bind (word address 0) fun s observedMagic => if s = 0 then
  if observedMagic = magic then
  .bind (word address 8) fun s observedVersion => if s = 0 then
  if observedVersion = version then
  .bind (word address 16) fun s total => if s = 0 then
  .bind (word address 24) fun s identity => if s = 0 then
  .bind (word address 32) fun s edition => if s = 0 then
  .bind (word address 40) fun s count => if s = 0 then
  .bind (word address 48) fun s rowBytes => if s = 0 then
  .bind (word address 56) fun s entriesOffset => if s = 0 then
  .bind (word address 64) fun s textOffset => if s = 0 then
  .bind (word address 72) fun s textBytes => if s = 0 then
  .bind (word address 80) fun s crc => if s = 0 then
  .bind (word address 88) fun s inverse => if s = 0 then
  if total = bytes then
  if identity = 0 then .done malformed 0 else if maximumIdentity < identity then .done malformed 0 else
  if edition = 0 then .done malformed 0 else if maximumEdition < edition then .done malformed 0 else
  if count = 0 then .done malformed 0 else if maximumEntries < count then .done resourceLimit 0 else
  if rowBytes = entryBytes then if entriesOffset = headerBytes then
  if textOffset = headerBytes + count * entryBytes then
  if maximumTextBytes < textBytes then .done resourceLimit 0 else
  if textOffset ≤ bytes then if textBytes = bytes - textOffset then
  if crc ≤ 0xffffffff then if inverse = (crc ^^^ 0xffffffff) then
    validateBody address bytes count textOffset crc
  else .done integrityFailure 0 else .done integrityFailure 0
  else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done unsupported 0 else .done s 0
  else .done malformed 0 else .done s 0
  else .done malformed 0 else .done malformed 0

/-- Borrow one validated node. The ordinal is zero based; selected node/source
anchor identity is ordinal+1. This never changes a submitted mathematical goal. -/
def select (address bytes ordinal : UInt64) : Action :=
  .bind (validate address bytes) fun s count => if s = 0 then
  if ordinal < count then .done 0 (address + headerBytes + ordinal * entryBytes)
  else .done selectionAbsent 0 else .done s 0

/-- A package can request only the pinned current goal reference. The caller
must bind package identity, edition, checksum and node anchor to any future
document evidence; this read alone creates no evidence. -/
def goal (address bytes ordinal : UInt64) : Action :=
  .bind (select address bytes ordinal) fun s entry => if s = 0 then word entry 16 else .done s 0

def character (address bytes ordinal role position : UInt64) : Action :=
  if role < 8 then
  .bind (select address bytes ordinal) fun s entry => if s = 0 then
  .bind (word entry (112 + role * 8)) fun s descriptor => if s = 0 then
  if position < spanLength descriptor then Lemma.User.Memory.read8 (address + spanOffset descriptor + position)
  else .done selectionAbsent 0 else .done s 0 else .done s 0
  else .done unsupported 0

end Lemma.Courses.PackageTarget
