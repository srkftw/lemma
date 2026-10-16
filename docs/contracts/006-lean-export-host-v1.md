# Lean export host resources, version 1

`lemma-lean-export-host/1` records an explicit `-j2` worker-pool argument on
kernel and independent-user export commands. The public build interfaces are
unchanged. Actual command evidence contains `lake env lean -j2 SOURCE.lean`;
the launcher does not rewrite an already recorded command. Genuine elaboration,
checked lowering, LLVM arguments, target helpers and link provenance retain
their existing contracts. This policy adds no target language feature or runtime.

The complete consumed-source inventory includes `scripts/lean_export_host.py`.
Its presence requires the exact versioned policy object in provenance. Missing,
unknown, malformed or inconsistent policy/argv evidence rejects. A current
builder missing its required helper rejects instead of silently selecting old
arguments. All selected export roots, ordering, pinned executables and working
directories remain checked independently.

Historical source archives without this helper retain their original commands
and absent/null host policy, including construction through the explicit
archived-source workspace. Supplying a new policy to that old inventory rejects.
The original Core0 build driver is unchanged. Earlier artifact identities and
failure reports retain their meanings.

Two Lean workers are not a two-thread process limit: the runtime can also use
GC and other host threads. Command deadlines, address-space limits, aggregate
RSS limits and cleanup supervision remain separate. `LEAN_NUM_THREADS=2` and
Lake's build arguments alone did not cap a separately launched `lake env lean`
process in the retained Linux diagnostic; explicit `-j2` is load-bearing here.
This is a host build policy, not a guest cycle, processor timing or execution
memory guarantee.

Focused checks:

```sh
python3 -m unittest discover -s tests/kernel -p test_lean_export_host.py -v
python3 -m unittest discover -s tests/kernel -p test_multi_image_audit.py -v
```

The actual preceding normal/initializer command corpora pass the new validator
with their original arguments. New-policy whole-image compilation/audits and
resource measurements require their own results; these tests alone do not
establish those outcomes.
