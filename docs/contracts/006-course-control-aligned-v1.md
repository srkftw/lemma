# Course control aligned spans1

`lemma-course-control-aligned/1` replaces the existing Notebook's scalar course
controls and submission identity painting. It is ordinary elaborated Lean,
using the existing User2 checked lowering and virtual write8/write64 effects.
The full Notebook artifact cohort is `lemma-installed-package-notebook/8`;
historical cohorts retain their independent admission rules.

The five control rows occupy x24..407/y640..739 and the identity row occupies
x24..407/y740..759. Labels, hexadecimal fields, package identities, requested
and shown editions, navigation, submission revision, domain, assumptions and
budget retain their scalar meanings. Width416..4096, height760..4096 and a
packed framebuffer no larger than2,000,000 bytes are admitted. Invalid geometry
and a public control position with bit63 set return240 before any store. The
private bit63 mode selects the separate identity span; it is not public state.

Each192-byte row is split into a1..8-byte prefix,23 aligned eight-byte spans
and a0..7-byte suffix. A zero-length suffix performs no access. Every desired
span is calculated from at most three adjacent original glyphs. Full spans
use checked write64; partial spans write their bytes in ascending order.
There are no framebuffer reads or accesses outside the original23,040-byte
footprint. A failed operation returns its actual status and leaves the prior
completed stores intact; retry reconstructs the complete selected region.
There is no hidden rollback, controller command, allocation or publication.

At canonical1650-pixel width the complete controls plus identity require3,615
stores, versus20,520 for the original scalar decomposition. This is an
operation count, not a measured CPU speedup. Full framebuffer and neighbouring
bytes at four strides, admission, actual partial-write failure and repair have
independent scalar Action checks. Genuine component LLVM/RV64 checks and four
ordinary Notebook catalog/IR/object checks are separate from whole-image audits
and actual controller/workflow qualification. None establishes physical timing,
fast-backend timing parity or whole-machine completion.

Reproduce the component in the pinned environment with an unused directory:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_control_render.py \
  --work-dir build/courses/UNUSED-control-render
```
