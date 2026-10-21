import Lemma.Platform.LemmaSim.IO
import Lemma.Platform.Silicon.BindingMultimodal
import Lemma.Kernel.Memory.Frames

/-! Version1/2 bounded controller driver. It never accepts an application MMIO
address. Stable queue heads are copied before explicit ACK; reads have no ACK.
The controller is synthetic converter input, not qualified physical sensors. -/
namespace Lemma.Drivers.Multimodal

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Platform.LemmaSim

def base : UInt64 := Lemma.Platform.Silicon.BindingMultimodal.multimodal_base
def read (stream offset : UInt64) : Action :=
  if stream < 9 then if offset < 256 then if offset % 8 = 0 then
    IO.read64 (base + 256 + stream * 256 + offset)
  else .done 2 0 else .done 2 0 else .done 2 0

def write (stream offset value : UInt64) : Action :=
  if stream < 9 then if offset < 256 then if offset % 8 = 0 then
    IO.write64 (base + 256 + stream * 256 + offset) value
  else .done 2 0 else .done 2 0 else .done 2 0

/-- Fixed historical descriptor is separately validated by the boot consumer.
This read-only versioned header discovers the additive aperture, not a JSON file. -/
def discover : Action :=
  .bind (IO.read64 base) fun s magic => if mmFailed s = true then .done s 0 else
  if mmDifferent magic 0x4c4d4d32 = true then .done 2 0 else
  .bind (IO.read64 (base + 8)) fun s version => if mmFailed s = true then .done s 0 else
  if (if version = 1 then false else if version = 2 then false else true) = true then .done 2 0 else
  .bind (IO.read64 (base + 16)) fun s features => if mmFailed s = true then .done s 0 else
  if mmDifferent features 511 = true then .done 2 0 else
  .bind (IO.read64 (base + 72)) fun s hz => if mmFailed s = true then .done s 0 else
  if mmDifferent hz 100000000 = true then .done 2 0 else
  .bind (IO.read64 (base + 80)) fun s capacity => if mmFailed s = true then .done s 0 else
  if mmDifferent capacity 16 = true then .done 2 0 else
  .bind (IO.read64 (base + 88)) fun s bytes => if mmFailed s = true then .done s 0 else
  if mmDifferent bytes 64 = true then .done 2 0 else
  .bind (IO.read64 (base + 96)) fun s physical => if mmFailed s = true then .done s 0 else
  if mmDifferent physical 0 = true then .done 15 0 else .done 0 features

private def headOffset (i : UInt64) : UInt64 :=
  if i = 0 then 112 else if i = 1 then 120 else if i = 2 then 128 else
  if i = 3 then 136 else if i = 4 then 224 else if i = 5 then 32 else
  if i = 6 then 192 else 72

private def copyStep (i _ : UInt32) (acc stream destination _ _ : UInt64) : Action :=
  .bind (read stream (headOffset i.toUInt64)) fun s v => if mmFailed s = true then .done s 0 else
  .bind (Access.write64 (destination + i.toUInt64 * 8) v) fun s _ => .done s acc

def take (stream handle : UInt64) : Action :=
  if 8 ≤ stream then .done 2 0 else
  .bind (read stream 144) fun s queued => if mmFailed s = true then .done s 0 else
  if queued = 0 then .done 6 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s destination => if mmFailed s = true then .done s 0 else
  .bind (read stream 224) fun s sequence => if mmFailed s = true then .done s 0 else
  .bind (read stream 32) fun s epoch => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 8 copyStep 8 0 stream destination 0 0 fun s _ => if mmFailed s = true then .done s 0 else
  .bind (read stream 224) fun s again => if mmFailed s = true then .done s 0 else
  .bind (read stream 32) fun s sameEpoch => if mmFailed s = true then .done s 0 else
  if mmDifferent sequence again = true then .done 4 0 else if mmDifferent epoch sameEpoch = true then .done 4 0 else
  .bind (write stream 152 1) fun s _ => .done s sequence

def command (stream command : UInt64) : Action :=
  .bind (write stream 24 command) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (read stream 16) fun s error => if mmFailed s = true then .done s 0 else .done error.toUInt8 0

end Lemma.Drivers.Multimodal
