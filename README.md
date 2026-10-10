# Lemma

## LemmaSim: permanent virtual Lemma One

**LemmaSim is a first-class, distributable embodiment of Lemma One**, not a temporary emulator. Both virtual and physical embodiments target one versioned [canonical machine contract](LEMMA_MACHINE_CONTRACT.md), sharing the freestanding Lean-authored RV64 operating system, mathematical capabilities, and user-visible device semantics. The ambition is complete functional equivalence, **not an already established physical-hardware result**. Physical properties such as thermals and writing-surface feel remain separate. Student, Developer, and Laboratory are modes of one LemmaSim.

Read the [cross-cutting LemmaSim plan](docs/plan/LEMMASIM.md) and the [simulation](sim/README.md) / [conformance](conformance/README.md) scaffolds. The existing `LemmaVM` QEMU boot-slice contract and G1-G7 implementation evidence remain unchanged and do not certify the complete virtual machine.


A pen-first mathematics computer, constructed from a freestanding Lean 4 foundation
on RISC-V. The historical boot reference is **LemmaVM**; the permanent virtual embodiment is **LemmaSim**; the operating system is **LemmaOS**;
the physical device is **Lemma One**.

**Current state: tested supervisor kernel and isolated volatile buffer service.**
Task 003 adds owned physical pages, Sv39 user address spaces, ordinary syscalls,
preemptive tasks, capabilities, blocking IPC and separately linked U-mode
applications. O0/O2 acceptance and legacy regressions passed at implementation
`14cc79be8914a349b729347cc05091aba6ac7ca7`; all eight jobs passed in both actual
[push](https://github.com/srkftw/lemma/actions/runs/38033677526) and
[PR CI](https://github.com/srkftw/lemma/actions/runs/38033679993).
Read the [Task 003 report](docs/evidence/003-kernel-isolated-services.md),
[gate ledger](docs/plan/003-gates.json) and
[checkpoint](docs/plan/003-session-state.md) for source-specific results,
commands, failures and trust limits. Its final report commit, merge and
post-merge CI are separate publication observations.

The earlier machine foundation remains qualified:
Task 001 established the Lean elaboration -> checked Core0 -> LLVM -> static
RV64 ELF -> QEMU `virt` path. Task 002 Gates 0–10 extend and qualify it with compiler-fault
detection, multi-root conformance, validated control flow, bounded iteration,
checked fixed-region RAM, compiled Lean UART interaction, and synchronous M-mode
traps with checked context preservation, and actual timer interrupts during
foreground computation. The integrated ten-command monitor and full cumulative/
legacy suite passed clean detached O0/O2 qualification at `09c47ba`.
Task 002 was merged through [PR #2](https://github.com/srkftw/lemma/pull/2);
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

The independent boot package and frame API remain available. These
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

The development transport remains live for fresh requests after boot. The
independent user ELF is in the build's `user/` directory. A supervisor build now
loads it into owned Sv39 mappings and accepts continuous run requests. The
ordinary U-mode, address-space API and architectural denial checks have observed
O0/O2 results in the gate ledger. Run the focused positive check with:

```sh
nix develop --no-write-lock-file --command ./scripts/build-kernel.sh \
  --configuration normal --stage supervisor --opt-level O2 \
  --output-dir build/kernel/user --clean
nix develop --no-write-lock-file --command python3 scripts/check_kernel_user.py \
  --image build/kernel/user/image.elf --output-dir build/kernel/user-run --clean
```

Each finite runner stops/reaps QEMU after actual observations and records that
explicit host cleanup. It does not treat a timeout or host stop as normal exit.

The service package has separately linked U-mode Buffer Server,
command client, peer client and CPU-bound application. Build and interact with
the ordinary package using:

```sh
nix develop --no-write-lock-file --command ./scripts/build-kernel.sh \
  --configuration service-normal --stage supervisor --opt-level O2 \
  --output-dir build/kernel/service-normal --clean --timeout 300
nix develop --no-write-lock-file --command python3 scripts/buffer-cli.py \
  --image build/kernel/service-normal/image.elf \
  --output-dir build/kernel/service-terminal --timeout 3600
```

Each registered user image can also be compiled and linked independently:

```sh
nix develop --no-write-lock-file --command ./scripts/build-user.sh \
  --configuration service-normal --image-key server --opt-level O2 \
  --output-dir build/user/buffer-server --clean --timeout 300
nix develop --no-write-lock-file --command ./scripts/audit-kernel.sh \
  build/user/buffer-server --timeout 120
```

The closed source registry is `Lemma/Compiler/DeploymentCatalog.lean`. The
independent user ELF, text/data payloads and manifest match the corresponding
boot-package constituent; the kernel loader supplies its owned mappings and
initial context.

The terminal accepts `help`, `version`, `ps`, `mem`, `discover` and bounded
`buffer create/write/append/read/status/destroy` commands. Read the returned
handle after creation. Text is encoded as UTF-8; `hex:00ff` supplies opaque
binary bytes. Each operation carries at most 128 bytes. Buffers are volatile,
and an old service epoch cannot identify data after a restart. Ordinary clients
have no task-management grant. The separate `service-development` package
contains the diagnostic controller and fault client used for acceptance.

The maintained service observer is `scripts/check_kernel_buffer.py`. Clean
committed-source acceptance uses the separate cumulative lanes:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_kernel_cumulative.py \
  --lane F-I --work-dir build/kernel/acceptance-F-I --clean --timeout 300 --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_cumulative.py \
  --lane J --work-dir build/kernel/acceptance-J --clean --timeout 300 --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_architecture.py \
  --work-dir build/kernel/acceptance-K --clean --timeout 300 --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_mutations.py \
  --expected-commit "$(git rev-parse HEAD)" \
  --work-dir build/kernel/acceptance-K-mutations --deadline 2400
```

The mutation campaign requires an unused output path and creates its own exact
clean detached controls and narrowly changed source checkouts. It preserves
original failed target observations rather than treating an unrelated failure
as mutation detection. Recover an interrupted run from the ledger and use a new
output path to retain previous evidence.

These lanes require their own observed results. The A-E controller, legacy
Core0/foundation acceptance and final Task003 qualification remain separate
requirements; a passing earlier checkpoint does not certify changed source.

## Task004 LemmaSim implementation checkpoint

The new `task/004-lemmasim-durable-ink` branch contains a genuine compiled RV64
notebook, isolated record service, pen/paper hardware models and a volatile/durable
block backend. Its primary notebook acceptance is still in progress. See the
[checkpoint](docs/plan/004-session-state.md),
[machine profile](docs/contracts/004-machine-profile-0.1.0.md),
[device ABI](docs/contracts/004-devices-v1.md),
[storage model](docs/contracts/004-block-medium-v1.md) and
[ink/page formats](docs/contracts/004-notebook-ink-v1.md).
Historical launch profiles retain their original meaning.

Prepare the pinned tools and guest images once, then launch without rebuilding:

```sh
./scripts/lemmasim build
./scripts/lemmasim init --disk build/lemmasim/my-notebook.raw --size-mib 256
./scripts/lemmasim run --disk build/lemmasim/my-notebook.raw --mode student
```

The resizable native QEMU window fits the portrait controller image to its
viewport and displays the controller's visible pixels. Pointer events
enter its pen FIFO. All toolbar, ink, page and document behavior runs in the guest.
The eight guest tools are home/notebook toggle, previous page, next/add page,
undo, redo, erase latest stroke, width and Save. Home closes the current namespace
and opens the other of two notebooks. The text beside the page number shows
SAVED, PENDING, FAILED or READ ONLY. Completed strokes autosave; Save requests a
durable checkpoint. Wait for Saved before closing when you want all pending work.
Large checkpoints keep an owner-bound guest receipt and use short status calls;
Pending remains visible until the replacement root's final flush succeeds.
Startup polls the store's Mounting state before opening a page, with a checked
ten-minute guest deadline. Neither operation extends a kernel reply lease.
A failed mount never triggers automatic formatting. `init` refuses existing
images unless `--force` explicitly requests destruction.

Developer capture, inspection and offline copies use the same machine:

```sh
./scripts/lemmasim run --disk build/lemmasim/my-notebook.raw --mode developer \
  --record build/lemmasim/writing-session
./scripts/lemmasim control --run-directory build/lemmasim/writing-session/run inspect
./scripts/lemmasim replay --session build/lemmasim/writing-session \
  --disk-copy build/lemmasim/replayed.raw
./scripts/lemmasim copy --disk build/lemmasim/my-notebook.raw --to /path/to/backup.raw
./scripts/lemmasim archive --session build/lemmasim/writing-session --to /path/to/evidence.tar.gz
```

After a successful clean full acceptance run, export its selected observations
with `./scripts/lemmasim archive --acceptance build/lemmasim/FULL_RUN --to
/path/to/task004-evidence.tar.gz`. This includes an exact implementation Git
bundle, identified guest images/build records, captured input and QEMU replay,
controller pixels, committed ink bytes, and baseline/workload/native stable
images. The export refuses missing or failed evidence. Session archives preserve
their captured initial medium; an external working image needs the separate
offline `copy` command. Neither archive bundles a native runtime installer or
provides permanent remote storage.

Controls `pause`, `resume`, `reset` and `power-cut` are outside guest authority;
mutating controls invalidate an unmodified replay claim. QEMU pause/reset may
drain and flush block nodes; use `power-cut` for a modeled loss of volatile
writes. Replay uses a fresh
media copy and refuses changed identities. Laboratory faults act on real block
write/flush ordinals (`--mode laboratory --fault cut-before-flush=N`, also
`cut-after-flush`, `tear-flush`, `fail-write`, `fail-flush`). Their exact notebook
crash acceptance is pending. Successful host flush assumes the local filesystem
and device honor QEMU's fsync. A process power cut loses the hardware filter's
volatile RAM writes; ordinary QEMU close is a separate clean host operation.

Use `--headless` when no native display is available and `--geometry 1404x1872`
for the second instance. Default geometry is1650×2200. The same guest queries
runtime geometry; neither instance is a procurement or physical-conformance
claim. Mouse pressure is synthetic; no physical pressure-aware tablet or visible
manual workflow has been tested here. The bounded guest supports64pages per
notebook and512chunk/edit entries per page, with explicit resource errors. The
required16-page/100000-sample workload and complete candidate regressions remain
unrun at this checkpoint. Actions artifacts expire after14days; the offline
archive is the explicit owner-controlled retention path.

## GitHub and Codex

The repository is **`srkftw/lemma`**, private, with default branch **`main`**.
Task 001 [PR #1](https://github.com/srkftw/lemma/pull/1) and Task 002
[PR #2](https://github.com/srkftw/lemma/pull/2) were merged by explicit owner
authorization. The reviewed Task002 integration is
`ff4045a79a6fda45f9cd8198587357846530a806`; subsequent main commit
`a899ccbb3c880e44ab529b65131cf6ea49a198d2` adds the LemmaSim architecture
documents from [PR #4](https://github.com/srkftw/lemma/pull/4). Both task
branches remain available. Check GitHub for live revision and merge status.

Current notebook work uses `task/004-lemmasim-durable-ink` and draft
[PR #5](https://github.com/srkftw/lemma/pull/5). Its assignment is
[Task004](codex/prompts/004-lemmasim-durable-ink.md); resume from its checkpoint
above. This task has a draft/review boundary and no merge authorization.
The Task003 A–K implementation is
`14cc79be8914a349b729347cc05091aba6ac7ca7`, subsequently merged through
[PR #3](https://github.com/srkftw/lemma/pull/3). Task004 started from reviewed
main `504f6e462e502d93192ba689d16d8552ca1e68b5`. See the separately identified
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

The new hardware/notebook observation matrix is maintained as:

```sh
nix develop --no-write-lock-file --command ./scripts/check-lemmasim.sh --clean
```

It uses the separately prepared LemmaSim QEMU, requires clean committed source,
builds fresh identified guest images and keeps every result under a new ignored
output path. `--lane writing` is a scoped development check. Required inherited
CI, client-isolation and source-negative qualification remain separate until
the Task004 report records their actual candidate results. The dependency map is
[recorded here](docs/plan/004-dependencies.md).
