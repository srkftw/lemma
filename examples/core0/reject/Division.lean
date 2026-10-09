import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.Division

def root (x y : UInt64) : UInt64 :=
  x / y

#core0_check root

end Lemma.Examples.Core0.Reject.Division
