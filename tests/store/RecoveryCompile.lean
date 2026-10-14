import Lemma.Services.Store.ServerRecovery
import Lemma.Services.Store.RecoveryClient
import Lemma.Compiler.CFGLower

/-! Genuine existing User2 scalar/Action lowering only. No image, device or
successful guest recovery is certified by this component declaration check. -/
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_2
      #[``Lemma.Services.Store.ServerRecovery.begin,
        ``Lemma.Services.Store.ServerRecovery.status,
        ``Lemma.Services.Store.ServerRecovery.application,
        ``Lemma.Services.Store.ServerRecovery.step,
        ``Lemma.Services.Store.ServerRecovery.mainRecoveryCourse,
        ``Lemma.Services.Store.RecoveryClient.beginCall,
        ``Lemma.Services.Store.RecoveryClient.pollCall] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_2 suite with
  | .ok _ => pure ()
  | .error diagnostic => throwError diagnostic
  logInfo "STORE_RECOVERY_COMPILE:PASS seven actual Lean roots under existing User2 scalar/IPC/owned memory authority; no whole-image/Save claim"
