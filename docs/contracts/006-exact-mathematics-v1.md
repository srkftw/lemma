<!--
# Restricted exact mathematics and original course v1

This preserves the original832-byte format and its observed milestone. The
maintained notebook now implements [version2](006-exact-mathematics-v2.md),
including guest migration and explicit uncertain review/override/disable.
Tap COURSE again to close its current panel; the former CLOSE cell is REVIEW.

This is an additive guest application format; historical ink, store, machine and
Core0 profiles retain their meanings. Target declarations genuinely elaborate
through the existing checked scalar/Action lowering and LLVM. It requires no
new compiler operation, foreign helper, managed object or target runtime. It
does not implement the Lean proof kernel, arbitrary algebra or close G2/G5–G7.

`lemma-exact/1` checks signed rational addition equality and univariate product
identities over Q[x]. Signed integers use canonical sign/magnitude u64 words:
bit63 denotes negative, bits0–62 magnitude, and negative zero rejects as
NeedsClarification. Public magnitudes and positive denominators are at most
1,000,000. Zero denominators return Invalid before arithmetic; exceeding the
declared representation returns Indeterminate. Rational cross products are
bounded by 2×10^18 and polynomial intermediates by 2×10^12, below bit63.
No wraparound, floating-point comparison, parsing success or host invocation
can authorize Verified.

The rational request is `a/ad + b/bd = n/d`, with explicit nonzero positive
denominators and an eight-step budget. The polynomial request is
`(a*x+b)*(c*x+d) = p2*x²+p1*x+p0`, requiring six steps. Equality checks the exact
three coefficients, rather than sampling x. Smaller budgets return
Indeterminate before arithmetic. The public outcomes are Unchecked0,
Verified1, Invalid2, NeedsClarification3, Unsupported4 and Indeterminate5.
The arithmetic budget is a deterministic semantic resource bound; it is
separate from kernel scheduling, stack, process death and host deadlines.

The original `lemma-course-arithmetic/1` package has fraction addition
`1/2+1/3`, then expansion `(x+1)*(x+1)`. The third page is an explicit Unsupported
example. Text and exercises are original; source/edition/rights anchor is
`Lemma/Courses/Arithmetic.lean`. Fraction equivalence and distributivity are
logical prerequisites; fractions then products is the pedagogical order.
There is no external textbook dependency, package installer or live tutor.

The pen-driven panel edits explicit typed numbers0–99 separately from raw ink.
Selection never interprets handwriting. Closing the panel reconstructs the
unchanged page from original ink. Ink outside the panel remains ordinary ink.
`CHECK` calls the guest arithmetic algorithm on the actual current answer;
`NEXT` changes the immutable goal identity; `HINT` records explicit assistance
and displays an authored local hint; `LIMIT` selects the eight-step or zero-step
budget; `CLOSE` hides the panel. The explainable baseline recommendation is
Practice after Invalid/Unchecked, Review later after Verified, or Needs support
after other terminal outcomes. This is an uncertain practice suggestion, not
evidence of learner understanding, retention, transfer or learning gain.

## Durable mathematical submission record

`lemma-mathematical-submission/1` uses magic `0x314854414d4d454c`, exactly832 bytes,
aligned little-endian u64 fields and key `0x8000+pageID` in the notebook's
existing namespace1/2. Those keys do not overlap roots, page indexes or raw ink.
The record is committed through the same guest store Begin/Stage/Commit path;
Saved still follows the actual backing barrier. No host parser constructs or
recovers a live document. Opening a missing key creates a fresh typed record;
malformed or incompatible existing bytes reject and never initialize over them.

| Offset | Meaning |
| --- | --- |
| 0,8,16 | magic, format1, original package identity `0x0001000000000001` |
| 24,32,40,48 | namespace, raw-ink page anchor, submission revision, original goal1/2/3 |
| 56,64,72,80,88 | typed numerator, denominator, polynomial constant/linear/quadratic coefficients |
| 96,104 | current outcome, evidence submission revision (both zero after edit) |
| 112,120,128 | checker/environment identity `0x0001000000000001`, domain equals goal, empty assumptions0 |
| 136,144,152 | arithmetic budget0/8, attempt count0–8, explicit local hint count0–32 |
| 160,168 | selected UI field, explainable recommendation0–3 |
| 176–248 | reserved zero |
| 256–831 | eight immutable nine-word attempt entries |

Every attempt stores revision, goal, numerator, denominator, all three
coefficients, outcome and budget. Editing increments the submission revision
and clears current applicability while preserving every earlier attempt.
History exhaustion returns Indeterminate and never overwrites an old entry.
At load, namespace/page/package/environment/domain/bounds and active history
are checked. Current Verified evidence is recomputed from its exact goal and
typed values. This record uses the existing store corruption checks, not media
authentication or a new immutable trust root.

The notebook lazily allocates owned pages `0x329000` and `0x32a000` for the live
record and immutable asynchronous save copy, after COURSE is opened. The
historical41 working pages and full dirty queue remain intact. The save copy
cannot change until its store transaction finishes. Course edits are admitted
only with no pending notebook save/raw tail; writing resumes between bounded
save/display operations. This is still an application-local checker, not a
separately isolated verifier service or managed-Lean runtime.

`Mathematics.copy` checks alignment/address bounds and copies exactly104 owned
64-bit words before starting a transaction. The existing generic store copy
retains its512-byte sector/transport limit. An original real target failure
from passing832 bytes to that helper remains retained; the larger record has
its own bounded copy rather than broadening a transport helper's contract.

The additive font extends its exact closed ASCII lookup to40–89. Existing glyphs
and the original footer switch remain unchanged. Course text, answer digits and
panel rows each have a separately owned compiler-generated jump table, admitted
only with exact19/25/8 domains, pure signatures, notebook image ownership and
the existing relocation/unsigned-bound checks. This is artifact provenance;
it adds no Core0 language operation or mathematical authority.

`tests/mathematics/ExactMath.lean` compares production signed arithmetic with an
independent host Int oracle and exercises record/UI/revision/resource failures.
Those observations are distinct from target linking/audits, actual RV64
notebook execution and physical conformance.

## Launch and interaction

Build the maintained canonical development notebook and prepare the same audited
image for the native fast machine:

```sh
nix develop --no-write-lock-file --command python3 scripts/build_kernel.py \
  --configuration lemmasim-silicon-power-notebook --stage supervisor \
  --opt-level O2 --output-dir build/kernel/my-course-notebook --timeout 300
nix develop --no-write-lock-file --command python3 scripts/audit_kernel.py \
  build/kernel/my-course-notebook
python3 scripts/lemmasim build --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --workload notebook --guest-build build/kernel/my-course-notebook
python3 scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --workload notebook --disk my-initialized-notebook.raw --session-dir build/my-course-session
```

This is the explicit ELF-preload development path, not product boot/update.
Use an already initialized notebook medium; opening does not format user media.
Tap COURSE below the notebook toolbar. Select N/D or C0/C1/C2 in the FIELD row,
then use PLUS/MINUS to edit the typed number. For `1/2+1/3`, enter N5/D6 and tap
CHECK. NEXT selects the polynomial exercise; C0=1, C1=2, C2=1 checks its exact
identity. HINT records assistance from the authored local course. LIMIT selects
the explicit zero/eight-step budget. CLOSE returns to the original ink.

The connected raw-input/durable/cold observer, with original declared bounds,
uses a private copy of its input medium and unused output path:

```sh
python3 scripts/check_math_session.py --disk my-initialized-notebook.raw \
  --work-dir build/my-course-observation --deadline 2400
```

It checks actual guest results, edit invalidation, immutable history, explicit
assistance, resource/unsupported outcomes, raw ink retention, controller pixels,
acknowledged bytes, independent cold reopening and a failed save. It does not
exercise a live tutor, managed runtime or Lean proof-kernel checking.

-->
