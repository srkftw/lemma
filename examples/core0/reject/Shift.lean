import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.Shift

def root (x amount : UInt64) : UInt64 :=
  x <<< amount

#core0_check root

end Lemma.Examples.Core0.Reject.Shift
