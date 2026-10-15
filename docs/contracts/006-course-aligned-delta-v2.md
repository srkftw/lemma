# Course text aligned delta2

`lemma-course-text-aligned-delta/2` is an additive guest Action, compiled by the
existing User2 frontend and LLVM lowering. The current notebook still selects
text-delta1. This component does not close the retained native6 or browser4
400-million-cycle course failures.

The source is a freshly prepared, private4096-byte glyph cache, disjoint from
the full declared framebuffer. Admission and error precedence match delta1.
The renderer paints the same384×320 Gray4 rectangle at(24,320), preserving the
original font, inter-line spaces, dimensions and all neighbouring bytes. Each
192-byte row is partitioned into a1..8-byte prefix,23 aligned eight-byte chunks
and a0..7-byte suffix. Zero-length suffixes perform no memory operation. A
chunk obtains its actual desired bytes from at most three adjacent cached
glyphs. No access is rounded outside the rectangle.

A full-word chunk uses aligned64-bit reads and writes. Partial chunks read all
of their bytes before their first write. Identical chunks perform no write.
Errors propagate their real status; previous chunks and a failed byte write's
ordered prefix remain changed. No hidden rollback or device publication occurs.
Successful Actions return the existing23-bit conservative column/row tile
projection from actual changed chunks. The notebook must publish those tiles
through its normal owned framebuffer/controller path.

Actual Action checks compare the full framebuffer with the original scalar
renderer at1650,1651 and1663 pixels, cover all canonical row alignments,
unchanged redraws, single-prefix repair, tile coverage and read/write failure
prefixes. The canonical full-difference case performs9640 framebuffer reads
and9640 writes covering exactly61440 bytes. Delta1's decomposition requires
54720 reads for that same geometry; this operation-count reduction is not a
measured target-cycle speedup. Genuine checked User2 lowering, LLVM verification
and RV64 object/helper inspection have separate component evidence. Notebook
integration, complete source-family artifact qualification and actual canonical
controller completion remain required.
