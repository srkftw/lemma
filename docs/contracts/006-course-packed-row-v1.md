# Course packed glyph rows 1

`lemma-installed-package-notebook/6` combines the full workspace restore repair
with a pure font operation. Canonical geometry, raw text, all framebuffer
reads/writes and fault order, dirty-tile policy, controller work, Doc8/checker
authority and journal/barrier semantics remain those of the existing paths.

A3×5 glyph row has three bits. Each bit produces three black or white pixels,
followed by three white spacing pixels. `packedCellRow` expands that selected
row into six little-endian Gray4 bytes, retaining high-nibble-first pixel order.
The black masks for the three columns are `0xf0ff`, `0xff0f00` and
`0xf0ff000000`; all other bits of the48-bit cell remain white. Only the three
selected glyph bits contribute. The caller guards the five spacing rows before
computing the selected row shift.

Every ordinary16-pixel word starts at cell offset0,4 or8. Two48-bit cell rows
are stitched with respectively `(a | b<<48)`, `(a>>16 | b<<32)` and
`(a>>32 | b<<16)`, with ordinary UInt64 truncation. Other starts use the original
per-pixel operation, preserving arbitrary public UInt64 inputs. The existing
white-word guard remains. No persistent cache, memory effect, display authority,
new runtime helper or language feature is introduced.

The codec repair copies exactly464 validated words into private staging. Its
bytes remain frozen through the actual save transaction; restore is not a Saved
receipt. The complete software6 source cohort requires both packed-row helpers
and both restore helpers. Partial/mixed cohorts reject; software1–5 retain
separate exact historical admissions and their original observed limitations.

Independent finite row/start/high-bit cases, the original per-pixel renderer,
full canonical/odd-stride/fault framebuffer Actions and scalar mathematics
pixels qualify components. Complete fresh ELF audits and actual guest/controller
workflows remain separate acceptance requirements. Static instruction counts
and host comparisons alone do not establish target speed or timing parity.
