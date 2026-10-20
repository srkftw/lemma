import Lemma.Documents.Mathematics
import Lemma.Courses.DocumentEventRows

/-! `lemma-authored-hint-visibility/1`. A historical aggregate assistance count
does not identify a proposal for the current submission. Only a recorded local
hint request for the same document revision and supported goal permits showing
that goal's authored hint. Events live inside the already validated, owned
document; namespace/page and package selection remain the caller's bindings.
Nothing here writes a document, creates evidence or changes the learner policy.
-/
namespace Lemma.Courses.HintVisibility
open Lemma.Core0.Memory Lemma.Documents

private def eventStep (i _ : UInt32) (found buffer revision goal _ : UInt64) : Action :=
  if DocumentEventRows.remaining found = 0 then
  let entry := Mathematics.legacyBytes + i.toUInt64 * 16
  .bind (Mathematics.field buffer (entry + 8)) fun s descriptor => if s = 0 then
  if DocumentEventRows.payloadRows descriptor = 0 then
    .bind (Mathematics.field buffer entry) fun s actualRevision => if s = 0 then
    if actualRevision = revision then
    if descriptor &&& 255 = 2 then
      if (descriptor >>> 8) &&& 255 = goal then
        if (descriptor >>> 16) &&& 255 = 1 then .done 0 1 else .done 0 found
      else .done 0 found
    else .done 0 found
    else .done 0 found else .done s 0
  else .done 0 (DocumentEventRows.beginPayload found descriptor)
  else .done s 0
  else .done 0 (DocumentEventRows.skipPayload found)

/-- Unknown historical event metadata cannot supply a current proposal.
Malformed admitted event counts fail before any framebuffer write. The bounded
scan preserves every event/count and propagates the first actual read error. -/
def current (buffer : UInt64) : Action :=
  .bind (Mathematics.field buffer 208) fun s version => if s = 0 then
  if DocumentEventRows.supportedFormat version = true then
    .bind (Mathematics.field buffer 192) fun s count => if s = 0 then
    if count ≤ 64 then
      .bind (Mathematics.field buffer 40) fun s revision => if s = 0 then
      .bind (Mathematics.field buffer 48) fun s goal => if s = 0 then
      if revision = 0 then .done 0 0 else
      if (if goal = 1 then true else goal = 2) = true then
        .boundedFoldU64 64 eventStep count.toUInt32 0 buffer revision goal 0 fun s found => if s = 0 then
          if DocumentEventRows.remaining found = 0 then .done 0 (DocumentEventRows.observation found)
          else .done 234 0 else .done s 0
      else .done 0 0 else .done s 0 else .done s 0
    else .done 235 0 else .done s 0
  else .done 0 0 else .done s 0

end Lemma.Courses.HintVisibility
