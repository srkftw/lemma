import Lemma.Platform.LemmaSim.IO
import Lemma.Platform.LemmaSim.DeviceABI
import Lemma.Kernel.Memory.Frames

/-! Compiled PIO transport only: tile upload and rectangle refresh. Pixel/brush
algorithms belong to the authorized U-mode surface producer, not this driver.
Busy preserves ownership of the accepted controller refresh. -/
namespace Lemma.Drivers.Paper
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Platform.LemmaSim

def base : UInt64 := DeviceABI.paperBase
def failed (s : UInt8) : Bool := if s = 0 then false else true
private def read (offset : UInt64) : Action := Lemma.Platform.LemmaSim.IO.read64 (base + offset)
private def write (offset value : UInt64) : Action := Lemma.Platform.LemmaSim.IO.write64 (base + offset) value

def invalid : UInt8 := 170
def busy : UInt8 := 171
def deviceError : UInt8 := 172

def dimensions : Action :=
  .bind (read DeviceABI.paperWidthOffset) fun s width =>
  if s = 0 then .bind (read DeviceABI.paperHeightOffset) fun s height =>
  if s = 0 then .done 0 (width ||| (height <<< 32)) else .done s 0 else .done s 0

def «initialize» : Action :=
  .bind (read DeviceABI.paperMagicOffset) fun s magic =>
  if failed s = true then .done s 0 else
  if magic = DeviceABI.paperMagic then
  .bind (read DeviceABI.paperVersionOffset) fun s version =>
  if failed s = true then .done s 0 else
  if version = 1 then dimensions else .done invalid 0 else .done invalid 0

private def uploadWord (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (buffer + i.toUInt64 * 8)) fun s packed =>
  if s = 0 then .bind (write (0x800 + i.toUInt64 * 8) packed) fun s _ => .done s acc
  else .done s 0

/-- handle is a resolved owner1/purpose1 bounce frame, not U memory. Width32
and height32 use512 packed bytes; edge tiles may be smaller. The guest supplies
white unused low nibbles. The controller independently validates every field. -/
def upload (handle x y width height : UInt64) : Action :=
  if width = 0 then .done invalid 0 else if 32 < width then .done invalid 0 else
  if height = 0 then .done invalid 0 else if 32 < height then .done invalid 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s buffer =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileXOffset x) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileYOffset y) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileWOffset width) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileHOffset height) fun s _ => if failed s = true then .done s 0 else
  let length := ((width + 1) / 2) * height
  .bind (write DeviceABI.paperTileLenOffset length) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 64 uploadWord ((length + 7) / 8).toUInt32 0 buffer 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperCommandOffset 1) fun s _ => if failed s = true then .done s 0 else
  .bind (read DeviceABI.paperErrorOffset) fun s error => if s = 0 then
    if error = 0 then .done 0 length else .done deviceError error else .done s 0

/-- One in-flight request; no wait loop in the driver. Status/sequence is
observed later by the bounded interrupt/completion path. -/
def refresh (sequence x y width height mode : UInt64) : Action :=
  if sequence = 0 then .done invalid 0 else
  .bind (read DeviceABI.paperStatusOffset) fun s status => if failed s = true then .done s 0 else
  if status &&& 1 = 1 then .done busy 0 else
  .bind (write DeviceABI.paperSequenceOffset sequence) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperRectXOffset x) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperRectYOffset y) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperRectWOffset width) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperRectHOffset height) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperModeOffset mode) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperCommandOffset 2) fun s _ => if failed s = true then .done s 0 else
  .bind (read DeviceABI.paperErrorOffset) fun s error => if s = 0 then
    if error = 0 then .done 0 sequence else .done deviceError error else .done s 0

def completion : Action :=
  .bind (read DeviceABI.paperCompletedOffset) fun s seq => if s = 0 then
  .bind (write DeviceABI.paperAckOffset seq) fun s _ => .done s seq else .done s 0

end Lemma.Drivers.Paper
