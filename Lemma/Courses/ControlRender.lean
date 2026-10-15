import Lemma.Courses.PackageRender

/-! Exact course-control and submission-identity pixels, aligned spans1.
No allocation, journal, evidence construction or controller authority. The
caller owns the existing framebuffer; the original120-row footprint, scalar
alphabet, state values and row order are preserved. Partial failure leaves
only previously completed byte/word stores. A new call reconstructs every row.
The original Notebook renderer remains available during qualification. -/
namespace Lemma.Courses.ControlRender
open Lemma.Core0.Memory
def hexDigit (value digit : UInt64) : UInt64 :=
  let nibble := (value >>> (digit * 4)) &&& 15
  if nibble < 10 then 48 + nibble else 55 + nibble

/-- These original labels are presentation assets only. The numeric fields
come from requested or actually validated package state, never a host menu. -/
def character (row column requested shown position : UInt64) : UInt64 :=
  let chunk := column / 8
  let packed : UInt64 := if row = 0 then
      if chunk = 0 then 0x2020202b45444f4e else if chunk = 1 then 0x2020202b454c4f52 else
      if chunk = 2 then 0x2020202b45474150 else 0x2020202020455355
    else if row = 1 then
      if chunk = 0 then 0x20202b544e454449 else if chunk = 1 then 0x2020202b54494445 else
      if chunk = 2 then 0x2020202044414f4c else 0x2020205445534552
    else if row = 2 then
      if chunk = 0 then 0x2020454352554f53 else if chunk = 1 then 0x204e4f4954494445 else
      if chunk = 2 then 0x2020535448474952 else 0x202020454c544954
    else if row = 3 then
      if chunk = 0 then 0x3030304920514552 else if chunk = 1 then 0x3030303030452030 else
      if chunk = 2 then 0x2030304e20303030 else 0x2020202020303052
    else
      if chunk = 0 then 0x3030492044414552 else if chunk = 1 then 0x3030303045203030 else
      if chunk = 2 then 0x2020202030303030 else 0x2020202020202020
  if row = 3 then
    if 5 ≤ column then if column < 9 then hexDigit (requested &&& 65535) (8 - column) else
    if 11 ≤ column then if column < 19 then hexDigit (requested >>> 16) (18 - column) else
    if column = 21 then (48 : UInt64) + (position &&& 255) / 10 else if column = 22 then (48 : UInt64) + (position &&& 255) % 10 else
    if column = 25 then (48 : UInt64) + (position >>> 8) / 10 else if column = 26 then (48 : UInt64) + (position >>> 8) % 10 else
    (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
  else if row = 4 then
    if 6 ≤ column then if column < 10 then hexDigit (shown &&& 65535) (9 - column) else
    if 12 ≤ column then if column < 20 then hexDigit (shown >>> 16) (19 - column) else
    (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
  else (packed >>> (column % 8 * 8)) &&& 255

def identityCharacter (column revision context : UInt64) : UInt64 :=
  let packed : UInt64 := if column / 8 = 0 then 0x3030303020564552 else
    if column / 8 = 1 then 0x3030303030303030 else
    if column / 8 = 2 then 0x2030442030303030 else 0x2020303042203041
  if 4 ≤ column then if column < 20 then hexDigit revision (19 - column) else
    if column = 22 then (48 : UInt64) + (context &&& 255) else
    if column = 25 then (48 : UInt64) + ((context >>> 8) &&& 255) else
    if column = 28 then (48 : UInt64) + ((context >>> 16) &&& 255) / 10 else
    if column = 29 then (48 : UInt64) + ((context >>> 16) &&& 255) % 10 else
    (packed >>> (column % 8 * 8)) &&& 255
  else (packed >>> (column % 8 * 8)) &&& 255


private def bytesStep (i _ : UInt32) (acc target word _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 (target+i.toUInt64) ((word >>> (i.toUInt64*8)) &&& 255)) fun s _ => .done s acc

private def spanStep (i _ : UInt32) (acc width requested shown position : UInt64) : Action :=
  -- The high bit selects the separate20-row exact submission identity span.
  let identity := position >>> 63
  let position := position &&& 0x7fffffffffffffff
  let y := i.toUInt64/25
  let chunk := i.toUInt64%25
  let firstY := if identity = 1 then 740 else 640
  let start := Lemma.Ink.Surface.framebuffer+(firstY+y)*((width+1)/2)+12
  let prefixBytes := if start%8 = 0 then 8 else 8-start%8
  let offset := if chunk = 0 then 0 else prefixBytes+(chunk-1)*8
  let count := if chunk = 0 then prefixBytes else if chunk = 24 then 8-prefixBytes else 8
  if count = 0 then .done 0 acc else
  let column := offset/6
  let first := PackageRender.glyph (if identity = 1 then identityCharacter column requested shown
    else character (y/20) column requested shown position)
  let second := if 6 < offset%6+count then PackageRender.glyph
    (if identity = 1 then identityCharacter (column+1) requested shown
     else character (y/20) (column+1) requested shown position) else 0
  let third := if 12 < offset%6+count then PackageRender.glyph
    (if identity = 1 then identityCharacter (column+2) requested shown
     else character (y/20) (column+2) requested shown position) else 0
  let mask := if count = 8 then 0xffffffffffffffff else ((1 : UInt64) <<< (count*8))-1
  let word := PackageRender.alignedSpanWord offset y first second third &&& mask
  let target := start+offset
  if count = 8 then .bind (Lemma.User.Memory.write64 target word) fun s _ => .done s acc else
  .boundedFoldU64 8 bytesStep count.toUInt32 acc target word 0 0 fun s value => .done s value

private def validGeometry (width height : UInt64) : Bool :=
  if width < 416 then false else if 4096 < width then false else
  if height < 760 then false else if 4096 < height then false else
  ((width+1)/2)*height ≤ 2000000

def renderControls (width height requested shown position : UInt64) : Action :=
  if validGeometry width height then
  if position >>> 63 = 0 then
  .boundedFoldU64 2500 spanStep 2500 0 width requested shown position fun s _ => .done s 0
  else .done 240 0 else .done 240 0

def renderIdentity (width height revision context : UInt64) : Action :=
  if validGeometry width height then
  .boundedFoldU64 500 spanStep 500 0 width revision context 0x8000000000000000 fun s _ => .done s 0
  else .done 240 0
end Lemma.Courses.ControlRender
