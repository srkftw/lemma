<!--
# Current development entry point

The current assignment is reliable incremental builds, validated reuse and cheaper
agent resumption. Start with `python3 scripts/dev_status.py`; use `--json` for the
complete source/worktree identity, reviewed verification boundaries, evidence,
invalidation reasons, job ownership, budgets and next action. Status writes
nothing and executes no build or test.

Normal kernel and independent user CLI builds reuse validated action results.
Enter the pinned environment with `nix develop --no-write-lock-file`, then use an
unused development output directory:

```sh
./scripts/build-kernel.sh --configuration lemmasim-silicon-bytes-bulk-notebook \
  --stage supervisor --opt-level O2 --output-dir build/kernel/dev-notebook-NEW
./scripts/build-user.sh --configuration lemmasim-silicon-bytes-bulk-notebook \
  --image-key notebook --opt-level O2 --output-dir build/user/dev-notebook-NEW
python3 scripts/dev_status.py --build build/kernel/dev-notebook-NEW
```

The incremental production campaign (`scripts/check_incremental_builds.py`)
defaults to `lemmasim-silicon-bytes-bulk-notebook`; the focused execution checker
uses canonical geometry and `lemma-silicon-dev/0.3.0`. This is a bounded notebook integration, not a claim that
all later Task006 deployments or backends are qualified. `--cache-dir <path>`
selects another shared local cache; the default is `build/action-cache`.
`--fresh` bypasses action reads and resets the protected private Lake compiled
state for that build. `--clean` resets only the selected output directory; it
does not request fresh compilation. Preserve retained evidence directories.
A new output directory may contain copied cached payloads; their producer and
commands remain original and their compilation remains reused.

Programmatic `build()` APIs default conservatively to fresh production, preserving
existing qualification callers. Normal CLIs opt into validated reuse. Existing
fresh checkers keep their fresh defaults; the explicit campaign override is:

```sh
LEMMA_BUILD_FRESH=1 ./scripts/check-core0.sh --clean \
  --work-dir build/core0/qualification-NEW
```

For a fresh notebook build, add `--fresh` to the kernel command above; run its
ordinary audit separately. A cold host compiler and a new cold guest are separate
observations. The measured integration reused validated host Lake imports while
executing every target action in the fresh phase:

| Canonical O2 production | Seconds | Fresh target actions | Reused target actions |
| --- | ---: | ---: | ---: |
| Fresh target production | 121.192 | 32 | 0 |
| Warm production | 11.701 | 0 | 32 |
| Selected Save response mutation | 49.544 | 8 | 24 |

Each phase also ran two protected incremental Lake preparations. Actual warm
process tracing found no Lean elaboration, LLVM compilation or linking. Audits
executed separately (172.061 / 134.388 / 108.231 seconds respectively). Both
positive images passed new canonical QEMU writing, Save, independent cold
recovery and failed-FLUSH/cold scenarios. The mutation produced guest error234
and no later Saved acknowledgement. See the [scoped report](../evidence/incremental-builds-v1.json)
for exact original producer identities, command traces, retained failures,
other measurements and the final source-bound host-check receipt location.

Actual notebook behavior is separate from compilation. The focused public-session
checker consumes an explicitly supplied built guest, validated native QEMU bundle
and an actual guest-initialized empty medium. It copies private medium bytes, admits
real raw pen events, Saves, starts new cold guests and tests failed first FLUSH:

```sh
python3 scripts/check_incremental_notebook.py --work-dir build/incremental/notebook-NEW \
  --native-bundle NATIVE_BUNDLE --guest-build GUEST_BUILD \
  --guest-source-root EXACT_SOURCE_ROOT --initial-medium ACKNOWLEDGED_EMPTY_MEDIUM
```

Those uppercase arguments identify actual admitted inputs; select them from the
retained campaign report. The checker performs no compilation or machine-state
restore. Its whole deadline is 1200 host seconds, each public operation at most
300 host seconds, and boot/action bounds are 30 virtual seconds each. Earlier
budgets and failures retain their original meanings.

Inspect or clean ephemeral storage with bounded commands:

```sh
python3 scripts/action_cache.py --cache-dir build/action-cache --limit 12
python3 scripts/action_cache.py --cache-dir build/action-cache --cleanup \
  --limit 100 --older-than-seconds 86400 --pin-action RETAINED_ACTION_KEY
```

Ordinary CI shares only a successful `tests/kernel` host receipt from metadata
with A–E. `scripts/host_prerequisites.py` binds the actual nonempty, unskipped
corpus, log, complete nonignored source inventory, Python pin, controlled
environment and checkout path. Original commit/tree remain producer provenance;
byte-identical publication commits do not invalidate it. Changed source or policy
still invalidates the receipt. Its child tool PATH is closed to immutable Nix
Python and Git; CI obtains Git through the locked `nix shell --inputs-from .
nixpkgs#git` route without changing the target toolchain. A–E executes Lake and every target qualification
action freshly. The aggregate workflow rejects skipped required jobs.

Cleanup respects active actions and explicit pins. Published claims must own their
producer receipts, output copies and source archives outside the ephemeral cache.
Do not edit cached objects. Materialized outputs are private copies.

`scripts/verification_routes.json` declares baseline claims, changed-input
boundaries, consumer edges and an optional explicit `evidence_paths` registry.
The baseline's `incremental-canonical-qemu` claim is the focused O2 canonical
scenario. The distinct `notebook-qemu` claim still requires the broader historical
writing/O0/O2 checker where a changed shared boundary requires it; a focused PASS
cannot satisfy that broader claim. The registry contains exact paths or
`{path, claim, kind}` entries; it performs no wildcard PASS search. A missing registered assessment is unavailable. An omitted
required claim is pending. Hash-validated receipts distinguish fresh-pass,
reused, pending, failed and unavailable. `--campaign <id>` labels only matching
explicit fresh campaign receipts fresh-pass; otherwise retained PASS is reused.
Use `--evidence <path>` for another explicit assessment, `--changed <path>`
repeatedly for scoped changes, or `--since <revision>` to override the objective's
configured `comparison_base`. Default routing includes committed changes from that
baseline plus dirty paths; committing identical file bytes cannot erase required checks.

`--build <directory>` validates the real action journal, original producer
identities, materialized outputs, current input/tool/recipe identities, host
Python, execution/dependency helpers and both current audit/admission validators. It reports original fresh/reused action counts
as production only. A cached artifact never satisfies an execution claim. The
routing model selects verification; exact consumed-input closures select action
keys. Unknown changed paths need review. Contracts and generated authorities are
inputs where declared. Backend, browser, source-negative, optimization and physical
requirements retain their separate scopes. A pure observer can revalidate retained
raw observations only by actually running and writing a new bound assessment.

An optional `--job-receipt <path>` explicitly adds an external active-job receipt.
Its `owner` requires boot ID, PID and kernel start ticks. Cache registrations use
the same ownership checks. Terminal receipts remain historical; a recycled PID
cannot invalidate observed cleanup. Unknown simulator/browser owners remain
unverified and are never inferred from a PID alone. Status never stops processes.
Human output is bounded by `--max-items 12`; JSON retains the complete assessment.

Assessment schema `lemma-dev-evidence/v1` contains `claim`, `kind` (production,
execution or validation), `route` (fresh, reused or revalidated), `result`, optional
`campaign`, and original `producer` (`source_commit`, `executed_at`, actual
`command`). `receipt` binds its original path/SHA256. Nonempty `inputs`, `outputs`
and current `validator` inventories map repository-relative paths to SHA256s.
Execution `context` declares backend, profile, scenario, driver, fixtures,
initial_state, input_events, seeds, fault_schedule and limits_environment. Retained
FAILs remain failed; missing or malformed evidence cannot pass. These assessments
supplement ordered-command and archived-source audits.

The historical [Task006 checkpoint](006-session-state.md) retains its exact source
identities, unfinished subsystems, live session phase budgets and original
failures. Read the relevant section when its dependency is needed. Do not restart
historical workloads to edit a report or extend a live admission deadline.
Physical conformance remains UNVERIFIED.

-->
