# LLVM/Core0 toolchain and upstream-emitter audit

Status: host-tool and source audit for Task 001, captured 2026-10-07.

This audit verifies the immutable compiler/emulator inputs used by the Task 001
development environment and records the decision boundary for Core0 lowering. It
does **not** claim that an RV64 image was built, booted, or executed. Guest-image,
ELF-closure, QEMU-command, and UART evidence belongs in
`docs/evidence/001-core0.md` after those commands have actually run.

## Scope and identity

The repository checked for this audit was `srkftw/lemma` at starting commit
`f384f13d9f4981023b88008f87f1aa7685372d5a` on branch
`task/001-core0-freestanding-slice`. The worktree was intentionally dirty because
Task 001 implementation was in progress. This is not a final source-tree identity;
the evidence record must capture the final relevant-input hashes.

The development flake locks nixpkgs to:

- source selector: `github:NixOS/nixpkgs/7dd199b0e2993e37b4775ed66b1c291699608c9f`
- revision: `7dd199b0e2993e37b4775ed66b1c291699608c9f`
- source: `/nix/store/ia7jffzy37hx46nm77rh05r5272170jh-source`
- `flake.lock` `narHash` / realized source NAR SHA-256:
  `sha256-o9ZUW4SlEAvFPIyJWnqChhOT/VHpHg8TAvEgmqK1fSI=`
- source NAR size: `209524712`

Unless a row says “flat source archive,” hashes below are SRI SHA-256 hashes of
the Nix archive serialization (NAR) of the named realized store path. These are
not hashes of a tar file and are deliberately distinguished from fixed-output
source-archive hashes.

| Tool/input | Immutable upstream identity | Realized Nix output | Output NAR SHA-256 (bytes) |
| --- | --- | --- | --- |
| Lean | `v4.34.1` / `5045d0056413266e57c625dcd7c365b10e377c52`; recursive source hash `sha256-JO1pCqWeotC4zjiIQZccEPXfVHnuDQC0DugyuJvIMRs=` | `/nix/store/ysdqz5kaw8paig5v5q8d94yg6lkk0pkf-lean4-4.34.1` | `sha256-CPrzJ6Fq5wxwravpLoJQIkp9WGW+3Lv8GjJG9nefwqo=` (`2945809536`) |
| Lean source | same revision; `/nix/store/1szlhrxfpn9a2xadknnd18ynp2qxcq7h-source` | realized fixed-output source | `sha256-JO1pCqWeotC4zjiIQZccEPXfVHnuDQC0DugyuJvIMRs=` (`674782584`) |
| LLVM tools | `llvmorg-20.1.8`; tag object `023ec9011c9a92cfa8922030eb266d66a10f78f8`, peeled commit `87f0227cb60147a26a1eeb4fb06e3b505e9c7261`; recursive source hash `sha256-ysyB/EYxi2qE9fD5x/F2zI4vjn8UDoo1Z9ukiIrjFGw=` | `/nix/store/2rqn5n8cihb3nkhbk5vwbygbpipz0xaq-llvm-20.1.8` | `sha256-N/rgDsq17lRAEQm9vf6YruWnIHN/DZhWM5Et1YCulJk=` (`129904400`) |
| LLD | same LLVM tag and peeled commit | `/nix/store/kavf1x7bf1j36jlnybs5am32lca7gw8a-lld-20.1.8` | `sha256-VfnUCqZmurMkXKzYy4hchZKNu6bVMKByWoNTCe0geZE=` (`42771664`) |
| QEMU | `v11.1.1`; tag object `5e35f26695645b20931e10d8567c7e0169e62c07`, peeled commit `c3d48b7d1e89604920e5b81b91140c2ad39a1943`; flat source-archive hash `sha256-B5/7/4pxEbvIkCIQfLq/O7/WFNX8nXzGdZkRlqyhJII=` | `/nix/store/9ihv5zpj6l7fl12mdcxrbmiih3wgrmhw-qemu-11.1.1` | `sha256-ZgXwd0SM3CJt8UkZ38IfhH2LMY7QaC99MQJLbLypRVQ=` (`1040964728`) |
| QEMU source archive | same revision; `/nix/store/5fncyn7ha91mjhrxsl6id2wdi6zlgbnb-qemu-11.1.1.tar.xz` | realized fixed-output file | NAR `sha256-X6rE+OzN854s6cBPR+VsVQntbZ1xdg6EVSF9h3OvHC0=` (`141888832`); file content hash is the flat hash above |

Additional realized outputs used by the flake are:

| Output | Store path | NAR SHA-256 (bytes) |
| --- | --- | --- |
| LLVM development output / `llvm-config` | `/nix/store/f7ignbzpa28d9js41mflrgka6x668r4y-llvm-20.1.8-dev` | `sha256-d74IdyX68ugLQiT5rPn7zyIi2iuml3bNurZnwHCtQh4=` (`32179168`) |
| Clang (unwrapped) | `/nix/store/c0jm2ghmasw8rljbixrhq3vw4hx2rgk8-clang-20.1.8` | `sha256-zy5fyFT/JnjPfCFKtAFKIMyFwqshmBorDoxRt7zyIVo=` (`52983728`) |
| Device-tree compiler | `/nix/store/7v9p68ylbqfcj7mapysfhff2vzwl75aw-dtc-1.8.1` | `sha256-xfFb10AV/TTaSUKchw2eN2tgFGfstpKvg0QL34+HQ1s=` (`581400`) |
| Python | `/nix/store/lb41b0anx1f98y9y5s9mdv97gjgsq740-python3-3.14.7` | `sha256-G7+E0T4FPbBU3fDd7ypzt5uDoKXRz+80fsI+WBUMsB0=` (`143188008`) |
| jq | `/nix/store/m3y7hqmy20nd1ps6qy8410a326255bf0-jq-1.8.2-bin` | `sha256-pqqaGdJ6OxreKzMR3PuZmeMBv8jkCgca+2DOV9UKAuU=` (`35680`) |

The authoritative machine-readable record, including derivation paths and replay
commands, is `tooling/toolchain-lock.json`.

## Observed versions and target-tool capability

The following was run through `nix develop --no-write-lock-file`:

```text
Lean (version 4.34.1, Release)
features=[]
Lake version 5.0.0-src (Lean version 4.34.1)
clang version 20.1.8
llvm-config: 20.1.8
LLD 20.1.8 (compatible with GNU linkers)
QEMU emulator version 11.1.1
Version: DTC 1.8.1
Python 3.14.7
jq-1.8.2
```

`llc --version` listed both `riscv32` and `riscv64` registered targets, and
`clang --print-targets` listed the same RISC-V targets. QEMU's
`qemu-system-riscv64 -machine help` listed `virt` and `-cpu help` listed RV64
CPU models. These checks establish only that the host tools expose the required
target and machine; they are not guest-execution evidence.

### Why the flake selects unwrapped Clang

The dev shell deliberately selects `llvm.clang-unwrapped`. The Nix cc-wrapper
at `/nix/store/1swlw4m64aq15jmni8gpib9xw4kad33s-clang-wrapper-20.1.8`
reads the shell's host hardening policy; `NIX_HARDENING_ENABLE` includes
`zerocallusedregs`, and its `nix-support/add-hardening.sh:182` adds
`-fzero-call-used-regs=used-gpr`. That option is not supported by Clang for the
RV64 bare-metal target.

A controlled probe compiled the same minimal LLVM module through the wrapped
and unwrapped executables inside the pinned dev shell, with
`--target=riscv64-unknown-elf -march=rv64imac -mabi=lp64 -ffreestanding
-fno-builtin -nostdlib -c`. The wrapped compiler exited 1 and produced no
object:

```text
Warning: supplying the --target riscv64-unknown-elf != x86_64-unknown-linux-gnu
argument to a nix-wrapped compiler may not work correctly
clang: error: unsupported option '-fzero-call-used-regs=used-gpr' for target
'riscv64-unknown-unknown-elf'
```

The unwrapped executable exited 0 and produced the object. It remains the same
pinned Clang 20.1.8 source revision as LLVM/LLD, but its own realized output,
derivation, path, and NAR hash are recorded separately. This avoids importing
host C-library paths and host-only hardening flags into target compilation; it
does not relax the later ELF/helper-closure audit.

### Actual Codex host

- NixOS `25.11 (Xantusia)`, build ID `25.11.3064.64049ca74d63`
- kernel: `Linux 6.12.63 #1-NixOS SMP PREEMPT_DYNAMIC Thu Dec 18 12:55:23 UTC 2025 x86_64 GNU/Linux`
- current and booted system: `/nix/store/mb5xv6j6q2rchb2kniq604yr17kd8sh2-nixos-system-nixos-25.11.3064.64049ca74d63`
- top-level system-path NAR SHA-256: `sha256-e34ctKnwlaJc74utD+m9Lg0oW0gcIFvtI0vzjF1Ravs=` (`18960` bytes)
- Nix `2.31.2`: `/nix/store/yhbbi1pjdkxss2f6k5pgg4gv0r8fva7f-nix-2.31.2`, NAR SHA-256 `sha256-zan+5d1pp/14W1qR/6qF/DWfgmZUOBb6g3KuMCP+ODo=`

The observed NixOS generation is recorded for forensic reproducibility, but it
is not a flake input. The pinned nixpkgs revision and flake outputs are the
portable host-environment definition. The top-level NixOS NAR hash is not a
standalone digest of every path in its closure; use `nix path-info --recursive`
when a complete host-closure inventory is needed.

## Verification commands

These commands were executed successfully unless an expected failure is shown
in the emitter probe below:

```sh
nix develop --no-write-lock-file --command lean --version
nix develop --no-write-lock-file --command lean --features
nix develop --no-write-lock-file --command lake --version
nix develop --no-write-lock-file --command llvm-config --version
nix develop --no-write-lock-file --command llc --version
nix develop --no-write-lock-file --command bash -lc \
  'command -v clang; clang --version; clang --print-targets'
nix develop --no-write-lock-file --command ld.lld --version
nix develop --no-write-lock-file --command qemu-system-riscv64 --version
nix develop --no-write-lock-file --command qemu-system-riscv64 -machine help
nix develop --no-write-lock-file --command qemu-system-riscv64 -cpu help
nix develop --no-write-lock-file --command dtc --version

nix path-info --json \
  /nix/store/ysdqz5kaw8paig5v5q8d94yg6lkk0pkf-lean4-4.34.1 \
  /nix/store/1szlhrxfpn9a2xadknnd18ynp2qxcq7h-source \
  /nix/store/2rqn5n8cihb3nkhbk5vwbygbpipz0xaq-llvm-20.1.8 \
  /nix/store/f7ignbzpa28d9js41mflrgka6x668r4y-llvm-20.1.8-dev \
  /nix/store/c0jm2ghmasw8rljbixrhq3vw4hx2rgk8-clang-20.1.8 \
  /nix/store/kavf1x7bf1j36jlnybs5am32lca7gw8a-lld-20.1.8 \
  /nix/store/9ihv5zpj6l7fl12mdcxrbmiih3wgrmhw-qemu-11.1.1 \
  /nix/store/5fncyn7ha91mjhrxsl6id2wdi6zlgbnb-qemu-11.1.1.tar.xz

git ls-remote https://github.com/leanprover/lean4.git \
  refs/tags/v4.34.1
git ls-remote https://github.com/llvm/llvm-project.git \
  refs/tags/llvmorg-20.1.8 'refs/tags/llvmorg-20.1.8^{}'
git ls-remote https://gitlab.com/qemu-project/qemu.git \
  refs/tags/v11.1.1 'refs/tags/v11.1.1^{}'
```

The source hashes can also be checked directly in the locked nixpkgs source:

- `pkgs/by-name/le/lean4/package.nix:25-34`
- `pkgs/development/compilers/llvm/default.nix:25-28`
- `pkgs/by-name/qe/qemu/package.nix:143-148`

## Immutable Lean source audit

All paths in this section are under the immutable source tree
`/nix/store/1szlhrxfpn9a2xadknnd18ynp2qxcq7h-source`.

### Normal compiler path and usable boundary

Ordinary Lean source is elaborated into declarations in a `Lean.Environment`.
The normal native compiler then proceeds as follows:

1. `src/Lean/Compiler/Main.lean:19-22` invokes `LCNF.main` for selected
   declaration names.
2. `src/Lean/Compiler/LCNF/Main.lean:156-212` filters declarations that need
   code, calls `toDecl`, runs base and monomorphization passes, runs impure
   passes, converts LCNF to `Lean.IR`, and installs the compiled IR.
3. `src/Lean/Compiler/LCNF/ToDecl.lean:121-180` reads the elaborated declaration
   from the environment, partially erases types and proofs, eta-expands,
   expands selected definitions/matchers, and produces LCNF.
4. `src/Lean/Compiler/LCNF/Passes.lean:144-158` makes reset/reuse explicit,
   runs `explicitBoxing`, inserts `explicitRc`, expands reuse, and coalesces
   reference-count operations before saving impure LCNF.

This establishes that the elaborated `Environment`/`ConstantInfo` body is a real
front-end boundary, before managed-runtime lowering. It is the boundary chosen
for the narrow Task 001 checker: inspect the requested declaration and every
reachable runtime declaration body, admit only exact scalar primitive
identities/types/effects, and translate the resulting checked Core0 IR. It does
not construct a toy AST in place of elaboration and it does not route through C.

### Upstream LLVM backend is absent in the pinned Lean binary

`src/CMakeLists.txt:82` defaults `LLVM` to `OFF`. When enabled,
`src/CMakeLists.txt:456-508` finds `llvm-config`, defines `LEAN_LLVM`, and at
lines 479-480 rejects every LLVM major except **19**. The locked external
toolchain is LLVM 20.1.8. The nixpkgs Lean derivation does not enable this
option, and the installed binary confirms that fact:

```text
$ lean --features
[]
```

`src/Lean/Shell.lean:133-136` would print `[LLVM]` only when
`Internal.hasLLVMBackend` is true. `src/Lean/Shell.lean:569-572` shows that
`lean -b` calls `initLLVM` and then `emitLLVM`; the spelling of the option is not
evidence that the feature exists in a particular build.

An actual probe was run:

```sh
printf 'def core0Probe (x : UInt64) : UInt64 := x + 1\n' | \
  timeout 20s nix develop --no-write-lock-file --command \
  lean --stdin -b /tmp/lemma-upstream-llvm-probe.bc
```

It exited 1, created no bitcode, and reported:

```text
LEAN ASSERTION VIOLATION
File: /build/source/src/library/llvm.cpp
Line: 244
false && ("Please build a version of Lean4 with -DLLVM=ON to invoke " "the LLVM backend function.")
'unreachable' code was reached
```

`src/library/llvm.cpp` conditionally supplies the LLVM C-API FFI under
`LEAN_LLVM`; its disabled branch supplies this assertion. Rebuilding this source
against the locked LLVM 20 would first fail its explicit LLVM-19 check. More
importantly, merely rebuilding would not resolve the target/runtime problems
below.

### Emitter target and ABI assumptions

`src/Lean/Compiler/IR/EmitLLVM.lean` is not presently an acceptable
freestanding RV64 emitter for this slice:

- Lines 24-36 state that its LLVM CI is dysfunctional, the code is not actually
  tested, and ABI updates for `IO.RealWorld`, erased `void` parameters, and
  closed-term static initializers remain TODOs.
- Lines 41-47 hard-code `size_t` to i64 and C `unsigned` to i32 while explicitly
  noting that the target should be instantiated. The emitter creates a module
  at lines 1640-1646 but does not set an RV64 target triple or data layout.
- Lines 329-345 map scalar widths directly, but map object, tagged object,
  erased, and void values to pointers; struct and union lowering panics as “not
  implemented yet.”
- Lines 485-488 show that Lean `Bool` is represented as i8 and converted to an
  LLVM condition by comparing it against zero.
- `getOrAddFunction` at lines 49-61 puts the `probe-stack=inline-asm` attribute
  on functions. That policy and any generated probing would need a separate
  freestanding stack/closure audit.
- Broad module code generation at lines 1216-1263 and 1611-1616 emits the
  compiler's module declarations, an initializer, and optionally a hosted
  `main`; it is not the Core0 root-and-transitive-dependency allowlist.

The absence of a triple/data layout is independently significant even on RV64,
where the current `size_t` guess happens to be 64 bits. Task 001 requires the
triple, LP64 ABI, pointer width, data layout, and ELF attributes to be explicit
and audited rather than inferred from the host or patched after an opaque
emission step.

### Managed representations, boxing, and reference counting

The compiler IR is intentionally coupled to the normal Lean runtime:

- `src/Lean/Compiler/IR/Basic.lean:41-85` defines heap `object`, tagged scalar
  pointers, `tobject`, erased/void values, and stack-returned structs/unions.
  It also states the runtime assumption that pointer and `size_t` widths match.
- `IRType.boxed` at lines 123-126 maps UInt8/UInt16 to tagged values, but maps
  UInt32/UInt64/`usize` through `tobject` in the general IR model.
- `src/Lean/Compiler/LCNF/ExplicitBoxing.lean:16-46` inserts box/unbox operations
  and boxed function variants for the interpreter and closures.
  `requiresBoxedVersion` includes functions with scalar parameters or results,
  so a direct scalar function does not imply that the compiled module contains
  only a scalar entry point.
- `src/Lean/Compiler/LCNF/ExplicitRC.lean:14-27` describes the liveness,
  ownership, borrowing, increment, and decrement insertion performed by
  `explicitRc`.
- `src/include/lean/lean.h:151-225` defines heap-object, constructor, array,
  string, and closure headers. Lines 334-336 define tagged scalar pointers.
  Lines 664-700 implement/reference the RC operations, and lines 796-838
  allocate and initialize constructors.
- On a 64-bit target, `lean_box_uint64` at lines 3001-3004 always allocates a
  constructor holding the 64-bit payload. Thus a generated UInt64 boxed wrapper
  necessarily introduces allocation even if its direct scalar entry point does
  not.

The emitter contains direct calls or declarations for these runtime-helper
classes:

- allocation/data: `lean_alloc_ctor`, `lean_alloc_closure`, constructor
  get/set/release/tag helpers, closure setters, string constructors;
- application: the `lean_apply_N` family and `lean_apply_m`;
- boxing: `lean_box`, numeric and float box/unbox helpers, Nat conversion from
  unsigned values and decimal strings;
- ownership: `lean_inc*`, `lean_dec*`, `lean_is_scalar`, `lean_is_exclusive`,
  `lean_del_object`, and persistent-object marking;
- initialization/hosted IO: `lean_initialize`,
  `lean_initialize_runtime_module`, imported-module initializers,
  `lean_io_mk_world`, IO-result inspection/construction/error display,
  `lean_setup_args`, task-manager initialization/finalization, and panic
  helpers.

Representative locations are
`src/Lean/Compiler/IR/EmitLLVM.lean:133-327,565-634,713-794,850-960,1282-1601`.
The exact closure depends on the declarations compiled, but an audit cannot
infer “runtime-free” merely from a scalar source signature.

### Externs, initialization, and the linked runtime bitcode

`src/Lean/Compiler/ExternAttr.lean:19-41` permits standard, ad-hoc, inline, and
opaque external entries selected by backend. The LLVM emitter's external call
path at `EmitLLVM.lean:656-686` selects the **C** extern entry, creates a named
external function declaration, and reports inline LLVM as unimplemented. This
is a general foreign-call mechanism, not the exact Core0 primitive identity and
effect allowlist required by the contract.

At `EmitLLVM.lean:1619-1676`, upstream emission always locates installed
`lean.h.bc`, parses it, links it into the output module, marks its defined
globals/functions internal, verifies the combined module, and writes bitcode.
`src/runtime/CMakeLists.txt:72-94` explains how that bitcode is generated by
turning the inline definitions in `lean.h` into Clang LLVM bitcode.

That inline bitcode is only part of the normal runtime story. The runtime build
at `src/runtime/CMakeLists.txt:1-67` includes C++ allocation, objects, threads,
mutexes, IO, processes, libuv, OpenSSL, stack overflow handling, and optional
mimalloc, and builds static runtime variants. `src/runtime/init_module.cpp:22-35`
initializes allocation, objects, IO, threads, mutexes, processes, stack overflow
handling, and libuv. `src/initialize/init.cpp:30-49` initializes the runtime,
Init/Std/Lean modules, kernel, library, and constructions subsystems.

Finally, `src/Lean/Compiler/FFI.lean:24-61` returns host C include and Lean
library linker flags. That is appropriate for the normal hosted toolchain but
cannot be reused as a freestanding guest linker contract. Static linkage would
not make those dependencies permissible.

### Host-only C probe used to inspect normal lowering

For diagnosis only, the pinned compiler's C emitter was asked to emit this
ordinary Lean declaration:

```lean
def core0Probe (x y : UInt64) : UInt64 :=
  if x < y then (x + y) * 3 else x - y
```

The command was:

```sh
printf '%s\n' \
  'def core0Probe (x y : UInt64) : UInt64 := if x < y then (x + y) * 3 else x - y' | \
  nix develop --no-write-lock-file --command \
  lean --stdin -c /tmp/lemma-upstream-c-probe.c
```

The generated direct entry point had scalar `uint64_t` parameters/result and
called the primitive helpers `lean_uint64_dec_lt`, `lean_uint64_add`,
`lean_uint64_mul`, and `lean_uint64_sub`. The same file also generated
`core0Probe___boxed`, which called `lean_unbox_uint64`, `lean_dec_ref`, and
`lean_box_uint64`, plus a module initializer calling
`lean_initialize_runtime_module`, `initialize_Init`, IO-result helpers, and RC.

This probe was not compiled into guest code and is not the Task 001 production
route. It demonstrates both useful scalar semantics to match and why “Lean can
emit a scalar C function” is insufficient evidence of a freestanding runtime
closure. Lean-to-C-to-LLVM remains prohibited.

## Decision for Task 001

The upstream LLVM emitter is **not usable as-is** for the freestanding Core0
slice because:

1. the pinned Lean binary reports no LLVM feature and `lean -b` fails;
2. the source backend requires LLVM 19 while the locked project backend is LLVM
   20.1.8;
3. the source itself records untested/stale ABI work;
4. it does not establish the RV64 triple or data layout;
5. it admits general C externs and emits managed boxing/RC/allocation,
   initialization, hosted-main, and task/IO helper paths; and
6. it unconditionally links upstream Lean runtime bitcode.

Task 001 therefore uses a narrow, Lean-authored, fail-closed lowering from
declarations already installed by Lean elaboration in `Lean.Environment` to a
small checked Core0 IR, followed by project-owned LLVM generation and the pinned
external LLVM tools. The boundary must retain declaration identity and walk the
root's actual transitive target dependencies. Unsupported expression forms,
managed representations, allocation, closures, arbitrary externs, initializer
effects, and unknown helpers are rejected before LLVM is emitted. Only exact
allowlisted scalar primitives may lower to corresponding integer operations.

The normal Lean compiler source above is used as the representation and semantic
reference, but neither its C emitter nor its managed LLVM emitter/runtime is a
guest dependency. This is a scoped scalar bootstrap route, not a claim that the
Lean managed ABI or all of G1 has been ported.

## Caveats and follow-up evidence

- Remote tag lookups were used to associate human-readable release tags with
  commits. Reproduction is anchored by the fixed Nix source hashes and recorded
  commits, not by assuming tags can never move.
- LLVM's monorepo source path was evaluated from nixpkgs but was not retained as
  an inspected local checkout for this audit. The locked nixpkgs expression
  fixes its recursive `fetchFromGitHub` hash, and the realized LLVM/LLD outputs
  have independent NAR hashes.
- QEMU's large host closure contains optional UI/device libraries. Those are host
  dependencies only; the eventual guest manifest must separately show that no
  such library or upstream runtime is linked into the RV64 ELF.
- Target support listings do not prove ABI correctness. The implementation
  evidence must still audit target triple/data layout, ELF class/machine/flags,
  entry point, load segments, relocations, symbols, linked inputs, LLVM
  intrinsics/helpers before and after optimization, and QEMU's reset trampoline
  and generated DTB.
- No QEMU boot or UART result is asserted by this document.
