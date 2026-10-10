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

run_cmd do
  for (operation, detail, expected) in #[(12,0,234),(12,1,0),(12,2,234),
      (13,0,0),(13,1,0),(13,2,234),(7,0,234),(8,1,234),
      (0,0,234),(13,0xffffffffffffffff,234)] do
    unless Lemma.Applications.Notebook.checkpointResponseStatus operation detail = expected do
      throwError "checkpoint receipt accepted an invalid completion boundary"
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1 #[``replyProbe] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => pure ()
  | .error error => throwError error
  logInfo "NOTEBOOK_CHECKPOINT:PASS ten literal Begin/Status boundaries and genuine production-decision lowering; disk execution separate"

end NotebookCheckpointFixture
