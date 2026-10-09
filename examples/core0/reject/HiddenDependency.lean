import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.HiddenDependency

def hiddenDivision (x : UInt64) : UInt64 :=
  x / 3

def root (x : UInt64) : UInt64 :=
  hiddenDivision (x + 1)

#core0_check root

end Lemma.Examples.Core0.Reject.HiddenDependency
