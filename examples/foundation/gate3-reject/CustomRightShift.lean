import Lemma.Core0

namespace Lemma.Examples.Foundation.Gate3Reject.CustomRightShift

set_option warn.classDefReducibility false

def deceptiveShift : HShiftRight UInt64 UInt64 UInt64 :=
  ⟨fun _ _ => 0⟩

def root (x amount : UInt64) : UInt64 :=
  @HShiftRight.hShiftRight UInt64 UInt64 UInt64 deceptiveShift x amount

#core0_check_v0_2 root

end Lemma.Examples.Foundation.Gate3Reject.CustomRightShift
