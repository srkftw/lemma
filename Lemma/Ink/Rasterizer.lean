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
private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def maximum (a b : UInt64) : UInt64 := if a < b then b else a

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

private def rasterStep (i _ : UInt32) (acc tile endpoints brush area : UInt64) : Action :=
  -- Validated values fit these fixed-width fields. Cached arguments avoid any
  -- context memory access or normalized-coordinate conversion per pixel.
  let columns := (area >>> 24) &&& 63
  let column := i.toUInt64 % columns
  let row := i.toUInt64 / columns
  let x := (area &&& 4095) + column
  let y := ((area >>> 12) &&& 4095) + row
  let index := ((area >>> 30) &&& 1023) + row * 32 + column
  let stride := tile >>> 32
  let destination := tile &&& 0xffffffff
  let targetIndex := if stride = 0 then index else y * stride * 2 + x
  if covered x y (endpoints &&& 0xffff) ((endpoints >>> 16) &&& 0xffff)
      ((endpoints >>> 32) &&& 0xffff) (endpoints >>> 48)
      (brush &&& 0xffff) ((brush >>> 16) &&& 0xffff)
      ((brush >>> 32) &&& 0xffff) (brush >>> 48) = true then
    paint destination targetIndex acc
  else .done 0 acc

/-- Coalesce the segment's intersecting tiles at the notebook/surface layer and
call once per such tile. Work is bounded1024 pixels plus16 context word reads per
call, independent of retained sample count. The pixel loop visits only the
conservative segment bounds clipped to this tile and the screen. This version produces monochrome
coverage in Gray4; quality-mode rendering can still display these exact pixels. -/
private def segmentInto (context tile tileX tileY width height stride : UInt64) : Action :=
  if validDimension width = false then .done invalid 0 else
  if validDimension height = false then .done invalid 0 else
  if width ≤ tileX then .done invalid 0 else
  if height ≤ tileY then .done invalid 0 else
  if tileX % 32 = 0 then if tileY % 32 = 0 then
  if span tile (if stride = 0 then tileBytes else stride * height) = false then .done invalid 0 else
  .bind (contextValid context) fun s _ =>
  if s = 0 then
    .bind (get context 0) fun s qx0 => if s = 0 then
    .bind (get context 8) fun s qy0 => if s = 0 then
    .bind (get context 16) fun s qx1 => if s = 0 then
    .bind (get context 24) fun s qy1 => if s = 0 then
    .bind (get context 32) fun s p0 => if s = 0 then
    .bind (get context 40) fun s p1 => if s = 0 then
    .bind (get context 48) fun s nominal => if s = 0 then
    .bind (get context 56) fun s pressure => if s = 0 then
    let x0 := pixel qx0 width
    let y0 := pixel qy0 height
    let x1 := pixel qx1 width
    let y1 := pixel qy1 height
    let radius := (nominal + 511) / 512
    let left := minimum x0 x1
    let top := minimum y0 y1
    let beginX := maximum tileX (if radius < left then left - radius else 0)
    let beginY := maximum tileY (if radius < top then top - radius else 0)
    let endX := minimum width (minimum (tileX + 32) (maximum x0 x1 + radius + 1))
    let endY := minimum height (minimum (tileY + 32) (maximum y0 y1 + radius + 1))
    if beginX < endX then if beginY < endY then
      let columns := endX - beginX
      let pixels := columns * (endY - beginY)
      let base := (beginY - tileY) * 32 + beginX - tileX
      let endpoints := x0 ||| (y0 <<< 16) ||| (x1 <<< 32) ||| (y1 <<< 48)
      let brush := p0 ||| (p1 <<< 16) ||| (nominal <<< 32) ||| (pressure <<< 48)
      let area := beginX ||| (beginY <<< 12) ||| (columns <<< 24) ||| (base <<< 30)
      .boundedFoldU64 1024 rasterStep pixels.toUInt32 0 (tile ||| (stride <<< 32)) endpoints brush area
        fun s changed => .done s changed
    else .done 0 0 else .done 0 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0
  else .done invalid 0 else .done invalid 0

/-- Paint a bounded tile using its caller-owned512-byte staging span. -/
def segment (context tile tileX tileY width height : UInt64) : Action :=
  segmentInto context tile tileX tileY width height 0

/-- Paint the same clipped segment pixels directly into an owned row-major
Gray4 surface. The tile still bounds each invocation to at most1024 pixels.
The caller can accumulate dirty tile IDs and upload them once before refresh;
it need not copy512 bytes into and out of staging for each raw sample. -/
def segmentSurface (context framebuffer tileX tileY width height : UInt64) : Action :=
  segmentInto context framebuffer tileX tileY width height ((width + 1) / 2)

end Lemma.Ink.Rasterizer
