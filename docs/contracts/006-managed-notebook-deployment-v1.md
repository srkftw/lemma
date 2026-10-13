<!--
# Managed Notebook software deployment, version1

`lemmasim-silicon-managed-notebook` and `lemmasim-silicon-managed-initialize`
select `lemma-managed-notebook-deployment-v1`. They use the unchanged
`lemma-silicon-dev/0.3.0` hardware binding, 1650×2200 Gray4 geometry, 128MiB
simulation RAM, 8192-frame guest pool, clocks and Power-v1 policy. This software
selection does not qualify processor timing, physical memory or a new device.
The same genuine Lean kernel roots and three separately linked applications are
used: Store is `core0-user-v0.1`, Notebook and Arithmetic are `core0-user-v0.2`,
and the Kernel remains `core0-kernel-v0.4`.

Every unit and the user-image catalog carry the exact `software_deployment`
contract, hardware profile and per-image profile map. The old Power-v1 Notebook
and initializer selections retain a User-v0.1 Notebook, their original catalog
shape and default wrapper admission. Historical archives remain selectable.
The new Notebook has no generated managed-record closure; merely selecting
User-v0.2 does not grant it Arithmetic's closed managed entry or allocator
provenance. Arithmetic retains its independently audited managed source closure.

The new selections opt into `lemma-checked-user-word-wrapper-v1`. The compiler
option is disabled by default and rejects any profile except User-v0.2. It admits
only an entire single virtualRead64 or virtualWrite64 checked platform Action
followed by `.done` forwarding the same bound status/value. All UInt64 arguments
must be forwarded in order; unused operand slots are literal zero; dependencies
are empty and direct/transitive effects exactly match the admitted operation.
No byte wrapper, MMIO, ownership algorithm or other policy body is admitted.

The complete LLVM wrapper retains misalignment error8 before range error7,
unsigned User interval `[0x10000,0x40000000)`, eight-byte width, volatile aligned
load/store and exact checked result. The independent preIR auditor pins that
whole body and the exact selected row/attribute inventory. Only `alwaysinline`
replaces its prior inspectable call-boundary attributes. Ordinary LLVM may
propagate proven constants; translation, PMP, faults and all kernel ownership
checks remain enforced by the running machine. The new optimization catalog
adds exact `user_wrapper_contract` and `user_wrappers` fields; legacy catalog
fields and complete physical-wrapper preimages remain unchanged.

This is an executable compiler/deployment extension, not full G2 language
support or a boot-performance claim. Exact fault-prefix and backend checks,
whole-image auditing, real guest execution and canonical cold Ready are separate
obligations. Development ELF-preload boot remains explicitly a development path.

-->
