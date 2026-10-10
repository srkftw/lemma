import Lemma.Platform.LemmaSim.IO

/-! Pinned virt hart0 S context1. Only block1/paper12/pen13 are enabled;
one claim is serviced per trap, expensive work is deferred to guest tasks. -/
namespace Lemma.Drivers.PLIC
open Lemma.Core0.Memory
private def write (address value : UInt64) : Action := Lemma.Platform.LemmaSim.IO.write32 address value

def «initialize» : Action :=
  .bind (write 0x0c000004 1) fun s _ => if s = 0 then
  .bind (write 0x0c000030 1) fun s _ => if s = 0 then
  .bind (write 0x0c000034 1) fun s _ => if s = 0 then
  .bind (write 0x0c002080 0x3002) fun s _ => if s = 0 then
  write 0x0c201000 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def claim : Action := Lemma.Platform.LemmaSim.IO.read32 0x0c201004

def complete (source : UInt64) : Action :=
  if source = 1 then write 0x0c201004 source else
  if source = 12 then write 0x0c201004 source else
  if source = 13 then write 0x0c201004 source else .done 169 0

end Lemma.Drivers.PLIC

namespace Lemma.Drivers.PLIC
open Lemma.Core0.Memory
/-- Mask a level source until the authorized consumer advances its stable head.
This prevents a full FIFO from starving the user task before it can ACK. -/
def disablePen : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c002080) fun s enabled =>
  if s = 0 then Lemma.Platform.LemmaSim.IO.write32 0x0c002080 (enabled &&& 0xffffdfff) else .done s 0
def enablePen : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c002080) fun s enabled =>
  if s = 0 then Lemma.Platform.LemmaSim.IO.write32 0x0c002080 (enabled ||| 8192) else .done s 0
/-- Paper's interrupted-refresh level remains asserted until a full quality
refresh completes. Mask it while the surface task performs bounded recovery. -/
def disablePaper : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c002080) fun s enabled =>
  if s = 0 then Lemma.Platform.LemmaSim.IO.write32 0x0c002080 (enabled &&& 0xffffefff) else .done s 0
def enablePaper : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c002080) fun s enabled =>
  if s = 0 then Lemma.Platform.LemmaSim.IO.write32 0x0c002080 (enabled ||| 4096) else .done s 0
end Lemma.Drivers.PLIC
