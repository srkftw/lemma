# Course workspace envelope 2

`lemma-installed-package-notebook/5` stores a lossless envelope of the existing
`lemma-course-workspace/1` object. Its decoded3712 bytes, Doc8, object key,
ownership, revision/provenance/history validation and Store journal format are
unchanged. This is an explicit stored-object migration, not a new journal.

All fields are little-endian aligned64-bit words. The first four words are
magic `0x3243574b504d454c` (`LEMPKWC2`), version2, decoded length3712 and exact
stored length. Eight bitmap words follow at offset32. Bit `i % 64` of word
`i / 64` names decoded word `i`, for `0 ≤ i < 464`. The last bitmap's high48
bits must be zero. Starting at offset96, each set bit contributes its nonzero
decoded word in increasing index order. Unset bits decode to zero. Encoded zero
values are rejected. Stored length equals96 plus8 times the population count,
is divisible by8 and is at most3808. Every decoded byte is retained, including
bytes with no current UI use. The journal's existing integrity checks cover
the complete stored payload; this encoding adds no authentication claim.

The guest first reads64 bytes, classifies the raw1 or envelope2 length, then
reads the complete bounded object and independently reads EOF. Header admission
alone never publishes a workspace. Envelope validation checks exact length,
bitmap bounds/count and canonical nonzero data, reconstructs privately, then
runs the complete original workspace and Doc8 validators before adoption.
Raw1 reads retain their original full validation and exact EOF. Only a missing
workspace at the initial read permits the existing legacy Doc8 import path;
malformed, unsupported or subsequently missing records never trigger formatting.

The encoder validates the active workspace at `0x33b000`, writes disjoint
staging at `0x32a000` and returns the exact length. Header magic is written last.
Staging remains frozen until the actual append/barrier reply. Compression and
RAM validation cannot emit Saved or substitute for that reply. Decode staging
uses the existing package-byte span at `0x332000` while the course is closed;
later package reads refill it before use. The same12 package pages, generation
checks and allocation counter remain. Opening phase5 is busy until full record
admission. Actual access errors and private partial effects remain observable;
there is no rollback claim for a failed staging write.

New software reads raw1 and envelope2 and writes envelope2 on the next ordinary
save. Software1–4 cannot read envelope2 workspace objects. Keep a pre-migration
export when using those older development images; this increment supplies no
boot rollback compatibility for the new object. Other notebook/ink objects,
user media and old journal entries are neither formatted nor rewritten.
General product update/rollback qualification remains a separate obligation.

All codec and selection policy is ordinary maintained Lean checked through the
existing scalar User2 lowering. Host test decoders are passive independent
oracles and cannot modify guest documents or media. The finite component checks
and exact source cohorts are separate from full ELF audits, actual RV64 saves,
cold recovery, browser execution and arbitrary-boundary checkpoint continuation.
