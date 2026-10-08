import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.InitializationEffect

initialize state : UInt64 ← pure 7

def root (x : UInt64) : UInt64 :=
  x + state

#core0_check root

end Lemma.Examples.Core0.Reject.InitializationEffect
