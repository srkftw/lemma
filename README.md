<!--
# Lemma

## LemmaSim: permanent virtual Lemma One

**LemmaSim is a first-class, distributable embodiment of Lemma One**, not a temporary emulator. Both virtual and physical embodiments target one versioned [canonical machine contract](LEMMA_MACHINE_CONTRACT.md), sharing the freestanding Lean-authored RV64 operating system, mathematical capabilities, and user-visible device semantics. The ambition is complete functional equivalence, **not an already established physical-hardware result**. Physical properties such as thermals and writing-surface feel remain separate. Student, Developer, and Laboratory are modes of one LemmaSim.

Read the [cross-cutting LemmaSim plan](docs/plan/LEMMASIM.md) and the [simulation implementation](sim/README.md) / [conformance checks](conformance/README.md). The existing `LemmaVM` QEMU boot-slice contract and G1-G7 implementation evidence remain unchanged and do not certify the complete virtual machine.


A pen-first mathematics computer, constructed from a freestanding Lean 4 foundation
on RISC-V. The historical boot reference is **LemmaVM**; the permanent virtual embodiment is **LemmaSim**; the operating system is **LemmaOS**;
the physical device is **Lemma One**.

**Current implementation: native durable ink notebook.** Task004 provides a
bounded offline notebook through the real Lean-authored RV64 guest. Its
[evidence report](docs/evidence/004-lemmasim-durable-ink.md) separates the tested
implementation from the report head and records exact acceptance/retention
identities. The finished mathematics machine and physical conformance remain
incomplete.

**Historical Task003 milestone: supervisor kernel and isolated volatile service.**
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

## Task004 native durable notebook

The new `task/004-lemmasim-durable-ink` branch contains a genuine compiled RV64
notebook, isolated record service, pen/paper hardware models and a volatile/durable
block backend. The [evidence report](docs/evidence/004-lemmasim-durable-ink.md)
records the bounded notebook qualification and its precise limitations. See the
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
The nine guest tools are home/notebook toggle, previous page, next/add page,
undo, redo, erase latest stroke, width, Save and Compact. Home closes the current
namespace and opens the other of two notebooks. The text beside the page number shows
SAVED, PENDING, FAILED or READ ONLY. Completed strokes autosave. After those
publications drain, Save checks the store's durable sequence with a short status
request; it does not copy the live record set. Wait for Saved before closing.
Compact explicitly reclaims append space by copying the latest records and
durably switching roots. It keeps an owner-bound guest receipt and uses short
status calls; Pending remains visible until the replacement root's final flush
succeeds. Compact before append space fills; after a Full error, restart to
recover acknowledged writing, then request Compact. It retains original ink,
including hidden strokes, and can take substantially longer than Save. It cannot
reclaim those immutable keys or bypass page/edit limits.
Startup polls the store's Mounting state before opening a page, with a checked
ten-minute guest deadline. Neither operation extends a kernel reply lease.
A failed mount never triggers automatic formatting. `init` refuses existing
images unless `--force` explicitly requests destruction.

Developer capture, inspection and offline copies use the same machine:

`run --record` blocks while the machine is running. Run `control ... inspect`
from a second terminal while the window and QMP connection remain live. After
Saved, close the machine and wait for the run command to exit and reap QEMU;
then perform replay, offline copy and archive in the first terminal.

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
`cut-after-flush`, `tear-flush`, `fail-write`, `fail-flush`). The evidence report identifies the admitted cutpoints and actual cold-recovery
observations; physical power-loss behavior remains unverified. Successful host flush assumes the local filesystem
and device honor QEMU's fsync. A process power cut loses the hardware filter's
volatile RAM writes; ordinary QEMU close is a separate clean host operation.

Use `--headless` when no native display is available and `--geometry 1404x1872`
for the second instance. Default geometry is1650×2200. The same guest queries
runtime geometry; neither instance is a procurement or physical-conformance
claim. Mouse pressure is synthetic; automated GTK input was exercised in a
dedicated pinned Xvfb environment. Physical pressure-aware tablet input and
manual visible interaction are NOT_RUN. A stationary held mouse without samples
reaches the one-synthetic-second contact watchdog: its unsaved tail is cancelled,
and lift/new contact resumes writing. The bounded guest has two fixed notebook
namespaces, 64 pages each, 512 immutable chunks and 512 edits per page, and
1024 latest store keys across their shared document-service authority domain.
Compact reclaims append space but does not remove those limits. The evidence
report records the 16-page/100,000-sample workload, actual latency and sampled
owned-memory scope. Actions artifacts expire after14days; verified offline
export is the explicit owner-controlled retention path.

## GitHub and Codex

The repository is **`srkftw/lemma`**, with default branch **`main`**.
Task 001 [PR #1](https://github.com/srkftw/lemma/pull/1) and Task 002
[PR #2](https://github.com/srkftw/lemma/pull/2) were merged by explicit owner
authorization. The reviewed Task002 integration is
`ff4045a79a6fda45f9cd8198587357846530a806`; subsequent main commit
`a899ccbb3c880e44ab529b65131cf6ea49a198d2` adds the LemmaSim architecture
documents from [PR #4](https://github.com/srkftw/lemma/pull/4). Both task
branches remain available. Check GitHub for live revision and merge status.

The native notebook from Task 004 is merged in
[PR #5](https://github.com/srkftw/lemma/pull/5). Its assignment is
[Task004](codex/prompts/004-lemmasim-durable-ink.md); resume from its checkpoint
above. Task 005 now uses `task/005-open-silicon-bringup` for the open RV64
RTL development backend, under the separate
[silicon binding](docs/contracts/005-silicon-dev-0.1.0.md) and
[checkpoint](docs/plan/005-session-state.md). The original Task 005 assignment
required a draft PR; the owner subsequently authorized finishing and a guarded
merge after verification and applicable CI pass. The native QEMU notebook
remains the default backend. Task 005 merged through
[PR #7](https://github.com/srkftw/lemma/pull/7); the subsequent specification
merge retained the same source tree. Task 006 starts from current main
`abd9920d54df04ce52da9386170e99012c39bdfb` on
`task/006-whole-machine-lemmasim`, with draft publication only.
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

## Silicon development backend

Task 005 adds `lemma-silicon-dev/0.1.0` to the existing launcher. The native QEMU
notebook remains the default. RTL supports Developer mode and the explicit
`service`, `initializer`, `devices` and `notebook` workloads; unsupported modes
fail without a backend fallback. Its RAM, framebuffer storage, raw medium and
visible panel are external simulation models. The reset path, processor,
translation, timer, interconnect and device controllers execute in RTL.

Prepare the selected workload once; ordinary runs reuse identified artifacts:

```sh
./scripts/lemmasim build --backend rtl --profile lemma-silicon-dev/0.1.0 --workload service
./scripts/lemmasim run --backend rtl --mode developer --workload service \
  --cycles 400000000 --observer-cycle 300000000 --timeout 3600 \
  --record build/silicon/developer-service-new --trace-limit 10000
```

The finite observer stop only bounds a Developer observation; functional
acceptance separately checks actual guest responses. UART, trace, actual
hardware counts, reset/input identity and logs are retained in the capture.
The isolated-service acceptance uses `scripts/check_kernel_buffer.py --backend rtl`
and its existing independent byte/frame oracles. Device bus checks are:

```sh
python3 scripts/check_silicon.py --lane devices --work-dir build/silicon/device-check-new --timeout 600 --jobs 2
```

Notebook/initializer/device runs require an explicit 256 MiB raw `--disk`;
`--events` supplies cycle-tagged raw pen/UART/reset input and `--fail-flush`
selects a declared external-medium barrier failure. A blank medium is formatted
only by the compiled Lean initializer. After the checkpoint's medium initialization
and raw-input preparation, the ordinary notebook invocation is:

```sh
./scripts/lemmasim build --backend rtl --workload notebook --opt-level O2
./scripts/lemmasim run --backend rtl --mode developer --workload notebook \
  --disk build/silicon/notebook-publication-new.raw \
  --events build/silicon/notebook-input-publication-new/events.txt \
  --record build/silicon/notebook-developer-new --cycles 2000000000 \
  --observer-cycle 1400000000 --timeout 7200 --trace-limit 1000 --block-trace
```

Use new capture/result paths: retained failures are never overwritten. Replay
requires `--backend rtl --session <capture> --disk-copy <new-medium-copy>` and
an explicit session timeout; it re-executes initial bytes and input before
comparing actual outputs. A completed capture is required. Current observations
include genuine Lean M/S/U execution, isolated service/IPC/fault containment,
guest device access and a pressure stroke/brush-width edit/explicit Save.
The current registered paper controller has closed A/B/C and literal protocol
checks, plus a complete write/edit/Save/cold workflow with exact recovered
records and full controller pixels. Failed-FLUSH passed without a false Saved
acknowledgement; a fresh cold hart recovered the acknowledged edited document
and full frame, with failed new work absent. Exact RTL replay passed by
regenerating all six captured outputs and the medium.
Each fresh hardware run retains its source/observer identities and validated
historical guest ELF reuse; earlier failures and results remain separate.

Bounded SoC synthesis reports 13.423078 mm² of mapped standard-cell area,
including 4 KiB register RAM which runs the scalar corpus. The notebook uses
external simulation RAM. Paper live global-route estimates meet 100 MHz
setup/hold at the declared TT corner, with zero reported electrical violations;
detailed routing timed out incomplete. A full-FIFO pen placement/CTS attempt
aborted in OpenROAD setup repair. SG13G2 enclosure-rule coverage requires
validation; its contribution to the route timeout is unmeasured. Controller
process DRC/LVS and extracted timing remain NOT_RUN. Exact commands, identities
and scoped results are in [the Task 005 checkpoint](docs/plan/005-session-state.md).
RTL is slower than the native notebook and does not claim physical conformance
or a physical nonvolatile boot solution. Open synthesis/layout recipes are in
[tooling/silicon](tooling/silicon/README.md).

## Task006 persistent machine sessions

The `lemma-silicon-dev/0.3.0` successor retains the canonical 1650×2200 notebook
binding and adds guest-controlled digital suspend, wake and reset-cause reporting
on matched QEMU and RTL controllers. Historical 0.1/0.2 profiles remain available.
Canonical QEMU writing, suspend/wake, warm reset, Save and new cold recovery
have separate observed workflows. The archived Bytes/Bulk canonical RTL guest
has separately observed cold Ready, ink/edit/navigation/Save, independent cold
recovery and unsuccessful-save recovery with complete pixel checks; see the
[native RTL receipt](docs/evidence/006-canonical-bytes-bulk-workflow.json).
The binding has
128 MiB external simulation RAM, a checked 32 MiB frame pool,
backend-specific checkpoints, an isolated durable backing for restored forks,
and a synthetic digital panel sequencer. The original profiles remain supported.
This is a larger running subset, not a completed Lemma One or physical signoff.
See the [session contract](docs/contracts/006-machine-session.md),
[checkpoint](docs/plan/006-session-state.md), and
[observed results](docs/evidence/006-whole-machine-lemmasim.md).

Prepare pinned QEMU and genuinely compiled guest images once:

```sh
./scripts/lemmasim build --backend qemu --profile lemma-silicon-dev/0.3.0 --workload initializer
./scripts/lemmasim build --backend qemu --profile lemma-silicon-dev/0.3.0 --workload notebook
mkdir -p "$HOME/.local/share/lemma"
./scripts/lemmasim init --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --disk "$HOME/.local/share/lemma/notebook.raw" --session-dir build/user-initialize
nix-shell tooling/lemmasim/session.nix --run \
  './scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 --mode student --disk "$HOME/.local/share/lemma/notebook.raw" --session-dir build/user-session --quantum 1000000'
```

Initialization exclusively creates a new medium; only the real Lean initializer
formats it. Preserve that raw file outside `build/`. Session directories and
checkpoint destinations must be new. Later launches reuse the existing medium
and prepared images without formatting or rebuilding. Preparation rejects stale
source/artifact identities. The native host presentation environment is pinned
for Linux x86-64. A local RTL/Wasm development bundle is available below;
installers and complete browser product acceptance remain unfinished.

Write with the pointer in the notebook canvas. The guest toolbar supplies Home,
previous/next page, Undo, Redo, Erase, brush Width, explicit Save and Compact.
`Saved` follows the guest store's actual durable barrier; provisional work and
failed saves have distinct guest-produced labels. Mouse pressure is explicitly
synthetic. `--tablet /dev/input/eventN` transports an accessible Linux evdev
device's reported capabilities and samples; physical tablet testing is not yet
qualified. The window's Power button transports its pressed/released levels;
the Lean kernel decides whether to suspend, reject a busy operation or resume
retained tasks. A held pen crosses an explicit loss/resynchronization boundary.
The window reports RUN, SUSPENDED and controller errors. Pause/Resume controls
stop and start simulation. Warm reset and cold cycle have separate retention
rules. This cooperative policy leaves timer/controller clocks running; electrical
sequencing, watchdog and brownout recovery remain unfinished.

Use the same live session from another terminal:

```sh
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"pause"}'
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"inspect"}'
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"clock"}'
./scripts/lemmasim snapshot --session-dir build/user-session --to build/user-checkpoint
./scripts/lemmasim restore --session-dir build/user-session --from build/user-checkpoint
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"resume"}'
```

The same physical-style button is available from a terminal. While paused, run
between press and release so they occur at distinct virtual boundaries:

```sh
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"pause"}'
./scripts/lemmasim button --session-dir build/user-session --level 1
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"run","cycles":1000000}'
./scripts/lemmasim button --session-dir build/user-session --level 0
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"run","cycles":1000000}'
```

Repeat the sequence to wake. `button --cycle N` schedules an explicit future
controller cycle. Both levels at one cycle are sampled together, producing no
rising edge. A raw press during display/storage work can return guest BUSY.
Inspect `devices.power`, queues and guest UART to retain the actual decision.
Warm reset uses `session-control --request '{"action":"warm-reset"}'`; a new
cold process uses `'{"action":"cold-cycle"}'`. Both retain the permitted durable
backing. Warm reset clears the pen FIFO and its timestamp domain; cooperative
suspend instead follows the explicit loss/resynchronization protocol.

Restore creates a private durable fork and disconnects live input adapters.
It neither overwrites the original notebook nor flushes pending work. To start
a separate paused fork, omit `--disk`:

```sh
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --headless --paused --restore build/user-checkpoint --session-dir build/user-fork
```

For an exact recorded suffix, pause at its final boundary, copy the closed
`external.jsonl` outside the session, and record `machine.virtual_ns` from
inspection. Then restore/replay into the isolated fork:

```sh
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"pause"}'
./scripts/lemmasim session-control --session-dir build/user-session --request '{"action":"inspect"}'
cp build/user-session/external.jsonl build/user-external.jsonl
./scripts/lemmasim session-replay --session-dir build/user-fork \
  --snapshot build/user-checkpoint --capture build/user-external.jsonl --until-ns 106368000276
./scripts/lemmasim session-control --session-dir build/user-fork --request '{"action":"destroy"}'
```

The number is an example; use the actual captured endpoint. QEMU's exact
nanosecond phase matters because its instruction clock is not an integer number
of 100 MHz controller clocks. RTL replay uses `--until-cycle` instead. There is
no exact QEMU/RTL microstate migration. `--trace-limit N` selects bounded detailed
tracing; ordinary sessions avoid it. Laboratory sessions may select an actual
failed barrier with `--fail-flush 1`; inspection retains failed operations.
RTL model serialization includes its caches/TLBs. QEMU migration flushes its
software TLB; cached Sv39 mappings and TCG translation blocks are not serialized.
The tested fast guest suffixes continue identically, but arbitrary cached-state
continuation remains unfinished. See the source audit in the checkpoint/evidence.

For RTL development, prepare the initializer and notebook with `build --backend rtl`
and the same profile, then select `--backend rtl` on the lifecycle commands. The
processor runs every hardware cycle; report its observed speed without a
real-time claim. `--memory-latency N` adds admitted external-memory backpressure.
The larger RTL notebook cold path remains a performance blocker; the original
Task005 notebook evidence retains its different binding and execution identity.
Both backends still use explicitly named ELF-preload development boot. USB
enumeration, digital Wi-Fi/Bluetooth, production power/recovery and a managed
mathematical runtime remain unfinished in the
[capability inventory](docs/plan/LEMMASIM.md). The backing peer and local browser
embodiment have their own commands and narrower qualification scopes.

### Local RTL browser development bundle

Prepare both genuinely compiled guest workloads, then build the existing RTL
`Machine` for a local Wasm worker. Each output directory must be new:

```sh
./scripts/lemmasim build --backend rtl --profile lemma-silicon-dev/0.3.0 --workload initializer
./scripts/lemmasim build --backend rtl --profile lemma-silicon-dev/0.3.0 --workload notebook
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --wasm-build build/wasm/local-new --output-dir build/browser/local-new
./scripts/lemmasim browser-serve --bundle build/browser/local-new --port 8765
```

Open [the local bundle](http://127.0.0.1:8765). It needs a browser supporting
worker OPFS synchronous access. The loopback server validates packaged
guest/Wasm identities and serves only inventoried bytes; changed files are
rejected during serving. Immutable bundles execute independently of newer
checkout edits. This admission does not establish notebook Ready or acceptance.
Create a new named medium through the actual
Lean initializer, or import an existing256MiB raw medium under a new name.
Open performs cold guest boot; controller output supplies the entire display.
Select **Open paused** before opening to load the same machine at cycle0 without
executing a boot prefix, then inspect it or restore a private checkpoint. The
**Display scale** control provides fit,100%,150% and200% presentation with a
scrollable viewport. It keeps the canonical controller plane and raw pen
coordinates; changing scale cancels any held contact before the transform changes.
WebGPU presents those pixels, with a same-byte2D fallback. Mouse pressure is
synthetic. The Laboratory raw-input control uses the native pen/button/UART
event contract; `now` selects the current exact virtual cycle/device time.
The Laboratory raw batch control admits up to1024 bounded native rows. Admission
executes no guest clock. A rejected row retains the accepted prefix, reports its
exact count and pauses the machine; exporting raw events preserves those rows.

Pause, checkpoint export, private-fork restore, backing export, cold/warm reset
and recorded-suffix replay operate on the same machine. Restore cannot resume
until its isolated origin backing has been copied, flushed and byte-validated.
Browser `flush` qualifies the origin storage barrier; eviction and physical
power-loss guarantees remain unqualified. Initialization/import refuse existing
names. Export includes observed unacknowledged backing changes; it is not an
implicit Save. No beforeunload save is promised.

The compiler is the native pinned build helper. This is explicit development
preload, without a production boot/update path or an in-browser Lean compiler.
Local bundle creation does not select a redistribution license. See the
[browser/state contract](docs/contracts/006-browser-machine-v1.md) and the
checkpoint for actual Ready, persistence and native/Wasm observation status;
building Wasm alone does not establish a usable complete browser machine.

An existing fully validated immutable native bundle can supply the unchanged
guest artifacts when rebuilding the current Wasm machine. This avoids falsely
claiming another target compilation:

```sh
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --wasm-build build/wasm/current-new --output-dir build/browser/current-new \
  --guest-bundle build/native/my-bundle
```

Add `--reuse-wasm` only for a previously built machine whose exact current
consumed sources/tools and outputs still validate.

## License and private material

No project license has been selected. Do not add a license, publish the repository,
or change visibility without the owner's decision. Preserve licenses and notices
for any third-party code introduced later. Do not commit supplier correspondence,
NDA documentation, panel waveforms, credentials, textbook files or personal learner data.

Task 005's newly authored RTL and narrowly scoped host adapter carry explicit
per-file Apache-2.0 notices for the authorized reusable open hardware milestone.
The newly authored silicon build and observation scripts use the same per-file
notices; the license text and scope are in [sim/rtl/NOTICE.md](sim/rtl/NOTICE.md).
Those notices do not relicense existing Lean sources or the repository as a
whole. The original project's license gap remains separate from functional
execution; upstream CVW and inspected PDK inputs retain their own licenses.

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

A local immutable native development bundle retains the exact audited guest and
backend inputs while implementation continues. It uses ELF preload and requires
the pinned external Linux/Nix host libraries listed in its manifest:

```sh
./scripts/lemmasim native-bundle-build --output-dir build/native/my-bundle
./scripts/lemmasim init --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/my-bundle --disk build/native/my-medium.raw
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/my-bundle --disk build/native/my-medium.raw \
  --session-dir build/native/my-session
```

Use `--backend rtl` for exact RTL execution of the same prepared guest.
[The native bundle contract](docs/contracts/006-native-bundle-v1.md) records
validation, host dependencies and unresolved redistribution limits.

To retain a new audited notebook and matching initializer on an existing
validated backend, the v2 packer keeps each consumed source revision explicitly:

```sh
./scripts/lemmasim native-bundle-build --base-bundle build/native/my-bundle \
  --notebook-build build/kernel/current-notebook \
  --initializer-build build/kernel/current-initializer \
  --output-dir build/native/new-bundle
```

The [v2 contract](docs/contracts/006-native-bundle-v2.md) explains exact archive
validation. This produces an immutable launch path for later independent cold
recovery; packaging alone does not qualify a guest workflow.

For an explicitly new, current-source audited development guest on the
unchanged bundled backend, use a new session directory:

```sh
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/my-bundle --guest-build build/kernel/current-notebook \
  --disk build/native/my-medium.raw --session-dir build/native/current-session
```

The launcher independently generates a capacity audit and checks current guest
provenance before execution. This option supplies no production update policy.
The exact Arithmetic OOM/fault/stall guest configurations additionally require
`--mode laboratory`; they cannot launch in Student or Developer mode.

The separately selected Bytes/Surface2 deployment keeps canonical hardware0.3
and the actual8192-frame pool. It runs ordinary bounded Lean ByteArray code in
the isolated arithmetic service, preserves old document evidence, and batches
seven owned display tiles after complete metadata preflight. Its current
source-bound build/launch paths are:

```sh
nix develop --no-write-lock-file --command python3 scripts/build_kernel.py \
  --stage supervisor --configuration lemmasim-silicon-bytes-bulk-notebook \
  --output-dir build/kernel/bytes-notebook-new --opt-level O2 --timeout 300
nix develop --no-write-lock-file --command python3 scripts/audit_kernel.py \
  build/kernel/bytes-notebook-new --timeout 300
nix develop --no-write-lock-file --command python3 scripts/build_kernel.py \
  --stage supervisor --configuration lemmasim-silicon-bytes-bulk-initialize \
  --output-dir build/kernel/bytes-initialize-new --opt-level O2 --timeout 300
nix develop --no-write-lock-file --command python3 scripts/audit_kernel.py \
  build/kernel/bytes-initialize-new --timeout 300
./scripts/lemmasim native-bundle-build --base-bundle build/native/task006-managed-v3-a1 \
  --notebook-build build/kernel/bytes-notebook-new \
  --initializer-build build/kernel/bytes-initialize-new \
  --output-dir build/native/bytes-new
./scripts/lemmasim init --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/bytes-new --disk build/native/bytes-user-new.raw
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/bytes-new --disk build/native/bytes-user-new.raw \
  --session-dir build/native/bytes-user-session
```

These local commands require the recorded immutable base bundle and pinned
host dependencies; a missing archive fails. Use new output/medium/session names.
COURSE opens the original offline exact-arithmetic sequence; typed edits,
checking, hints, review overrides and Save remain guest operations. A successful
check is restricted arithmetic evidence, not the Lean proof-kernel gate.
The [connected receipt](docs/evidence/006-managed-bytes-integration.json)
records actual RV64 course, migration, real heap OOM and cold-recovery results.
QEMU remains an instruction-clock functional path; RTL timing qualification is
separate. `--backend rtl` selects the same compiled guest on the exact RTL core.

The immutable `build/native/task006-bytes-bulk-a1` guest completed the
[canonical native RTL workflow](docs/evidence/006-canonical-bytes-bulk-workflow.json).
Cold Ready was independently observed at609M cycles/2872.596s of runtime calls.
Actual raw pen, Undo, Redo, page2/page1 navigation and explicit Save preserved
all original samples and matched every controller pixel. Two new cold CPUs
each recovered at657M cycles, including after a real FLUSH failure and a Save
attempt that remained Failed. Full1650×2200 Gray4,128MiB external RAM and8192
owned frames/32MiB were retained. Original observer/startup FAILs remain intact;
this archived image excludes the later Array and Surface row-carry changes.

The actual prepared Bytes static bundle uses the unchanged, fully validated
Wasm core and explicit archived consumed inputs:

```sh
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --reuse-wasm --wasm-build build/wasm/task006-managed-canonical-runtime-a1 \
  --guest-bundle build/native/task006-bytes-bulk-a1 \
  --wasm-input-bundle build/native/task006-sums-a1 \
  --output-dir build/browser/bytes-new
./scripts/lemmasim browser-serve --bundle build/browser/bytes-new --port 8769
```

In newly prepared bundles, Run bounded accepts an exact cycle budget and an
optional1–7200-second host limit. Host-limit pauses retain the executed prefix
and pending machine work; they do not count as successful Ready observations.
The worker checks between calls of at most50000 cycles, so a synchronous call
can finish after the host deadline. The bound carries across initializer launch
without replenishment. Resume starts ordinary continuous execution.

The [actual Byte/Bulk browser cold and native comparison](docs/evidence/006-canonical-native-browser-cold.json)
passed real durable reopen at631.55M browser cycles under its original2B/7200s
bounds. An independent native cold from the same opaque bytes then matched
every wrapper/generatedRTL byte, all3.63M pixels and all durable bytes at the
declared657M boundary. Original browser writing timing FAIL remains retained;
course/Product acceptance and general parity remain separate work in the
[current checkpoint](docs/plan/006-session-state.md).
An additional [matched raw-event suffix](docs/evidence/006-canonical-native-browser-suffix.json)
passed exact658000003 state/output equality on private own-backend restores,
with all three hardware-accepted samples and the first guest raw copy observed
under the declared600s/backend bound. New Save/display completion is separate.
Product ROM/update and companion commands are documented in
[the product boot contract](docs/contracts/006-product-boot-v1.md) and
[the USB notebook contract](docs/contracts/006-usb-bulk-notebook-v1.md).
Current product installation is owner-local CRC integrity, with authenticated
production identity and anti-rollback still unfinished.

The additive bounded ordinary Array deployment has its own [language/runtime
contract](docs/contracts/MANAGED_ARRAY_V1.md) and [actual RV64 connected receipt](docs/evidence/006-managed-array-integration.json).
The same COURSE workflow runs with independently linked User5 arithmetic,
full UInt64 boxes, COW arrays and actual graph reclamation. General managed
Lean and the proof kernel remain unfinished. The retained local bundle launches
with the normal interface (use a new private copy of your existing medium):

```sh
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-array-bulk-a1 --disk build/native/array-user.raw \
  --session-dir build/native/array-user-session
nix develop --no-write-lock-file --command python3 scripts/check_math_session.py \
  --disk build/silicon/task006-loader-cold-a1/fast-medium.raw \
  --native-bundle build/native/task006-array-bulk-a1 --require-array-identity \
  --work-dir build/array-course-new --boot-seconds 60 --action-seconds 30 --deadline 1200
```

To rebuild, use the ByteArray build/audit/pack commands above with exact
configurations `lemmasim-silicon-array-bulk-notebook` and
`lemmasim-silicon-array-bulk-initialize`; all replacement images are freshly
audited before packing. An immutable base backend is reused only after its
complete consumed sources and dependencies validate. QEMU has instruction-clock
functional scope. Actual RTL and Wasm Array observations remain separate.

Existing acknowledged ByteArray course media can continue under Array
arithmetic. [The actual migration/cold receipt](docs/evidence/006-array-document-migration.json)
preserves earlier checking identities and assistance; new checks carry their
own Array identity. To reproduce against a new private output directory:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_array_document_migration.py \
  --disk build/task006-bytes-math-a1/closed-course.raw \
  --native-bundle build/native/task006-array-bulk-a1 \
  --work-dir build/array-doc5-migration-new --boot-seconds 60 --action-seconds 30 --deadline 1200
```

The checker copies the supplied opaque medium; only the guest migrates and
publishes its document. This command starts from Doc5 without a snapshot.

### Bounded managed String development deployment

The [User6/Doc7 receipt](docs/evidence/006-managed-string-integration.json)
qualifies the exact guest mathematics/course/edit/assistance/Save/newcold and
OOM containment paths. The [mixed migration](docs/evidence/006-string-document-migration.json)
keeps prior ByteArray/Array evidence and appends a real String-service result.
Use the prepared immutable artifacts without rebuilding the machine:

```sh
./scripts/lemmasim init --backend qemu \
  --native-bundle build/native/task006-string-bulk-a1 \
  --disk build/string-notebook-NEW.raw --session-dir build/string-init-NEW --timeout 120
./scripts/lemmasim session --backend qemu \
  --native-bundle build/native/task006-string-bulk-a1 \
  --disk build/string-notebook-NEW.raw --session-dir build/string-session-NEW
./scripts/lemmasim browser-serve \
  --bundle build/browser/task006-string-bulk-host-limit-a1 --port 8775
```

Open the local static bundle at`http://127.0.0.1:8775`. It packages the same
RV64 String guest for the existing RTL/Wasm worker; actual browser String
Ready/course/durability remains unqualified. The compiler is the native pinned
Lean/LLVM helper. Local dependency/notice and redistribution limitations remain.
Both native commands use explicit development ELF preload, not product ROM boot.

For actual existing mixed Doc6 media, the guest performs migration and checking:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_array_document_migration.py \
  --disk build/task006-array-doc5-migration-a3/cold-course.raw \
  --native-bundle build/native/task006-string-bulk-a1 --destination-runtime string \
  --work-dir build/string-doc6-migration-NEW --boot-seconds 60 --action-seconds 30 --deadline 1200
```

The String subset admits at most40 UTF8 bytes with actual heap allocation,
retained aliases and graph reclamation. The integrated service uses ASCII hex
encodings of complete UInt64 values. General String/runtime/proof-kernel scope
is separate. The [prepared initializer repair](docs/evidence/006-native-bundle-initialization.json)
ensures `--native-bundle` is honored even when `--profile` is omitted.

### Aligned journal checksums and prepared Array deployment

[The checksum qualification](docs/evidence/006-store-checksum-words.json) preserves
Store-v1 bytes, error handling and guest recovery while reducing aligned512-byte
reads from512 byte accesses to64 checked word accesses. Fresh complete guest
builds/audits and real fast-backend course/check/edit/hint/review/ink/Save/newcold/
failed-save passed. Changed canonical RTL actual cold Ready/full pixels now
qualifies890Mcycles/3651.507731seconds, with the retained P5/P6 observer failure
independently corrected. The whole Notebook also contains later shared String
support, so this is not an isolated boot-speed comparison. The prepared public
initializer actually ran.

```sh
./scripts/lemmasim init --backend qemu \
  --native-bundle build/native/task006-array-checksum-words-a1 \
  --disk build/array-checksum-notebook-NEW.raw --session-dir build/array-checksum-init-NEW --timeout 120
./scripts/lemmasim session --backend qemu \
  --native-bundle build/native/task006-array-checksum-words-a1 \
  --disk build/array-checksum-notebook-NEW.raw --session-dir build/array-checksum-session-NEW
nix develop --no-write-lock-file --command python3 scripts/check_store_checksum.py \
  --work-dir build/store-checksum-NEW --timeout 300
```

This is development ELF preload. The same immutable native bundle provides the
exact RTL path with `--backend rtl`. The fast backend keeps its instruction-clock
scope. The corresponding prepared browser artifact is
`build/browser/task006-array-checksum-words-a1`; its changed guest cold/browser
workflow is not yet qualified.

[Independent companion cold recovery](docs/evidence/006-companion-acknowledged-boundary.json)
now passed from an observational acknowledged peer archive: a new USB8 CPU and
separate persistent policy4 peer recovered Saved5, exact bytes and every controller
pixel at680Mcycles/4353.814seconds, without formatting or republishing. The hosted
lost-ACK case also restarts both client and peer and retains one durable effect.
Full original notebook navigation/Save and full USB wire timing remain separate.

### Prepared packed-course notebook

[The packed course renderer](docs/evidence/006-course-word-rendering.json) preserves
raw ink, revisions, exact isolated checking and glyphs. The same30 fast course
interactions use9.557% fewer instruction-clock cycles. Actual course/edit/hint/
acknowledged Save, independent cold/full pixels and unsuccessful Save qualify the
prepared new guest. These commands use immutable audited source/tool/object
archives; normal launch does not consult the changed checkout.

```sh
./scripts/lemmasim init --backend qemu \
  --native-bundle build/native/task006-array-course-words-a1 \
  --disk build/course-word-notebook-NEW.raw --session-dir build/course-word-init-NEW --timeout 120
./scripts/lemmasim session --backend qemu \
  --native-bundle build/native/task006-array-course-words-a1 \
  --disk build/course-word-notebook-NEW.raw --session-dir build/course-word-session-NEW
./scripts/lemmasim browser-serve --bundle build/browser/task006-array-course-words-a1 --port 8780
nix develop --no-write-lock-file --command python3 scripts/check_course_renderer.py \
  --work-dir build/course-word-component-NEW --timeout 300
```

Use COURSE in the guest notebook; edit the rational/polynomial fields, submit,
request the authored bounded hint and Save. Hints are authored local assistance;
the full proof kernel, immutable course packages and permissioned tutor remain
unfinished. Native`--backend rtl` retains the exact digital execution path.
Development ELF preload and QEMU instruction-clock scope remain explicit.
New static guest packaging is qualified; its actual browser cold/workflow is
pending. The earlier Array private browser course now has actual isolated
Unsupported, OPFS Saved and native cold recovery of exported bytes; its original
browser cold deadline FAIL remains. Browser Run bounded can pause after the next
real completed panel scan. A course scan can complete before a pending Save;
wait for the guest's Saved footer and durable receipt.

To pack both already audited normal roles after sources advance:

```sh
./scripts/lemmasim native-bundle-build --profile lemma-silicon-dev/0.3.0 \
  --base-bundle build/native/task006-array-bulk-a1 \
  --notebook-build build/kernel/task006-array-course-words-a2 \
  --initializer-build build/kernel/task006-array-course-words-initialize-a1 \
  --guest-source-root build/task006-array-course-word-source-archive-a1 \
  --output-dir build/native/course-word-NEW
```

The complete original inventory, every source/artifact and pinned host-tool
realization must validate. No archived source fallback is implicit. Local bundle
notices retain unresolved redistribution and external Nix host dependencies.
[Companion final Saved11](docs/evidence/006-usb8-final-saved11.json) also cold-recovers
all actual edited/navigated bytes and full pixels on a new CPU/restarted persistent
peer, without republishing. Full USB wire timing/PHY and unsuccessful final Save
remain separate from this qualified transaction/recovery path.


### Original RTL source bundle with optional Wasm host optimization

The optional `simd-lto` preset compiles the same circuitry with LLVM LTO and
WebAssembly SIMD. It requires browser SIMD support. The scalar preset remains
the default. Guest work, virtual cycles, controller ordering and persistence
barriers keep their existing semantics.

The following build/pack commands executed with the complete original239-input
source closure and the genuine packed-course guest. Use fresh output paths when
running them again:

```sh
python3 scripts/silicon_wasm.py --profile lemma-silicon-dev/0.3.0 \
  --source-bundle build/browser/task006-array-panel-stop-a1 \
  --host-optimization simd-lto --output-dir build/wasm/simd-NEW
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --wasm-build build/wasm/simd-NEW --reuse-wasm \
  --wasm-input-bundle build/browser/task006-array-panel-stop-a1 \
  --guest-bundle build/native/task006-array-course-words-a1 \
  --output-dir build/browser/simd-NEW
./scripts/lemmasim browser-serve \
  --bundle build/browser/task006-course-word-simd-lto-a2 --port 8781
```

`browser-build` also accepts `--wasm-source-bundle` and `--host-optimization`
for a fresh combined build. Source admission rejects missing, corrupt or mixed
original inputs; the host header is regenerated by the archived original binding
policy and checked against its original digest. Importing that policy leaves the
source archive read-only.

[The exact comparison](docs/evidence/006-browser-simd-lto.json) observes the same
10M real guest cycles at71.381388s scalar versus58.029916s SIMD/LTO on a shared
host. All authoritative checkpoint bytes match at9/32/1M/10M cycles; separately
checked implementation metadata differs. This is an18.7% host-time reduction
for that workload, with no guest-cycle reduction. Full changed-guest browser
cold Ready and mathematics/course acceptance are still running separately.

The [repaired browser capture and cold receipt](docs/evidence/006-browser-fixed-cold.json)
now independently reaches actual Ready at878.55M clocks/5332.565worker seconds,
with all250 recorded reads, unchanged acknowledged bytes and every expected
controller pixel. Its same cold machine opens the course, edits to5/6 and
receives isolated guest Verified atrevision22 followed by Saved41/barrier298.
The same cold machine subsequently acknowledges hint/edit/Invalid and
history-cap Indeterminate/manual review through Saved46. A new cycle-zero
browser machine reopens the actual origin data and reaches Ready at952.15M
clocks/4599.933elapsed seconds, with all313 reference-derived READ offsets and
returned bytes, every acknowledged object and all3.63M expected controller
pixels exact. Its reopened course loads all2496 mathematical bytes through
owned Sv39 pages and presents the saved resource/manual-review labels.
The original475M close and separate40M diagnostic still fail full closed
display; cold recovery remains a distinct result. This is the built-in reference
sequence and restricted exact checker; installed-course frontends and the full
proof kernel remain unfinished.

The current prepared browser controls use Student mode by default. Select
Developer or Laboratory before Open for raw event batches, bounded runs,
inspection, outcome binding and offline replay. Mode is fixed until Close and
enforced by the worker. All modes use the same guest ownership and checker;
these operator tools do not grant teacher or tutor authority. Student retains
writing, power, reset, opaque backup import/export and private checkpoint restore.
Choose100%/150%/200% display scale and scroll the notebook to read at full size.
Open paused prepares the machine without executing a cold prefix.

```sh
./scripts/lemmasim browser-serve --bundle build/browser/task006-session-modes-a1 --port 8785
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --wasm-build build/wasm/task006-capture-u64-simd-a1 --reuse-wasm \
  --wasm-input-bundle build/browser/task006-capture-u64-simd-a1 \
  --guest-bundle build/native/task006-array-table-prefix-a2 \
  --output-dir build/browser/session-modes-NEW
```

[Actual mode observations](docs/evidence/006-browser-readable-paused.json)
retain the complete unchanged Student private course checkpoint and the real
Developer raw-button/one-clock controller boundary. Host fixtures additionally
reject restricted direct messages without changing clocks, pending timers or
backing. New cold guest acceptance and teacher/tutor permissions are distinct.

The canonical portable builder also accepts a complete v2 native source archive.
It validates the original binary, every consumed source, generated binding and
archived profile JSON before compiling the same circuitry and `Machine` for
Wasm. The portable C ABI and build recipe retain their own source identities.
The [fresh native/portable build receipt](docs/evidence/006-canonical-native-wasm-source-v1.json)
records39.17s native and75.58s portable builds. Guest execution and exact applicable
native/Wasm suffixes remain separate checks. The following command actually built
the prepared portable machine; use an unused output directory for another build:

```sh
python3 scripts/silicon_wasm.py --profile lemma-silicon-dev/0.3.0 \
  --native-build build/silicon/task006-canonical-port-a1 \
  --native-source-root build/silicon/task006-canonical-port-a1/consumed-source-root \
  --host-optimization simd-lto --output-dir build/wasm/canonical-NEW
```

`simd-lto` requires WebAssembly SIMD; `scalar` remains available. A missing,
old v1, corrupt or mismatched canonical archive fails before portable compilation.
Neither source admission nor a successful build establishes a cold notebook,
browser compiler, completed USB/radio browser adapter or redistribution rights.

### Opt-in native live USB reattachment

The prepared `build/native/task006-usb-live-recovery-a1` package admits
`lemma-usb-live-recovery/1` on unchanged Clocked13 circuitry. Its original
Clocked notebook and initializer guests retain their separate audits. This
operator control reconnects the raw process after actual EOF; guest failed-save
reconciliation and shadow journal remount still require their new software
successor. It never sets configured, authenticated or Saved state.

The following launches use the independent opaque Saved11 peer/outbox retained
by the qualified public-control scenario. Use an unused session directory and
run the peer in a separate terminal:

```sh
./scripts/lemmasim companion serve \
  --prepared build/usb/host-pending-policy3-a1/companion/prepared.json \
  --directory build/usb/native-recovery-public-command-a2/peer \
  --socket build/usb/native-recovery-public-command-a2/peer.sock
./scripts/lemmasim session --backend rtl --profile lemma-silicon-dev/0.13.0 \
  --workload usb-clocked-bulk-notebook --mode developer --paused \
  --native-bundle build/native/task006-usb-live-recovery-a1 \
  --session-dir build/user-usb-recovery-new \
  --usb-recovery --usb-host-prepared build/usb/host-pending-policy4-a3/prepared.json \
  --usb-peer-directory build/usb/native-recovery-public-command-a2/peer \
  --usb-peer-socket build/usb/native-recovery-public-command-a2/peer.sock \
  --usb-host-state build/usb/native-recovery-public-command-a2/outbox
./scripts/lemmasim session-control --session-dir build/user-usb-recovery-new \
  --request '{"action":"inspect"}'
```

A paused original owner with terminal transport may submit `usb-reconnect` with
exact `epoch`, `next_request` and `binding` values from inspection. The tested
operator request was epoch2/request3 atcycle4000; values are validated before
capture or child creation. Restored forks use recorded outcomes and never
launch a replacement peer. See [the versioned contract](docs/contracts/006-usb-live-recovery-v1.md)
and [actual qualification](docs/evidence/006-usb-live-recovery.json).

The reusable structural check can consume the sealed earlier raw prefix:

```sh
nix-shell tooling/silicon/sim.nix --run 'python3 scripts/check_native_usb_recovery.py --rtl-build build/silicon/task006-usb-live-recovery-a1 --retained-component build/usb/native-recovery-component-a1 --work-dir build/usb/recovery-check-new'
```

Omitting `--retained-component` runs a new bounded raw lifecycle fixture first.
These checks execute the real Machine core and generated circuitry, with no
guest image, notebook, journal recovery or full USB conformance claim.

-->

## Current Task006 package and browser development path

The prepared four-process PackageClosure deployment uses the canonical
1650×2200 Gray4 machine,128MiB simulation RAM and the real32MiB/8192-frame
guest pool. Kernel4 runs isolated Store1, Notebook2, Closure7 arithmetic and
PackageInstaller1 images. Both matched images have passed genuine Lean/LLVM
compilation and full RV64 audits. The new installed-course native/browser
user scenarios are still being executed; compilation is not their acceptance.

Launch the prepared native machine on a privately backed existing medium:

```sh
./scripts/lemmasim session --backend rtl --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-package-layout2-matched-fsize-a5 \
  --workload notebook --mode developer --paused \
  --session-dir build/AN_UNUSED_PACKAGE_SESSION --disk YOUR_PRIVATE_MEDIUM.raw
./scripts/lemmasim session-control --session-dir build/AN_UNUSED_PACKAGE_SESSION \
  --request '{"action":"run","cycles":1000000000}'
./scripts/lemmasim session-control --session-dir build/AN_UNUSED_PACKAGE_SESSION \
  --request '{"action":"inspect"}'
./scripts/lemmasim course-install --session-dir build/AN_UNUSED_PACKAGE_SESSION \
  --package YOUR_ORIGINAL_COURSE.lcp --transaction 1
./scripts/lemmasim session-control --session-dir build/AN_UNUSED_PACKAGE_SESSION \
  --request '{"action":"run","cycles":100000000}'
```

The course command sends raw UART bytes. `RAW_COMMAND_ADMITTED` is not a durable
installation. The guest validates the package and reports its actual `0x4b1`
result after Store publication. Use the existing course authoring path; keep
the original transaction for reconciliation after an uncertain outcome.
Run installation after the machine displays Ready. The1B-clock request is
bounded execution; other media and workloads require their own observed Ready.

The same prepared package supports `--backend qemu` with repaired runtime188e5447.
Its instruction-clock behavior remains distinct from exact RTL timing. To pack
the currently prepared fast runtime with an unchanged, fully audited native
guest pair, use the native build helper below. It validates both roles before
creating output, preserves every old consumed version and records the new
binary, derivation, sources and external Nix libraries. It does not compile or
execute the guest, change the base bundle or touch user media.

```sh
./scripts/lemmasim native-bundle-build --refresh-fast \
  --base-bundle build/native/task006-package-layout2-fsize-a4 \
  --expected-fast-sha256 188e544730915c0c781f22a1937c0b758fd5931a65e995c8eb69df3fad0fd674 \
  --output-dir build/AN_UNUSED_MATCHED_NATIVE_BUNDLE
```

The prepared browser runs the same audited guest on the existing RTL/Wasm core:

```sh
./scripts/lemmasim browser-serve \
  --bundle build/browser/task006-package-layout2-fsize-a6 --port 8793
```

At `http://127.0.0.1:8793/`, select Developer before opening, import an existing
raw medium under a new name, then Open. **Install a course package** sends the
selected `.lcp` through the modeled UART and pauses for ordered admission;
Resume runs the guest installer. The installation label observes only complete
new guest reports. Student mode rejects this owner control. Partial input
requires a cold Close/Open before retry; generic raw capture retains its exact
accepted prefix. Save, checking, course reading and learner events remain guest
operations. Checkpoint restore is a private continuation; Close/Open from
backing bytes performs real cold recovery. OPFS barriers qualify origin storage,
with eviction and physical power-loss guarantees still unresolved.

Exact build/package commands, source/tool identities and retained failures are
in [the current checkpoint](docs/plan/006-session-state.md) and
[browser contract](docs/contracts/006-browser-machine-v1.md). These are local
development bundles with ELF preload and a native build helper. Browser-local
compilation, production authentication, full teacher/tutor permissions,
proof-kernel closure, exact fast timing and physical signoff remain unfinished;
the project-wide redistribution license is unresolved.

The later fully audited descriptor direct-load guest pair is prepared as
`build/native/task006-descriptor-direct-a1` and
`build/browser/task006-descriptor-direct-a1`. The same launch commands above
accept these bundle paths. Their exact reusable packaging commands are:

```sh
./scripts/lemmasim native-bundle-build --profile lemma-silicon-dev/0.3.0 \
  --base-bundle build/native/task006-registry-borrow-a1 \
  --notebook-build build/kernel/task006-descriptor-direct-notebook-a3 \
  --initializer-build build/kernel/task006-descriptor-direct-initializer-a3 \
  --guest-source-root build/courses/task006-descriptor-direct-whole-a3/consumed-source-root \
  --output-dir build/AN_UNUSED_DIRECT_NATIVE_BUNDLE
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --reuse-wasm --wasm-build build/browser/task006-fsize-native-port-a2 \
  --guest-bundle build/AN_UNUSED_DIRECT_NATIVE_BUNDLE \
  --wasm-input-bundle build/AN_UNUSED_DIRECT_NATIVE_BUNDLE \
  --output-dir build/AN_UNUSED_DIRECT_BROWSER_BUNDLE
```

Actual fast guest course/checking/learner/ink interactions and separate cold
recovery are recorded in [the integrated receipt](docs/evidence/006-descriptor-direct-integrated.json).
The original connected-run aggregate limit and Pending/Saved footer mismatch
remain failures. This qualification does not establish a finished browser course
workflow, pipeline timing parity or arbitrary checkpoint continuation.

The audited text-delta guest pair is prepared in
`build/native/task006-package-delta-a1` and
`build/browser/task006-package-delta-a1`. Use these paths with the same native
session/browser-serve commands above. Actual fast course-header views improve
to46–49M instruction-clock units; the original3B connected-case limit still
fails during Close. The original canonical RTL400M course case failed with rendering unfinished. Its source,
limits and full audit results are retained in
[the text-delta receipt](docs/evidence/006-course-text-delta-v1.json).

The newer audited white-word guest is prepared at
`build/native/task006-package-sparse-a1` and
`build/browser/task006-package-sparse-a1`. It retains the same actual pixels
and reduces pure font work. Its fast39-phase course/checking/learner/ink case
reaches acknowledged ink at2.607B instruction-clock units and completes Close
at2.859B. The original3B aggregate fails during the subsequent cold boot.
A separate new-CPU cold case recovers all256MiB and every controller pixel,
then reopens the worked material and exercise without a new checker request.
Use the ordinary native session and local browser commands above with these
bundle paths. This is development preload; the browser course workflow and
fast pipeline timing parity remain open. See
[the white-word receipt](docs/evidence/006-course-white-word-v1.json).

The compact workspace guest saves every3712 decoded bytes using272–1256 stored
bytes through the existing journal/barrier path. Source5's complete fresh ELF
audits and actual saves/cold byte-and-pixel recovery pass, but actual course
reopen fails220 because it used a512-byte sector-copy helper for3712 bytes.
That retained failure is repaired by a dedicated464-word private restore in
source6, alongside a pure packed-row renderer. Complete source/component checks
pass. Corrected software6 now passes actual course/check/learner/ink/Close/newCPUcold/full workspace reopen under the original3B/900s fast functional limit (2.649B/218.995s). Real partial-pwrite/EFBIG Failed→cold→ordinary workspace retry→ink also passes; every acknowledged byte and controller pixel is checked. Source5 bundles at
`build/{native,browser}/task006-workspace-codec-a1` retain this known defect.
Older development images cannot reopen the new envelope. Migration and staging
rules are explicit in
[the envelope contract](docs/contracts/006-course-workspace-envelope-v2.md).


The corrected source6 development bundles are
`build/native/task006-packed-row-a1` and `build/browser/task006-packed-row-a1`.
Use the native session and static browser commands above with these paths.
Canonical RTL qualification is running under the original limits; QEMU
instruction-clock results do not establish pipeline timing. Software4's actual
local browser cold reached Ready at801.15M cycles/4712.470 simulation seconds
with192MiB heap and exact complete controller/backing output; its bounded
course-opening case remains separate. [The corrected guest receipt](docs/evidence/006-course-packed-row-restore.json)
records the full build identities, retained failures and functional limits.

```sh
./scripts/lemmasim native-bundle-build --profile lemma-silicon-dev/0.3.0 \
  --base-bundle build/native/task006-workspace-codec-a1 \
  --notebook-build build/kernel/task006-packed-row-notebook-a1 \
  --initializer-build build/kernel/task006-packed-row-initializer-a1 \
  --guest-source-root build/courses/task006-packed-row-whole-a1/consumed-source-root \
  --output-dir build/AN_UNUSED_PACKED_NATIVE_BUNDLE
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --reuse-wasm --wasm-build build/browser/task006-fsize-native-port-a2 \
  --guest-bundle build/AN_UNUSED_PACKED_NATIVE_BUNDLE \
  --wasm-input-bundle build/AN_UNUSED_PACKED_NATIVE_BUNDLE \
  --output-dir build/AN_UNUSED_PACKED_BROWSER_BUNDLE
```

The installed-package notebook also has an explicitly selected Clocked13
companion recovery4 development bundle, `build/native/task006-usb-package-recovery-a1`.
It adds the separately isolated guest installer to the existing recoverable USB
Store, notebook and closure checker. This pair passes linked artifact audits;
its real install/lost-reply/offline-ink/retry/cold scenario is still running.
Use `--workload usb-clocked-package-retry-bulk-notebook --usb-recovery` with this
bundle and the same prepared USB host/peer/outbox session arguments shown above.
The old three-process recovery names remain distinct. The normal course command
now admits this exact four-process profile:

```sh
./scripts/lemmasim course-install --session-dir build/usb/your-session \
  --package build/courses/your-package/arithmetic.lcp --transaction 65537
```

This sends raw UART bytes. Only the actual guest/peer barrier can produce an
Installed or Saved receipt. See [recovery4 contracts](docs/contracts/006-package-companion-recovery-v1.md)
and [source-bound evidence](docs/evidence/006-package-companion-recovery4.json).
The current aligned course renderer has passed source/Action/object qualification;
its linked canonical/native/browser timing acceptance is pending. The previous
source6 native and source4 browser400M course failures remain failures.

The aligned2 notebook pair is fully linked/audited and prepared locally in
`build/native/task006-aligned-notebook-a1` and
`build/browser/task006-aligned-notebook-a1`. Its42-phase fast course/checker/
learner/ink/newcold/reopen and actual partial-write failure/retry cases pass.
New RTL and browser cold/course runs are still active. Launch the prepared
local browser with:

```sh
./scripts/lemmasim browser-serve \
  --bundle build/browser/task006-aligned-notebook-a1 --port 8796
```

Use the existing session/init/snapshot commands above with the native bundle.
The original source6/native and source4/browser400M course failures are retained;
see [aligned2 evidence](docs/evidence/006-course-aligned-delta-v2.json).


The additive public-development-key authenticated Product10ROM is documented in
[the development authentication contract](docs/contracts/006-development-boot-authentication-v1.md).
It uses the same native RTL machine and guest recovery transactions. The key
`00..1f` is public test material; production identity and anti-rollback remain
open. Actual MAC rejection, authenticated canonical Ready, raw ink/Save and
independent authenticated cold recovery pass on the older Product10 notebook.
Installation plus both boots and Save take 2.3308 billion RTL clocks and
12,123.862 host seconds. The latest course image and interrupted authenticated
update/power acceptance remain separate open results.

```sh
nix develop --no-write-lock-file --command python3 scripts/check_crypto.py \
  --work-dir build/boot/crypto-new
nix develop --no-write-lock-file --command python3 scripts/build_development_auth_boot.py \
  --public-development-key --work-dir build/boot/auth-rom-new
./scripts/lemmasim-auth --public-development-key --help
```

The retained prepared instance is`build/boot/task006-development-auth-prepared-a6`.
Its normal commands are`create-medium`, `launch`, `install`, `tag`, `publish`,
`status`, `boot`, `capacity` and`key-info`; use each command's`--help`. Installation
requires a source-validated opaque product package and a slot-specific tag made
with`scripts/package_development_auth_tag.py --public-development-key`. No host
preinstallation of a running image is part of this path.


The current control-spans1 pair is prepared at
`build/native/task006-control-notebook-a1` and
`build/browser/task006-control-notebook-a1`. Both full ordinary image audits
pass. The42-phase fast course/mathematics/learner/ink/independent-cold workflow
and actual2-byte partial-pwrite failure/cold/retry pass. Total instruction clocks
fall2,639,000,287→2,615,000,279 (0.91%). Actual canonical RTL reaches Ready in
802M clocks and the first COURSE body in398M; the next title/header fails its
original100M limit. Browser cold fails its original7200s host bound at796.15M
clocks before Ready. Original400M COURSE failures remain failures. Use the same
session/course/snapshot commands above with this native bundle. Exact
[control evidence](docs/evidence/006-course-control-aligned-v1.json) separates
compilation, fast functional results and canonical timing.

A static browser machine can now be packaged with its own local launcher and
extracted away from the checkout. The package uses the original validator and
loopback server, unchanged guest/ROM/Wasm/controller bytes and only Python's
standard library. This is a local prepared development distribution; original
notices and unresolved redistribution permission remain in NOTICE.txt.

```sh
python3 scripts/package_browser.py \
  --bundle build/browser/task006-control-notebook-a1 \
  --output-dir build/distribution/AN_UNUSED_BROWSER_PACKAGE \
  --archive build/distribution/AN_UNUSED_BROWSER_PACKAGE.tar.gz
tar -xzf build/distribution/AN_UNUSED_BROWSER_PACKAGE.tar.gz -C YOUR_EXTRACTION_DIRECTORY
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-browser/serve.py --verify-only
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-browser/serve.py --port 8787
```

Open `http://127.0.0.1:8787/`. Python3.10+ is required; isolated launch from
another working directory has been exercised on Linux. No checkout, Nix,
Lean/LLVM, Python package installation or network download is used by this
launcher. This does not add a browser-local compiler. The prepared current
archive is `build/distribution/task006-control-browser-a3.tar.gz` (2,052,683
bytes); [actual extraction/server evidence](docs/evidence/006-local-browser-distribution-v1.json)
records the identities and retained original missing-import failure.
Keep the chosen port to retain the same browser storage origin, and export raw
backing bytes for backup. Restoring a checkpoint is continuation; reopening
raw backing invokes guest cold recovery. Complete browser course/mathematics,
durable reload and universal native installation remain
separate unfinished obligations.

The canonical native bundle also has an extracted local command package. It
retains the original compiled guest and both backends and validates all their
normal admission checks after relocating source lookup locations. Exact host
libraries remain at their inventoried Nix paths; an optional offline export
can supply those paths on a compatible Nix host.

```sh
python3 scripts/package_native.py \
  --bundle build/native/task006-control-notebook-a1 \
  --output-dir build/distribution/AN_UNUSED_NATIVE_PACKAGE \
  --archive build/distribution/AN_UNUSED_NATIVE_PACKAGE.tar.gz \
  --include-nix-runtime
tar -xzf build/distribution/AN_UNUSED_NATIVE_PACKAGE.tar.gz -C YOUR_EXTRACTION_DIRECTORY
# Only if the inventoried host libraries are absent, using normal Nix permissions:
nix-store --import < YOUR_EXTRACTION_DIRECTORY/lemmasim-native/runtime-closure.nar
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-native/run.py --help
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-native/run.py init \
  --backend qemu --profile lemma-silicon-dev/0.3.0 --disk /outside/package/new.raw
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-native/run.py session \
  --backend rtl --profile lemma-silicon-dev/0.3.0 --disk /outside/package/new.raw \
  --session-dir /outside/package/live --mode developer --paused --headless
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-native/run.py session-control \
  --session-dir /outside/package/live --request '{"action":"run","cycles":1000000}'
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-native/run.py snapshot \
  --session-dir /outside/package/live --to /outside/package/cut
python3 -I YOUR_EXTRACTION_DIRECTORY/lemmasim-native/run.py session \
  --backend rtl --profile lemma-silicon-dev/0.3.0 --restore /outside/package/cut \
  --session-dir /outside/package/private-fork --mode developer --paused --headless
```

Keep each session's sibling `.bundle` and `.bundle.relocation.json`. Restored
media are private; raw-media reopen invokes guest cold recovery. `run.py`
forwards the usual course/raw-input/replay controls; `COMMAND --help` shows
their arguments. Explicit development guest overrides may need their original
build/source environment. This version does not package product boot/update
or optional companion/radio adapters. The prepared local archive is
`build/distribution/task006-control-native-a4.tar.gz` (28,413,646 bytes including
a49,253,648-byte offline runtime export). The
[native distribution contract](docs/contracts/006-local-native-distribution-v1.md)
and [actual qualification](docs/evidence/006-local-native-distribution-v1.json)
separate artifact admission, real RTL transport, private runtime import and
restored suffix equality from full workflow and clean-host installation.

The extracted native command has also exercised the installed-course/checker/
learner/ink/Save workflow and independent cold/reopen:2,615,000,279 instruction
clocks within the original3B/900s bounds. The original live harness census FAIL
and its independently corrected missing-only cold observer remain distinct.
Actual guest initialization without `--session-dir`, both subcommand help pages
and unchanged package integrity pass on A4. Initializer logs default beside the
external medium as `new.raw.initialize`. Exact RTL/browser workflow deadlines,
new-host installation, fast timing/cached-state continuation and permissioned
tutor transport remain separate.

The current dirty-batch9 guest keeps the same canonical machine and submits up
to four queued dirty tiles in one owned Surface packet. Both fresh full image
audits, the42-phase fast course/math/learner/ink/cold/reopen workflow and real
partial-write/failure/cold/retry pass. Same-workload fast instruction clocks
fall2,615,000,279→2,302,000,127 (11.97%); exact RTL/browser timing is still running.
Read [the evidence and limits](docs/evidence/006-notebook-dirty-batch-v1.json).

Build and audit a fresh notebook from the current maintained Lean source using
an unused output directory (the initializer uses configuration
`lemmasim-silicon-package-closure-entry2-bulk-initialize`):

```sh
nix develop --no-write-lock-file --command python3 scripts/build_kernel.py \
  --stage supervisor --opt-level O2 \
  --configuration lemmasim-silicon-package-closure-entry2-bulk-notebook \
  --output-dir build/kernel/my-dirty9-notebook --timeout 300
nix develop --no-write-lock-file --command python3 scripts/audit_kernel.py \
  build/kernel/my-dirty9-notebook --timeout 300
```

Prepared, audited guests are in `build/native/task006-dirty-batch-notebook-a1`.
The local extracted native archive is
`build/distribution/task006-dirty-batch-native-a1.tar.gz`. After extraction,
use its `lemmasim-native/run.py`; keep media/session paths outside the package:

```sh
python3 -I /path/to/lemmasim-native/run.py init --backend qemu \
  --profile lemma-silicon-dev/0.3.0 --disk /outside/new.raw
python3 -I /path/to/lemmasim-native/run.py session --backend qemu \
  --profile lemma-silicon-dev/0.3.0 --disk /outside/new.raw \
  --session-dir /outside/student-session --mode student
```

The graphical native presentation needs host Python/Tk; the existing
`--headless` and Developer raw-control paths remain available. Snapshot,
private restore and replay use the same commands documented above. The current
`lemmasim course-install` spelling uses RTL Developer/Laboratory transport.
The new `lemmasim-course` command also supports the opt-in fast UART bundle
below. Earlier extracted archives retain their original fast runtime. No host
document or journal reconstruction supplies the guest. Native package v1 excludes
optional product/USB/radio adapters, and new-host/licensing limits remain.

The matching extracted static browser archive is
`build/distribution/task006-dirty-batch-browser-a1.tar.gz`. Run its standalone
launcher with `python3 -I /path/to/lemmasim-browser/serve.py --port 8798`.
It uses the exact new RV64 guest and existing RTL Wasm machine, not a browser
notebook implementation. The actual packages-only cold case at8798 reached Ready at806M RTL cycles in
6999.82s within its original1B/7200s bound. It created the initial notebook;
prior saved-ink cold recovery and the full browser course workflow remain open.

The canonical fast machine can now install an authored course on an empty
guest-initialized medium through actual guest UART instructions. The same
maintained notebook then reads courses, checks answers, records learner events,
writes ink and recovers acknowledged bytes/pixels after cold boot. This is a
functional fast transport; exact RTL timing and general QEMU cached-state
continuation remain open. See the [contract](docs/contracts/006-fast-uart-ingress-v1.md)
and [actual qualification](docs/evidence/006-fast-uart-ingress-v1.json).

The prepared opt-in pair is `build/native/task006-dirty-batch-raw-uart-a2`.
Use new media and session paths; `init` executes the RV64 initializer:

```sh
./scripts/lemmasim init --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-dirty-batch-raw-uart-a2 \
  --disk build/my-raw-uart.raw --session-dir build/my-raw-uart-initialize
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-dirty-batch-raw-uart-a2 \
  --disk build/my-raw-uart.raw --session-dir build/my-raw-uart-session \
  --mode developer --paused --headless
```

In a second terminal, advance the machine and inspect actual Ready/controller
completion before installing. Course commands require a paused Developer or
Laboratory owner. Admission is provisional; only the guest's K1/4b1 outcome
after its backing barrier is an installation receipt.

```sh
./scripts/lemmasim session-control --session-dir build/my-raw-uart-session \
  --request '{"action":"run","cycles":300000000}'
./scripts/lemmasim session-control --session-dir build/my-raw-uart-session \
  --request '{"action":"inspect"}'
./scripts/lemmasim-course install --session-dir build/my-raw-uart-session \
  --package build/courses/task006-package-qualified-a5/package/arithmetic.lcp \
  --transaction 1
./scripts/lemmasim session-control --session-dir build/my-raw-uart-session \
  --request '{"action":"run","cycles":100000000}'
./scripts/lemmasim snapshot --session-dir build/my-raw-uart-session --to build/my-raw-uart-cut
```

The same `lemmasim-course` command supports `load` and `delete-probe`; its help
lists required identity/edition/CRC/node or transaction fields. Use the existing
session restore/replay commands with this exact `--native-bundle`. Snapshots
retain pending bytes and UART backpressure; cold recovery uses raw media.
The reusable real-guest conformance command, including an independent cold load,
is:

```sh
nix develop --no-write-lock-file --command python3 conformance/lemmasim/check_fast_uart_ingress.py \
  --native-bundle build/native/task006-dirty-batch-raw-uart-a2 \
  --package build/courses/task006-package-qualified-a5/package/arithmetic.lcp \
  --work-dir build/uart/AN_UNUSED_RAW_UART_CHECK
```

To rebuild this opt-in backend against an unchanged audited guest bundle, run
each role explicitly, then seal an unused bundle. The default QEMU recipe and
previous immutable bundles retain their original scope.

```sh
LEMMA_FAST_RAW_UART=1 nix develop --no-write-lock-file --command ./scripts/lemmasim build \
  --backend qemu --profile lemma-silicon-dev/0.3.0 --workload notebook \
  --guest-bundle build/native/task006-dirty-batch-notebook-a1 --opt-level O2
LEMMA_FAST_RAW_UART=1 nix develop --no-write-lock-file --command ./scripts/lemmasim build \
  --backend qemu --profile lemma-silicon-dev/0.3.0 --workload initializer \
  --guest-bundle build/native/task006-dirty-batch-notebook-a1 --opt-level O2
LEMMA_FAST_RAW_UART=1 ./scripts/lemmasim native-bundle-build --refresh-fast \
  --profile lemma-silicon-dev/0.3.0 --base-bundle build/native/task006-dirty-batch-notebook-a1 \
  --expected-fast-sha256 97ab475eda8da56508c99601c4331cc2b802a7f4f52ac8aace720964a8aaddf7 \
  --output-dir build/native/AN_UNUSED_RAW_UART_BUNDLE
```


The extracted native version2 archive includes that raw-UART backend and the
same course command surface:

```sh
tar -xzf build/distribution/task006-raw-uart-native-a2.tar.gz -C /your/extraction
cd /tmp
python3 -I /your/extraction/lemmasim-native/run.py init --backend qemu \
  --profile lemma-silicon-dev/0.3.0 --disk /your/media/new.raw
python3 -I /your/extraction/lemmasim-native/run.py session --backend qemu \
  --profile lemma-silicon-dev/0.3.0 --disk /your/media/new.raw \
  --session-dir /your/sessions/new --mode developer --paused --headless
```

In a second terminal use the same `run.py session-control` commands above,
then `run.py course-install --session-dir /your/sessions/new --package
/your/course.lcp --transaction 1`. Version2 also supplies `course-load` and
`course-delete-probe`. Their help gives the explicit edition/CRC/node fields.
All mutable paths must be outside the extracted directory; preserve the
session's sibling bundle view. Python3.10+ and the inventoried Nix runtime
remain prerequisites. The optional runtime export requires an explicit import
on a compatible host. New-host installation and redistribution rights remain
unresolved. Exact archive identities and the actual extracted guest/cold and
retained-suffix qualifications are in the
[native distribution evidence](docs/evidence/006-local-native-distribution-v1.json).

The same real-guest UART conformance checker accepts `--launcher
/absolute/path/to/lemmasim-native/run.py` instead of `--native-bundle`, with the
same `--package` and an unused `--work-dir`. Every machine/init/course command
then executes the extracted launcher from/tmp with isolated Python-I.

The course-preserving Save guest is prepared as
`build/native/task006-course-preserving-save-notebook-a1` and
`build/browser/task006-course-preserving-save-a1`. In the course view, ordinary
Save now publishes Pending and waits for the real status reply while retaining
the authored text and annotation pixels. The fast machine has executed annotation,
explicit Saved/detail0 and an independent cold reopening with exact full display
and medium bytes. Its RTL and browser qualifications remain separate running cases.
Launch the ordinary native session with the prepared bundle, or serve the static
Wasm machine locally:

```sh
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-course-preserving-save-notebook-a1 \
  --disk /your/notebook.raw --session-dir build/AN_UNUSED_COURSE_SAVE_SESSION \
  --mode student
./scripts/lemmasim browser-serve \
  --bundle build/browser/task006-course-preserving-save-a1 --port 8799
```

A reusable regression command opens the first installed package's node0 body on
notebook1/page1, annotates it through raw pen input, presses idle Save, and creates
a second cold CPU to compare the complete course/ink display and medium. Its
`--disk` is an existing actual guest-created medium containing that package;
`--package` is the matching immutable package for independent pixel observation.
The command copies the input privately and does not install or format it.

```sh
nix develop --no-write-lock-file --command python3 scripts/check_course_save.py \
  --backend qemu --disk build/browser/task006-pointer-ink-save-browser-export-a1/medium.raw \
  --package build/courses/task006-package-qualified-a5/package/arithmetic.lcp \
  --native-bundle build/native/task006-course-preserving-save-notebook-a1 \
  --guest-build build/kernel/task006-course-preserving-save-notebook-notebook-a1 \
  --guest-source-root build/courses/task006-course-preserving-save-notebook-whole-a1/consumed-source-root \
  --work-dir build/courses/AN_UNUSED_COURSE_SAVE_CHECK
```

`--backend rtl` uses the same workflow and exact machine clocks. The declared
limits are3B aggregate units,1B per cold,400M per course opening,200M for the
annotation and60M for explicit Save; host ceilings are900s fast/21600s RTL.
The independent observer requires a newly completed scan and the actual
Pending/Saved receipt, with complete pixel/medium equality. Fast units do not
establish RTL pipeline timing or arbitrary cached-state checkpoint continuation.
The prepared native distribution2 archive for this guest is
`build/distribution/task006-course-preserving-save-native-a1.tar.gz`. Use its
extracted `run.py` as above. Its actual extracted initializer, queued UART/private
fork, installation, independent cold recovery and Load pass. Clean-host
installation and redistribution rights remain separate.

The newer empty-ingress policy2 guest is prepared in
`build/native/task006-ingress-idle-notebook-a1` and
`build/browser/task006-ingress-idle-a1`. It backs off only empty installer
reads before the first header byte. On the same fast machine and Saved8 medium,
cold Ready uses185,000,001 units versus249,000,006; the complete course annotation,
explicit Save and independent cold/reopen case uses576,000,030 versus762,000,035.
The comparison retains the full display/pool and strengthens the independent
annotation expectation. These are fast functional units; exact RTL and browser
qualification remain separate running cases.

```sh
./scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --native-bundle build/native/task006-ingress-idle-notebook-a1 \
  --disk /your/notebook.raw --session-dir build/AN_UNUSED_IDLE2_SESSION --mode student
./scripts/lemmasim browser-serve --bundle build/browser/task006-ingress-idle-a1 --port 8800
```

Use the same `check_course_save.py` command with the idle2 bundle,
`--guest-build build/kernel/task006-ingress-idle-notebook-notebook-a1` and
`--guest-source-root build/courses/task006-ingress-idle-notebook-whole-a1/consumed-source-root`.
The new ordinary failed-save check uses those same arguments and inputs:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_course_failed_save.py \
  --backend qemu --disk build/browser/task006-pointer-ink-save-browser-export-a1/medium.raw \
  --package build/courses/task006-package-qualified-a5/package/arithmetic.lcp \
  --native-bundle build/native/task006-ingress-idle-notebook-a1 \
  --guest-build build/kernel/task006-ingress-idle-notebook-notebook-a1 \
  --guest-source-root build/courses/task006-ingress-idle-notebook-whole-a1/consumed-source-root \
  --work-dir build/courses/AN_UNUSED_FAILED_COURSE_SAVE_CHECK
```

It requires actual Failed/no Saved, independently computed complete course/ink
pixels and a new cold CPU recovering the original acknowledged display/bytes.
Its injected first-FLUSH failure occurs before writeback; it does not establish
rollback for actual OS failures. The native and static browser archives are
`build/distribution/task006-ingress-idle-native-a1.tar.gz` and
`build/distribution/task006-ingress-idle-browser-a1.tar.gz`. The extracted native
archive passes initialization/UART/install/fork/cold-Load; browser cold is running.
The native archive retains the documented Python/Nix prerequisites and rights
limitations. Use the browser archive's extracted stdlib launcher as documented
above; it serves the same local machine without compiling a guest.
