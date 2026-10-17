import Lemma.Core0.Memory

/-! Scalar policy for the opt-in notebook failure/retry successor. The policy
never authorizes a Saved observation; only the original Store reply/barrier
checks may do that. It admits only the exact retained raw/page/root record.
Opaque I/O ambiguity is not rolled back or converted into success. -/
namespace Lemma.Notebook.RetryPolicy

def version : UInt64 := 1
def maximumAttempts : UInt64 := 3
def maximumOfflineSamples : UInt64 := 384

/-- These are existing owned User buffers, not new physical authority. -/
def retainedRecordValid (source bytes object stage : UInt64) : Bool :=
  if bytes % 8 = 0 then
    if stage = 0 then
      if source = 0x300000 then
        if 200 ≤ bytes then if bytes ≤ 27776 then if 0x10001 ≤ object then true else false else false else false
      else if source = 0x308000 then
        if 200 ≤ bytes then if bytes ≤ 27776 then if 0x10001 ≤ object then true else false else false else false
      else false
    else if stage = 1 then
      if source = 0x318000 then if 32 ≤ bytes then if bytes ≤ 32768 then
        if 0x101 ≤ object then if object ≤ 0x140 then true else false else false else false else false else false
    else if stage = 2 then
      if source = 0x320000 then if bytes = 64 then if object = 1 then true else false else false else false
    else false
  else false

/-- A returned device-I/O error is still a failure. Unknown/corrupt/resource or
read-only outcomes cannot be made retryable by this policy. -/
def retainableFailure (status source bytes object stage : UInt64) : Bool :=
  if status = 227 then retainedRecordValid source bytes object stage else false

def retryStatus (attempts source bytes object stage : UInt64) : UInt8 :=
  if retainedRecordValid source bytes object stage then
    if attempts < maximumAttempts then 0 else 235
  else 234

/-- The failed source remains pinned until its full publication chain is
acknowledged. Offline input has one other bounded buffer; aliases reject. -/
def offlineBufferAvailable (active retained count : UInt64) : Bool :=
  if count < maximumOfflineSamples then
    if active = 0x300000 then if active = retained then false else true else
    if active = 0x308000 then if active = retained then false else true else false
  else false

/-- A prior coherent, writable prefix can admit a new exact record request.
A higher sequence is uncertain publication, not permission to acknowledge or
blindly repeat it. Read-only/error/mounting states require actual remount. -/
def reconciliationStatus (mode observed known : UInt64) : UInt8 :=
  if mode = 1 then if observed = known then 0 else 234 else 234

-- No success transition is supplied here. A new reply with a complete matching
-- request, generation, status and publication observation remains mandatory.
end Lemma.Notebook.RetryPolicy
