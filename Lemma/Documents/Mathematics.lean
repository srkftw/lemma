import Lemma.User.Memory
import Lemma.Mathematics.Exact

/-! `lemma-mathematical-submission/1`: typed answers and evidence are separate
from immutable raw ink. The ordinary store retains this exact 832-byte record.
Eight immutable attempt entries preserve earlier evidence when answers change.
This is a bounded original course package, not an imported proof environment. -/
namespace Lemma.Documents.Mathematics
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Mathematics

def magic : UInt64 := 0x314854414d4d454c
def packageIdentity : UInt64 := 0x0001000000000001
def bytes : UInt64 := 832
def object (page : UInt64) : UInt64 := 0x8000 + page
def field (buffer offset : UInt64) : Action := Memory.read64 (buffer + offset)
def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer + offset) value

private def copyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  let offset := i.toUInt64 * 8
  .bind (field source offset) fun s value => if s = 0 then
  .bind (put target offset value) fun s _ => .done s (acc + 8) else .done s 0

/-- Preserve the complete record in its owned immutable transaction buffer.
The generic store transport copy is sector-bounded; this record is832 bytes. -/
def copy (source target : UInt64) : Action :=
  if source % 8 = 0 then if target % 8 = 0 then
  if source ≤ 0xffffffffffffffff - bytes then if target ≤ 0xffffffffffffffff - bytes then
  .boundedFoldU64 104 copyStep 104 0 source target 0 0 fun s copied => .done s copied
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0

private def zeroStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (put buffer (i.toUInt64 * 8) 0) fun s _ => .done s acc

def create (buffer ns page : UInt64) : Action :=
  if ns = 0 then .done 234 0 else if 2 < ns then .done 234 0 else
  if page = 0 then .done 234 0 else if 64 < page then .done 234 0 else
  .boundedFoldU64 104 zeroStep 104 0 buffer 0 0 0 fun s _ => if s = 0 then
  .bind (put buffer 0 magic) fun s _ => if s = 0 then
  .bind (put buffer 8 1) fun s _ => if s = 0 then
  .bind (put buffer 16 packageIdentity) fun s _ => if s = 0 then
  .bind (put buffer 24 ns) fun s _ => if s = 0 then
  .bind (put buffer 32 page) fun s _ => if s = 0 then
  .bind (put buffer 40 1) fun s _ => if s = 0 then
  .bind (put buffer 48 1) fun s _ => if s = 0 then
  .bind (put buffer 64 1) fun s _ => if s = 0 then
  .bind (put buffer 112 Exact.checkerIdentity) fun s _ => if s = 0 then
  .bind (put buffer 120 1) fun s _ => if s = 0 then
  .bind (put buffer 136 8) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

def result (goal n d p0 p1 p2 budget : UInt64) : UInt64 :=
  if goal = 1 then Exact.rational 1 2 1 3 n d budget else
  if goal = 2 then Exact.polynomial 1 1 1 1 p0 p1 p2 budget else Exact.unsupported

/-- Each edit invalidates current applicability while retaining attempt history.
The bounded UI uses nonnegative integer coefficients 0..99, a proper subset of
the checker domain; no interpretation is inferred from ink. -/
def revise (buffer : UInt64) : Action :=
  .bind (field buffer 40) fun s revision => if s = 0 then
  if 0x7ffffffffffffffe ≤ revision then .done 235 0 else
  .bind (put buffer 40 (revision + 1)) fun s _ => if s = 0 then
  .bind (put buffer 96 0) fun s _ => if s = 0 then
  .bind (put buffer 104 0) fun s _ => .done s (revision + 1)
  else .done s 0 else .done s 0 else .done s 0

def edit (buffer offset operation : UInt64) : Action :=
  if offset < 56 then .done 234 0 else if 88 < offset then .done 234 0 else
  if offset % 8 = 0 then
  .bind (field buffer offset) fun s value => if s = 0 then
  let next := if operation = 0 then (if value = 0 then 0 else value - 1) else
    if operation = 1 then (if value < 99 then value + 1 else value) else value
  if next = value then .done 0 0 else
  .bind (revise buffer) fun s _ => if s = 0 then put buffer offset next else .done s 0
  else .done s 0 else .done 234 0

private def historyStep (i _ : UInt32) (acc buffer entry _ _ : UInt64) : Action :=
  let offset := i.toUInt64 * 8
  let source := if offset = 0 then 40 else if offset = 8 then 48 else
    if offset < 56 then offset + 40 else if offset = 56 then 96 else 136
  .bind (field buffer source) fun s value => if s = 0 then
  .bind (put entry offset value) fun s _ => .done s acc else .done s 0

/-- A genuine check is a scalar algorithm over the user's current typed values.
History exhaustion reports Indeterminate without replacing older entries. -/
def submit (buffer : UInt64) : Action :=
  .bind (field buffer 48) fun s goal => if s = 0 then
  .bind (field buffer 56) fun s n => if s = 0 then
  .bind (field buffer 64) fun s d => if s = 0 then
  .bind (field buffer 72) fun s p0 => if s = 0 then
  .bind (field buffer 80) fun s p1 => if s = 0 then
  .bind (field buffer 88) fun s p2 => if s = 0 then
  .bind (field buffer 136) fun s budget => if s = 0 then
  .bind (field buffer 144) fun s attempts => if s = 0 then
  .bind (field buffer 40) fun s revision => if s = 0 then
  let outcome := if attempts < 8 then result goal n d p0 p1 p2 budget else Exact.indeterminate
  .bind (put buffer 96 outcome) fun s _ => if s = 0 then
  .bind (put buffer 104 revision) fun s _ => if s = 0 then
  .bind (put buffer 168 (if outcome = Exact.verified then 2 else if outcome = Exact.invalid then 1 else 3)) fun s _ => if s = 0 then
  .bind (if attempts < 8 then
    .boundedFoldU64 9 historyStep 9 0 buffer (buffer + 256 + attempts * 72) 0 0 fun s _ =>
      if s = 0 then put buffer 144 (attempts + 1) else .done s 0
    else .done 0 0) fun s _ => .done s outcome
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Assistance is explicit and durable. This is an authored local course hint,
not a model response or a trusted mathematical result. -/
def hint (buffer : UInt64) : Action :=
  .bind (field buffer 152) fun s count => if s = 0 then
  if count < 32 then put buffer 152 (count + 1) else .done 235 0 else .done s 0

private def validateOperandStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (field buffer (56 + i.toUInt64 * 8)) fun s value => if s = 0 then
  if 99 < value then .done 234 0 else .done 0 acc else .done s 0

private def validateReservedStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (field buffer (176 + i.toUInt64 * 8)) fun s value => if s = 0 then
  if value = 0 then .done 0 acc else .done 234 0 else .done s 0

private def validateHistoryStep (i _ : UInt32) (acc buffer count revision _ : UInt64) : Action :=
  let entry := buffer + 256 + i.toUInt64 * 72
  .bind (field entry 0) fun s oldRevision => if s = 0 then
  .bind (field entry 8) fun s goal => if s = 0 then
  .bind (field entry 16) fun s n => if s = 0 then
  .bind (field entry 24) fun s d => if s = 0 then
  .bind (field entry 32) fun s p0 => if s = 0 then
  .bind (field entry 40) fun s p1 => if s = 0 then
  .bind (field entry 48) fun s p2 => if s = 0 then
  .bind (field entry 56) fun s outcome => if s = 0 then
  .bind (field entry 64) fun s budget => if s = 0 then
  if i.toUInt64 < count then
    if oldRevision = 0 then .done 234 0 else if revision < oldRevision then .done 234 0 else
    if goal = 0 then .done 234 0 else if 3 < goal then .done 234 0 else
    if 99 < n then .done 234 0 else if 99 < d then .done 234 0 else
    if 99 < p0 then .done 234 0 else if 99 < p1 then .done 234 0 else if 99 < p2 then .done 234 0 else
    if budget = 0 then if outcome = result goal n d p0 p1 p2 budget then .done 0 acc else .done 234 0 else
    if budget = 8 then
    if outcome = result goal n d p0 p1 p2 budget then .done 0 acc else .done 234 0
    else .done 234 0
  else if oldRevision ||| goal ||| n ||| d ||| p0 ||| p1 ||| p2 ||| outcome ||| budget = 0 then .done 0 acc else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Unknown/malformed records reject; they never initialize a replacement.
Current applicable evidence is recomputed against the precise original goal. -/
def validate (buffer ns page : UInt64) : Action :=
  .bind (field buffer 0) fun s value => if s = 0 then
  if value = magic then
  .bind (field buffer 8) fun s value => if s = 0 then
  if value = 1 then
  .bind (field buffer 16) fun s value => if s = 0 then
  if value = packageIdentity then
  .bind (field buffer 24) fun s value => if s = 0 then
  if value = ns then
  .bind (field buffer 32) fun s value => if s = 0 then
  if value = page then
  .bind (field buffer 40) fun s revision => if s = 0 then
  if revision = 0 then .done 234 0 else if 0x7ffffffffffffffe < revision then .done 234 0 else
  .bind (field buffer 48) fun s goal => if s = 0 then
  if goal = 0 then .done 234 0 else if 3 < goal then .done 234 0 else
  .bind (field buffer 96) fun s outcome => if s = 0 then
  if 5 < outcome then .done 234 0 else
  .bind (field buffer 104) fun s evidenceRevision => if s = 0 then
  if outcome = 0 then if evidenceRevision = 0 then validateTail buffer revision goal outcome else .done 234 0 else
  if evidenceRevision = revision then validateTail buffer revision goal outcome else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 234 0 else .done s 0 else .done 234 0 else .done s 0
  else .done 234 0 else .done s 0 else .done 234 0 else .done s 0
  else .done 234 0 else .done s 0
where
  validateTail (buffer revision goal outcome : UInt64) : Action :=
    .bind (field buffer 112) fun s environment => if s = 0 then
    if environment = Exact.checkerIdentity then
    .bind (field buffer 120) fun s domain => if s = 0 then
    if domain = goal then
    .bind (field buffer 128) fun s assumptions => if s = 0 then
    if assumptions = 0 then
    .bind (field buffer 136) fun s budget => if s = 0 then
    if budget = 0 then validateRest buffer revision goal outcome budget else
    if budget = 8 then validateRest buffer revision goal outcome budget else .done 234 0
    else .done s 0 else .done 234 0 else .done s 0
    else .done 234 0 else .done s 0 else .done 234 0 else .done s 0
  validateRest (buffer revision goal outcome budget : UInt64) : Action :=
    .bind (field buffer 144) fun s attempts => if s = 0 then
    if 8 < attempts then .done 234 0 else
    .bind (field buffer 152) fun s hints => if s = 0 then
    if 32 < hints then .done 234 0 else
    .bind (field buffer 56) fun s n => if s = 0 then
    .bind (field buffer 64) fun s d => if s = 0 then
    .bind (field buffer 72) fun s p0 => if s = 0 then
    .bind (field buffer 80) fun s p1 => if s = 0 then
    .bind (field buffer 88) fun s p2 => if s = 0 then
    if outcome = 0 then validateBounds buffer attempts revision else
    if outcome = 5 then if attempts = 8 then validateBounds buffer attempts revision else
      if result goal n d p0 p1 p2 budget = outcome then validateBounds buffer attempts revision else .done 234 0
    else if result goal n d p0 p1 p2 budget = outcome then validateBounds buffer attempts revision else .done 234 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
    else .done s 0 else .done s 0 else .done s 0
  validateBounds (buffer attempts revision : UInt64) : Action :=
    .bind (field buffer 160) fun s selected => if s = 0 then
    if (if selected = 0 then true else if selected = 56 then true else if selected = 64 then true else
      if selected = 72 then true else if selected = 80 then true else if selected = 88 then true else false) = true then
    .bind (field buffer 168) fun s recommendation => if s = 0 then
    if 3 < recommendation then .done 234 0 else
    .boundedFoldU64 10 validateReservedStep 10 0 buffer 0 0 0 fun s _ => if s = 0 then
    .boundedFoldU64 5 validateOperandStep 5 0 buffer 0 0 0 fun s _ => if s = 0 then
    .boundedFoldU64 8 validateHistoryStep 8 0 buffer attempts revision 0 fun s _ => .done s 0
    else .done s 0 else .done s 0 else .done s 0 else .done 234 0 else .done s 0

end Lemma.Documents.Mathematics
