import Lemma.Core0.Memory

/-! User virtual-memory operations. The compiler bounds the scalar address
domain; the current hardware mapping supplies ownership and permission checks. -/
namespace Lemma.User.Memory
open Lemma.Core0.Memory

def read8 (address : UInt64) : Action :=
  .platform .virtualRead8 address 0 0 0 0 0 fun s v => .done s v
def read64 (address : UInt64) : Action :=
  .platform .virtualRead64 address 0 0 0 0 0 fun s v => .done s v
def write8 (address value : UInt64) : Action :=
  .platform .virtualWrite8 address value 0 0 0 0 fun s v => .done s v
def write64 (address value : UInt64) : Action :=
  .platform .virtualWrite64 address value 0 0 0 0 fun s v => .done s v

end Lemma.User.Memory
