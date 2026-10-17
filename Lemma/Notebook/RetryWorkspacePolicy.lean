import Lemma.Notebook.RetryClosurePolicy

/-! Additive installed-workspace recovery shapes. This is a routing guard,
not integrity, ownership, a mathematical result or a durability receipt.
The Notebook validates the complete compact envelope and decoded workspace
against its actual current namespace/page before retention or reconciliation.
Historical raw/page/root and Closure7/Doc8 profiles retain their definitions.
-/
namespace Lemma.Notebook.RetryWorkspacePolicy

def version : UInt64 := 4

def workspaceRecordValid (source bytes object stage : UInt64) : Bool :=
  if stage = 3 then if source = 0x32a000 then
    if bytes % 8 = 0 then if 96 ≤ bytes then if bytes ≤ 3808 then
      if 0x504b000000000001 ≤ object then if object ≤ 0x504b000000000040 then true else false
      else false else false else false else false else false else false

def retainedRecordValid (source bytes object stage : UInt64) : Bool :=
  if stage = 3 then workspaceRecordValid source bytes object stage
  else Lemma.Notebook.RetryPolicy.retainedRecordValid source bytes object stage

def retainableFailure (status source bytes object stage : UInt64) : Bool :=
  if status = 227 then retainedRecordValid source bytes object stage else false

def retryStatus (attempts source bytes object stage : UInt64) : UInt8 :=
  if retainedRecordValid source bytes object stage then
    if attempts < Lemma.Notebook.RetryPolicy.maximumAttempts then 0 else 235
  else 234

def publicationEnds (stage : UInt64) : Bool :=
  Lemma.Notebook.RetryClosurePolicy.publicationEnds stage

end Lemma.Notebook.RetryWorkspacePolicy
