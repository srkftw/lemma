import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.HostedIO

def root (x : UInt64) : IO UInt64 :=
  pure (x + 1)

#core0_check root

end Lemma.Examples.Core0.Reject.HostedIO
