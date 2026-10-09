import Lemma.Core0.ScalarLemmas

/-!
Auditable theorem dependency report for the local `core0-v0.2` scalar facts.

This file is executed by the Gate 3 acceptance driver.  These are deliberately
local arithmetic/conversion facts, not a proof of frontend or compiler correctness.
-/

#print axioms Lemma.Core0.ScalarLemmas.fixedWidthNormalize_lt
#print axioms Lemma.Core0.ScalarLemmas.fixedWidthNormalize_idempotent
#print axioms Lemma.Core0.ScalarLemmas.maskedShiftCount_lt
#print axioms Lemma.Core0.ScalarLemmas.shiftCountMask_eq_mod
#print axioms Lemma.Core0.ScalarLemmas.shiftCountMask_lt
#print axioms Lemma.Core0.ScalarLemmas.u8ToU32ToU8
#print axioms Lemma.Core0.ScalarLemmas.u8ToU64ToU8
#print axioms Lemma.Core0.ScalarLemmas.u32ToU64ToU32
