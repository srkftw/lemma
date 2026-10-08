# Trust and dependency manifest

Status: required audit structure. Task 001 implements executable scalar-image audit
and provenance; Task 002 Gates 1--6 extend it with fault manifests, versioned suites,
control-flow/loop checks, checked-memory effects, and a closed compiled-device path.
Later trap/timer/runtime categories remain open.

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

## Gate 6 device trust boundary

The trusted guest machine primitives remain the structured startup, the IO-fence
primitive, and the status-coded SiFive-test operation in the minimal device harness.
UART policy and algorithms are compiled from elaborated Lean source. The device catalog
admits only four exact source identities and records their fixed address, direction,
byte width, volatility, alignment, ordering, and modeled register side effect.

The audit must bind the manifest to normalized source and symbols, reject stale or
duplicated operation/effect metadata, and inspect both O0/O2 IR and machine code. It
checks wrong addresses, widths, volatility, alignment, missing/reordered fences,
duplicate physical operations, forbidden generic MMIO, hosted dependencies, and UART
logic appearing in the harness. QEMU and its emulated UART remain host/emulator trust,
not guest code and not a physical-device result. The finite model and four local
theorems are mathematical evidence with narrower claims than the target executions.

## Gate 7 trap trust boundary under qualification

`core0-v0.6` adds only four exact synchronous-trap source identities and a
closed typed Lean machine sequence for masking, vector entry, complete integer
context preservation, CSR snapshots, explicit return, and bounded finishers.
Compiled Lean owns dispatch policy, observations, diagnostics, arithmetic, and
software-denial checks. Private frame/probe storage is not ordinary RAM authority.
The audit must name every symbol, CSR operation, object and generated instruction
role, check the nine-argument call and complete save/restore sequence, and bind
source/effect metadata to LLVM and machine code. Test-only wrong-slot restore
must be a declared valid-image mutation, not an unexplained audit bypass.

Local policy lemmas, source probes, resource/disassembly audits, and actual trap
executions are distinct evidence. The fixed-RAM/no-NMI entry-tail premises and
single-hart non-nesting limitations remain explicit; see
[`traps-core0-v06.md`](../audits/traps-core0-v06.md). Gate 7 target acceptance is
pending, and timer/concurrency/runtime categories are not thereby qualified.

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
