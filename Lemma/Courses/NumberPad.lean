import Lemma.Courses.PackageRender

/-! Guest-rendered Gray4 number pad1. The384x200 region starts at448,160;
the ordinary pen service supplies normalized coordinates. This renderer only
writes its owned framebuffer span. No document, journal or checker authority. -/
namespace Lemma.Courses.NumberPad
open Lemma.Core0.Memory

/-- Relative coordinates.12 is outside an active key. -/
def key (x y : UInt64) : UInt64 :=
  if 384 ≤ x then 12 else if y < 40 then 12 else if 200 ≤ y then 12 else
  let row := (y - 40) / 40
  let column := x / 128
  if row < 3 then row * 3 + column + 1 else
  if column = 0 then 10 else if column = 1 then 0 else 11

/-- The pad's only dynamic asset is the limit header. Raw ink may overdraw it;
that separately tracked damage forces the same reconstruction as a header
change. No damaged or unpainted span is treated as an authoritative cache. -/
def repaintNeeded (painted prior limited damaged : UInt64) : UInt64 :=
  if prior ≤ 1 then if limited ≤ 1 then
  if painted = 1 then if prior = limited then if damaged = 0 then 0 else 1 else 1 else 1
  else 1 else 1

def character (row column limited : UInt64) : UInt64 :=
  if row = 0 then
    let packed : UInt64 := if limited = 1 then 0x39392054494d494c else 0x39392d3045505954
    if column < 8 then (packed >>> (column * 8)) &&& 255 else 32
  else if row % 2 = 0 then
    if row < 8 then
      if column = 4 then 48 + (row / 2 - 1) * 3 + 1 else
      if column = 15 then 48 + (row / 2 - 1) * 3 + 2 else
      if column = 26 then 48 + (row / 2 - 1) * 3 + 3 else 32
    else if row = 8 then
      if column = 3 then 67 else if column = 4 then 76 else if column = 5 then 82 else
      if column = 15 then 48 else if column = 24 then 66 else if column = 25 then 65 else
      if column = 26 then 67 else if column = 27 then 75 else 32
    else 32
  else 32

private def bytesStep (i _ : UInt32) (acc target word _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 (target + i.toUInt64) ((word >>> (i.toUInt64 * 8)) &&& 255)) fun s _ => .done s acc

private def spanStep (i _ : UInt32) (acc width limited _ _ : UInt64) : Action :=
  let y := i.toUInt64 / 25
  let chunk := i.toUInt64 % 25
  let start := Lemma.Ink.Surface.framebuffer + (160 + y) * ((width + 1) / 2) + 224
  let prefixBytes := if start % 8 = 0 then 8 else 8 - start % 8
  let offset := if chunk = 0 then 0 else prefixBytes + (chunk - 1) * 8
  let count := if chunk = 0 then prefixBytes else if chunk = 24 then 8 - prefixBytes else 8
  if count = 0 then .done 0 acc else
  let column := offset / 6
  let first := PackageRender.glyph (character (y / 20) column limited)
  let second := if 6 < offset % 6 + count then PackageRender.glyph (character (y / 20) (column + 1) limited) else 0
  let third := if 12 < offset % 6 + count then PackageRender.glyph (character (y / 20) (column + 2) limited) else 0
  let mask := if count = 8 then 0xffffffffffffffff else ((1 : UInt64) <<< (count * 8)) - 1
  let word := PackageRender.alignedSpanWord offset y first second third &&& mask
  if count = 8 then .bind (Lemma.User.Memory.write64 (start + offset) word) fun s _ => .done s acc else
  .boundedFoldU64 8 bytesStep count.toUInt32 acc (start + offset) word 0 0 fun s value => .done s value

def render (width height limited : UInt64) : Action :=
  if width < 832 then .done 240 0 else if 4096 < width then .done 240 0 else
  if height < 360 then .done 240 0 else if 4096 < height then .done 240 0 else
  if 1 < limited then .done 240 0 else
  if ((width + 1) / 2) * height ≤ 2000000 then
  .boundedFoldU64 5000 spanStep 5000 0 width limited 0 0 fun s _ => .done s 0
  else .done 240 0
end Lemma.Courses.NumberPad
