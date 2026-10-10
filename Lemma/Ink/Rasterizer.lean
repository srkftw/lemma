import Lemma.Ink.Geometry
import Lemma.User.Memory

/-! Guest-only version1 Gray4 tile rasterization. The caller owns an aligned
64-byte segment context and a512-byte tile span in its user address space.
The eight context words are qx0,qy0,qx1,qy1,p0,p1,widthQ8,pressureMaximum.
Tile x/y are pixel origins divisible by32. Geometry is runtime-discovered.
Rendering only writes covered pixels black into the caller's current tile.
Initialize the tile white, or load/replay its previous guest-produced pixels.
The return count names newly changed pixels; zero means no dirty upload needed.
Raw sample records/lifecycle remain separate from this rendering context. -/
namespace Lemma.Ink.Rasterizer
open Lemma.Core0.Memory
open Lemma.Ink.Geometry

def invalid : UInt8 := 16
def tileBytes : UInt64 := 512
def contextBytes : UInt64 := 64
def brushVersion : UInt64 := 1

private def span (address bytes : UInt64) : Bool :=
  if 0x10000 ≤ address then if address < 0x40000000 then
  if bytes ≤ 0x40000000 - address then true else false else false else false
private def get (context offset : UInt64) : Action := Lemma.User.Memory.read64 (context + offset)

private def clearStep (i _ : UInt32) (acc tile _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 (tile + i.toUInt64) 255) fun s _ => .done s acc

def clearTile (tile : UInt64) : Action :=
  if span tile tileBytes = false then .done invalid 0 else
  .boundedFoldU64 512 clearStep 512 0 tile 0 0 0 fun s _ => .done s tile

private def contextValid (context : UInt64) : Action :=
  if span context contextBytes = false then .done invalid 0 else
  if context % 8 = 0 then
    .bind (get context 0) fun s x0 => if s = 0 then
    .bind (get context 8) fun s y0 => if s = 0 then
    .bind (get context 16) fun s x1 => if s = 0 then
    .bind (get context 24) fun s y1 => if s = 0 then
    .bind (get context 32) fun s p0 => if s = 0 then
    .bind (get context 40) fun s p1 => if s = 0 then
    .bind (get context 48) fun s width => if s = 0 then
    .bind (get context 56) fun s pressure => if s = 0 then
    if coordinateMaximum < x0 then .done invalid 0 else
    if coordinateMaximum < y0 then .done invalid 0 else
    if coordinateMaximum < x1 then .done invalid 0 else
    if coordinateMaximum < y1 then .done invalid 0 else
    if width < 256 then .done invalid 0 else
    if 8192 < width then .done invalid 0 else
    if 65535 < pressure then .done invalid 0 else
    if pressure < p0 then .done invalid 0 else
    if pressure < p1 then .done invalid 0 else .done 0 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0

private def paint (tile index acc : UInt64) : Action :=
  let offset := index / 2
  .bind (Lemma.User.Memory.read8 (tile + offset)) fun s original =>
  if s = 0 then
    let packed := if index % 2 = 0 then original &&& 15 else original &&& 240
    if packed = original then .done 0 acc else
    .bind (Lemma.User.Memory.write8 (tile + offset) packed) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else .done s 0
  else .done s 0

private def rasterStep (i _ : UInt32) (acc context tile dimensions origin : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let x := (origin &&& 0xffff) + i.toUInt64 % 32
  let y := (origin >>> 16) + i.toUInt64 / 32
  if width ≤ x then .done 0 acc else
  if height ≤ y then .done 0 acc else
  .bind (get context 0) fun s qx0 => if s = 0 then
  .bind (get context 8) fun s qy0 => if s = 0 then
  .bind (get context 16) fun s qx1 => if s = 0 then
  .bind (get context 24) fun s qy1 => if s = 0 then
  .bind (get context 32) fun s p0 => if s = 0 then
  .bind (get context 40) fun s p1 => if s = 0 then
  .bind (get context 48) fun s nominal => if s = 0 then
  .bind (get context 56) fun s pressureMaximum => if s = 0 then
  if covered x y (pixel qx0 width) (pixel qy0 height) (pixel qx1 width) (pixel qy1 height)
      p0 p1 nominal pressureMaximum = true then paint tile i.toUInt64 acc else .done 0 acc
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Coalesce the segment's intersecting tiles at the notebook/surface layer and
call once per such tile. Work is bounded1024 pixels plus8 preflight words per
call, independent of retained sample count. This version produces monochrome
coverage in Gray4; quality-mode rendering can still display these exact pixels. -/
def segment (context tile tileX tileY width height : UInt64) : Action :=
  if validDimension width = false then .done invalid 0 else
  if validDimension height = false then .done invalid 0 else
  if width ≤ tileX then .done invalid 0 else
  if height ≤ tileY then .done invalid 0 else
  if tileX % 32 = 0 then if tileY % 32 = 0 then
  if span tile tileBytes = false then .done invalid 0 else
  .bind (contextValid context) fun s _ =>
  if s = 0 then
    .boundedFoldU64 1024 rasterStep 1024 0 context tile (width ||| (height <<< 16))
      (tileX ||| (tileY <<< 16)) fun s changed => .done s changed
  else .done s 0
  else .done invalid 0 else .done invalid 0

end Lemma.Ink.Rasterizer
