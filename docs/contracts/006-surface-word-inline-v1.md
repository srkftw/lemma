<!--
# Surface word callback inlining v1

`lemma-surface-word-inline-v1` is a closed compiler-policy selection for the
Package Notebook User2 root `Lemma.Applications.Notebook.mainPackageClosureBulk`
under exactly `lemmasim-silicon-package-closure-entry2-bulk-notebook` and
`lemmasim-silicon-package-closure-entry2-bulk-initialize`. It changes no Surface,
Notebook, memory, device, mathematical, or durable-document source semantics.
Historical configurations and callback lowering remain unchanged.

The genuine Lean exporter first checks the full source-derived checked Action
bodies of `tileLoadWordStep`, `bulkCopyWord`, their two callers, and `gatherWord`.
It also checks the three scalar layout declarations, both complete callback
signatures/effects and exhaustive incoming caller sets. Only those two callback
names are excluded from `preserveCalls`. Their LLVM definitions are internal
`nounwind`; no new `alwaysinline` or general eligibility rule is added. The
existing pinned LLVM O2 pipeline must remove both definitions and inline their
original bodies inside the original64-iteration loops. No grouped Surface
implementation or broader accepted Lean language is introduced.

The generated unit carries the closed `surface_word_inline` record with contract,
policy, two ordered source/symbol/signature/effect/caller rows, and exact integer
budget/count64. `scripts/surface_word_inline.py` rejects malformed metadata,
wrong roles/versions/roots/software tuples, partial catalogues, and other symbols.
Its `catalog(unit)`, `validate(ir,unit,optimized=...)`, and
`removed_symbols(unit)` APIs compose with ordinary unit/IR/object audits.
`removed_symbols` alone is never permission to omit a definition: its caller
must first successfully validate the actual optimized IR. Package Notebook
inventory admission subtracts exactly those two unowned library callbacks only
after that validation. All189 owned Package body/caller checks remain required.

The observer pins five complete preIR bodies and three complete postIR bodies.
Its finite normalization rebinds exact one-to-one generated symbol names to their
source owners and expands module-local attribute-group numbers to their complete
attribute tokens; it discards no instruction, operand, edge or attribute.
Independent CFG/dataflow gates require all64 iterations, full64-bit values,
original framebuffer/tile/packet address calculations, gather-status checks,
ordered volatile loads/stores, original first-error results, and bounds before
subsequent reads/writes. The unaligned gather reads its first word before the
second-word range check and only reads the second word after that check succeeds.
The packet-copy loop reads its tile word before checking the packet destination,
and writes that same full word only on the successful path. Partial writes and
hardware-fault prefixes therefore retain their source order.

LLVM may prove the fixed aligned tile span `[0x20500,0x20700)` valid and remove
redundant pure address checks. It may not replace a volatile memory operation,
assume cross-trap address-space validity, omit a hardware permission check,
recover from a hardware fault in host code, or reorder the admitted accesses.
Synthetic Action failure injection checks the abstract Action prefix; it is not
a temporal RAM-fault model or a physical measurement. Canonical target execution
and performance remain separate from source, Action, LLVM, object and host tests.
The original925M Undo/200M-bound failure remains a failure.

Generated outputs and exact producer/observer source inventories live under
ignored `build/`. The evidence record identifies the actual selected producer,
all retained failed observations, unchanged historical sources, and the separate
qualification results. There is no inherited target CPU or speedup claim.
-->
