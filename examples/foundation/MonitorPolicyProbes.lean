import examples.foundation.Monitor
import Lemma.Core0
import Lemma.Compiler.CFGLower

/-!
Direct scalar policy/encoder probes and genuine two-root checker/lowering.
These do not simulate UART timing or hardware interrupts and prove no compiler
correctness property. All hardware observations require the separate RV64 runs.
-/
namespace Lemma.Examples.Foundation.Monitor.PolicyProbes

open Lemma.Examples.Foundation.Monitor

#guard Protocol.helloTag = 0x31304e4f4d4d454c
#guard Protocol.requestMagic = 0x39514d4c
#guard Protocol.validHeader 0x39514d4c 1 0 = true
#guard Protocol.validHeader 0x36514d4c 1 0 = false
#guard Protocol.validHeader 0x39514d4c 0 0 = false
#guard Protocol.validHeader 0x39514d4c 2 0 = false
#guard Protocol.validHeader 0x39514d4c 1 1 = false
#guard Protocol.expectedLength 1 = 0
#guard Protocol.expectedLength 3 = 32
#guard Protocol.expectedLength 4 = 24
#guard Protocol.expectedLength 5 = 16
#guard Protocol.expectedLength 6 = 8
#guard Protocol.expectedLength 7 = 8
#guard Protocol.expectedLength 9 = 16
#guard Protocol.expectedLength 10 = 0
#guard Protocol.expectedLength 0 = 255
#guard Protocol.expectedLength 255 = 255
#guard Protocol.readyByte 14 = 0x31
#guard Protocol.readyByte 15 = 0x0a
#guard Protocol.readyByte 21 = 0x0a
#guard Protocol.responseHeaderByte 3 0 0 = 0x39
#guard Protocol.responseHeaderByte 5 17 0 = 17
#guard Protocol.responseHeaderByte 6 0 0 = 32
#guard Protocol.responseHeaderByte 8 0 0x8877665544332211 = 0x11
#guard Protocol.responseHeaderByte 15 0 0x8877665544332211 = 0x88
#guard validBufferRange 0 3840 = true
#guard validBufferRange 3839 1 = true
#guard validBufferRange 3840 0 = true
#guard validBufferRange 3840 1 = false
#guard validBufferRange 3841 0 = false
#guard validBufferRange 0 3841 = false
#guard validBufferRange 0xffffffffffffffff 1 = false
#guard validBufferRange 1 0xffffffffffffffff = false
#guard validPeriod 1 = false
#guard validPeriod 9999 = false
#guard validPeriod 10000 = true
#guard validPeriod 1000000 = true
#guard validPeriod 0 = false
#guard validPeriod 1000001 = false
#guard validFixedQuanta 4096 = true
#guard validFixedQuanta 4097 = false
#guard validDelta 1 = true
#guard validDelta 256 = true
#guard validDelta 0 = false
#guard validDelta 257 = false
#guard validWorkGoal 999742 256 = true
#guard validWorkGoal 999744 256 = false
#guard validWorkGoal 0xffffffffffffffff 1 = false
#guard scalarEvaluation 0 0xffffffffffffffff 2 = 1
#guard scalarEvaluation 1 0xffffffffffffffff 0x8000000000000000 = 0x7fffffffffffffff

open Lean Elab Command

elab "#monitor_frontend_lowering_probe" : command => do
  let roots := #[``Lemma.Examples.Foundation.Monitor.foreground,
    ``Lemma.Examples.Foundation.Timer.dispatch]
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV07 (← getEnv) roots with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  unless suite.contractVersion == "core0-v0.7" && suite.roots.size == 2 &&
      suite.roots[0]!.signature.args.isEmpty &&
      suite.roots[1]!.signature.args == Array.replicate 9 Lemma.Core0.Ty.u64 do
    throwError "monitor checked roots or unchanged v0.7 profile differ"
  unless suite.usedTimerOps.size == 7 &&
      Lemma.Core0.Timer.Op.all.all suite.usedTimerOps.contains do
    throwError "monitor does not reach all seven exact timer operations"
  unless suite.usedTrapOps.size == 2 && suite.usedTrapOps.contains .ecall &&
      suite.usedTrapOps.contains .breakpoint do
    throwError "monitor synchronous primitive subset differs"
  unless suite.usedDeviceOps.size == 4 do
    throwError "monitor does not reach all four closed UART operations"
  let preserveCalls := suite.scalarFunctions.map (fun f => f.name) ++
    suite.actionFunctions.map (fun f => f.name)
  let lowered ← match Lemma.Compiler.lowerActionSuiteV07 suite { preserveCalls } with
    | .ok lowered => pure lowered
    | .error message => throwError message
  unless lowered.roots.size == 2 do throwError "monitor lowering omitted a root"
  logInfo m!"Monitor genuine v0.7 frontend/lowering passed: {suite.scalarFunctions.size} scalar functions, {suite.actionFunctions.size} Action functions, 7 timer/2 trap/4 UART operations"

#monitor_frontend_lowering_probe
#eval IO.println "MONITOR_POLICY_PROBES:50 FRONTEND_LOWERING:1"

end Lemma.Examples.Foundation.Monitor.PolicyProbes
