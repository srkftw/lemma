<!--
# Owned course workspace v1

`lemma-course-workspace/1` is a separate 3712-byte record containing the unchanged
2496-byte Doc8, its current package selection and up to eight attempt bindings.
It keeps the existing Store journal, mathematical document formats and all
historical application roots unchanged. A selection binding records provenance;
the actual guest checker reply and original execution identity remain required.

The header is magic0/version8/bytes16/namespace24/page32/innerBytes40/mask48/
reserved56. Doc8 begins at64, current selection at2560, and eight 128-byte rows
at2688. Mask bits0..7 identify known attempt rows; bit8 identifies the current
selection. Absent rows are entirely zero and mean Unknown. Namespace1/2 and
page1..64 retain their existing authority. The separately selected object key
is `0x504b000000000000 | page`; reading it does not install or overwrite packages.

`create` imports an already validated Doc8 into disjoint staging, preserving
every inner byte and explicitly marking all package provenance Unknown. It is
not the transition used to update an existing workspace: that would erase old
known rows. `validate` checks the original document, execution identities and
learner events before package rows. Known rows bind the exact historical
revision, goal, domain, assumptions and actual request budget. The package's
current admitted exercise references1/2 require budget8. CRC and source/rights
spans bind the original immutable edition; CRC is not authentication or a rights
grant.

`captureSelection` requires the caller's explicit typed goal/revision selection
and a canceled/consumed outstanding checker. It revalidates the entire actual
package; prose cannot select a mathematical goal. `snapshotSelection` copies the
exact applicable current binding before a real request. A changed revision,
goal, domain, assumption or request budget cannot use stale package provenance.

`stageRefresh` preserves every old semantic/execution attempt, known/Unknown
binding and ordered learner-event prefix while staging an edit or hint.
`stageCompleted` accepts exactly one new Doc8 attempt and the exact retained
selection snapshot, current Protocol7 origin/request and declared resource
budget. It records provenance only after the original admitted completion.
`stageUnknownSelection` clears only current provenance for an explicit builtin
or resource override. `stageCompletedUnknown` adds one actual builtin attempt
with zero package metadata while retaining earlier known rows. Unsupported
package goals, exhausted bounded resources, malformed records and absent/stale
selection retain their distinct errors.

All transition inputs remain immutable through their Action; target staging is
owned, aligned, bounded and disjoint from the input records. Preflight failures
do not publish bytes. Staging failures retain their actual written prefix and
error, leaving active input untouched; no memory rollback is promised. The
staging magic stays zero until completion. The integrating Notebook must adopt
only successful staging, keep the submitted binding and Save source immutable
until terminal consumption, and obtain its Saved acknowledgement from the
existing real Store barrier. Snapshots do not flush or finish these operations.

```sh
nix develop --no-write-lock-file --command python3 scripts/check_course_workspace.py \
  --output-dir build/courses/course-workspace-new \
  --package build/courses/task006-package-qualified-a5/package/arithmetic.lcp
```

The original component qualified in16.074 seconds: all67 consumed source inputs
remain exact, eight ordinary User2 roots lower to223 checked functions, and
LLVM O2 produces a freestanding RV64 object with no unresolved helpers. Actual
imported Actions exercise old Unknown history, new known history, explicit
builtin transitions, independently valid reordered learner events, actual
resource overrides and private staging faults. Hosted fixture preparation is
not a guest checker reply. Notebook package loading/rendering/checking, wrapper
Save/reopen and controller pixels still require their connected execution.
-->
