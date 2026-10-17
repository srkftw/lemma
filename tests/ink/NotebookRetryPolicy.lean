import Lemma.Notebook.RetryPolicy

open Lemma.Notebook.RetryPolicy

example : version = 1 := rfl
example : retryStatus 0 0x300000 344 65548 0 = 0 := by decide
example : retryStatus 2 0x300000 344 65548 0 = 0 := by decide
example : retryStatus 3 0x300000 344 65548 0 = 235 := by decide
example : retainedRecordValid 0x300000 344 65548 0 = true := by decide
example : retainedRecordValid 0x318000 2496 257 1 = true := by decide
example : retainedRecordValid 0x320000 64 1 2 = true := by decide
example : retainedRecordValid 0x300008 344 65548 0 = false := by decide
example : retainedRecordValid 0x300000 27784 65548 0 = false := by decide
example : retainedRecordValid 0x300000 199 65548 0 = false := by decide
example : retainedRecordValid 0x318000 32776 257 1 = false := by decide
example : retainedRecordValid 0x318000 64 321 1 = false := by decide
example : retainedRecordValid 0x320000 72 1 2 = false := by decide
example : retainedRecordValid 0x320000 64 0 2 = false := by decide
example : retainedRecordValid 0x32a000 1856 1 3 = false := by decide
example : retainableFailure 234 0x300000 344 65548 0 = false := by decide
example : retainableFailure 235 0x300000 344 65548 0 = false := by decide
example : retainableFailure 0 0x300000 344 65548 0 = false := by decide
example : retainableFailure 227 0x300000 344 65548 0 = true := by decide
example : offlineBufferAvailable 0x308000 0x300000 383 = true := by decide
example : offlineBufferAvailable 0x300000 0x300000 0 = false := by decide
example : offlineBufferAvailable 0x308000 0x300000 384 = false := by decide
example : offlineBufferAvailable 0x318000 0x300000 0 = false := by decide

example : reconciliationStatus 1 11 11 = 0 := by decide
example : reconciliationStatus 1 12 11 = 234 := by decide
example : reconciliationStatus 1 10 11 = 234 := by decide
example : reconciliationStatus 0 11 11 = 234 := by decide
example : reconciliationStatus 2 11 11 = 234 := by decide
example : reconciliationStatus 3 11 11 = 234 := by decide
example : reconciliationStatus 4 11 11 = 234 := by decide

def main : IO Unit := IO.println "NotebookRetryPolicy literal/error/alias/boundary examples checked"
