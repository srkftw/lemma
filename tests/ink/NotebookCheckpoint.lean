import Lemma.Applications.Notebook
import Lemma.Compiler.CFGLower

/-! Literal checkpoint-reply boundaries over the production decision. A Begin
receipt never authorizes Saved. This host fixture also checks genuine Lean
elaboration/lowering; it is not a disk flush or guest execution result. -/
namespace NotebookCheckpointFixture
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler

def replyProbe (operation detail : UInt64) : Lemma.Core0.Memory.Action :=
  .done (Lemma.Applications.Notebook.checkpointResponseStatus operation detail) 0

def saveProbe (operation mode observed prior : UInt64) : Lemma.Core0.Memory.Action :=
  .done (Lemma.Applications.Notebook.saveResponseStatus operation mode observed prior) 0

run_cmd do
  for (operation, detail, expected) in #[(12,0,234),(12,1,0),(12,2,234),
      (13,0,0),(13,1,0),(13,2,234),(7,0,234),(8,1,234),
      (0,0,234),(13,0xffffffffffffffff,234)] do
    unless Lemma.Applications.Notebook.checkpointResponseStatus operation detail = expected do
      throwError "checkpoint receipt accepted an invalid completion boundary"
  for (operation, mode, observed, prior, expected) in #[(8,1,7,7,0),
      (8,1,8,7,0),(8,1,6,7,234),(8,0,8,7,234),(8,2,8,7,234),
      (8,3,8,7,234),(8,4,8,7,234),(12,1,8,7,234),(13,1,8,7,234),
      (8,1,0,0,0),(8,1,0,1,234)] do
    unless Lemma.Applications.Notebook.saveResponseStatus operation mode observed prior = expected do
      throwError "explicit Save accepted an unready or regressed durable sequence"
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1 #[``replyProbe, ``saveProbe] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => pure ()
  | .error error => throwError error
  logInfo "NOTEBOOK_CHECKPOINT:PASS ten Compact and eleven quick Save boundaries; genuine production-decision lowering; disk execution separate"

end NotebookCheckpointFixture
