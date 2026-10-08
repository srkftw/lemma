# Architecture baseline

Status: design constraints, not implementation evidence.

## Layers

`Lean source -> checked Core0 -> LLVM -> RV64 ELF -> LemmaVM` establishes the first
execution path. A managed Lean runtime is constructed afterward. Above it sit the
capability kernel, services, durable store, ink/document system, mathematical
checkers, semantic textbooks, learner state and permissioned tutor.

**Core0** is an explicitly checked freestanding fragment, not all Lean programs.
**Managed Lean** supplies allocation, object representations and library services
only after those implementations exist on the device. Host Lean running the
compiler is not the device runtime.

**LemmaVM** is a versioned machine contract, initially backed by a pinned QEMU RISC-V
`virt` configuration. The final privilege design is M -> S -> U with Sv39. The first
smoke image remains in machine mode. User isolation is a Stage II claim.

**Lemma One** will use a RISC-V board and a separately engineered writing cartridge /
controller. Its physical drivers implement shared service interfaces. The cartridge
is not assumed procured; its exact interface package is not part of this repository.
No physical display work blocks the first compiler/VM milestone.

## Target-language boundary

Application, OS, runtime, project compiler and checker implementations are maintained
in Lean. A small audited generator may emit machine primitives/startup/LLVM artifacts.
Declarations must not merely wrap hand-authored programs in another language.
Build tools are allowed to be implemented upstream in other languages on the host;
all target inputs and generated code must have an explicit origin.

## Authority and evidence boundaries

- Kernel capabilities enforce access; typed handles alone are not authority.
- Raw ink, proposed interpretation, verification result and learner estimate are separate.
- The proof kernel is not the operating-system kernel.
- Tutor outputs and recognition results are untrusted proposals.
- Correctness evidence binds the exact goal, domain, assumptions, submission,
  environment, checker version and resource outcome.
- Storage commits have a specified failure model; saving to a software queue is not durability.
- Virtual display timing is a model. Pen-to-visible-ink latency needs physical measurement.

## What is deliberately not frozen

The exact Lean/LLVM revision pair, complete Core0 feature set, managed Lean ABI,
physical board firmware closure, peripheral ISAs, screen connectors, waveforms,
FPGA resources, and native network cryptography are not validated by this scaffold.
The first task freezes only a tested scalar profile and its toolchain.

## Third-party reference points

Lean's runtime ABI and upstream LLVM emitter are inputs to the audit, not evidence
of freestanding readiness. QEMU's firmware selection and RISC-V's psABI are inputs
to the virtual platform contract. See `docs/SOURCES.md` for official references.
