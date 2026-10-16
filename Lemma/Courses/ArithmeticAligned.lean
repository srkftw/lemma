import Lemma.Courses.Arithmetic

/-! Additive aligned arithmetic presentation. The historical scalar and sparse
renderers retain their bodies. Only ordinary owned virtual framebuffer stores
are used; no controller, document, checking or persistence authority is added. -/
namespace Lemma.Courses.ArithmeticAligned
open Lemma.Core0.Memory Lemma.User Lemma.Documents

private def putByte (i _ : UInt32) (acc address word _ _ : UInt64) : Action :=
  .bind (Memory.write8 (address + i.toUInt64) ((word >>> (i.toUInt64 * 8)) &&& 255)) fun s _ => .done s acc

/-- An arbitrary byte span within the existing384-pixel arithmetic row. Three
adjacent3x5 glyphs cover the only three-cell case. Blank line rows avoid all
font work, preserving the exact white spacing of the historical renderer. -/
def spanWord (offset y goal values displayState : UInt64) : UInt64 :=
  if 15 ≤ y % 20 then 0xffffffffffffffff else
  let column := offset / 6
  let first := Lemma.Ink.Surface.letter (Arithmetic.panelCharacter (y / 20) column goal values displayState)
  let second := Lemma.Ink.Surface.letter (Arithmetic.panelCharacter (y / 20) (column + 1) goal values displayState)
  let third := if offset % 6 = 5 then
    Lemma.Ink.Surface.letter (Arithmetic.panelCharacter (y / 20) (column + 2) goal values displayState) else 0
  Lemma.Courses.PackageRender.alignedSpanWord offset y first second third

private def renderStep (i _ : UInt32) (acc width goal values displayState : UInt64) : Action :=
  let chunk := i.toUInt64 % 25
  let y := i.toUInt64 / 25
  let start := Lemma.Ink.Surface.framebuffer + (160 + y) * ((width + 1) / 2) + 12
  let prefixBytes := if start % 8 = 0 then 8 else 8 - start % 8
  let offset := if chunk = 0 then 0 else prefixBytes + (chunk - 1) * 8
  let count := if chunk = 0 then prefixBytes else if chunk = 24 then 8 - prefixBytes else 8
  if count = 0 then .done 0 acc else
  let word := spanWord offset y goal values displayState
  if count = 8 then .bind (Memory.write64 (start + offset) word) fun s _ => .done s acc
  else .boundedFoldU64 8 putByte count.toUInt32 acc (start + offset) word 0 0 fun s value => .done s value

/-- Same declared30720-byte rectangle at(24,160). Every byte is written once;
no access rounds outside the rectangle. Aligned full words and ordered partial
byte spans propagate actual access faults without rollback. Other geometry
retains the historical renderer and its admission/error behavior. -/
def render (buffer width : UInt64) : Action :=
  if width = 1650 then
  .bind (Mathematics.field buffer 48) fun s goal => if s = 0 then
  .bind (Mathematics.field buffer 56) fun s n => if s = 0 then
  .bind (Mathematics.field buffer 64) fun s d => if s = 0 then
  .bind (Mathematics.field buffer 72) fun s p0 => if s = 0 then
  .bind (Mathematics.field buffer 80) fun s p1 => if s = 0 then
  .bind (Mathematics.field buffer 88) fun s p2 => if s = 0 then
  .bind (Mathematics.field buffer 96) fun s outcome => if s = 0 then
  .bind (Mathematics.field buffer 152) fun s hints => if s = 0 then
  .bind (Mathematics.field buffer 40) fun s revision => if s = 0 then
  .bind (Mathematics.field buffer 144) fun s attempts => if s = 0 then
  .bind (Lemma.Courses.Review.summary buffer) fun s review => if s = 0 then
  .boundedFoldU64 4000 renderStep 4000 0 width goal
    (n ||| (d <<< 7) ||| (p0 <<< 14) ||| (p1 <<< 21) ||| (p2 <<< 28))
    (outcome ||| (hints <<< 3) ||| ((revision % 100) <<< 9) ||| (attempts <<< 16) ||| (review <<< 24)) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else Arithmetic.renderSparse buffer width

end Lemma.Courses.ArithmeticAligned
