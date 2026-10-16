import Lemma.Courses.PackageTarget

/-! `lemma-course-reader-location/1` is browsing provenance only. Its separate
object can name any validated instructional node, including explanations and
review material. It never changes a submission, creates a checking selection,
or supplies evidence. The package CRC binds source/edition/rights bytes; CRC
is corruption detection, not authentication or a rights grant.

Layout (128 bytes): magic/version/namespace/page/package/edition/CRC/node/
source-anchor/reader-revision, followed by six reserved zero words. A reader
revision is not a Store durability receipt. Callers must retain staged bytes
until the real journal/barrier acknowledges them. Old workspace formats and
all historical reader paths remain unchanged. -/
namespace Lemma.Courses.ReaderLocation
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

def magic : UInt64 := 0x31524452434d454c
def version : UInt64 := 1
def bytes : UInt64 := 128
def maximumRevision : UInt64 := 0x7fffffffffffffff
def object (page : UInt64) : UInt64 := 0x5244000000000000 ||| page

private def read (buffer offset : UInt64) : Action := Lemma.User.Memory.read64 (buffer + offset)
private def write (buffer offset value : UInt64) : Action := Lemma.User.Memory.write64 (buffer + offset) value
private def shape (buffer ns page : UInt64) : UInt64 :=
  if buffer % 8 = 0 then if buffer ≤ 0xffffffffffffffff - bytes then
  if 0 < ns then if ns ≤ 2 then if 0 < page then if page ≤ 64 then 1 else 0 else 0
  else 0 else 0 else 0 else 0

private def clearStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (write buffer (8 + i.toUInt64 * 8) 0) fun s _ => .done s acc

/-- Validate the actual complete package before writing disjoint private
staging. Source fields and node identity are read before publication begins;
an access fault leaves an unpublished partial record, never an acknowledgement.
All node kinds are admitted for reading; none gains mathematical authority. -/
def capture (buffer package length ordinal ns page revision : UInt64) : Action :=
  if shape buffer ns page = 1 then
  if revision = 0 then .done malformed 0 else if maximumRevision < revision then .done resourceLimit 0 else
  if package ≤ 0xffffffffffffffff - length then
  if (if buffer + bytes ≤ package then (1 : UInt64) else if package + length ≤ buffer then 1 else 0) = 1 then
  .bind (PackageTarget.select package length ordinal) fun s entry => if s = 0 then
  .bind (read package 24) fun s identity => if s = 0 then
  .bind (read package 32) fun s edition => if s = 0 then
  .bind (read package 80) fun s crc => if s = 0 then
  .bind (read entry 0) fun s node => if s = 0 then
  .bind (read entry 64) fun s anchor => if s = 0 then
  .bind (write buffer 0 0) fun s _ => if s = 0 then
  .boundedFoldU64 15 clearStep 15 0 buffer 0 0 0 fun s _ => if s = 0 then
  .bind (write buffer 8 version) fun s _ => if s = 0 then
  .bind (write buffer 16 ns) fun s _ => if s = 0 then
  .bind (write buffer 24 page) fun s _ => if s = 0 then
  .bind (write buffer 32 identity) fun s _ => if s = 0 then
  .bind (write buffer 40 edition) fun s _ => if s = 0 then
  .bind (write buffer 48 crc) fun s _ => if s = 0 then
  .bind (write buffer 56 node) fun s _ => if s = 0 then
  .bind (write buffer 64 anchor) fun s _ => if s = 0 then
  .bind (write buffer 72 revision) fun s _ => if s = 0 then
  .bind (write buffer 0 magic) fun s _ => if s = 0 then .done 0 node else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0

private def reservedStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (read buffer (80 + i.toUInt64 * 8)) fun s value => if s = 0 then
  if value = 0 then .done 0 acc else .done malformed 0 else .done s 0

/-- A valid location is still only browsing metadata. It does not validate an
installed package, authorize a goal, or assert that this record was saved.
Every error returns zero, never a partly validated selected node. -/
def validate (buffer ns page : UInt64) : Action :=
  if shape buffer ns page = 1 then
  .bind (read buffer 0) fun s tag => if s = 0 then
  .bind (read buffer 8) fun s v => if s = 0 then
  if tag = magic then if v = version then
  .bind (read buffer 16) fun s actualNS => if s = 0 then
  .bind (read buffer 24) fun s actualPage => if s = 0 then
  if actualNS = ns then if actualPage = page then
  .bind (read buffer 32) fun s identity => if s = 0 then
  .bind (read buffer 40) fun s edition => if s = 0 then
  .bind (read buffer 48) fun s crc => if s = 0 then
  .bind (read buffer 56) fun s node => if s = 0 then
  .bind (read buffer 64) fun s anchor => if s = 0 then
  .bind (read buffer 72) fun s revision => if s = 0 then
  if identity = 0 then .done malformed 0 else if maximumIdentity < identity then .done malformed 0 else
  if edition = 0 then .done malformed 0 else if maximumEdition < edition then .done malformed 0 else
  if 0xffffffff < crc then .done malformed 0 else
  if node = 0 then .done malformed 0 else if maximumEntries < node then .done malformed 0 else
  if anchor = node then
  if revision = 0 then .done malformed 0 else if maximumRevision < revision then .done resourceLimit 0 else
  .boundedFoldU64 6 reservedStep 6 0 buffer 0 0 0 fun s _ => .done s (if s = 0 then node else 0)
  else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done s 0 else .done s 0
  else .done unsupported 0 else .done malformed 0 else .done s 0 else .done s 0
  else .done malformed 0

/-- Recheck the complete current immutable package and exact node. A stale
edition/content/anchor is absent browsing context, not Invalid mathematics.
No byte of the record, package or mathematical workspace is written. -/
def resolve (buffer ns page package length : UInt64) : Action :=
  .bind (validate buffer ns page) fun s node => if s = 0 then
  .bind (PackageTarget.select package length (node - 1)) fun s entry => if s = 0 then
  .bind (read package 24) fun s identity => if s = 0 then
  .bind (read buffer 32) fun s savedIdentity => if s = 0 then
  .bind (read package 32) fun s edition => if s = 0 then
  .bind (read buffer 40) fun s savedEdition => if s = 0 then
  .bind (read package 80) fun s crc => if s = 0 then
  .bind (read buffer 48) fun s savedCRC => if s = 0 then
  .bind (read entry 64) fun s anchor => if s = 0 then
  .bind (read buffer 64) fun s savedAnchor => if s = 0 then
  if identity = savedIdentity then if edition = savedEdition then if crc = savedCRC then
  if anchor = savedAnchor then .done 0 node else .done selectionAbsent 0
  else .done selectionAbsent 0 else .done selectionAbsent 0 else .done selectionAbsent 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

end Lemma.Courses.ReaderLocation
