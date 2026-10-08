import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.Allocation

def root (x : UInt64) : UInt64 :=
  let boxed := [x, x + 1]
  boxed.head?.getD 0

#core0_check root

end Lemma.Examples.Core0.Reject.Allocation
