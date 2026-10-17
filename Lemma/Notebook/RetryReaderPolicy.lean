import Lemma.Notebook.RetryWorkspacePolicy

/-! Additive recovery5 routing for the reader's separate immutable 128-byte
record. Shape admission is not integrity, ownership, a package selection, a
mathematical result or a durability receipt. The caller must resolve the full
record against its current owned namespace/page and complete loaded package.
Recovery4 and every historical raw/page/root/workspace shape remain exact. -/
namespace Lemma.Notebook.RetryReaderPolicy

def version : UInt64 := 5

def readerRecordValid (source bytes object stage : UInt64) : Bool :=
  if stage = 3 then if source = 0x32af00 then if bytes = 128 then
    if 0x5244000000000001 ≤ object then if object ≤ 0x5244000000000040 then true else false
    else false else false else false else false

def retainedRecordValid (source bytes object stage : UInt64) : Bool :=
  if readerRecordValid source bytes object stage then true
  else Lemma.Notebook.RetryWorkspacePolicy.retainedRecordValid source bytes object stage

def retainableFailure (status source bytes object stage : UInt64) : Bool :=
  if status = 227 then retainedRecordValid source bytes object stage else false

def retryStatus (attempts source bytes object stage : UInt64) : UInt8 :=
  if retainedRecordValid source bytes object stage then
    if attempts < Lemma.Notebook.RetryPolicy.maximumAttempts then 0 else 235
  else 234

end Lemma.Notebook.RetryReaderPolicy
