import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.CapturingClosure

def root (x : UInt64) : UInt64 :=
  let captures := fun y : UInt64 => x + y
  captures 1

#core0_check root

end Lemma.Examples.Core0.Reject.CapturingClosure
