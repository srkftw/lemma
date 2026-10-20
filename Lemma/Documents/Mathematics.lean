import Lemma.User.Memory
import Lemma.Mathematics.OwnedSubmission
import Lemma.Mathematics.ExecutionIdentity
import Lemma.Mathematics.ExecutionIdentityV2
import Lemma.Mathematics.ExecutionIdentityV4
import Lemma.Mathematics.ExecutionIdentityV3

/-! Typed answers and evidence remain separate from immutable raw ink.
Historical832/1856-byte records retain their exact semantic layouts. The
additive2496-byte submission/3 stores separately versioned execution identities
for new isolated replies; migrated historical execution identities are Unknown.
Every record retains eight immutable attempts and64 ordered learner events. This is a bounded original course package, not an
imported proof environment or evidence of mathematical understanding. -/
namespace Lemma.Documents.Mathematics
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Mathematics

def magic : UInt64 := 0x314854414d4d454c
def packageIdentity : UInt64 := 0x0001000000000001
def legacyBytes : UInt64 := 832
def bytes : UInt64 := 1856
def currentBytes : UInt64 := 2496
def policyIdentity : UInt64 := 0x0001000000000001
def object (page : UInt64) : UInt64 := 0x8000 + page
def field (buffer offset : UInt64) : Action := Memory.read64 (buffer + offset)
def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer + offset) value

/-- Ordered learner events share the existing durable submission transaction.
Capacity is checked before any operation changes the submission or policy. -/
def eventCapacity (buffer : UInt64) : Action :=
  .bind (field buffer 192) fun s count => if s = 0 then
  if count < 64 then .done 0 count else .done 235 0 else .done s 0

def appendEvent (buffer kind value index : UInt64) : Action :=
  .bind (eventCapacity buffer) fun s count => if s = 0 then
  .bind (field buffer 40) fun s revision => if s = 0 then
  .bind (field buffer 48) fun s goal => if s = 0 then
  let entry := buffer + legacyBytes + count * 16
  .bind (put entry 0 revision) fun s _ => if s = 0 then
  .bind (put entry 8 (kind ||| (goal <<< 8) ||| (value <<< 16) ||| (index <<< 24))) fun s _ => if s = 0 then
  put buffer 192 (count + 1)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- REVIEW cycles explicit manual choices and disable; AUTO is restored after
disable. Policy changes never change the submitted goal or trusted evidence. -/
def reviewMode (buffer : UInt64) : Action :=
  .bind (eventCapacity buffer) fun s _ => if s = 0 then
  .bind (field buffer 184) fun s mode => if s = 0 then
  let next := (mode + 1) % 5
  .bind (put buffer 184 next) fun s _ => if s = 0 then
  .bind (put buffer 216 1) fun s _ => if s = 0 then appendEvent buffer 3 next 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

private def copyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  let offset := i.toUInt64 * 8
  .bind (field source offset) fun s value => if s = 0 then
  .bind (put target offset value) fun s _ => .done s (acc + 8) else .done s 0

/-- Preserve the complete record in its owned immutable transaction buffer.
The generic store transport copy is sector-bounded; this record is1856 bytes. -/
def copy (source target : UInt64) : Action :=
  if source % 8 = 0 then if target % 8 = 0 then
  if source ≤ 0xffffffffffffffff - bytes then if target ≤ 0xffffffffffffffff - bytes then
  .boundedFoldU64 232 copyStep 232 0 source target 0 0 fun s copied => .done s copied
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0

/-- The v3 transaction copy includes every active and historical execution
identity. Historical1856-byte copy retains its original separate interface. -/
def copyCurrent (source target : UInt64) : Action :=
  if source % 8 = 0 then if target % 8 = 0 then
  if source ≤ 0xffffffffffffffff - currentBytes then if target ≤ 0xffffffffffffffff - currentBytes then
  .boundedFoldU64 312 copyStep 312 0 source target 0 0 fun s copied => .done s copied
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0

private def zeroStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (put buffer (i.toUInt64 * 8) 0) fun s _ => .done s acc

def create (buffer ns page : UInt64) : Action :=
  if ns = 0 then .done 234 0 else if 2 < ns then .done 234 0 else
  if page = 0 then .done 234 0 else if 64 < page then .done 234 0 else
  .boundedFoldU64 232 zeroStep 232 0 buffer 0 0 0 fun s _ => if s = 0 then
  .bind (put buffer 0 magic) fun s _ => if s = 0 then
  .bind (put buffer 8 2) fun s _ => if s = 0 then
  .bind (put buffer 16 packageIdentity) fun s _ => if s = 0 then
  .bind (put buffer 24 ns) fun s _ => if s = 0 then
  .bind (put buffer 32 page) fun s _ => if s = 0 then
  .bind (put buffer 40 1) fun s _ => if s = 0 then
  .bind (put buffer 48 1) fun s _ => if s = 0 then
  .bind (put buffer 64 1) fun s _ => if s = 0 then
  .bind (put buffer 112 Exact.checkerIdentity) fun s _ => if s = 0 then
  .bind (put buffer 120 1) fun s _ => if s = 0 then
  .bind (put buffer 136 8) fun s _ => if s = 0 then
  .bind (put buffer 176 policyIdentity) fun s _ => if s = 0 then
  .bind (put buffer 200 1) fun s _ => if s = 0 then
  .bind (put buffer 208 1) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

def result (goal n d p0 p1 p2 budget : UInt64) : UInt64 :=
  OwnedSubmission.result goal n d p0 p1 p2 budget

/-- Each edit invalidates current applicability while retaining attempt history.
The bounded UI uses nonnegative integer coefficients 0..99, a proper subset of
the checker domain; no interpretation is inferred from ink. -/
private def clearExecution (buffer : UInt64) : Action :=
  .bind (field buffer 8) fun s version => if s = 0 then
  if version = 3 then ExecutionIdentity.clearCurrent buffer else
  if version = 4 then ExecutionIdentityV2.clearCurrent buffer else
  if version = 8 then ExecutionIdentityV4.clearCurrent buffer else
  if version = 7 then ExecutionIdentityV4.clearCurrent buffer else
  if version = 6 then ExecutionIdentityV4.clearCurrent buffer else
  if version = 5 then ExecutionIdentityV3.clearCurrent buffer else .done 0 0
  else .done s 0

def revise (buffer : UInt64) : Action :=
  .bind (field buffer 40) fun s revision => if s = 0 then
  if 0x7ffffffffffffffe ≤ revision then .done 235 0 else
  .bind (put buffer 40 (revision + 1)) fun s _ => if s = 0 then
  .bind (put buffer 96 0) fun s _ => if s = 0 then
  .bind (put buffer 104 0) fun s _ => if s = 0 then
  .bind (clearExecution buffer) fun s _ => .done s (revision + 1)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

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

/-- Publish only a result still bound to the current original submission.
The isolated endpoint client independently validates the checker/request and
copied document identity before invoking this operation. -/
def completeSubmit (buffer revision goal outcome : UInt64) : Action :=
  if outcome = 0 then .done 234 0 else if 5 < outcome then .done 234 0 else
  .bind (eventCapacity buffer) fun s _ => if s = 0 then
  .bind (field buffer 40) fun s currentRevision => if s = 0 then
  .bind (field buffer 48) fun s currentGoal => if s = 0 then
  if currentRevision = revision then if currentGoal = goal then
  .bind (field buffer 144) fun s attempts => if s = 0 then
  if 8 < attempts then .done 234 0 else
  if (if attempts = 8 then if outcome = Exact.indeterminate then true else false else true) = true then
  .bind (clearExecution buffer) fun s _ => if s = 0 then
  .bind (put buffer 96 outcome) fun s _ => if s = 0 then
  .bind (put buffer 104 revision) fun s _ => if s = 0 then
  .bind (put buffer 168 (if outcome = Exact.verified then 2 else if outcome = Exact.invalid then 1 else 3)) fun s _ => if s = 0 then
  .bind (if attempts < 8 then
    .boundedFoldU64 9 historyStep 9 0 buffer (buffer + 256 + attempts * 72) 0 0 fun s _ =>
      if s = 0 then put buffer 144 (attempts + 1) else .done s 0
    else .done 0 0) fun s _ => if s = 0 then
  .bind (appendEvent buffer (if attempts < 8 then 1 else 5) outcome (if attempts < 8 then attempts else 0)) fun s _ => .done s outcome
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0 else .done s 0

/-- Protocol2 publishes its separately audited execution authority only for
an admitted current result. All preflight checks precede semantic publication.
No error/OOM/death/cancellation invokes this operation. -/
def completeExecution (buffer revision goal outcome request budget : UInt64) : Action :=
  if request = 0 then .done 234 0 else if 0x7ffffffffffffffe < request then .done 234 0 else
  if (if budget = 0 then true else budget = 8) = false then .done 234 0 else
  .bind (field buffer 8) fun s version => if s = 0 then if version = 3 then
  .bind (field buffer 136) fun s currentBudget => if s = 0 then if currentBudget = budget then
  .bind (field buffer 144) fun s index => if s = 0 then if index < 8 then
  .bind (completeSubmit buffer revision goal outcome) fun s actual => if s = 0 then
  .bind (ExecutionIdentity.publish buffer request index budget) fun s _ => .done s actual
  else .done s 0 else .done 235 0 else .done s 0 else .done 234 0 else .done s 0
  else .done 234 0 else .done s 0

/-- Protocol3 publishes only the new closed sums identity into document4.
The semantic, request, revision and resource checks precede publication. -/
def completeExecutionSums (buffer revision goal outcome request budget : UInt64) : Action :=
  if request = 0 then .done 234 0 else if 0x7ffffffffffffffe < request then .done 234 0 else
  if (if budget = 0 then true else budget = 8) = false then .done 234 0 else
  .bind (field buffer 8) fun s version => if s = 0 then if version = 4 then
  .bind (field buffer 136) fun s currentBudget => if s = 0 then if currentBudget = budget then
  .bind (field buffer 144) fun s index => if s = 0 then if index < 8 then
  .bind (completeSubmit buffer revision goal outcome) fun s actual => if s = 0 then
  .bind (ExecutionIdentityV2.publish buffer request index budget) fun s _ => .done s actual
  else .done s 0 else .done 235 0 else .done s 0 else .done 234 0 else .done s 0
  else .done 234 0 else .done s 0

/-- Historical/local checking retains its real owned-object implementation.
Canonical software bootargs2/3 instead use the isolated endpoint asynchronously.
History exhaustion reports Indeterminate without replacing older entries. -/
def submit (buffer : UInt64) : Action :=
  .bind (eventCapacity buffer) fun s _ => if s = 0 then
  .bind (field buffer 48) fun s goal => if s = 0 then
  .bind (field buffer 56) fun s n => if s = 0 then
  .bind (field buffer 64) fun s d => if s = 0 then
  .bind (field buffer 72) fun s p0 => if s = 0 then
  .bind (field buffer 80) fun s p1 => if s = 0 then
  .bind (field buffer 88) fun s p2 => if s = 0 then
  .bind (field buffer 136) fun s budget => if s = 0 then
  .bind (field buffer 144) fun s attempts => if s = 0 then
  .bind (field buffer 40) fun s revision => if s = 0 then
  .bind (if attempts < 8 then OwnedSubmission.check goal n d p0 p1 p2 budget else .done 0 Exact.indeterminate) fun s outcome => if s = 0 then
  completeSubmit buffer revision goal outcome
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

/-- Assistance is explicit and durable. This is an authored local course hint,
not a model response or a trusted mathematical result. -/
def hint (buffer : UInt64) : Action :=
  .bind (eventCapacity buffer) fun s _ => if s = 0 then
  .bind (field buffer 152) fun s count => if s = 0 then
  if count < 32 then
  .bind (put buffer 152 (count + 1)) fun s _ => if s = 0 then appendEvent buffer 2 1 0 else .done s 0
  else .done 235 0 else .done s 0 else .done s 0

/-- Four ordered rows retain the exact original school/request identity.
Scope1 is a write-ahead preparation with uncertain presentation. Scope2 records
only completion of the guest raster routine, never panel visibility. The caller
publishes both through the ordinary workspace Store transaction. -/
private def remoteDigestStep (i _ : UInt32) (acc event _ _ _ : UInt64) : Action :=
  .bind (field event (32+i.toUInt64*8)) fun s value => if s = 0 then .done 0 (acc ||| value) else .done s 0
private def remoteCompareStep (i _ : UInt32) (acc a b _ _ : UInt64) : Action :=
  .bind (field a (i.toUInt64*8)) fun s x => if s = 0 then
  .bind (field b (i.toUInt64*8)) fun s y => if s = 0 then .done 0 (acc ||| (x ^^^ y)) else .done s 0 else .done s 0
private def remotePreparedCompareStep (i _ : UInt32) (acc a b _ _ : UInt64) : Action :=
  .bind (field a (i.toUInt64*8)) fun s x => if s = 0 then
  .bind (field b (i.toUInt64*8)) fun s y => if s = 0 then
  let mask := if i = 1 then ~~~((255 : UInt64) <<< 16) else 0xffffffffffffffff
  .done 0 (acc ||| ((x ^^^ y) &&& mask)) else .done s 0 else .done s 0
private def remoteFindStep (i _ : UInt32) (acc buffer count event prepared : UInt64) : Action :=
  if count ≤ i.toUInt64 then .done 0 acc else
  if acc &&& 255 > 0 then .done 0 acc else
  if acc >>> 8 > 0 then .done 0 (acc-256) else
  let entry := buffer+legacyBytes+i.toUInt64*16
  .bind (field entry 8) fun s descriptor => if s = 0 then
  if descriptor &&& 255 = 7 then
    .bind (field event 8) fun s original => if s = 0 then
    let wanted := if prepared = 1 then (original &&& ~~~((255 : UInt64) <<< 16)) ||| ((1 : UInt64) <<< 16) else original
    if descriptor = wanted then
      .bind (field entry 24) fun s oldBinding => if s = 0 then
      .bind (field event 24) fun s binding => if s = 0 then
      if oldBinding = binding then
        .bind (if prepared = 1 then
          .boundedFoldU64 8 remotePreparedCompareStep 8 0 entry event 0 0 fun s value => .done s value
          else .boundedFoldU64 8 remoteCompareStep 8 0 entry event 0 0 fun s value => .done s value) fun s difference => if s = 0 then
        if difference = 0 then .done 0 (i.toUInt64+1) else .done 234 0 else .done s 0
      else .done 0 768 else .done s 0 else .done s 0
    else .done 0 768 else .done s 0
  else .done 0 acc else .done s 0
private def requireRemotePrepared (buffer count event : UInt64) : Action :=
  .boundedFoldU64 64 remoteFindStep 64 0 buffer count event 1 fun s found => if s = 0 then
  if found &&& 255 > 0 then .done 0 0 else .done 234 0 else .done s 0
private def remoteCopyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (field source (i.toUInt64*8)) fun s value => if s = 0 then
  .bind (put target (i.toUInt64*8) value) fun s _ => .done s acc else .done s 0

/-- Append or reuse one exact immutable remote event. Preparing reserves eight
rows before presentation so a later raster-completed observation has room.
Access failures retain actual private staging effects; no durable claim occurs
until the caller receives its real Store Commit. -/
private def appendRemoteUnchecked (buffer event : UInt64) : Action :=
  .bind (field buffer 40) fun s revision => if s = 0 then
  .bind (field buffer 48) fun s goal => if s = 0 then
  .bind (field buffer 32) fun s page => if s = 0 then
  .bind (field buffer 192) fun s count => if s = 0 then
  .bind (field buffer 208) fun s format => if s = 0 then
  .bind (field event 0) fun s expected => if s = 0 then
  .bind (field event 8) fun s descriptor => if s = 0 then
  .bind (field event 16) fun s object => if s = 0 then
  .bind (field event 24) fun s binding => if s = 0 then
  let scope := (descriptor >>> 16) &&& 255
  if (if format = 1 then true else format = 2) = false then .done 234 0 else
  if expected = revision then if goal = ((descriptor >>> 8) &&& 255) then
  if descriptor &&& 255 = 7 then if (descriptor >>> 24) &&& 255 = 4 then
  if descriptor >>> 32 > 0 then if (if scope = 1 then true else scope = 2) = true then
  if object = (0x504b000000000000 ||| page) then
  if binding > 0 then if binding ≤ 0x7ffffffffffffffe then if count ≤ 64 then
  .boundedFoldU64 4 remoteDigestStep 4 0 event 0 0 0 fun s digest => if s = 0 then
  if digest = 0 then .done 234 0 else
  .boundedFoldU64 64 remoteFindStep 64 0 buffer count event 0 fun s found => if s = 0 then
  if found &&& 255 > 0 then .done 0 (found &&& 255) else
  if (if scope = 1 then 56 else 60) < count then .done 235 0 else
  .boundedFoldU64 8 remoteCopyStep 8 0 event (buffer+legacyBytes+count*16) 0 0 fun s _ => if s = 0 then
  .bind (put buffer 208 2) fun s _ => if s = 0 then
  .bind (put buffer 192 (count+4)) fun s _ => if s = 0 then .done 0 (count+1) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- A raster-completed claim requires an earlier byte-identical prepared
identity, with only the explicit scope byte changed. -/
def appendRemote (buffer event : UInt64) : Action :=
  .bind (field buffer 192) fun s count => if s = 0 then
  .bind (field event 8) fun s descriptor => if s = 0 then
  .bind (if (descriptor >>> 16) &&& 255 = 2 then requireRemotePrepared buffer count event else .done 0 0)
    fun s _ => if s = 0 then appendRemoteUnchecked buffer event else .done s 0
  else .done s 0 else .done s 0

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

private def validateEventStep (i _ : UInt32) (acc buffer count revision attempts : UInt64) : Action :=
  let count := count &&& 0xffffffff
  let entry := buffer + legacyBytes + i.toUInt64 * 16
  if acc >>> 32 > 0 then .done 0 (acc-((1 : UInt64) <<< 32)) else
  .bind (field entry 0) fun s eventRevision => if s = 0 then
  .bind (field entry 8) fun s descriptor => if s = 0 then
  if count ≤ i.toUInt64 then if eventRevision ||| descriptor = 0 then .done 0 acc else .done 234 0 else
  if eventRevision = 0 then .done 234 0 else if revision < eventRevision then .done 234 0 else
  let kind := descriptor &&& 255
  let goal := (descriptor >>> 8) &&& 255
  let value := (descriptor >>> 16) &&& 255
  let index := (descriptor >>> 24) &&& 255
  if kind = 7 then
    .bind (field buffer 208) fun s format => if s = 0 then
    if format = 2 then if goal > 0 then if goal ≤ 3 then
    if (if value = 1 then true else value = 2) = true then
    if index = 4 then if descriptor >>> 32 > 0 then if i.toUInt64+4 ≤ count then
    .bind (field entry 16) fun s object => if s = 0 then
    .bind (field entry 24) fun s binding => if s = 0 then
    .bind (field buffer 32) fun s page => if s = 0 then
    if object = (0x504b000000000000 ||| page) then
    if binding > 0 then if binding ≤ 0x7ffffffffffffffe then
    .boundedFoldU64 4 remoteDigestStep 4 0 entry 0 0 0 fun s digest => if s = 0 then
    if digest > 0 then
      .bind (if value = 2 then requireRemotePrepared buffer i.toUInt64 entry else .done 0 0)
        fun s _ => if s = 0 then .done 0 (acc ||| ((3 : UInt64) <<< 32)) else .done s 0
    else .done 234 0 else .done s 0
    else .done 234 0 else .done 234 0 else .done 234 0
    else .done s 0 else .done s 0 else .done s 0
    else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
    else .done 234 0 else .done 234 0 else .done 234 0 else .done s 0
  else if descriptor >>> 32 = 0 then
  if goal = 0 then .done 234 0 else if 3 < goal then .done 234 0 else
  if kind = 1 then
    if attempts ≤ index then .done 234 0 else if index = acc &&& 255 then
    let history := buffer + 256 + index * 72
    .bind (field history 0) fun s oldRevision => if s = 0 then
    .bind (field history 8) fun s oldGoal => if s = 0 then
    .bind (field history 56) fun s oldOutcome => if s = 0 then
    if eventRevision = oldRevision then if goal = oldGoal then if value = oldOutcome then .done 0 (acc + 1)
    else .done 234 0 else .done 234 0 else .done 234 0
    else .done s 0 else .done s 0 else .done s 0 else .done 234 0
  else if index = 0 then
    if kind = 2 then if value = 1 then .done 0 (acc + 256) else .done 234 0 else
    if kind = 3 then if value ≤ 4 then .done 0 ((acc &&& ~~~((255 : UInt64) <<< 16)) ||| (value <<< 16)) else .done 234 0 else
    if kind = 4 then if value = 1 then .done 0 acc else .done 234 0 else
    if kind = 5 then if value = 5 then if attempts = 8 then .done 0 acc else .done 234 0 else .done 234 0 else
    -- A v1 record did not retain the goal/revision of each hint. Migration
    -- preserves an explicitly marked aggregate, never fabricates those events.
    if kind = 6 then if value = 0 then .done 234 0 else if value ≤ 32 then .done 0 (acc + value * 256) else .done 234 0
    else .done 234 0
  else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0

private def validatePolicyReservedStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (field buffer (224 + i.toUInt64 * 8)) fun s value => if s = 0 then
  if value = 0 then .done 0 acc else .done 234 0 else .done s 0

private def validateExtension (buffer revision attempts : UInt64) : Action :=
  .bind (field buffer 8) fun s version => if s = 0 then
  if version = 1 then .boundedFoldU64 10 validateReservedStep 10 0 buffer 0 0 0 fun s _ => .done s 0 else
  .bind (field buffer 176) fun s identity => if s = 0 then
  .bind (field buffer 184) fun s mode => if s = 0 then
  .bind (field buffer 192) fun s count => if s = 0 then
  .bind (field buffer 200) fun s uncertainty => if s = 0 then
  .bind (field buffer 208) fun s eventVersion => if s = 0 then
  .bind (field buffer 216) fun s showReason => if s = 0 then
  .bind (field buffer 152) fun s hints => if s = 0 then
  if identity = policyIdentity then if mode ≤ 4 then if count ≤ 64 then
  if uncertainty = 1 then if (if eventVersion = 1 then true else eventVersion = 2) = true then if showReason ≤ 1 then
  .boundedFoldU64 4 validatePolicyReservedStep 4 0 buffer 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 64 validateEventStep 64 0 buffer count revision attempts fun s summary => if s = 0 then
  if summary &&& 255 = attempts then if (summary >>> 8) &&& 255 = hints then
  if summary >>> 16 = mode then .done 0 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Unknown/malformed records reject; they never initialize a replacement.
Current applicable evidence is recomputed against the precise original goal. -/
def validate (buffer ns page : UInt64) : Action :=
  .bind (field buffer 0) fun s value => if s = 0 then
  if value = magic then
  .bind (field buffer 8) fun s value => if s = 0 then
  if value = 1 then validateHeader buffer ns page else
  if value = 2 then validateHeader buffer ns page else
  if value = 3 then validateHeader buffer ns page else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0
where
  validateHeader (buffer ns page : UInt64) : Action :=
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
    else .done 234 0 else .done s 0
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
    .bind (validateExtension buffer revision attempts) fun s _ => if s = 0 then
    .boundedFoldU64 5 validateOperandStep 5 0 buffer 0 0 0 fun s _ => if s = 0 then
    .boundedFoldU64 8 validateHistoryStep 8 0 buffer attempts revision 0 fun s _ => if s = 0 then
    .bind (field buffer 8) fun s version => if s = 0 then
    if version = 3 then ExecutionIdentity.validate buffer else .done 0 0
    else .done s 0 else .done s 0
    else .done s 0 else .done s 0 else .done s 0 else .done 234 0 else .done s 0

private def upgradeZeroStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (put buffer (legacyBytes + i.toUInt64 * 8) 0) fun s _ => .done s acc

private def upgradeAttemptStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  let index := i.toUInt64
  let history := buffer + 256 + index * 72
  let event := buffer + legacyBytes + index * 16
  .bind (field history 0) fun s revision => if s = 0 then
  .bind (field history 8) fun s goal => if s = 0 then
  .bind (field history 56) fun s outcome => if s = 0 then
  .bind (put event 0 revision) fun s _ => if s = 0 then
  .bind (put event 8 ((1 : UInt64) ||| (goal <<< 8) ||| (outcome <<< 16) ||| (index <<< 24))) fun s _ => .done s (acc + 1)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- The caller has strictly validated the original v1 record. Its typed answer,
evidence and complete attempt history survive migration. Unanchored old hints
remain a conservative aggregate with no invented goal/revision history. -/
def upgrade (buffer : UInt64) : Action :=
  .bind (field buffer 8) fun s version => if s = 0 then
  if version = 2 then .done 0 0 else if version = 1 then
  .bind (field buffer 144) fun s attempts => if s = 0 then
  .bind (field buffer 152) fun s hints => if s = 0 then
  .boundedFoldU64 128 upgradeZeroStep 128 0 buffer 0 0 0 fun s _ => if s = 0 then
  .bind (put buffer 8 2) fun s _ => if s = 0 then
  .bind (put buffer 176 policyIdentity) fun s _ => if s = 0 then
  .bind (put buffer 200 1) fun s _ => if s = 0 then
  .bind (put buffer 208 1) fun s _ => if s = 0 then
  .boundedFoldU64 8 upgradeAttemptStep attempts.toUInt32 0 buffer 0 0 0 fun s _ => if s = 0 then
  .bind (put buffer 192 attempts) fun s _ => if s = 0 then
  .bind (if hints = 0 then .done 0 0 else appendEvent buffer 6 hints 0) fun s _ => .done s 1
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done 234 0 else .done s 0

/-- Validated v1/v2 records migrate with explicitly Unknown execution slots.
No old result is labeled with this implementation or a fabricated request ID. -/
def upgradeCurrent (buffer : UInt64) : Action :=
  .bind (field buffer 8) fun s version => if s = 0 then
  if version = 3 then .done 0 0 else
  .bind (upgrade buffer) fun s _ => if s = 0 then
  .bind (ExecutionIdentity.createExtension buffer) fun s _ => if s = 0 then
  .bind (put buffer 8 3) fun s _ => .done s 1
  else .done s 0 else .done s 0 else .done s 0

def createCurrent (buffer ns page : UInt64) : Action :=
  .bind (create buffer ns page) fun s _ => if s = 0 then
  upgradeCurrent buffer else .done s 0

/-- Document4 is an additive authority registry. Historical validate still
rejects4 and retains the exact old execution-identity semantics. -/
def validateSums (buffer ns page : UInt64) : Action :=
  .bind (field buffer 8) fun s version => if s = 0 then
  if version = 4 then
  .bind (field buffer 0) fun s actualMagic => if s = 0 then
  if actualMagic = magic then
  .bind (validate.validateHeader buffer ns page) fun s _ => if s = 0 then
  ExecutionIdentityV2.validate buffer else .done s 0
  else .done 234 0 else .done s 0
  else validate buffer ns page else .done s 0

/-- The caller strictly validated the original record first. v3 history remains
byte-for-byte Known/Unknown; v1/v2 migration inherits its original Unknown rule.
Only format and registry version change before the normal Store transaction. -/
def upgradeSums (buffer : UInt64) : Action :=
  .bind (field buffer 8) fun s version => if s = 0 then
  if version = 4 then .done 0 0 else
  .bind (upgradeCurrent buffer) fun s _ => if s = 0 then
  .bind (put buffer 1864 ExecutionIdentityV2.extensionVersion) fun s _ => if s = 0 then
  .bind (put buffer 8 4) fun s _ => .done s 1 else .done s 0 else .done s 0 else .done s 0

def createSums (buffer ns page : UInt64) : Action :=
  .bind (createCurrent buffer ns page) fun s _ => if s = 0 then
  upgradeSums buffer else .done s 0

end Lemma.Documents.Mathematics
