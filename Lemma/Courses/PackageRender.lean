import Lemma.Courses.PackageTarget
import Lemma.Ink.Surface

/-! `lemma-course-text-panel/1` prepares one bounded page from the actual
validated package bytes. There is no cross-Action validation token. The source
and glyph cache are private caller-owned pages with no asynchronous writer;
their checked disjoint spans make the same-Action read view immutable. Errors
may alter an unpublished glyph cache, but never start a display transaction.

The authored 3x5 font uses uppercase presentation for lowercase ASCII. Other
printable ASCII has an explicit missing-glyph box rather than disappearing.
Raw package text, anchors and mathematical objects remain unchanged. -/
namespace Lemma.Courses.PackageRender
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

def columns : UInt64 := 32
def rows : UInt64 := 16
def cacheBytes : UInt64 := 4096

def glyph (character : UInt64) : UInt64 :=
  let code := if 97 ≤ character then if character ≤ 122 then character - 32 else character else character
  if code = 32 then 0 else
  if code = 74 then 0x124e else if code = 90 then 0x72a7 else
  if code = 46 then 0x0002 else if code = 44 then 0x0014 else
  if code = 58 then 0x0410 else if code = 59 then 0x0414 else
  if code = 39 then 0x2400 else if code = 34 then 0x5a00 else
  if code = 33 then 0x2482 else if code = 63 then 0x7282 else
  if code = 95 then 0x0007 else if code = 60 then 0x1541 else
  if code = 62 then 0x4454 else
  let known := Lemma.Ink.Surface.letter code
  if known = 0 then 0x7b6f else known

private def separate (a n b m : UInt64) : UInt64 :=
  if a + n ≤ b then 1 else if b + m ≤ a then 1 else 0

private def clearStep (i _ : UInt32) (acc output _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write64 (output + i.toUInt64 * 8) 0) fun s _ => .done s acc

private def textStep (i _ : UInt32) (cursor source output _ _ : UInt64) : Action :=
  if cursor < columns * rows then
  .bind (Lemma.User.Memory.read8 (source + i.toUInt64)) fun s character => if s = 0 then
  if character = 10 then .done 0 (cursor + columns - cursor % columns) else
  .bind (Lemma.User.Memory.write64 (output + cursor * 8) (glyph character)) fun s _ =>
  if s = 0 then .done 0 (cursor + 1) else .done s 0
  else .done s 0
  else .done Status.iterationStop i.toUInt64

/-- Validate once, then prepare actual selected text in a disjoint4096-byte
glyph cache. `position` is a raw text-byte offset; success returns the first
unrepresented byte for explicit pagination. LF advances to the next row and
wrap uses32 columns. Neither an entry pointer nor a validity token escapes.
Arguments/role precede package validation, then ordinal/span/position checks;
the cache is untouched until all those checks pass. -/
def prepare (address bytes ordinal role position output : UInt64) : Action :=
  if role < 8 then
  if output % 8 = 0 then if output ≤ 0xffffffffffffffff - cacheBytes then
  if address ≤ 0xffffffffffffffff - bytes then
  if separate address bytes output cacheBytes = 1 then
  .bind (PackageTarget.validate address bytes) fun s count => if s = 0 then
  if ordinal < count then
  let entry := address + headerBytes + ordinal * entryBytes
  .bind (Lemma.User.Memory.read64 (entry + 112 + role * 8)) fun s descriptor => if s = 0 then
  let offset := spanOffset descriptor
  let length := spanLength descriptor
  if position ≤ length then
  .boundedFoldU64 512 clearStep 512 0 output 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 512 textStep (length - position).toUInt32 0 (address + offset + position) output 0 0 fun s next =>
  if s = Status.iterationStop then .done 0 (position + next)
  else if s = 0 then .done 0 length else .done s 0
  else .done s 0
  else .done selectionAbsent 0 else .done s 0
  else .done selectionAbsent 0 else .done s 0
  else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0
  else .done unsupported 0

private def pixel (position row first second : UInt64) : UInt64 :=
  if row < 15 then if position % 12 < 9 then
    let selected := if position < 12 then first else second
    if (selected >>> (14 - (row / 3 * 3 + position % 12 / 3))) &&& 1 = 1 then 0 else 15
  else 15 else 15

private def pair (position row first second : UInt64) : UInt64 :=
  (pixel position row first second <<< 4) ||| pixel (position + 1) row first second

/-- Gray4 high-nibble-first pixels packed into a little-endian aligned word.
Two cached glyphs cover at most two12-pixel cells of the16-pixel span. -/
def panelWord (x y first second : UInt64) : UInt64 :=
  let start := x % 12
  let row := y % 20
  pair start row first second |||
  (pair (start + 2) row first second <<< 8) |||
  (pair (start + 4) row first second <<< 16) |||
  (pair (start + 6) row first second <<< 24) |||
  (pair (start + 8) row first second <<< 32) |||
  (pair (start + 10) row first second <<< 40) |||
  (pair (start + 12) row first second <<< 48) |||
  (pair (start + 14) row first second <<< 56)

private def renderByteStep (i _ : UInt32) (acc address word _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 (address + i.toUInt64) ((word >>> (i.toUInt64 * 8)) &&& 255)) fun s _ => .done s acc

private def renderStep (i _ : UInt32) (acc cache width _ _ : UInt64) : Action :=
  let x := (i.toUInt64 % 24) * 16
  let y := i.toUInt64 / 24
  let cell := (y / 20) * columns + x / 12
  .bind (Lemma.User.Memory.read64 (cache + cell * 8)) fun s first => if s = 0 then
  .bind (if x / 12 + 1 < columns then Lemma.User.Memory.read64 (cache + (cell + 1) * 8)
    else .done 0 0) fun s second => if s = 0 then
  let word := panelWord x y first second
  let target := Lemma.Ink.Surface.framebuffer + (320 + y) * ((width + 1) / 2) + 12 + x / 2
  if target % 8 = 0 then
    .bind (Lemma.User.Memory.write64 target word) fun s _ => .done s acc
  else .boundedFoldU64 8 renderByteStep 8 acc target word 0 0 fun s value => .done s value
  else .done s 0 else .done s 0

/-- Render a prepared cache into owned Gray4 framebuffer pixels at(24,320),
384x320. The notebook must explicitly mark/publish this region through its
normal tile/controller path. This Action has no panel or storage authority.
Its cache is disjoint from the complete declared framebuffer span. -/
def render (cache width height : UInt64) : Action :=
  if 416 ≤ width then if width ≤ 4096 then if 640 ≤ height then if height ≤ 4096 then
  if cache % 8 = 0 then if cache ≤ 0xffffffffffffffff - cacheBytes then
  let framebufferBytes := ((width + 1) / 2) * height
  if separate cache cacheBytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  .boundedFoldU64 7680 renderStep 7680 0 cache width 0 0 fun s _ => .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0

/-- Connected package-to-framebuffer entry point. Source, cache and complete
framebuffer are disjoint before any cache/display write. The validation view
does not cross a return, syscall, publication or package-buffer mutation. The
returned position is raw text pagination, never a storage or proof receipt. -/
def renderSelected (address bytes ordinal role position cache width height : UInt64) : Action :=
  if 416 ≤ width then if width ≤ 4096 then if 640 ≤ height then if height ≤ 4096 then
  if address ≤ 0xffffffffffffffff - bytes then
  let framebufferBytes := ((width + 1) / 2) * height
  if separate address bytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  if cache % 8 = 0 then if cache ≤ 0xffffffffffffffff - cacheBytes then
  if separate cache cacheBytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  .bind (prepare address bytes ordinal role position cache) fun s next => if s = 0 then
  .bind (render cache width height) fun s _ => if s = 0 then .done 0 next else .done s 0
  else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0
  else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0

end Lemma.Courses.PackageRender

/-! `lemma-course-text-delta/1` compares the actual owned framebuffer with the
same freshly prepared pixels. It retains no validation or presentation cache.
The low13 result bits name touched32-pixel columns and the following10 bits
name rows. Their Cartesian product conservatively covers every changed pixel;
only the Notebook's normal dirty queue may publish those tiles. -/
namespace Lemma.Courses.PackageRender
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

/-- Pure presentation shortcut: blank glyphs and the five inter-line rows
have exactly the same sixteen white pixels as panelWord. No memory or cache
state is consulted, and nonblank words retain the original font operation. -/
def sparsePanelWord (x y first second : UInt64) : UInt64 :=
  if 15 ≤ y % 20 then 0xffffffffffffffff else
  if first ||| second = 0 then 0xffffffffffffffff else panelWord x y first second

private def readByteStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read8 (address + i.toUInt64)) fun s byte =>
  if s = 0 then .done 0 (acc ||| (byte <<< (i.toUInt64 * 8))) else .done s 0

private def readWord (address : UInt64) : Action :=
  if address % 8 = 0 then Lemma.User.Memory.read64 address else
  .boundedFoldU64 8 readByteStep 8 0 address 0 0 0 fun s value => .done s value

private def deltaStep (i _ : UInt32) (acc cache width _ _ : UInt64) : Action :=
  let x := (i.toUInt64 % 24) * 16
  let y := i.toUInt64 / 24
  let cell := (y / 20) * columns + x / 12
  .bind (Lemma.User.Memory.read64 (cache + cell * 8)) fun s first => if s = 0 then
  .bind (if x / 12 + 1 < columns then Lemma.User.Memory.read64 (cache + (cell + 1) * 8)
    else .done 0 0) fun s second => if s = 0 then
  let word := sparsePanelWord x y first second
  let target := Lemma.Ink.Surface.framebuffer + (320 + y) * ((width + 1) / 2) + 12 + x / 2
  .bind (readWord target) fun s previous => if s = 0 then
  if previous = word then .done 0 acc else
  let changed := acc ||| ((1 : UInt64) <<< ((24 + x) / 32)) |||
    ((1 : UInt64) <<< ((39 + x) / 32)) ||| ((1 : UInt64) <<< (13 + y / 32))
  if target % 8 = 0 then
    .bind (Lemma.User.Memory.write64 target word) fun s _ => .done s changed
  else .boundedFoldU64 8 renderByteStep 8 changed target word 0 0 fun s value => .done s value
  else .done s 0 else .done s 0 else .done s 0

/-- Fresh actual pixels, unchanged geometry/font and no hidden persistent
cache. New framebuffer read faults propagate before that word's first write;
write faults retain their real ordered partial effects. A failed Action never
starts a device transaction. Success names every changed tile conservatively. -/
def renderDelta (cache width height : UInt64) : Action :=
  if 416 ≤ width then if width ≤ 4096 then if 640 ≤ height then if height ≤ 4096 then
  if cache % 8 = 0 then if cache ≤ 0xffffffffffffffff - cacheBytes then
  let framebufferBytes := ((width + 1) / 2) * height
  if separate cache cacheBytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  .boundedFoldU64 7680 deltaStep 7680 0 cache width 0 0 fun s changed => .done s changed
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0

/-- Same selected source/cache/framebuffer admission and validation as panel1.
Success packs the raw pagination position in the low32 bits and the23-bit
changed-tile projection above it. No host, controller or storage authority. -/
def renderSelectedDelta (address bytes ordinal role position cache width height : UInt64) : Action :=
  if 416 ≤ width then if width ≤ 4096 then if 640 ≤ height then if height ≤ 4096 then
  if address ≤ 0xffffffffffffffff - bytes then
  let framebufferBytes := ((width + 1) / 2) * height
  if separate address bytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  if cache % 8 = 0 then if cache ≤ 0xffffffffffffffff - cacheBytes then
  if separate cache cacheBytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  .bind (prepare address bytes ordinal role position cache) fun s next => if s = 0 then
  if next ≤ 0xffffffff then
  .bind (renderDelta cache width height) fun s changed =>
  if s = 0 then .done 0 (next ||| (changed <<< 32)) else .done s 0
  else .done resourceLimit 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0
  else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0

end Lemma.Courses.PackageRender

/-! `lemma-course-header-panel/1` is an append-only presentation extension.
The original node roles0..7 and every renderer definition above stay unchanged.
Header fields0..3 show actual title/source/edition/rights bytes, without granting
authentication, mathematical authority or rights to the described material. -/
namespace Lemma.Courses.PackageRender
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

/-- The caller owns an immutable package and a disjoint unpublished glyph
cache. Field/index/position errors precede cache writes. The entire actual
package is checked before interpreting its header text span. -/
def prepareHeader (address bytes field position output : UInt64) : Action :=
  if field < 4 then
  if output % 8 = 0 then if output ≤ 0xffffffffffffffff - cacheBytes then
  if address ≤ 0xffffffffffffffff - bytes then
  if separate address bytes output cacheBytes = 1 then
  .bind (PackageTarget.validate address bytes) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.read64 (address + 96 + field * 8)) fun s descriptor => if s = 0 then
  let offset := spanOffset descriptor
  let length := spanLength descriptor
  if position ≤ length then
  .boundedFoldU64 512 clearStep 512 0 output 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 512 textStep (length - position).toUInt32 0 (address + offset + position) output 0 0 fun s next =>
  if s = Status.iterationStop then .done 0 (position + next)
  else if s = 0 then .done 0 length else .done s 0
  else .done s 0
  else .done selectionAbsent 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done unsupported 0

/-- Validate all source/cache/framebuffer spans before any presentation write.
Only controller-produced framebuffer publication by the integrating Notebook
may display these pixels. The canonical typed goal panel is outside this region. -/
def renderHeaderSelected (address bytes field position cache width height : UInt64) : Action :=
  if 416 ≤ width then if width ≤ 4096 then if 640 ≤ height then if height ≤ 4096 then
  if address ≤ 0xffffffffffffffff - bytes then
  let framebufferBytes := ((width + 1) / 2) * height
  if separate address bytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  if cache % 8 = 0 then if cache ≤ 0xffffffffffffffff - cacheBytes then
  if separate cache cacheBytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  .bind (prepareHeader address bytes field position cache) fun s next => if s = 0 then
  .bind (render cache width height) fun s _ => if s = 0 then .done 0 next else .done s 0
  else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0
  else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0

end Lemma.Courses.PackageRender

namespace Lemma.Courses.PackageRender
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat

/-- Header counterpart of text-delta1, retaining all actual package checks
and raw text while returning the same bounded presentation projection. -/
def renderHeaderSelectedDelta (address bytes field position cache width height : UInt64) : Action :=
  if 416 ≤ width then if width ≤ 4096 then if 640 ≤ height then if height ≤ 4096 then
  if address ≤ 0xffffffffffffffff - bytes then
  let framebufferBytes := ((width + 1) / 2) * height
  if separate address bytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  if cache % 8 = 0 then if cache ≤ 0xffffffffffffffff - cacheBytes then
  if separate cache cacheBytes Lemma.Ink.Surface.framebuffer framebufferBytes = 1 then
  .bind (prepareHeader address bytes field position cache) fun s next => if s = 0 then
  if next ≤ 0xffffffff then
  .bind (renderDelta cache width height) fun s changed =>
  if s = 0 then .done 0 (next ||| (changed <<< 32)) else .done s 0
  else .done resourceLimit 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0
  else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0 else .done resourceLimit 0

end Lemma.Courses.PackageRender
