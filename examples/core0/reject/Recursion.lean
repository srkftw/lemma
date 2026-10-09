import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.Recursion

partial def root (x : UInt64) : UInt64 :=
  root x

#core0_check root

end Lemma.Examples.Core0.Reject.Recursion
