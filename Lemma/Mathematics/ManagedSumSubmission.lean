import Lemma.Mathematics.ManagedResult
import Lemma.Mathematics.OwnedSubmission

/-! The additive managed execution path for the isolated arithmetic service.
The admitted exact/1 mathematical domain stays unchanged. Heap/OOM/cancellation
statuses are actual resource failures and never create mathematical evidence. -/
namespace Lemma.Mathematics.ManagedSumSubmission
open Lemma.Core0.Memory

private def positiveRational (n d budget : UInt64) : Action :=
  if Exact.canonical n = false then .done 0 Exact.needsClarification else
  if d = 0 then .done 0 Exact.invalid else
  if Exact.bounded n = false then .done 0 Exact.indeterminate else
  if Exact.limit < d then .done 0 Exact.indeterminate else
  if budget < 8 then .done 0 Exact.indeterminate else
  if n &&& Exact.sign = Exact.sign then .done 0 Exact.invalid else
  .managedSums2 ManagedResult.compareFiveSix n d fun status outcome =>
    if status = 0 then .done 0 outcome
    else .done status 0

def check (goal n d p0 p1 p2 budget : UInt64) : Action :=
  if goal = 1 then positiveRational n d budget
  else OwnedSubmission.check goal n d p0 p1 p2 budget

end Lemma.Mathematics.ManagedSumSubmission
