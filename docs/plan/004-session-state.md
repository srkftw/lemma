# Task 004 checkpoint

Branch: `task/004-lemmasim-durable-ink`, based on main
`504f6e462e502d93192ba689d16d8552ca1e68b5` after one fetch on 2026-10-10.
Status: IMPLEMENTING; the primary completion boundary is unmet.
[Draft PR #5](https://github.com/srkftw/lemma/pull/5) remains draft. No merge is authorized.

Published implementation: `c96a375531cbf9a8e6e692b4b1aec2760c290eef`, tree
`5a251eef6386ddf14e41e6d7261165fe41d12b71`. README has actual build/init/run,
Developer capture/replay and offline copy/archive commands. The compiled guest
has descriptor/DTB validation, a 32 MiB owned pool, 16 KiB stacks, PLIC pen/paper,
modern VirtIO/flush, isolated durable records, integer ink/rasterization, pages,
editing and an asynchronous save path. Source existence is not gate acceptance.

Exact-candidate `build/lemmasim/task004-c96a375-full1` is FAIL/reaped before
isolation boot: the strict production-object comparison found LLVM's local FILE
symbol differed by deployment name. Actual notebook/store code, data,
relocations and linked bytes match. The Lean exporter now uses a scoped stable
semantic label; the complete-object comparison is retained. Fresh dirty
ordinary/isolation O2 builds and full audits pass; both complete production
objects and linked User images are identical, with unchanged executable text.
Result: `lemmasim-complete-object-identity-dev1/result.json`, SHA256
`f3b1745a3d3ccdb98996dbaba30b84918665804971a3dbc604232a2e8cb06cca`.
A fresh private four-root build and all eleven actual fixtures pass (112.96s):
`fresh-writing-imports-four-roots-attempt1/result.json`, SHA256
`fde3db62baa3eaea2fb0ee8bc6824e405d51756e3fc373362c60111ecd220edd`.
All processes are reaped; these are preflight observations, not a new guest pass. O2/O0 basic
writing and cold committed-byte/controller-pixel comparison, editing/two
notebooks and cold recovery pass in this same campaign. Later isolation,
read-only media, second geometry, loss/replay/native, faults, source negatives
and 100,000-sample workload are NOT_RUN. Do not turn the retained FAIL into PASS.
O2 notebook SHA256: `902e4a5841bcf93fba429d24faf47965b65953765d3fb6295bba2c6aa5617ff1`.
Selected trap bounds: O0 9,328 / 16,352; O2 1,984 / 16,352 usable bytes, including
288-byte entry. These are selected-path bounds, not whole-program proofs.

Actual PR CI run `38084399190` checks synthetic merge
`e67aebe0b632ccaf35f4ff8397b09d0a106a3dbf`. At its retained progress snapshot,
host, legacy and buffer jobs passed; six jobs were running with no failure.
Snapshot directory: `build/lemmasim/ci-c96a375-run38084399190`.
No older green result passes a changed executable candidate.

Keep failures in `task004-80b89dc-full1`, `task004-dea6281-full1`,
`task004-115a335-full1` and their `ci-*` directories. Stale IPC audits and fresh
Store/Notebook module prerequisites were repaired. Fresh private preparation
passed all ten fixtures without inherited modules or outer-cache changes:
`fresh-fixture-cache-115a335-checkerfix-attempt1/result.json`, SHA256
`270b83acdccc8d28206969b3cb892dc586d14ae3d09f60d0bc33f47822adc9b0`.
The header validator's literal checks, genuine Core0 closure and RV64 O0/O2
objects pass: `ink-header-codegen-attempt1/result.json`, SHA256
`9f86794ee14b9e0401633fa71d9f1db45fd35ba4802be17adaa23e5515e13b10`.
The separate exact `dea6281` J lane passed four actual O0/O2 workflows and audits:
`build/worktrees/task004-inherited-kernel/build/kernel/verify-J-dea6281/result.json`,
SHA256 `0a928036080269b3556a1b24f27116e09faece1d23b86acb61bf5e8b40116875`.

Earlier dirty development observations remain scoped: unchanged 100 Hz dev6
retained 6,250 unique samples with Saved53 and exact cold bytes/pixels; original
observer FAILs remain. Dirty dev5 native GTK/QMP ingress, actual QEMU replay,
cold recovery and reset-during-busy restoration passed. Manual interaction and
physical tablet input are NOT_RUN. Retain `focused6250-64e3bbb-input8-dev6`,
`native-gtk-64e3bbb-dirty-dev5-attempt1`, `inherited-a1-handoff.json` and historical
CI artifacts. QMP reset may drain/flush; it is not a power cut.

Pinned host QEMU v17 SHA256:
`0e95380d2eb582ebf95f989fc6a07eac26a50c222bbbee95dd5fa5421d2864ce`.
Next: commit the verified scoped exporter fix, run the fresh exact-candidate full
matrix and required actual CI, export offline evidence outside ignored build/,
write one concise report/result/manifest, and update the draft. Actions artifacts
retain for 14 days; final permanent offline retention is pending. Legacy profiles,
physical UNVERIFIED status, and later managed-runtime/mathematics boundaries stay
unchanged. Do not claim completion from this checkpoint.
