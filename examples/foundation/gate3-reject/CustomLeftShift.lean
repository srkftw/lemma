import Lemma.Core0

namespace Lemma.Examples.Foundation.Gate3Reject.CustomLeftShift

set_option warn.classDefReducibility false

def deceptiveShift : HShiftLeft UInt8 UInt8 UInt8 :=
  ⟨fun _ _ => 0⟩

def root (x amount : UInt8) : UInt8 :=
  @HShiftLeft.hShiftLeft UInt8 UInt8 UInt8 deceptiveShift x amount

#core0_check_v0_2 root

end Lemma.Examples.Foundation.Gate3Reject.CustomLeftShift
