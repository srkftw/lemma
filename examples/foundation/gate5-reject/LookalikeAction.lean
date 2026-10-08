import Lemma.Core0

namespace Lookalike

inductive Action where
  | load8 (region : UInt8) (offset : UInt64)

def root (region : UInt8) (offset : UInt64) : Action :=
  Action.load8 region offset

#core0_check_v0_4 root

end Lookalike
