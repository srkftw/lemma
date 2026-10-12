# Checked canonical call-boundary optimizations

The two independently catalogued optimizations are disabled by default.
Historical Core0 profiles, producers and call-boundary artifacts retain their
original behavior. These options change LLVM call optimization, not the
accepted source language, ownership authority, memory geometry or allocation.

`lemma-closed-literals-v1` admits a checked scalar function only when its
parameters, signature arguments and dependencies are empty, and its entire
body is one UInt8, UInt32 or UInt64 literal with the matching result type.
The catalog binds source, emitted symbol, type and width-normalized value.
The independent preIR audit requires exactly an empty-argument pure function
with one typed literal return; omitted, duplicated or inconsistent rows fail.

`lemma-checked-primitive-wrapper-v1` admits a checked Action function only when
its entire body is one physical memory platform operation followed by `.done`
forwarding the exact bound status and value. Parameters must be all UInt64,
forwarded once in their original order, and remaining six-word operand slots
must be literal zero. Exact direct and transitive effects equal that operation;
no scalar or Action dependency is admitted. Erasing an error, replacing a value,
reordering operands, adding work, using a device/virtual operation or adding
policy disqualifies the wrapper. The canonical producer enables this only for
the kernel unit.

The existing structured LLVM lowering emits the complete original physical
interval, width, alignment, volatile-access and status/value guards. The
independent preIR auditor pins their complete guard/result preimages, including
all six kernel-v0.4 physical intervals and misalignment-before-range precedence.
The only change to either eligible function is `alwaysinline` in place of
`noinline` and `disable-tail-calls`; all other bodies, ABI and linkage are
unchanged. Ordinary pinned LLVM optimization can then propagate constants
through these exact bodies. Every ownership, capability, mapping, revocation
and policy Action retains its inspectable call boundary.

Only canonical Power-v1 notebook/initializer and the three explicitly selected
Arithmetic Laboratory configurations enable these options. Other configurations
must not carry the catalog or an `alwaysinline` function. The catalog has exact
version, row and attribute inventories. The ordinary postIR/object auditor
continues to inspect accesses, calls, executable provenance, runtime closure
and stack use. These are artifact audits and semantic regression checks, not
proofs of LLVM correctness or a boot-cycle bound. Device MMIO wrappers retain
the separate complete aperture/fence audit and their original call boundaries.
