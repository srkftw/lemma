import Lemma.Core0

namespace Lemma.Examples.Foundation.Gate3Reject.CustomDivision

set_option warn.classDefReducibility false

def deceptiveDivision : HDiv UInt64 UInt64 UInt64 :=
  ⟨fun _ _ => 0⟩

def root (x y : UInt64) : UInt64 :=
  @HDiv.hDiv UInt64 UInt64 UInt64 deceptiveDivision x y

#core0_check_v0_2 root

end Lemma.Examples.Foundation.Gate3Reject.CustomDivision
