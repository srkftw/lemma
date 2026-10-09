import examples.foundation.TrapConformance

/-! Direct host evaluation of the original elaborated policy, not the Core0
interpreter.  These probes and two local lemmas do not certify emitted code. -/

open Lemma.Examples.Foundation.Trap

#guard resumeAddress 11 0x1000 0x1800 0 0 0x1000 0x1004 0x2000 0x2004 = 0x1004
#guard resumeAddress 3 0x2000 0x1800 0 0 0x1000 0x1004 0x2000 0x2004 = 0x2004
#guard resumeAddress 3 0x2000 0x1800 0x2000 0 0x1000 0x1004 0x2000 0x2004 = 0x2004
#guard resumeAddress 11 0x1000 0xa00001800 0 0 0x1000 0x1004 0x2000 0x2004 = 0x1004
#guard resumeAddress 11 0x1004 0x1800 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 3 0x1000 0x1800 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 11 0x2000 0x1800 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 2 0x1000 0x1800 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 0x8000000000000007 0x1000 0x1800 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 11 0x1000 0x1808 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 11 0x1000 0x1880 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 11 0x1000 0x800 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 11 0x1000 0x21800 0 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 11 0x1000 0x1800 1 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 3 0x2000 0x1800 0x2004 0 0x1000 0x1004 0x2000 0x2004 = 0
#guard resumeAddress 11 0x1000 0x1800 0 128 0x1000 0x1004 0x2000 0x2004 = 0
#guard denialStatus 0 = 1
#guard denialStatus 11 = 9
#guard denialStatus 13 = 1
#guard mix 0 1 = (0x100000001b3 : UInt64)

theorem approvedEcallResume (pc resume breakSite breakResume mstatus : UInt64)
    (statusValid : (mstatus &&& 0x21888) = 0x1800) :
    resumeAddress 11 pc mstatus 0 0 pc resume breakSite breakResume = resume := by
  simp [resumeAddress, statusValid]

theorem approvedBreakpointResume (pc resume ecallSite ecallResume mstatus : UInt64)
    (statusValid : (mstatus &&& 0x21888) = 0x1800) :
    resumeAddress 3 pc mstatus pc 0 ecallSite ecallResume pc resume = resume := by
  simp [resumeAddress, statusValid]

#print axioms approvedEcallResume
#print axioms approvedBreakpointResume
#eval IO.println "TRAP_POLICY_PROBES:20"
