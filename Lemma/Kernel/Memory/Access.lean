import Lemma.Core0.Memory

/-! Trusted physical-storage boundary. The execution profile checks the exact
operation and bounds every access before constructing a pointer. User exports
cannot admit these operations. No allocator or policy lives in this boundary. -/
namespace Lemma.Kernel.Memory.Access
open Lemma.Core0.Memory

def read8 (address : UInt64) : Action :=
  .platform .physicalRead8 address 0 0 0 0 0 (fun s v => .done s v)
def read64 (address : UInt64) : Action :=
  .platform .physicalRead64 address 0 0 0 0 0 (fun s v => .done s v)
def write8 (address value : UInt64) : Action :=
  .platform .physicalWrite8 address value 0 0 0 0 (fun s v => .done s v)
def write64 (address value : UInt64) : Action :=
  .platform .physicalWrite64 address value 0 0 0 0 (fun s v => .done s v)

end Lemma.Kernel.Memory.Access
