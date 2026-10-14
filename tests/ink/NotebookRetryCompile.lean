import Lemma.Applications.Notebook
import Lemma.Compiler.CFGLower

/-! Genuine elaboration and existing User2 scalar/Action lowering for the
opt-in retry roots. This does not admit a deployment or run an RV64 guest. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  let roots := #[``Lemma.Applications.Notebook.retryRetainFailure,
    ``Lemma.Applications.Notebook.retryBeginInspect,
    ``Lemma.Applications.Notebook.retryPollInspect,
    ``Lemma.Applications.Notebook.retryPumpSave,
    ``Lemma.Applications.Notebook.retryToolbar,
    ``Lemma.Applications.Notebook.retryAppendRaw,
    ``Lemma.Applications.Notebook.retryInputLimit,
    ``Lemma.Applications.Notebook.retryCancelInput,
    ``Lemma.Applications.Notebook.retryInputSample,
    ``Lemma.Applications.Notebook.drainRetryInput,
    ``Lemma.Applications.Notebook.retryStep,
    ``Lemma.Applications.Notebook.mainRetrySumsBulk]
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_2 roots with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_2 suite with
  | .ok _ => pure ()
  | .error diagnostic => throwError diagnostic
  logInfo "NOTEBOOK_RETRY_COMPILE:PASS twelve actual Lean successor roots under existing User2/Action authority; no deployment/guest/Save claim"
