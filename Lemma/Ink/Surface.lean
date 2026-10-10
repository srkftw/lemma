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

/-- Own3x5 glyphs, authored as literal bits, no imported font/license dependency.
Toolstrip glyphs: home, previous, next, undo, redo, eraser, width, save. -/
def glyph (number : UInt64) : UInt64 :=
  if number = 0 then 0x5bed else if number = 1 then 0x4924 else
  if number = 2 then 0x1249 else if number = 3 then 0x6b4f else
  if number = 4 then 0x7b4d else if number = 5 then 0x79cf else
  if number = 6 then 0x5b6d else 0x79e7

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
