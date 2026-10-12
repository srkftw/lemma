import Lemma.Platform.LemmaSim.IO
import Lemma.Platform.LemmaSim.DeviceABI
import Lemma.Drivers.Paper
import Lemma.Drivers.Pen
import Lemma.Drivers.PLIC
import Lemma.Kernel.Console
import Lemma.Kernel.Memory.Frames

/-! Quarantined silicon development fixture. These are actual guest MMIO
observations, never hardware or application policy. The external input corpus
must overflow the pen FIFO before this fixture consumes it. -/
namespace Lemma.Platform.Silicon.Development.DeviceProbe
open Lemma.Core0.Memory
open Lemma.Platform.LemmaSim
open Lemma.Kernel.Memory
private def fatal : Action := .done 178 0
private def paperRead (offset : UInt64) : Action := IO.read64 (DeviceABI.paperBase + offset)
private def paperWrite (offset value : UInt64) : Action := IO.write64 (DeviceABI.paperBase + offset) value
private def penRead (offset : UInt64) : Action := IO.read64 (DeviceABI.penBase + offset)
private def penWrite (offset value : UInt64) : Action := IO.write64 (DeviceABI.penBase + offset) value

private def paper : Action :=
  .bind (paperWrite DeviceABI.paperCommandOffset 99) fun s _ => if s = 0 then
  .bind (paperRead DeviceABI.paperErrorOffset) fun s invalid => if s = 0 then if invalid = 1 then
  .bind Lemma.Drivers.Paper.completion fun s _ => if s = 0 then
  .bind (Lemma.Drivers.Paper.refresh 1 0 0 1 1 2) fun s accepted => if s = 0 then if accepted = 1 then
  .bind (Lemma.Drivers.Paper.refresh 2 0 0 1 1 2) fun busy _ => if busy = Lemma.Drivers.Paper.busy then
  .bind (paperWrite DeviceABI.paperCommandOffset 2) fun s _ => if s = 0 then
  .bind (paperRead DeviceABI.paperErrorOffset) fun s rejected => if s = 0 then if rejected = 4 then
  .bind (paperWrite DeviceABI.paperResetOffset 1) fun s _ => if s = 0 then
  .bind (paperRead DeviceABI.paperStatusOffset) fun s status => if s = 0 then if status &&& 9 = 8 then
  .bind (paperRead DeviceABI.paperErrorOffset) fun s interrupted => if s = 0 then if interrupted = 6 then
  .bind (paperRead DeviceABI.paperCompletedOffset) fun s completed => if s = 0 then if completed = 0 then
  Lemma.Kernel.Console.record 0x40e invalid busy.toUInt64 rejected interrupted
  else fatal else .done s 0 else fatal else .done s 0 else fatal else .done s 0
  else .done s 0 else fatal else .done s 0 else .done s 0 else fatal
  else fatal else .done s 0 else .done s 0 else fatal else .done s 0 else .done s 0

private def pen : Action :=
  .bind (Frames.allocate 1 1) fun s handle => if s = 0 then
  .bind (penRead DeviceABI.penCountOffset) fun s count => if s = 0 then if count = 1 then
  .bind (penRead DeviceABI.penHeadSeqOffset) fun s head => if s = 0 then if head = 1 then
  .bind (penWrite DeviceABI.penAckOffset (head + 1)) fun s _ => if s = 0 then
  .bind (penRead DeviceABI.penErrorOffset) fun s badAck => if s = 0 then if badAck = 2 then
  .bind (penRead DeviceABI.penHeadSeqOffset) fun s same => if s = 0 then if same = head then
  .bind (Lemma.Drivers.Pen.take handle) fun loss epoch => if loss = Lemma.Drivers.Pen.lost then if epoch = 2 then
  .bind (penRead DeviceABI.penCountOffset) fun s cleared => if s = 0 then if cleared = 0 then
  .bind (penWrite DeviceABI.penResetOffset 1) fun s _ => if s = 0 then
  .bind (Lemma.Drivers.Pen.take handle) fun warm nextEpoch => if warm = Lemma.Drivers.Pen.lost then if nextEpoch = 3 then
  Lemma.Kernel.Console.record 0x40f head badAck epoch nextEpoch
  else fatal else fatal else .done s 0 else fatal else .done s 0 else fatal else fatal
  else fatal else .done s 0 else fatal else .done s 0 else .done s 0 else fatal else .done s 0
  else fatal else .done s 0 else .done s 0

def run : Action :=
  .bind paper fun s _ => if s = 0 then
  -- Interrupted remains a real level until a full quality refresh completes.
  -- This negative diagnostic masks that source so it can observe pen13 while
  -- preserving the uncertain panel state; the notebook owns real recovery.
  .bind Lemma.Drivers.PLIC.disablePaper fun s _ => if s = 0 then pen else .done s 0
  else .done s 0
end Lemma.Platform.Silicon.Development.DeviceProbe
