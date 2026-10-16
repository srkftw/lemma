import Lemma.Notebook.RetryReaderPolicy

open Lemma.Notebook.RetryReaderPolicy
example : version = 5 := rfl
example : readerRecordValid 0x32af00 128 0x5244000000000001 3 = true := by decide
example : readerRecordValid 0x32af00 128 0x5244000000000040 3 = true := by decide
example : readerRecordValid 0x32af00 120 0x5244000000000001 3 = false := by decide
example : readerRecordValid 0x32af00 136 0x5244000000000001 3 = false := by decide
example : readerRecordValid 0x32af08 128 0x5244000000000001 3 = false := by decide
example : readerRecordValid 0x32af00 128 0x5244000000000000 3 = false := by decide
example : readerRecordValid 0x32af00 128 0x5244000000000041 3 = false := by decide
example : readerRecordValid 0x32af00 128 0x5244000000000001 2 = false := by decide
example : readerRecordValid 0x32a000 128 0x504b000000000001 3 = false := by decide
example : retainedRecordValid 0x32a000 96 0x504b000000000001 3 = true := by decide
example : retainedRecordValid 0x32a000 3808 0x504b000000000040 3 = true := by decide
example : retainedRecordValid 0x300000 344 65548 0 = true := by decide
example : retainedRecordValid 0x318000 2496 257 1 = true := by decide
example : retainedRecordValid 0x320000 64 1 2 = true := by decide
example : Lemma.Notebook.RetryWorkspacePolicy.retainedRecordValid
    0x32af00 128 0x5244000000000001 3 = false := by decide
example : retainableFailure 227 0x32af00 128 0x5244000000000001 3 = true := by decide
example : retainableFailure 231 0x32af00 128 0x5244000000000001 3 = false := by decide
example : retryStatus 2 0x32af00 128 0x5244000000000001 3 = 0 := by decide
example : retryStatus 3 0x32af00 128 0x5244000000000001 3 = 235 := by decide

def main : IO Unit := IO.println "READER_RETRY_SHAPE5:PASS exact128/ownedstaging/64pages/historicalfamilies; no integrity/durability/CPU claim"
