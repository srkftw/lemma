# Lemma

A pen-first mathematics computer, constructed from a freestanding Lean 4 foundation
on RISC-V. The reference machine is **LemmaVM**; the operating system is **LemmaOS**;
the physical device is **Lemma One**.

**Current state: construction scaffold.** No Core0 compiler, target runtime, bootable
image, or passing hardware milestone is claimed by this initial commit. The first
implementation assignment is [Codex task 001](codex/prompts/001-core0-freestanding-slice.md).

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
and six physical-port units, all initially `planned`.

## Start here

Read [AGENTS.md](AGENTS.md), [the architecture](docs/ARCHITECTURE.md), and the four contracts:

1. [Core0](docs/contracts/CORE0.md)
2. [Target ABI](docs/contracts/TARGET_ABI.md)
3. [LemmaVM](docs/contracts/LEMMA_VM.md)
4. [Trust and dependencies](docs/contracts/TRUST_MANIFEST.md)

The first task must choose and verify immutable toolchain pins. This scaffold does
not invent a working Lean/LLVM combination, a `lean-toolchain`, or a build command.
The intended code boundaries are documented in [the source map](docs/SOURCE_MAP.md).

## Checks that exist today

```sh
python3 scripts/check_scaffold.py
python3 -m unittest discover -s tests/scaffold -v
```

These validate **repository metadata and safety of the publishing helper**. They do
not compile Lean, boot QEMU, or qualify G1. Target tests are the first Codex task's work.

## GitHub and Codex

The repository is **`srkftw/lemma`**, private, with default branch **`main`**.
The owner created the empty GitHub repository; the prepared starter is published
through the connected GitHub file/tree/commit operations. No Codex task is launched
by publication.

Select this repository and `main` in Codex, then assign
`codex/prompts/001-core0-freestanding-slice.md`. Have Codex work on a task branch and
return a reviewable change. The first task audits/pins the toolchain and builds the
first real scalar Core0 -> LLVM -> bare-metal RV64 execution path.

`scripts/publish-github.sh` is retained as a tested bootstrap helper for the original
empty-remote workflow. **Do not run it on this already-published repository.** It
intentionally refuses an existing repository or `origin`; see [publishing notes](docs/PUBLISHING.md).

## License and private material

No project license has been selected. Do not add a license, publish the repository,
or change visibility without the owner's decision. Preserve licenses and notices
for any third-party code introduced later. Do not commit supplier correspondence,
NDA documentation, panel waveforms, credentials, textbook files or personal learner data.
