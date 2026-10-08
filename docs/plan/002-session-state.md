# Task 002 session state

- Base: Task 001 report-bearing commit `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`
  (tree `88d2c23aafbd2b3a40a195755c01494de9ffad75`), stacked because PR #1 is unmerged.
- Working branch: `task/002-machine-foundation`.
- Highest passing gate: Gate 2.
- Current gate: Gate 3, in progress; it has not passed.
- Current failure: none.
- Latest clean passing implementation: `687ee7e292b7a049f8fd35fcf17097c80c3d5665`
  (tree `9b3a8e06a0ce683b887a75ee9c615eb856965a1c`).
- Next executable action: define the explicit post-v0.1 profile for structured basic
  blocks, conditional branches/merge values, complement, shifts, and unsigned
  division/remainder; preserve the `core0-v0.1` rejection behavior and begin with
  direct-source probes for the pinned Lean edge semantics.

## Gate 0 historical checkpoint

Executed against clean `b8e9c593...` source on 2026-10-08:

```text
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases/profile, 13 expected rejections, 23 fresh QEMU boots
```

Historical aggregate SHA-256:
`3a3cb9244b4a84b1a93ff869843aa3619622719ef6f431067e5502cbefc58a7c`.

## Gate 1 historical and cumulative checkpoint

Gate 1 first passed against clean implementation `8878d2c...` (tree
`a110453f...`) with 2 controls, 12 mutants, 3 intended source rejections, 7 audit
regressions, 24 fresh QEMU boots, and 12/12 verified behavioral mismatches. Its first
aggregate SHA-256 was
`a3fd012ad0dac0d20e16321c32c7006502b8c22921499517bab1468b669bf50c`.

The same complete Gate 1 checks were rerun in the cumulative clean Gates 1-2 command
at `687ee7e...`. The current Gate 1 aggregate is
`build/foundation/gates1-2-clean/gate1/gate1-results.json`, SHA-256
`b09cfaa81a8e1d567f3afe492570bd04112c86cec9378cb9cfab987e64a9bffe`.
All 14 control/mutant provenance records name that commit and are clean.

## Gate 2 commands and observed results

Executed against clean source `687ee7e...` on 2026-10-08:

```text
nix develop --no-write-lock-file --command lake build
  exit 0; 20 jobs
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
  exit 0; 86/86 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases/profile, 13 rejections, 23 fresh QEMU boots
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-2-clean --clean --timeout 300 --qemu-timeout 10
  exit 0; GATES 1-2 PASS; Gate 1: 24 boots; Gate 2: 136 boots
```

Gate 2 recorded 37 genuine elaborated roots, 1,024 distinct cases/profile, 61 valid
and 7 negative boots/profile, 1,024 direct-source/model matches, 2,048
source/model/target profile matches, five metamorphic pairs, and 327,680 exhaustive
UInt8 direct/model comparisons. O0 and O2 retain a real audited ten-argument RV64
call with narrow ninth/tenth arguments, a 32-byte 16-aligned caller frame, and exact
LP64 extension attributes.

Evidence identities:

- cumulative Gates 1-2:
  `45ba122a148518e76062512f7358d536c16924f1bd881380d69c4819da02a158`;
- Gate 2:
  `6b3e775f3f7ffeb17ed5b9d781d8ae38815afea07944d3e7fc45de21beb3b5cc`;
- cumulative Task 001 regression:
  `30a4b52daf4703df172137eef828a5b6d4052efa42b7cc6c95b099edf05361fe`.

## Decisions that must survive a resume

- Preserve `core0-v0.1` and its rejection corpus; Gate 3 requires an explicit new
  profile rather than silently expanding v0.1.
- Task 001 historical artifacts remain bound to `800d359...`; its clean report-bearing
  verification and GitHub synthetic merge are separately identified in Task 001
  evidence.
- Runtime input bytes are ASCII `LEMMA001`; the loaded little-endian word is
  `0x313030414d4d454c`. The separate Task 001 corpus tag is
  `0x4c454d4d41303031`.
- Gate 1 mutations are test-only Lean transformations, never production inputs. A
  mutant audit requires an audited clean control and proves that the reported
  replacement is the sole pre-optimization IR delta.
- Gate 2's additive typed ABI is `lemma-scalar-test-v1`, suite
  `0x7812482420151ea4`; it does not replace the legacy harness. Source and runtime
  seeds are `0x4c454d4d41323032` and `0x52554e54494d4532`.
- Direct-source and checked-model routes share the pinned Lean elaborator/type checker;
  the direct route does not import or call the Core0 checker/evaluator. Do not describe
  the three comparison routes as absolutely independent proof systems.
- Schema-2 provenance binds exact source and `.olean` inputs. O0/O2 Gate 2 profiles
  share byte-identical checked suite/ABI/source artifacts and name a clean
  `687ee7e...` source.
- Gates 0-3 advance Stage I only. Later M-mode work cannot by itself mark Stage II
  Unit 2.1 or 2.2 passed, and neither G1 nor G2 is complete.

Machine-readable status is in `docs/plan/002-gates.json`.
