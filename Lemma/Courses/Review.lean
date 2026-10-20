import Lemma.Documents.Mathematics
import Lemma.Courses.DocumentEventRows

/-! `lemma-offline-review/1`: a fixed, explainable baseline over durable learner
events. Exact attempts and assistance are observations of a task, not evidence
of understanding or learning gain. The estimate always remains uncertain.
Manual override and disable belong to the learner, not the checker or tutor. -/
namespace Lemma.Courses.Review
open Lemma.Core0.Memory
open Lemma.Documents
open Lemma.User

/-- Low three bits: disabled0, practice1, later2, support3. Next three bits
identify the explanation: no attempt1, assisted2, exact attempt3, invalid4,
unsupported/resource5, manual6, disabled7. -/
def policy (outcome assisted mode : UInt64) : UInt64 :=
  if mode = 4 then 56 else
  if mode = 0 then
    if outcome = 1 then if assisted = 0 then 26 else 17 else
    if outcome = 0 then 9 else if outcome = 2 then 33 else 43
  else mode ||| ((6 : UInt64) <<< 3)

private def eventStep (i _ : UInt32) (acc buffer count goal _ : UInt64) : Action :=
  if count ≤ i.toUInt64 then .done 0 acc else
  if DocumentEventRows.remaining acc = 0 then
  .bind (Mathematics.field buffer (Mathematics.legacyBytes + i.toUInt64 * 16 + 8)) fun s descriptor => if s = 0 then
  let kind := descriptor &&& 255
  let eventGoal := (descriptor >>> 8) &&& 255
  if DocumentEventRows.payloadRows descriptor = 0 then
  if kind = 6 then .done 0 (acc ||| 8) else
  if eventGoal = goal then
    if kind = 2 then .done 0 (acc ||| 8) else
    if kind = 1 then .done 0 ((acc &&& (8 : UInt64)) ||| ((descriptor >>> 16) &&& (7 : UInt64))) else
    if kind = 5 then .done 0 ((acc &&& (8 : UInt64)) ||| (5 : UInt64)) else .done 0 acc
  else .done 0 acc
  else .done 0 (DocumentEventRows.beginPayload (if eventGoal = goal then acc ||| 8 else acc) descriptor)
  else .done s 0
  else .done 0 (DocumentEventRows.skipPayload acc)

/-- Reconstruct the baseline from ordered durable events on every render.
Assistance is conservatively retained for its goal, including a marked legacy
aggregate whose old source goal was never recorded. -/
def summary (buffer : UInt64) : Action :=
  .bind (Mathematics.field buffer 48) fun s goal => if s = 0 then
  .bind (Mathematics.field buffer 184) fun s mode => if s = 0 then
  .bind (Mathematics.field buffer 192) fun s count => if s = 0 then
  if count ≤ 64 then
  .bind (Mathematics.field buffer 216) fun s showReason => if s = 0 then
  .boundedFoldU64 64 eventStep 64 0 buffer count goal 0 fun s estimate => if s = 0 then
  if DocumentEventRows.remaining estimate = 0 then
  .done 0 (policy (estimate &&& 7) ((estimate >>> 3) &&& 1) mode ||| (mode <<< 6) ||| (showReason <<< 9))
  else .done 234 0
  else .done s 0 else .done s 0 else .done 235 0 else .done s 0 else .done s 0 else .done s 0

end Lemma.Courses.Review
