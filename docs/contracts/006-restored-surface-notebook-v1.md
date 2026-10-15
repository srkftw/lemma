# Restored Surface notebook1

`lemma-restored-surface-notebook-artifact/1` identifies Package notebook cohort10
for both the canonical and clocked-companion deployments. It extends cohort9's
four-tile dirty FIFO batching to full framebuffer restoration after controller
state loss. It changes no ISA, machine clock, memory capacity, device ABI,
managed runtime, durable document format or checkpoint serialization.

`restorePaperBatch` reads the existing restoration cursor at state offset488.
For the admitted Surface dimensions, it submits at most four consecutive tile
indices in one existing owned Surface-v2 packet. The final batch has one, two
or three tiles when appropriate. Each index occupies sixteen bits; unused
lanes are zero. The full batch avoids a shift by64 when constructing that mask.
The unchanged Surface implementation validates geometry and ownership, prepares
all pixel bytes before a controller call, and checks completion counts.

The cursor advances only by the returned completed prefix. A controller error
with an accepted prefix returns that error and retains the remaining suffix
for retry. Cursor-read or pixel-preparation faults submit no packet. Exhausted
restoration submits no additional work. Existing generation, owned-copy,
rectangle, zero-before-publication, pinning and controller checks stay active.

Both selected Package loops call `pumpRefreshRestoredBatched`. It preserves
the prior refresh state machine, refresh rectangle/sequence and four-tile
per-iteration budget. Dirty work uses the remainder of that budget. A refresh
is requested only after the complete restoration and dirty queue finish.
The historical `pumpRefresh` and `pumpRefreshBatched` definitions remain, as
does the initial boot call to the historical pump. Historical artifacts retain
their own catalogs, source archives and independent validation.

The existing artifact authority file retains cohort9 unchanged and carries a
separate nested cohort10 authority. Each admitted deployment requires both
actual ordinary notebook/initializer catalogs and complete pre/post LLVM
body/global/caller pins from genuine elaboration and checked lowering. Mixing
old and new selected pumps, a partial corpus, unknown catalogs or changed
bodies rejects. No host renderer, journal recovery or mathematical authority
is introduced.

Literal Action and genuine checked LLVM component results qualify four/tail
batches, partial completion/error/retry, cursor/preparation faults and clipped
35x33/canonical edge tiles. Complete linked-image audits, actual guest execution
and measured performance are separate requirements. A component or compiler
trace is not a successful notebook boot or physical panel qualification.
