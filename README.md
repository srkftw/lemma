# Lemma

A pen-first mathematics computer, constructed from a freestanding Lean 4 foundation
on RISC-V. The reference machine is **LemmaVM**; the operating system is **LemmaOS**;
the physical device is **Lemma One**.

**Current state: tested freestanding diagnostic monitor and machine foundation.**
Task 001 established the Lean elaboration -> checked Core0 -> LLVM -> static
RV64 ELF -> QEMU `virt` path. Task 002 Gates 0–10 extend and qualify it with compiler-fault
detection, multi-root conformance, validated control flow, bounded iteration,
checked fixed-region RAM, compiled Lean UART interaction, and synchronous M-mode
traps with checked context preservation, and actual timer interrupts during
foreground computation. The integrated ten-command monitor and full cumulative/
legacy suite passed clean detached O0/O2 qualification at `09c47ba`.
Task 002 is published as [draft stacked PR #2](https://github.com/srkftw/lemma/pull/2);
the initial actual CI failed at Gate 3's pinned-source materialization. Its repair
passed full fresh local qualification and all three jobs in both actual
[push](https://github.com/srkftw/lemma/actions/runs/37825241614) and
[PR CI](https://github.com/srkftw/lemma/actions/runs/37825247231) runs. Tested
implementation and later report-bearing commits remain distinct.
This is not a managed runtime, complete OS, hardware milestone,
or completion of G1/G2. See [Task 001 evidence](docs/evidence/001-core0.md),
[Task 002 evidence](docs/evidence/002-machine-foundation.md), and the
[continuation checkpoint](docs/plan/002-session-state.md).

## Invariants

- RISC-V is mandatory for the application machine. ARM is not a substitute.
- Maintained target software is Lean 4. No target-side C, C++, Rust, Zig, or handwritten
  assembly, and no upstream Lean target runtime hidden in the link.
- Host Lean, LLVM, LLD, QEMU, Nix and host-only build orchestration are development
  dependencies, not device runtime components. Generated machine code, LLVM IR,
  assembly and linker artifacts have explicit Lean-source provenance.
- The notebook must work offline before recognition, checking or tutoring is required.
- Raw ink, interpreted mathematics, checking evidence, and learner estimates are
  different records. A tutor never acquires verification authority.
- Model properties, execution tests and physical measurements are different evidence.

## Build order

| Gate | Construction | Required result |
| --- | --- | --- |
| G1 | Core0, LLVM audit, LemmaVM | Accounted-for freestanding target execution |
| G2 | Boot, runtime, traps, memory, scheduling | Isolated managed-Lean execution |
| G3 | Capabilities, IPC, storage | Authorized and recoverable committed records |
| G4 | Pen, display, ink, mathematical documents | Complete offline notebook |
| G5 | Exact checking and proof checking | Reproducible, correctly scoped evidence |
| G6 | Semantic textbooks and learner state | Traceable offline learning sequence |
| G7 | Networking, tutor, learning policy | Permissioned assistance and evaluated adaptation |

See [the detailed construction plan](docs/plan/BUILD_ORDER.md) and its
[machine-readable backlog](docs/plan/construction-units.json): 56 software units
and six physical-port units.  The Stage I entries remain partial until their broader
gate evidence is complete.

## Start here

Read [AGENTS.md](AGENTS.md), [the architecture](docs/ARCHITECTURE.md), and the four contracts:

1. [Core0](docs/contracts/CORE0.md)
2. [Target ABI](docs/contracts/TARGET_ABI.md)
3. [LemmaVM](docs/contracts/LEMMA_VM.md)
4. [Trust and dependencies](docs/contracts/TRUST_MANIFEST.md)

Task 001 pins the tested Lean/LLVM/LLD/QEMU environment in `flake.lock`,
`lean-toolchain`, and `tooling/toolchain-lock.json`.  The chosen frontend reads genuine
Lean-elaborated declarations and uses a narrow project lowering because the pinned
Lean package does not contain its optional upstream LLVM emitter.  The audit and choice
are documented in [the LLVM/Core0 audit](docs/audits/llvm-core0.md).  Code boundaries
are documented in [the source map](docs/SOURCE_MAP.md).

## Checks

```sh
python3 scripts/check_scaffold.py
python3 -m unittest discover -s tests/scaffold -v
nix develop --command python3 -m unittest discover -s tests/core0 -v
nix develop --command ./scripts/check-core0.sh --clean
```

The first two remain metadata/publishing-helper checks.  The Core0 acceptance command
builds Lean, audits the two-object target closure, validates the QEMU DTB, executes a
nonempty O0/O2 differential corpus on fresh RV64 boots, tests expected rejections,
checks repeat-build hashes, mutates accepted source, and proves the audit rejects a
statically resolved foreign object.  A finite green corpus is not a compiler proof and
does not qualify all of G1.

The recorded Task 002 passing prefix also has real host/target checks:

```sh
nix develop --no-write-lock-file --command lake build
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 9 \
  --work-dir build/foundation/gate9-recheck --clean --timeout 300 --qemu-timeout 20
```

Phase 9 builds and audits O0/O2 images and runs 18 fresh QEMU boots. Historical
focused acceptance at `8fd45d8` handled 1,598 requests, observed 1,461 hardware interrupts and 20
synchronous recoveries, and checked 192 ring records, with malformed-request
recovery, bounds checks, timer restart/shutdown and both session-budget edges.
The earlier clean cumulative Gates 1–8 run passed 456 boots at `42674c1`;
legacy acceptance separately passed 23 boots. The current extended cumulative
and detached-worktree qualification have separate fresh evidence below; they
do not inherit these historical passes.

The cumulative/stress and final qualification interfaces are:

```sh
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all --stress \
  --work-dir build/foundation/gates1-9-clean --clean --timeout 300 --qemu-timeout 20
nix develop --no-write-lock-file --command python3 scripts/qualify_foundation.py \
  --gate9-dir build/foundation/gates1-9-clean/gate9 \
  --work-dir build/foundation/qualification --clean --timeout 300 --qemu-timeout 20
```

Qualification requires committed, clean source. It independently replays retained
monitor evidence, repeats same-profile builds, and exercises stale-PASS and missing/
tampered-evidence failures. Clean `09c47ba` passed 438 foundation, 32 Core0 and
18 scaffold host tests, a cold 53-job Lean build, 482 cumulative and 23 legacy
QEMU boots, 26 raw-session replays, 16 reproducible artifacts/profile and five
failure experiments. The monitor handled 2,742 requests with 4,229 observed
hardware IRQs, 60 synchronous recoveries and 576 retained records. A catalog-
construction defect in the first qualification attempt was caught, fixed and
retested; its failed evidence remains retained. A later fresh-CI pinned-source
materialization defect was repaired and the full clean suite repeated; the earlier
successful `e0e1f21` run is historical, not rebound. See the report for exact source
and later publication identities. CI separately runs metadata/host,
legacy RV64, and cumulative foundation/qualification jobs with retained artifacts.

## Kernel foundation development

The accepted A/B prefix has an independent boot package and frame API. These
commands run inside the pinned environment; `bootstrap-m` does not claim S/U
execution. Keep source stable between build and observation: stale bindings fail.

```sh
nix develop --no-write-lock-file --command ./scripts/build-kernel.sh \
  --configuration normal --stage bootstrap-m --opt-level O2 \
  --output-dir build/kernel/normal --clean
nix develop --no-write-lock-file --command python3 scripts/run_kernel.py \
  --image build/kernel/normal/image.elf --output-dir build/kernel/normal-run --clean
nix develop --no-write-lock-file --command ./scripts/build-kernel.sh \
  --configuration frames-development --stage bootstrap-m --opt-level O2 \
  --output-dir build/kernel/frames --clean
nix develop --no-write-lock-file --command python3 scripts/check_kernel_frames.py \
  --image build/kernel/frames/image.elf --output-dir build/kernel/frames-run --clean
```

The development transport remains live for fresh requests after boot. It is absent
from normal roots. The independent user ELF is in the build's `user/` directory;
loading/executing it is a later gate. Each finite runner stops/reaps QEMU after
actual observations and records that explicit host cleanup.

## GitHub and Codex

The repository is **`srkftw/lemma`**, private, with default branch **`main`**.
Task 001 [PR #1](https://github.com/srkftw/lemma/pull/1) and Task 002
[PR #2](https://github.com/srkftw/lemma/pull/2) were merged by explicit owner
authorization. Main `ff4045a79a6fda45f9cd8198587357846530a806` contains the reviewed
Task002 tree. Both task branches remain available.

For current kernel work, select `task/003-kernel-isolated-services` and read
its assignment, gate ledger and resume checkpoint. The current accepted prefix
is A–C; S-mode execution and timer forwarding work, while U-mode and services
remain outstanding. See
[Task003 evidence](docs/evidence/003-kernel-isolated-services.md).
Task 001's original assignment remains preserved at
`codex/prompts/001-core0-freestanding-slice.md`.

`scripts/publish-github.sh` is retained as a tested bootstrap helper for the original
empty-remote workflow. **Do not run it on this already-published repository.** It
intentionally refuses an existing repository or `origin`; see [publishing notes](docs/PUBLISHING.md).

## License and private material

No project license has been selected. Do not add a license, publish the repository,
or change visibility without the owner's decision. Preserve licenses and notices
for any third-party code introduced later. Do not commit supplier correspondence,
NDA documentation, panel waveforms, credentials, textbook files or personal learner data.
