import Lemma.Core0

namespace Lemma.Examples.Foundation.Gate3Reject.BranchHiddenExtern

@[extern "lemma_gate3_forbidden_foreign"]
opaque foreignStep (x : UInt64) : UInt64

def helper (x : UInt64) : UInt64 :=
  foreignStep x

def root (takeSafeBranch : Bool) (x divisor : UInt64) : UInt64 :=
  if takeSafeBranch then x / divisor else helper x

#core0_check_v0_2 root

end Lemma.Examples.Foundation.Gate3Reject.BranchHiddenExtern
