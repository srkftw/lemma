import Lemma.User.Syscall
import Lemma.User.Memory

/-! User-owned Gray4 surface. Every byte is produced by guest code. The kernel
receives bounded tile copies, and the controller alone publishes visible pixels.
The framebuffer is ordinary owned User memory, not arbitrary physical DMA. -/
namespace Lemma.Ink.Surface
open Lemma.Core0.Memory
open Lemma.User

def framebuffer : UInt64 := 0x110000
def metadata : UInt64 := 0x20200
def tile : UInt64 := 0x20500

def geometry (cap : UInt64) : Action := Syscall.call 64 cap 0 0 0 0
def acceptedSequence (cap : UInt64) : Action := Syscall.call 64 cap 3 0 0 0
def status (cap : UInt64) : Action := Syscall.call 64 cap 4 0 0 0
private def set (slot value : UInt64) : Action := Memory.write64 (metadata + slot) value

private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let va := framebuffer + i.toUInt64 * 4096
  .bind (Syscall.allocatePage va) fun s result => if s = 0 then
  if result = va then .done 0 (acc + 1) else .done 95 0 else .done s 0

def allocate (width height : UInt64) : Action :=
  if width = 0 then .done 16 0 else if 4096 < width then .done 16 0 else
  if height = 0 then .done 16 0 else if 4096 < height then .done 16 0 else
  let pages := (((width + 1) / 2) * height + 4095) / 4096
  if 1024 < pages then .done 16 0 else
  .boundedFoldU64 1024 allocateStep pages.toUInt32 0 0 0 0 0 fun s n => .done s n

/-- Authored3x5 uppercase alphabet and digits, row-major top-left bit14.
Source assets have no imported font or runtime dependency. -/
def letter (code : UInt64) : UInt64 :=
  if code = 65 then 0x2bed else if code = 68 then 0x6b6e else
  if code = 69 then 0x79a7 else if code = 70 then 0x79a4 else
  if code = 71 then 0x796f else if code = 72 then 0x5bed else
  if code = 73 then 0x7497 else if code = 76 then 0x4927 else
  if code = 78 then 0x5ffd else if code = 79 then 0x7b6f else
  if code = 80 then 0x7be4 else if code = 82 then 0x6bad else
  if code = 83 then 0x79cf else if code = 85 then 0x5b6f else
  if code = 86 then 0x5b6a else if code = 87 then 0x5b7f else
  if code = 89 then 0x5a92 else
  if code = 48 then 0x7b6f else if code = 49 then 0x2c97 else
  if code = 50 then 0x73e7 else if code = 51 then 0x73cf else
  if code = 52 then 0x5bc9 else if code = 53 then 0x79cf else
  if code = 54 then 0x79ef else if code = 55 then 0x7292 else
  if code = 56 then 0x7bef else if code = 57 then 0x7bcf else 0

/-- Home, left/right arrows, undo, redo, erase, width, save. -/
def glyph (number : UInt64) : UInt64 :=
  if number = 0 then letter 72 else if number = 1 then 0x29e2 else
  if number = 2 then 0x23ca else if number = 3 then letter 85 else
  if number = 4 then letter 82 else if number = 5 then letter 69 else
  if number = 6 then letter 87 else letter 83

def backgroundPixel (x y width height : UInt64) : UInt64 :=
  if height ≤ y then 15 else
  if y < 128 then
    let buttonWidth := width / 8
    let buttonX := x % buttonWidth
    let button := x / buttonWidth
    if buttonX < 3 then 0 else if buttonWidth - 3 ≤ buttonX then 0 else
    if y < 3 then 0 else if 125 ≤ y then 0 else
    if 36 ≤ y then if y < 96 then
    if 24 ≤ buttonX then if buttonX < 60 then
      let bit := (y - 36) / 12 * 3 + (buttonX - 24) / 12
      if (glyph button >>> (14 - bit)) &&& 1 = 1 then 0 else 15
    else 15 else 15 else 15 else 15
  else if y = 148 then 0 else if x = 24 then 12 else if width - 25 = x then 12 else
    if 180 ≤ y then if (y - 180) % 96 = 0 then 13 else 15 else 15

private def backgroundStep (i _ : UInt32) (acc dimensions _ _ _ : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let stride := (width + 1) / 2
  let x := (i.toUInt64 % stride) * 2
  let y := i.toUInt64 / stride
  let high := backgroundPixel x y width height
  let low := if width ≤ x + 1 then 15 else backgroundPixel (x + 1) y width height
  .bind (Memory.write8 (framebuffer + i.toUInt64) ((high <<< 4) ||| low)) fun s _ => .done s acc

/-- A full redraw is used for page open/edit recovery. Live ink uploads only
intersecting tiles and coalesces their bounding refresh rectangle. -/
def background (width height : UInt64) : Action :=
  let bytes := ((width + 1) / 2) * height
  if 2000000 < bytes then .done 16 0 else
  -- Two bounded halves keep each fold under the profile's1000000 budget.
  let first := if bytes < 1000000 then bytes else 1000000
  .boundedFoldU64 1000000 backgroundStep first.toUInt32 0 (width ||| (height <<< 16)) 0 0 0 fun s _ =>
  if s = 0 then
  .boundedFoldU64 1000000 backgroundTail (bytes - first).toUInt32 0 (width ||| (height <<< 16)) first 0 0 fun s _ => .done s bytes
  else .done s 0
where
  backgroundTail (i _ : UInt32) (acc dimensions offset _ _ : UInt64) : Action :=
    backgroundStep (i + offset.toUInt32) 0 acc dimensions 0 0 0

private def tileLoadStep (i _ : UInt32) (acc dimensions origin _ _ : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let x := (origin &&& 0xffff) + (i.toUInt64 % 16) * 2
  let y := (origin >>> 16) + i.toUInt64 / 16
  if height ≤ y then Memory.write8 (tile + i.toUInt64) 255 else
  if width ≤ x then Memory.write8 (tile + i.toUInt64) 255 else
  .bind (Memory.read8 (framebuffer + y * ((width + 1) / 2) + x / 2)) fun s byte =>
  if s = 0 then .bind (Memory.write8 (tile + i.toUInt64) byte) fun s _ => .done s acc else .done s 0

def loadTile (x y width height : UInt64) : Action :=
  .boundedFoldU64 512 tileLoadStep 512 0 (width ||| (height <<< 16)) (x ||| (y <<< 16)) 0 0 fun s _ => .done s 0

private def tileStoreStep (i _ : UInt32) (acc dimensions origin _ _ : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let x := (origin &&& 0xffff) + (i.toUInt64 % 16) * 2
  let y := (origin >>> 16) + i.toUInt64 / 16
  if height ≤ y then .done 0 acc else if width ≤ x then .done 0 acc else
  .bind (Memory.read8 (tile + i.toUInt64)) fun s byte => if s = 0 then
  .bind (Memory.write8 (framebuffer + y * ((width + 1) / 2) + x / 2) byte) fun s _ => .done s acc
  else .done s 0

def storeTile (x y width height : UInt64) : Action :=
  .boundedFoldU64 512 tileStoreStep 512 0 (width ||| (height <<< 16)) (x ||| (y <<< 16)) 0 0 fun s _ => .done s 0

private def compactStep (i _ : UInt32) (acc stride _ _ _ : UInt64) : Action :=
  .bind (Memory.read8 (tile + (i.toUInt64 / stride) * 16 + i.toUInt64 % stride)) fun s byte =>
  if s = 0 then .bind (Memory.write8 (tile + i.toUInt64) byte) fun s _ => .done s acc else .done s 0

def uploadTile (cap x y width height : UInt64) : Action :=
  let w := if 32 < width - x then 32 else width - x
  let h := if 32 < height - y then 32 else height - y
  .bind (set 0 x) fun s _ => if s = 0 then
  .bind (set 8 y) fun s _ => if s = 0 then
  .bind (set 16 w) fun s _ => if s = 0 then
  .bind (set 24 h) fun s _ => if s = 0 then
  .bind (if w = 32 then .done 0 0 else
    .boundedFoldU64 512 compactStep (((w + 1) / 2) * h).toUInt32 0 ((w + 1) / 2) 0 0 0 fun s _ => .done s 0) fun s _ =>
  if s = 0 then Syscall.call 64 cap 1 metadata tile 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def uploadStep (i _ : UInt32) (acc cap dimensions _ _ : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let columns := (width + 31) / 32
  let x := (i.toUInt64 % columns) * 32
  let y := (i.toUInt64 / columns) * 32
  .bind (loadTile x y width height) fun s _ => if s = 0 then
  .bind (uploadTile cap x y width height) fun s _ => .done s acc else .done s 0

def uploadAll (cap width height : UInt64) : Action :=
  let count := ((width + 31) / 32) * ((height + 31) / 32)
  .boundedFoldU64 16384 uploadStep count.toUInt32 0 cap (width ||| (height <<< 16)) 0 0 fun s _ => .done s count

def refresh (cap sequence x y width height mode : UInt64) : Action :=
  .bind (set 0 x) fun s _ => if s = 0 then
  .bind (set 8 y) fun s _ => if s = 0 then
  .bind (set 16 width) fun s _ => if s = 0 then
  .bind (set 24 height) fun s _ => if s = 0 then
  .bind (set 32 mode) fun s _ => if s = 0 then
  .bind (set 40 sequence) fun s _ => if s = 0 then
  Syscall.call 64 cap 2 metadata 0 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

end Lemma.Ink.Surface
