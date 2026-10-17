import Lemma.Courses.PackageTarget

/-! `lemma-course-selection-binding/1` is128 bytes of provenance, never proof
evidence. It supplements, rather than replaces, the mathematical document's
original builtin goal/checker/environment identity. Layout: magic0/version8/
package16/edition24/CRC32/node40/sourceAnchor48/kind56/goal64/checker72/domain80/
assumptions88/budget96/sourceTextSpan104/rightsTextSpan112/submissionRevision120.
The checksum binds the full immutable package bytes including its source and
rights text. Spans are offsets/lengths inside that package, not host pointers.

Capture writes an unpublished, disjoint caller-owned staging binding. Only a
successful capture permits publication; an access fault never creates evidence.
After publication its bytes and the validated package stay immutable. Keeping
one binding per actual attempt preserves historical provenance when a selected
lesson or submission is edited. `applicable` reports applicability only, not
Verified: actual guest checker results/versions/resources remain mandatory. -/
namespace Lemma.Courses.PackageBinding
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

def magic : UInt64 := 0x31444e494253434c
def version : UInt64 := 1
def bytes : UInt64 := 128

private def word (address offset : UInt64) : Action := Lemma.User.Memory.read64 (address + offset)
private def put (address offset value : UInt64) : Action := Lemma.User.Memory.write64 (address + offset) value
private def spanValid (value : UInt64) : UInt64 :=
  if 0 < spanLength value then if spanLength value ≤ maximumFieldBytes then
  if spanOffset value ≤ maximumBytes then if spanLength value ≤ maximumBytes - spanOffset value then 1 else 0
  else 0 else 0 else 0

private def captureField (i _ : UInt32) (acc binding package entry _ : UInt64) : Action :=
  let index := i.toUInt64
  let source := if index < 3 then package else if index < 11 then entry else package
  let offset := if index = 0 then 24 else if index = 1 then 32 else if index = 2 then 80 else
    if index = 3 then 0 else if index = 4 then 64 else if index = 5 then 8 else
    if index = 6 then 16 else if index = 7 then 24 else if index = 8 then 32 else
    if index = 9 then 40 else if index = 10 then 72 else if index = 11 then 104 else 120
  .bind (word source offset) fun s value => if s = 0 then
  .bind (put binding (16 + index * 8) value) fun s _ => .done s acc else .done s 0

/-- Only exercise nodes with the currently admitted exact goal1/2 may create
a checking-selection binding. Unsupported/author text does not change a goal.
The revision comes from the original submitted object and must be nonzero. -/
def capture (binding package length ordinal revision : UInt64) : Action :=
  if binding % 8 = 0 then if binding ≤ 0xffffffffffffffff - bytes then
  if package ≤ 0xffffffffffffffff - length then
  if (if binding + bytes ≤ package then (1 : UInt64) else if package + length ≤ binding then 1 else 0) = 1 then
  if revision = 0 then .done malformed 0 else if 0x7fffffffffffffff < revision then .done resourceLimit 0 else
  .bind (PackageTarget.select package length ordinal) fun s entry => if s = 0 then
  .bind (word entry 8) fun s kind => if s = 0 then
  .bind (word entry 16) fun s goal => if s = 0 then
  if kind = 3 then if (if goal = 1 then (1 : UInt64) else if goal = 2 then 1 else 0) = 1 then
  .bind (put binding 0 0) fun s _ => if s = 0 then
  .bind (put binding 8 version) fun s _ => if s = 0 then
  .boundedFoldU64 13 captureField 13 0 binding package entry 0 fun s _ => if s = 0 then
  .bind (put binding 120 revision) fun s _ => if s = 0 then
  .bind (put binding 0 magic) fun s _ => if s = 0 then .done 0 (ordinal + 1) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done unsupported 0 else .done unsupported 0
  else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0 else .done malformed 0

private def fieldsValid (binding : UInt64) : Action :=
  .bind (word binding 16) fun s identity => if s = 0 then
  .bind (word binding 24) fun s edition => if s = 0 then
  .bind (word binding 32) fun s crc => if s = 0 then
  .bind (word binding 40) fun s node => if s = 0 then
  .bind (word binding 48) fun s anchor => if s = 0 then
  .bind (word binding 56) fun s kind => if s = 0 then
  .bind (word binding 64) fun s goal => if s = 0 then
  .bind (word binding 72) fun s checker => if s = 0 then
  .bind (word binding 80) fun s domain => if s = 0 then
  .bind (word binding 88) fun s assumptions => if s = 0 then
  .bind (word binding 96) fun s budget => if s = 0 then
  .bind (word binding 104) fun s source => if s = 0 then
  .bind (word binding 112) fun s rights => if s = 0 then
  .bind (word binding 120) fun s revision => if s = 0 then
  if identity = 0 then .done malformed 0 else if maximumIdentity < identity then .done malformed 0 else
  if edition = 0 then .done malformed 0 else if maximumEdition < edition then .done malformed 0 else
  if 0xffffffff < crc then .done malformed 0 else
  if node = 0 then .done malformed 0 else if maximumEntries < node then .done malformed 0 else
  if anchor = node then if kind = 3 then
  if (if goal = 1 then (1 : UInt64) else if goal = 2 then 1 else 0) = 1 then
  if referenceStatus kind goal checker domain assumptions budget = 0 then
  if spanValid source = 1 then if spanValid rights = 1 then
  if revision = 0 then .done malformed 0 else if 0x7fffffffffffffff < revision then .done resourceLimit 0 else .done 0 goal
  else .done malformed 0 else .done malformed 0
  else .done (referenceStatus kind goal checker domain assumptions budget) 0
  else .done unsupported 0 else .done unsupported 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def validate (binding : UInt64) : Action :=
  if binding % 8 = 0 then if binding ≤ 0xffffffffffffffff - bytes then
  .bind (word binding 0) fun s tag => if s = 0 then
  .bind (word binding 8) fun s observedVersion => if s = 0 then
  if tag = magic then if observedVersion = version then fieldsValid binding
  else .done unsupported 0 else .done malformed 0
  else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0

/-- Exact applicability to the submitted revision/goal/domain/assumptions.
False retains the old binding and is not an Invalid mathematical result. -/
def applicable (binding revision goal domain assumptions : UInt64) : Action :=
  .bind (validate binding) fun s actualGoal => if s = 0 then
  .bind (word binding 80) fun s actualDomain => if s = 0 then
  .bind (word binding 88) fun s actualAssumptions => if s = 0 then
  .bind (word binding 120) fun s actualRevision => if s = 0 then
  if actualRevision = revision then if actualGoal = goal then if actualDomain = domain then
  if actualAssumptions = assumptions then .done 0 1 else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

end Lemma.Courses.PackageBinding
