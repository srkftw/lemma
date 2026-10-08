# Task 002 session state

- Base: Task 001 report-bearing commit `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`
  (tree `88d2c23aafbd2b3a40a195755c01494de9ffad75`), stacked because PR #1 is unmerged.
- Working branch: `task/002-machine-foundation`.
- Highest passing gate: Gate 1.
- Current gate: Gate 2, in progress.
- Current failure: none.
- Latest passing implementation: `8878d2c65a6d76bc94ef0e8a9e036404bc76582c`
  (tree `a110453f7d92b342f193cd36e889db9a370d3232`).
- Next executable action: define the additive versioned typed test ABI and represent
  RV64 LP64 parameter/result extension attributes in structured LLVM, then bring up
  the first multi-root direct-source/model/target ABI cases without changing v0.1.

## Gate 0 commands and observed results

Executed against a clean `b8e9c593...` source tree on 2026-10-08:

```text
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases at O0/O2, 13 expected rejections, 23 fresh QEMU boots
```

Fresh aggregate record: `build/core0/check/check-results.json`, SHA-256
`3a3cb9244b4a84b1a93ff869843aa3619622719ef6f431067e5502cbefc58a7c`.
Both profile provenance files name `b8e9c593...` and `dirty_tree: false`.

## Gate 1 commands and observed results

Executed against clean source `8878d2c...` on 2026-10-08:

```text
nix develop --no-write-lock-file --command lake build
  exit 0; 15 jobs
python3 scripts/check_scaffold.py
  exit 0; metadata PASS
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
  exit 0; 19/19 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases at O0/O2, 13 rejections, 23 fresh QEMU boots
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 1 --clean
  exit 0; 2 controls, 12 mutants, 3 rejections, 7 audit regressions,
  24 fresh QEMU boots, 12/12 verified behavioral mismatches
```

Gate 1 aggregate SHA-256:
`a3fd012ad0dac0d20e16321c32c7006502b8c22921499517bab1468b669bf50c`.
Task 001 cumulative regression SHA-256 at the same source:
`690732e4a97a29bc25cf168c46d9f8f857667d432c5c6271463bde1fdaff4f18`.

## Decisions that must survive a resume

- Preserve `core0-v0.1` and its rejection corpus; new operations use a new profile.
- Task 001 historical artifacts remain bound to `800d359...`; the clean report-bearing
  verification and GitHub synthetic merge are separately identified in its evidence.
- Runtime input bytes are ASCII `LEMMA001`; the loaded little-endian word is
  `0x313030414d4d454c`. The separate corpus tag remains `0x4c454d4d41303031`.
- Gate 1 mutations are test-only Lean transformations, never production inputs.
- A mutant audit requires an audited clean control and proves the reported replacement
  is the sole pre-optimization IR delta.
- Schema-2 build provenance records artifact category and hashes the exact imported
  Lean `.olean`; historical schema-1 release evidence remains accepted as release only.
- Gates 0–3 advance Stage I only. Task 002's later M-mode work cannot by itself mark
  Stage II unit 2.1 or 2.2 passed because their broader roadmap requirements remain open.

Machine-readable status is in `docs/plan/002-gates.json`.
