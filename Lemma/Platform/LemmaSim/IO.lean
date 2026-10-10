import Lemma.Core0.Memory

/-! The v0.3 kernel-only device boundary. Every access is width-, alignment-,
range-checked and fenced by the compiler. This module grants no U-mode authority.
Addresses are selected by the concrete drivers, never application requests. -/
namespace Lemma.Platform.LemmaSim.IO
open Lemma.Core0.Memory

def read32 (address : UInt64) : Action :=
  .platform .deviceRead32 address 0 0 0 0 0 fun s v => .done s v
def write32 (address value : UInt64) : Action :=
  .platform .deviceWrite32 address value 0 0 0 0 fun s v => .done s v
def read64 (address : UInt64) : Action :=
  .platform .deviceRead64 address 0 0 0 0 0 fun s v => .done s v
def write64 (address value : UInt64) : Action :=
  .platform .deviceWrite64 address value 0 0 0 0 fun s v => .done s v

end Lemma.Platform.LemmaSim.IO
