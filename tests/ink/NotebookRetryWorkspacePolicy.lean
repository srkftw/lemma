import Lemma.Notebook.RetryWorkspacePolicy

open Lemma.Notebook.RetryWorkspacePolicy
example : version = 4 := rfl
example : workspaceRecordValid 0x32a000 96 0x504b000000000001 3 = true := by decide
example : workspaceRecordValid 0x32a000 3808 0x504b000000000040 3 = true := by decide
example : workspaceRecordValid 0x32a000 95 0x504b000000000001 3 = false := by decide
example : workspaceRecordValid 0x32a000 104 0x504b000000000000 3 = false := by decide
example : workspaceRecordValid 0x32a000 104 0x504b000000000041 3 = false := by decide
example : workspaceRecordValid 0x32a000 3816 0x504b000000000001 3 = false := by decide
example : workspaceRecordValid 0x32a000 105 0x504b000000000001 3 = false := by decide
example : workspaceRecordValid 0x32a008 104 0x504b000000000001 3 = false := by decide
example : retainedRecordValid 0x32a000 2496 0x8001 3 = false := by decide
example : Lemma.Notebook.RetryClosurePolicy.retainedRecordValid 0x32a000 104 0x504b000000000001 3 = false := by decide
example : retainedRecordValid 0x300000 344 65548 0 = true := by decide
example : retainedRecordValid 0x318000 2496 257 1 = true := by decide
example : retainedRecordValid 0x320000 64 1 2 = true := by decide
example : retainableFailure 227 0x32a000 104 0x504b000000000001 3 = true := by decide
example : retainableFailure 234 0x32a000 104 0x504b000000000001 3 = false := by decide
example : retryStatus 2 0x32a000 104 0x504b000000000001 3 = 0 := by decide
example : retryStatus 3 0x32a000 104 0x504b000000000001 3 = 235 := by decide
example : publicationEnds 3 = true := by decide
example : publicationEnds 0 = false := by decide

def main : IO Unit := IO.println "WORKSPACE_RETRY_SHAPE:PASS checked shape boundaries and distinct old families; no integrity/durability/CPU claim"
