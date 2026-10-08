import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.CompilerReplacement

unsafe def uncheckedReplacement (x : UInt64) : UInt64 :=
  x

@[implemented_by uncheckedReplacement]
def root (x : UInt64) : UInt64 :=
  x + 1

#core0_check root

end Lemma.Examples.Core0.Reject.CompilerReplacement
