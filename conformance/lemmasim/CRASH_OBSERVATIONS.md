<!--
# Notebook device-fault observations

`check_crash_workflow.py` is an independent offline observer. It imports the
independent `store_oracle.py`, never the production store engine or notebook
codec. It cannot repair media, feed recovered objects to a guest, draw pixels,
or substitute for a new CPU/guest boot. Its result is one storage/provenance
observation within the Task 004 acceptance matrix. A separate cold guest launch,
page navigation through raw input, and controller-visible comparison are still
required. Synthetic unit examples are not actual QEMU fault evidence.

Before a fault family, stop a successful guest run after its final `0x421` ACK,
copy its stable medium, and export it with `inspect_notebook.py`. Retain its
actual serial output. The export's independently observed committed sequence
must equal that final ACK; a Pending/Failed state or unacknowledged tail cannot
be relabeled as an acknowledged baseline. Use fresh copies of that baseline
for the reference and every fault case. Do not mutate the original image.

Create a successful append reference and a successful Save/checkpoint reference
through the ordinary guest workflow. Name candidate boundaries from their real
medium writes and independently recovered record positions:

```sh
python3 conformance/lemmasim/check_crash_workflow.py --plan \
  --baseline-export BASELINE_EXPORT \
  --reference-disk SUCCESSFUL_COPY --reference-media SUCCESSFUL_MEDIA_TRACE \
  --output build/lemmasim/new-fault-plan.json
```

The plan contains case templates, not a PASS. Only latest committed record
positions are named; superseded mutable revisions and no-write mount/close
flushes remain explicitly unnamed. Choose a template and add `fault` with one
of `cut-before-flush`, `cut-after-flush`, `tear-flush`, or `fail-flush`. These are
exact one-based filter ordinals. Run the real machine with that filter option,
retain its actual disk, media/device traces and guest output, and then observe:

```sh
python3 conformance/lemmasim/check_crash_workflow.py \
  --baseline-export BASELINE_EXPORT --baseline-serial BASELINE_SERIAL \
  --disk FAULT_COPY --serial FAULT_SERIAL \
  --input RAW_FIXTURE --input-manifest RAW_MANIFEST --devices FAULT_DEVICE_TRACE \
  --media FAULT_MEDIA_TRACE --case SELECTED_CASE_JSON \
  --output build/lemmasim/new-crash-observation.json
```

Append templates record the exact header, body-sector count and publication
position. A payload flush must contain exactly the header/body and next-tail
sentinel writes; a publication flush must contain exactly its publication sector.
Checkpoint templates name the actual inactive segment and the alternating root
slot. With the production v1 initialization (both generation-1 roots, slot zero
selected), the next root write is byte offset `(oldGeneration % 2) * 512`.
The old root and segment must remain available. The checker independently
requires the actual fault event at the named ordinal. A torn case additionally
requires the recorded first dirty sector's 256-byte new/256-byte old write.

| Named phase and device cut | Meaning |
| --- | --- |
| Payload, cut before flush | Payload remains volatile; prior ACK survives |
| Payload, cut after flush | Payload stable, publication still absent |
| Publication, cut before flush | Publication queued, final barrier absent |
| Publication, cut after flush | Final publication durable, completion/ACK not yet delivered |
| Publication, torn flush | Publication is absent or wholly valid; zero trailing fields can permit whole recovery |
| Payload, torn flush | Stable header with missing body/publication cannot expose a partial transaction |
| Payload/publication, failed flush | Real device error reaches guest `0x424` |
| Checkpoint segment, cut before/after flush | Old root continues to govern until replacement root is durable |
| Checkpoint root, cut before/after or torn flush | Independently valid old/new root governs; prior ACK bytes survive |

The observer compares baseline immutable chunks byte-for-byte, requires all old
page entries in order and prior editing history, independently checks page flags
against applied edits, and rejects an ACK beyond stable recovered sequence or
before its catalog/index publication. Every new ink sample must be an exact
member of the actual FIFO ingress mapped from the raw fixture, with one original
stroke action and calibration/lifecycle preserved. A complete valid but
unacknowledged record may recover. Valid orphan or unfinished chunks are allowed;
they are reported as chunks, never invented completed strokes. A cut can end
input before its scheduled suffix: the observed prefix and unobserved suffix
are explicit and do not establish full-session replay.

These fault cases append or checkpoint. Undo/redo/erase may legitimately change
an applied edit cursor or discard a redo suffix, so they have their own complete
workflow/recovery checker rather than weakening the append fault invariant.
A checkpoint ACK with unchanged logical sequence still requires a newer durable
root generation. Unknown/damaged nonempty media fail; no formatting fallback is
provided. Failed checks retain a new FAIL JSON and exit nonzero.

Run the compact literal checker boundaries with:

```sh
python3 -m unittest discover -s tests/lemmasim \
  -p 'test_crash_workflow_observer.py' -v
```

The maintained campaign drives both references, then nine append barriers/error
cases and six checkpoint barriers/error cases, with a fresh disk copy and a real
cold guest process for every case. It takes build metadata and the executable
identity explicitly; it does not build dependencies during a launch. The caller
must identify whether those inputs are development or the final committed
candidate. Its Python entry point is
`campaign(metadata, qemu, baseline_disk, baseline_export, baseline_serial, out)`
in `scripts/check_lemmasim_faults.py`; the same file exposes a CLI:

```sh
python3 scripts/check_lemmasim_faults.py --metadata PREPARED_BUILD_JSON \
  --qemu PINNED_LEMMASIM_QEMU --baseline-disk ACKNOWLEDGED_DISK_COPY \
  --baseline-export BASELINE_EXPORT --baseline-serial BASELINE_SERIAL \
  --output build/lemmasim/new-device-fault-campaign
```

The baseline serial directory must also contain its actual `visible.ppm`. All
references and fault runs have bounded waits and are reaped through the native
launch helper. The original baseline hash is checked again after completion.
The campaign records explicit FAIL on the first failed observation; remaining
cases cannot yield an ordinary PASS. Cold comparison uses stable committed bytes
and either the baseline or successful appended page's real controller pixels,
according to the independently observed whole page publication. An orphan
unpublished chunk never changes that expected page. No host pixel production or
live recovery is involved.

A v1 root/publication has all nonzero fields and checksums in its first 104 bytes.
A cut after the model writes the first 256 bytes may therefore leave a wholly
valid publication when the old trailing bytes were also zero. That admitted
outcome is reported honestly. The separate torn-payload case writes a new
header while leaving its body/publication incomplete; the store observer must
retain the acknowledged baseline and refuse the incomplete append suffix.

The maintained publication-barrier regression is
`scripts/check_lemmasim_publication_negative.py`. It requires a positive image
whose actual clean build provenance matches the supplied committed candidate.
It creates a fresh detached experimental checkout and changes exactly one Lean
branch: completion of publication write (phase 20) calls `acknowledged` instead
of requesting the real final flush (phase 21). The genuine pinned Lean/LLVM/RV64
pipeline builds that quarantined image. Its source patch, original build
provenance, and separate `UNQUALIFIED_NEGATIVE_ONLY` label are retained; the
altered implementation is never imported into the trusted checkout.

```sh
python3 scripts/check_lemmasim_publication_negative.py \
  --metadata PREPARED_BUILD_JSON --qemu PINNED_LEMMASIM_QEMU \
  --candidate-commit EXACT_CLEAN_BUILD_COMMIT \
  --baseline-disk ACKNOWLEDGED_DISK_COPY --baseline-export BASELINE_EXPORT \
  --baseline-serial BASELINE_SERIAL --output build/lemmasim/new-barrier-regression
```

Both positive and negative consume the same ordinary one-stroke raw device
input on fresh copies. After the actual guest `0x421` record, maintained
read-only inspection captures pending medium state, then Laboratory controls
cut the running whole process with SIGKILL. The owner launch thread reaps the process. There is no normal
QMP stop, quit, reset or cleanup flush before that cut. QEMU stop can
flush block nodes and would mask this particular ordering error. The independent store oracle must
retain the positive ACK and reject the negative's ACK beyond stable recovery.
The negative observer's result remains **FAIL**; the enclosing regression may
report PASS only when that real behavioral failure was observed and rejected,
with previously acknowledged ink preserved in both cases. This tests a storage
ordering bug, not a changed-source hash. Final candidate execution is separate
from development experiments using earlier explicitly identified images.

-->
