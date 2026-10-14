import Lemma.Notebook.RetryClosurePolicy

open Lemma.Notebook.RetryClosurePolicy
example : version = 2 := rfl
example : mathematicalRecordValid 0x32a000 2496 0x8001 3 = true := by decide
example : mathematicalRecordValid 0x32a000 2496 0x8040 3 = true := by decide
example : mathematicalRecordValid 0x32a008 2496 0x8001 3 = false := by decide
example : mathematicalRecordValid 0x32a000 2488 0x8001 3 = false := by decide
example : mathematicalRecordValid 0x32a000 2504 0x8001 3 = false := by decide
example : mathematicalRecordValid 0x32a000 1856 0x8001 3 = false := by decide
example : mathematicalRecordValid 0x32a000 2496 0x8000 3 = false := by decide
example : mathematicalRecordValid 0x32a000 2496 0x8041 3 = false := by decide
example : mathematicalRecordValid 0x32a000 2496 0x8001 2 = false := by decide
example : retainableFailure 227 0x32a000 2496 0x8001 3 = true := by decide
example : retainableFailure 234 0x32a000 2496 0x8001 3 = false := by decide
example : retryStatus 2 0x32a000 2496 0x8001 3 = 0 := by decide
example : retryStatus 3 0x32a000 2496 0x8001 3 = 235 := by decide
example : retainedRecordValid 0x300000 344 65548 0 = true := by decide
example : retainedRecordValid 0x318000 2496 257 1 = true := by decide
example : retainedRecordValid 0x320000 64 1 2 = true := by decide
example : Lemma.Notebook.RetryPolicy.retainedRecordValid 0x32a000 2496 0x8001 3 = false := by decide
example : publicationEnds 2 = true := by decide
example : publicationEnds 3 = true := by decide
example : publicationEnds 0 = false := by decide
example : publicationEnds 1 = false := by decide
example : publicationEnds 4 = false := by decide

def main : IO Unit := IO.println "Closure retry shape policy: literal positive/negative examples checked; no execution or durability claim"
