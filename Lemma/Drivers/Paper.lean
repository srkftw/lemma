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

/-- Additive Surface-v2 source slot. The existing upload entry is unchanged.
Every field and owner is checked afresh, and each controller command retains
its own error result. No batch atomicity or controller bypass is implied. -/
def uploadOffset (handle offset x y width height : UInt64) : Action :=
  if width = 0 then .done invalid 0 else if 32 < width then .done invalid 0 else
  if height = 0 then .done invalid 0 else if 32 < height then .done invalid 0 else
  let length := ((width + 1) / 2) * height
  let copied := ((length + 7) / 8) * 8
  if offset % 8 = 0 then if offset ≤ 4096 - copied then
  .bind (Frames.resolvePurpose 1 handle 1) fun s buffer =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileXOffset x) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileYOffset y) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileWOffset width) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileHOffset height) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileLenOffset length) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 64 uploadWord ((length + 7) / 8).toUInt32 0 (buffer + offset) 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperCommandOffset 1) fun s _ => if failed s = true then .done s 0 else
  .bind (read DeviceABI.paperErrorOffset) fun s error => if s = 0 then
    if error = 0 then .done 0 length else .done deviceError error else .done s 0
  else .done invalid 0 else .done invalid 0

/-- Paper-v2 is selected only by validated successor discovery. Read actual
controller version and staging register; a profile label alone cannot admit it. -/
def initializeNext : Action :=
  .bind (read DeviceABI.paperMagicOffset) fun s magic => if s = 0 then
  if magic = DeviceABI.paperMagic then
  .bind (read DeviceABI.paperVersionOffset) fun s version => if s = 0 then
  if version = 2 then
  .bind (read 184) fun s staging => if s = 0 then
  if staging = 3584 then dimensions else .done invalid 0
  else .done s 0 else .done invalid 0 else .done s 0
  else .done invalid 0 else .done s 0

private def uploadWordNext (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (buffer + i.toUInt64 * 8)) fun s packed =>
  if s = 0 then .bind (write (0xe00 + i.toUInt64 * 8) packed) fun s _ => .done s acc
  else .done s 0

/-- handle is a resolved owner1/purpose1 bounce frame, not U memory. Width32
and height32 use512 packed bytes; edge tiles may be smaller. The guest supplies
white unused low nibbles. The controller independently validates every field. -/
def uploadNext (handle x y width height : UInt64) : Action :=
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
  .boundedFoldU64 64 uploadWordNext ((length + 7) / 8).toUInt32 0 buffer 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperCommandOffset 1) fun s _ => if failed s = true then .done s 0 else
  .bind (read DeviceABI.paperErrorOffset) fun s error => if s = 0 then
    if error = 0 then .done 0 length else .done deviceError error else .done s 0


def uploadOffsetNext (handle offset x y width height : UInt64) : Action :=
  if width = 0 then .done invalid 0 else if 32 < width then .done invalid 0 else
  if height = 0 then .done invalid 0 else if 32 < height then .done invalid 0 else
  let length := ((width + 1) / 2) * height
  let copied := ((length + 7) / 8) * 8
  if offset % 8 = 0 then if offset ≤ 4096 - copied then
  .bind (Frames.resolvePurpose 1 handle 1) fun s buffer =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileXOffset x) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileYOffset y) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileWOffset width) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileHOffset height) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileLenOffset length) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 64 uploadWordNext ((length + 7) / 8).toUInt32 0 (buffer + offset) 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperCommandOffset 1) fun s _ => if failed s = true then .done s 0 else
  .bind (read DeviceABI.paperErrorOffset) fun s error => if s = 0 then
    if error = 0 then .done 0 length else .done deviceError error else .done s 0
  else .done invalid 0 else .done invalid 0



/-- Paper3 preserves disjoint staging and adds a read-only executed-refresh
witness. Only actual version3 and its real3584 aperture select this entry. -/
def initializeExecuted : Action :=
  .bind (read DeviceABI.paperMagicOffset) fun s magic => if s = 0 then
  if magic = DeviceABI.paperMagic then
  .bind (read DeviceABI.paperVersionOffset) fun s version => if s = 0 then
  if version = 3 then
  .bind (read 184) fun s staging => if s = 0 then
  if staging = 3584 then dimensions else .done invalid 0
  else .done s 0 else .done invalid 0 else .done s 0
  else .done invalid 0 else .done s 0

/-- Private bounded paper staging span. A group still issues the original
ordered read64 then fenced write64 pair for every word. The local guards expose
the already owned pool/staging bounds to the checked LLVM lowering. -/
private def uploadWordBlockAt (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  let ordinal := i.toUInt64 * 8
  let source := buffer + ordinal * 8
  let stage := DeviceABI.paperBase + 0x800 + ordinal * 8
  if i < 8 then
  if Frames.pool ≤ source then if source ≤ Frames.expandedPoolLimit - 64 then
  if source % 8 = 0 then
  .bind (Access.read64 source) fun s word0 => if s = 0 then
  .platform .deviceWrite64 stage word0 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 (source + 8)) fun s word1 => if s = 0 then
  .platform .deviceWrite64 (stage + 8) word1 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 (source + 16)) fun s word2 => if s = 0 then
  .platform .deviceWrite64 (stage + 16) word2 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 (source + 24)) fun s word3 => if s = 0 then
  .platform .deviceWrite64 (stage + 24) word3 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 (source + 32)) fun s word4 => if s = 0 then
  .platform .deviceWrite64 (stage + 32) word4 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 (source + 40)) fun s word5 => if s = 0 then
  .platform .deviceWrite64 (stage + 40) word5 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 (source + 48)) fun s word6 => if s = 0 then
  .platform .deviceWrite64 (stage + 48) word6 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 (source + 56)) fun s word7 => if s = 0 then
  .platform .deviceWrite64 (stage + 56) word7 0 0 0 0 fun s _ => if s = 0 then
  .done 0 acc
  else .done s acc else .done s 0 else .done s acc else .done s 0 else .done s acc else .done s 0 else .done s acc else .done s 0 else .done s acc else .done s 0 else .done s acc else .done s 0 else .done s acc else .done s 0 else .done s acc else .done s 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0

private def uploadWordTailAt (i _ : UInt32) (acc buffer first _ _ : UInt64) : Action :=
  let ordinal := first + i.toUInt64
  let source := buffer + ordinal * 8
  if ordinal < 64 then
  if Frames.pool ≤ source then if source ≤ Frames.expandedPoolLimit - 8 then
  if source % 8 = 0 then
  .bind (Access.read64 source) fun s packed => if s = 0 then
  .platform .deviceWrite64 (DeviceABI.paperBase + 0x800 + ordinal * 8) packed 0 0 0 0
    fun s _ => .done s acc
  else .done s 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0

private def uploadWordsAt (buffer count : UInt64) : Action :=
  if count ≤ 64 then
  .boundedFoldU64 8 uploadWordBlockAt (count / 8).toUInt32 0 buffer 0 0 0 fun s _ =>
  if s = 0 then
  .boundedFoldU64 7 uploadWordTailAt (count % 8).toUInt32 0 buffer ((count / 8) * 8) 0 0
    fun s v => .done s v
  else .done s 0 else .done invalid 0

/-- Kernel-only same-Action source frame borrow. The sole selected bulk caller
has freshly resolved owner1/purpose1 generation before any PIO and retains a
frame disjoint from descriptor/cap/registry/stack metadata and every DMA span.
All shape/span, ordered word/PIO, command and error checks remain live. This
address is not a User pointer and never survives the enclosing syscall. -/
def uploadOffsetAt (buffer offset x y width height : UInt64) : Action :=
  if Frames.pool ≤ buffer then if buffer ≤ Frames.expandedPoolLimit - 4096 then
  if buffer % 4096 = 0 then
  if width = 0 then .done invalid 0 else if 32 < width then .done invalid 0 else
  if height = 0 then .done invalid 0 else if 32 < height then .done invalid 0 else
  let length := ((width + 1) / 2) * height
  let copied := ((length + 7) / 8) * 8
  if offset % 8 = 0 then if offset ≤ 4096 - copied then
  .bind (write DeviceABI.paperTileXOffset x) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileYOffset y) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileWOffset width) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileHOffset height) fun s _ => if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperTileLenOffset length) fun s _ => if failed s = true then .done s 0 else
  .bind (uploadWordsAt (buffer + offset) ((length + 7) / 8)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write DeviceABI.paperCommandOffset 1) fun s _ => if failed s = true then .done s 0 else
  .bind (read DeviceABI.paperErrorOffset) fun s error => if s = 0 then
    if error = 0 then .done 0 length else .done deviceError error else .done s 0
  else .done invalid 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0

end Lemma.Drivers.Paper
