# Trust and dependency manifest

Status: required audit structure; executable audit and target manifest generation begin in task 001.

## Categories

1. **Host execution:** Lean compiler/elaborator/runtime, LLVM, LLD, QEMU, build tools,
   OS, scripts, Nix and test tools. These may be non-Lean upstream dependencies.
2. **Guest code:** compiled Core0 functions, explicitly generated startup and primitive
   lowerings, and later Lean-authored runtime/kernel/services. Every executable byte needs provenance.
3. **Emulator artifacts:** reset trampoline/ROM, device tree and test fixtures. These
   are declared platform assumptions, not hidden dependencies of a purported native runtime.
4. **Physical firmware/peripherals:** audited separately when hardware is introduced.
   RISC-V application code does not establish every controller's internal ISA.
5. **Mathematical trust:** reference semantics/proofs with recorded assumptions. Later
   proof-kernel and exercise environments have their own transitive axiom manifests.

## Minimum generated evidence fields

- Source commit, dirty-tree status and hashes for relevant source/configuration inputs.
- Immutable tool revisions, package identities, flags, host/target architecture and ABI.
- Source declaration -> normalized representation -> lowered IR -> object -> image mapping.
- Allowed primitives and each primitive's type, effect contract, implementation and reason.
- All object/archive paths, section/symbol inventory, linker map, ELF attributes and relocations.
- Every external call before and after optimization, with resolution and provenance.
- QEMU invocation, declared platform artifacts, runtime input, UART output and termination status.
- Test names, seeds, run counts, results, rejected fixtures and exact diagnostic reasons.
- Claims established, claims not established and remaining blocked work.

An empty test corpus, missing manifest, missing dependency, unknown linked object,
skipped QEMU run or unrecognized runtime call is not success. Exit nonzero on acceptance failure.

## Prohibited shortcuts

Do not hide an upstream runtime by static linkage, rename banned symbols, copy object
files without source provenance, add no-op reference counting, substitute C-generated
application code, or emit hardcoded expected answers. LLVM intrinsics also require audit
because optimization/code generation can lower them into external helper calls.

## Reproducibility claim

Separate repeatable behavior from byte-identical output. Rebuild twice from clean
outputs with pinned dependencies; compare artifact hashes where determinism is expected.
Explain metadata differences rather than discarding them silently. Keep credentials,
supplier NDA files and personal data out of evidence bundles.

`tooling/toolchain-lock.json` starts unresolved. It is not a reproducible-build lock until
task 001 replaces each required entry with a verified immutable identity and commands.
