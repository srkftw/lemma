# Course text incremental presentation1

`lemma-course-text-delta/1` advances installed-package Notebook software to
`lemma-installed-package-notebook/3`. Machine0.3, all12 owned package pages,
layout2 allocation counter, immutable packages, raw ink, Doc8, workspace1,
Protocol7 and Store formats remain unchanged. Historical text-panel1 and
header-panel1 declarations and their complete audit cohorts remain supported.

The new selected node/header entry points prepare the actual validated text
with the existing font, pagination and disjoint source/cache/framebuffer spans.
They compare every freshly computed16-pixel word with actual framebuffer bytes.
Identical words require no framebuffer write. Aligned words use checked64-bit
accesses; other words use eight ordered checked byte accesses. There is no
persistent pixel cache or validity token, so intervening annotation/redraw pixels
are observed and repaired on the next selected-text render.

Success returns the raw next-text position in bits0..31 and a23-bit presentation
projection in bits32..54. Within that projection, bits0..12 name absolute32-pixel
columns0..12 and bits13..22 name rows10..19. Each changed16-pixel word marks
both columns it intersects and its row. The Cartesian product conservatively
covers all changed pixels and may include unchanged tiles. The actual Notebook
checks these bits for its130 candidate tiles and marks only that product in the
existing deduplicated FIFO. A zero projection leaves the pending dirty queue and
rectangle untouched. Nonzero changes use the original rectangle/refresh path;
ordinary controller uploads and completion are still required. No host presents
cosmetic ink or manufactures a display receipt.

Argument, source validation, ordinal/span and pagination errors retain their
existing precedence before presentation. A new framebuffer read fault stops
before that word's first write. Write faults retain real ordered partial writes;
neither fault starts a device transaction or promises rolled-back memory.
Subsequent ordinary guest error/redraw policy remains responsible for recovery.
The owned spans have no asynchronous writer during this Action. No storage,
kernel policy, mathematical or controller authority is added.

The complete source comparison against the prior actual User2 export changes
only `packageTileStep` and `renderPackageText`, adds six ordinary Lean functions
and removes four now-unreachable panel1 functions from this selected closure.
All812 other pre-optimization bodies are identical. The optimized capture-field
table reference is separately rebound to its actual new owner; all table bytes,
bounds and pointer-use checks remain load-bearing. Admission requires the whole
new family, layout2 and exact signatures, pre/post bodies and callers. Mixing
cohorts is rejected. No Core0 language or runtime extension is introduced.

`tests/courses/Render.lean` compares every actual canonical framebuffer byte
with the original renderer and an independent scalar glyph/pixel oracle. It
checks changed-pixel coverage, unchanged text, actual damaged pixels crossing
tile boundaries, header/body transitions, odd stride and read/write fault
prefixes. `tests/courses/NotebookPackage.lean` executes the actual private tile
callback and checks the real pending queue without device authority. These are
host Action observations. Full audited RV64 artifacts and observed target
performance/connected workflow have their own results; component success does
not imply them.

```sh
nix develop --no-write-lock-file --command lake build Lemma.Applications.Notebook
nix develop --no-write-lock-file --command \
  lake env lean --run tests/courses/Render.lean
nix develop --no-write-lock-file --command \
  lake env lean --run tests/courses/NotebookPackage.lean
```
