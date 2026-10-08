# Task 002 session state

- Base: Task 001 report-bearing commit `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`
  (tree `88d2c23aafbd2b3a40a195755c01494de9ffad75`), stacked because PR #1 is unmerged.
- Working branch: `task/002-machine-foundation`.
- Highest passing gate: Gate 0.
- Current gate: Gate 1, in progress.
- Current failure: none.
- Next executable action: implement the quarantined Lean-authored lowering-fault API and
  its O0/O2 behavioral-mismatch driver, then run focused host tests and the Gate 1 matrix.

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

## Decisions that must survive a resume

- Preserve `core0-v0.1` and its rejection corpus; new operations use a new profile.
- Task 001 historical artifacts remain bound to `800d359...`; the clean report-bearing
  verification and GitHub synthetic merge are separately identified in its evidence.
- Runtime input bytes are ASCII `LEMMA001`; the loaded little-endian word is
  `0x313030414d4d454c`. The separate corpus tag remains `0x4c454d4d41303031`.
- Gate 1 mutations are test-only Lean transformations, never production inputs.
- Gates 0–3 advance Stage I only. Task 002's later M-mode work cannot by itself mark
  Stage II unit 2.1 or 2.2 passed because their broader roadmap requirements remain open.

Machine-readable status is in `docs/plan/002-gates.json`.
