import Lemma.Core0

namespace Lemma.Examples.Foundation.Gate3Reject.CustomRemainder

set_option warn.classDefReducibility false

def deceptiveRemainder : HMod UInt32 UInt32 UInt32 :=
  ⟨fun _ _ => 0⟩

def root (x y : UInt32) : UInt32 :=
  @HMod.hMod UInt32 UInt32 UInt32 deceptiveRemainder x y

#core0_check_v0_2 root

end Lemma.Examples.Foundation.Gate3Reject.CustomRemainder
