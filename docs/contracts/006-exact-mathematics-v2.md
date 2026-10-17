<!--
# Durable uncertain offline review v2

This additive successor preserves `lemma-exact/1`, original goal/package and
checker identities, outcomes and the first832-byte typed-answer/attempt layout
described in [v1](006-exact-mathematics-v1.md). It versions the durable record
as `lemma-mathematical-submission/2`, exactly1856 bytes. Raw ink and the existing
journal format remain unchanged. The same two lazily allocated owned pages hold
the live record and complete232-word immutable transaction copy.

| Offset | Version2 field |
| --- | --- |
| 8 | record version2 |
| 176 | `lemma-offline-review/1` identity `0x0001000000000001` |
| 184 | mode: automatic0, manual practice1/later2/support3, disabled4 |
| 192 | ordered event count0–64 |
| 200 | understanding uncertain1; zero/other values reject |
| 208 | event encoding version1 |
| 216 | show policy explanation0/1 |
| 224–248 | reserved zero |
| 832–1855 | sixty-four ordered16-byte learner events |

Each event contains its submission revision and a descriptor. Descriptor bytes
0–3 contain kind, original goal identity, value and attempt index; the upper
four bytes are zero. Kind1 references the next immutable exact attempt, with
matching revision/goal/outcome and index0–7. Kind2 records an explicit local
hint with value1. Kind3 records an explicit mode choice0–4. Kind4 records goal
navigation with value1. Kind5 records an Indeterminate submission after the
eight-attempt bound. Kind6 is the expressly unanchored legacy hint aggregate
with value1–32; it never claims old individual hints had known source revisions.
Unused entries are zero. Loader validation binds all attempt events to the
actual independently recomputed history and recomputes hint/mode aggregates.
Unknown identities, values or mismatched aggregates reject without formatting.

An operation checks event capacity before changing its submission, hint count
or policy. Exhaustion returns the existing bounded resource error; it preserves
all prior events, evidence and notebook ink. Hint/attempt bounds retain their
original32/eight limits. Mode changes do not revise the submitted goal or
mathematical evidence. They save through the same guest store transaction;
only its actual barrier acknowledgment can authorize Saved. A failed barrier
may have persisted provisional backing bytes and never rolls the medium back.

The guest first reads and validates the common832-byte prefix. For v2 it reads
the full1856 bytes through actual bounded store IPC. A valid v1 record migrates
inside the guest: every original answer, revision, domain and exact attempt
survives; events reference the recorded attempts. The old global hint count is
retained as kind6 because v1 never stored the source goal/revision of each hint.
The migration is acknowledged through an ordinary store barrier. Interrupted
publication leaves the existing journal recovery semantics in control. Unknown
or malformed records never migrate or initialize a replacement.

`Lemma.Courses.Review` reconstructs a conservative estimate from these events:
no attempt recommends practice; an unassisted exact attempt recommends review
later; an assisted exact attempt recommends practice; an invalid attempt
recommends practice; unsupported/resource outcomes recommend support. Assistance
stays associated with its observed goal. A legacy aggregate conservatively
counts as assistance for every goal. The displayed explanation names the
observed reason. All recommendations say UNCERTAIN: task evidence is not a
measurement of understanding, delayed/transfer assessment or learning gain.
There is no learned policy, opaque score, tutor authority or reward optimization.

The panel retains actual typed editing, CHECK/NEXT/HINT/LIMIT. REVIEW cycles
manual practice, manual later, manual support, disabled and automatic, saving
every choice. Its row displays the explicit mode/recommendation and uncertainty;
the authored reason is visible after a choice. Tap COURSE again to return to
raw ink. Hints remain explicitly authored local material, not a live provider.
The exact closed font adds K; the pure course text owner has33 messages. Artifact
audits retain exact50 glyphs and33/25/8 bounded course lookup domains and negative
content/index/target provenance checks; this adds no compiler language feature.

Build/audit/prepare/launch commands are the same as v1 with a fresh unused
output directory. `scripts/check_math_session.py` exercises the full current
mathematical workflow. The version migration/review/override/disable/cold and
failed-save observer consumes an actual acknowledged v1 course medium:

```sh
python3 scripts/check_review_session.py --disk my-acknowledged-v1-course.raw \
  --work-dir build/my-review-observation --deadline 2400
```

The actual source-bound native fast campaign is recorded in
[the concise evidence](../evidence/006-offline-review.json): migration, all five
ordered modes, exact pixels, independent cold recovery and unsuccessful barrier
passed. Its original wrong-M-row observer failure remains preserved. This does
not establish canonical RTL or browser execution of the complete course.

It supplies only raw pen input, medium backing and independent observations.
No host process builds guest learner events or grants mathematical evidence.
This bounded original course application remains short of managed Lean,
isolated checking service, proof-kernel checking, general immutable package
installation, held-out assessment, learner model calibration, permissioned
tutor transport and demonstrated learning gains.

-->
