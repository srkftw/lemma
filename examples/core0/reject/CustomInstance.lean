import Lemma.Core0

namespace Lemma.Examples.Core0.Reject.CustomInstance

def deceptiveAdd : HAdd UInt64 UInt64 UInt64 :=
  ⟨fun _ _ => 0⟩

def root (x y : UInt64) : UInt64 :=
  @HAdd.hAdd UInt64 UInt64 UInt64 deceptiveAdd x y

#core0_check root

end Lemma.Examples.Core0.Reject.CustomInstance
