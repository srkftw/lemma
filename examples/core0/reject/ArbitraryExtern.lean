import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.ArbitraryExtern

@[extern "lemma_forbidden_foreign"]
opaque foreignStep (x : UInt64) : UInt64

def root (x : UInt64) : UInt64 :=
  foreignStep x

#core0_check root

end Lemma.Examples.Core0.Reject.ArbitraryExtern
