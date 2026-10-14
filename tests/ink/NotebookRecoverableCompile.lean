import Lemma.Applications.Notebook
import Lemma.Compiler.CFGLower

open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_2
      #[``Lemma.Applications.Notebook.recoverableBegin,
        ``Lemma.Applications.Notebook.recoverablePollControl,
        ``Lemma.Applications.Notebook.recoverablePollRead,
        ``Lemma.Applications.Notebook.recoverablePumpSave,
        ``Lemma.Applications.Notebook.recoverableToolbar,
        ``Lemma.Applications.Notebook.recoverableInputSample,
        ``Lemma.Applications.Notebook.drainRecoverableInput,
        ``Lemma.Applications.Notebook.recoverableStep,
        ``Lemma.Applications.Notebook.mainRecoverableSumsBulk] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_2 suite with
  | .ok _ => pure ()
  | .error diagnostic => throwError diagnostic
  logInfo "NOTEBOOK_RECOVERABLE_COMPILE:PASS nine actual Lean roots under existing User2 scalar/IPC/owned memory authority; no deployment/Save claim"
