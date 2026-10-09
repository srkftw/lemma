import Lemma.Core0

namespace Lemma.Examples.Foundation.Gate3Reject.CustomComplement

set_option warn.classDefReducibility false

def deceptiveComplement : Complement UInt64 :=
  ⟨fun _ => 0⟩

def root (x : UInt64) : UInt64 :=
  @Complement.complement UInt64 deceptiveComplement x

#core0_check_v0_2 root

end Lemma.Examples.Foundation.Gate3Reject.CustomComplement
