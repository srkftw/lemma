import Lemma.Platform.LemmaSim.IO
import Lemma.Platform.LemmaSim.DeviceABI
import Lemma.Kernel.Memory.Frames

/-! Stable-head PIO driver. Raw records are copied intact to kernel-owned
storage before ACK. Ink authorities interpret them in user space. Loss never
looks like an ordinary sample: it returns a separate epoch-resync outcome. -/
namespace Lemma.Drivers.Pen
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Platform.LemmaSim

def base : UInt64 := DeviceABI.penBase
def invalid : UInt8 := 173
def empty : UInt8 := 174
def lost : UInt8 := 175
def failed (s : UInt8) : Bool := if s = 0 then false else true
private def read (offset : UInt64) : Action := Lemma.Platform.LemmaSim.IO.read64 (base + offset)
private def write (offset value : UInt64) : Action := Lemma.Platform.LemmaSim.IO.write64 (base + offset) value

def «initialize» : Action :=
  .bind (read DeviceABI.penMagicOffset) fun s magic => if failed s = true then .done s 0 else
  if magic = DeviceABI.penMagic then
  .bind (read DeviceABI.penVersionOffset) fun s version => if failed s = true then .done s 0 else
  if version = 1 then read 40 else .done invalid 0 else .done invalid 0

private def copyWord (i _ : UInt32) (acc destination _ _ _ : UInt64) : Action :=
  .bind (read (0x100 + i.toUInt64 * 8)) fun s value =>
  if s = 0 then .bind (Access.write64 (destination + i.toUInt64 * 8) value) fun s _ =>
  .done s acc else .done s 0

/-- A loss cancels the consumer's current stroke before it may accept the next
contact. No sample is acknowledged if copy or epoch/sequence recheck fails.
The model inhibits ingress across overflow until LOSS_ACK and a new boundary. -/
def take (handle : UInt64) : Action :=
  .bind (read DeviceABI.penStatusOffset) fun s status => if failed s = true then .done s 0 else
  if status &&& 2 = 2 then
    .bind (read DeviceABI.penEpochOffset) fun s epoch => if failed s = true then .done s 0 else
    .bind (write DeviceABI.penLossAckOffset epoch) fun s _ => if s = 0 then .done lost epoch else .done s 0
  else if status &&& 1 = 1 then
    .bind (Frames.resolvePurpose 1 handle 1) fun s destination =>
    if failed s = true then .done s 0 else
    .bind (read DeviceABI.penHeadSeqOffset) fun s sequence => if failed s = true then .done s 0 else
    .bind (read DeviceABI.penHeadEpochOffset) fun s epoch => if failed s = true then .done s 0 else
    .boundedFoldU64 9 copyWord 9 0 destination 0 0 0 fun s _ =>
    if failed s = true then .done s 0 else
    .bind (read DeviceABI.penHeadSeqOffset) fun s again => if failed s = true then .done s 0 else
    .bind (read DeviceABI.penHeadEpochOffset) fun s sameEpoch => if failed s = true then .done s 0 else
    if sequence = again then if epoch = sameEpoch then
      .bind (write DeviceABI.penAckOffset sequence) fun s _ => if s = 0 then .done 0 sequence else .done s 0
    else .done lost sameEpoch else .done lost sameEpoch
  else .done empty 0

end Lemma.Drivers.Pen
