import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.ExternWithBody

@[extern "lemma_forbidden_foreign_with_body"]
def root (x : UInt64) : UInt64 :=
  x + 1

#core0_check root

end Lemma.Examples.Core0.Reject.ExternWithBody
