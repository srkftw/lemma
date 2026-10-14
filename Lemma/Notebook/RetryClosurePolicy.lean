import Lemma.Notebook.RetryPolicy

/-! Separately selected Closure7/Doc8 recovery shape policy. Historical retry
policy remains version1 and rejects mathematical records. These scalar checks
do not establish allocation ownership, document identity, mathematical authority
or durability; the new Notebook Actions supply those separate checks. -/
namespace Lemma.Notebook.RetryClosurePolicy

def version : UInt64 := 2

def mathematicalRecordValid (source bytes object stage : UInt64) : Bool :=
  if stage = 3 then
    if source = 0x32a000 then
      if bytes = 2496 then
        if 0x8001 ≤ object then if object ≤ 0x8040 then true else false
        else false
      else false
    else false
  else false

def retainedRecordValid (source bytes object stage : UInt64) : Bool :=
  if stage = 3 then mathematicalRecordValid source bytes object stage
  else Lemma.Notebook.RetryPolicy.retainedRecordValid source bytes object stage

def retainableFailure (status source bytes object stage : UInt64) : Bool :=
  if status = 227 then retainedRecordValid source bytes object stage else false

def retryStatus (attempts source bytes object stage : UInt64) : UInt8 :=
  if retainedRecordValid source bytes object stage then
    if attempts < Lemma.Notebook.RetryPolicy.maximumAttempts then 0 else 235
  else 234

/-- Shape-only distinction. The caller must complete the original exact record
after a matching normal commit or barrier-backed full READ/EOF reconciliation;
this Boolean never warrants Saved on its own. -/
def publicationEnds (stage : UInt64) : Bool :=
  if stage = 2 then true else if stage = 3 then true else false

end Lemma.Notebook.RetryClosurePolicy
