<!--
# USB decoded-packet backing host policy3

This additive hosted Lean policy retains `USBHOST/2 PACKET_BYTES_DEV` and
`LMUSBRW2`. These identify the raw packet transport and capture format. The
prepared host identity separately declares `lemma-usb-host-dev/3` and
`lemma-usb-pending-policy/3`; it binds the actual Lean sources, generated host
objects, executable and pinned host tools. Historical policy2 observations keep
their original identities and failures.

The guest reaches USB configuration through real SETUP, data and status stages.
The host transfers CRC-checked packet bytes and a specified opaque backing
protocol to an independent hosted Lean durable peer. It never interprets guest
documents, journal roots, ink or mathematical evidence. This is a decoded-packet
development boundary, with physical USB encoding and full USB conformance still
open. Attached USB whole-machine checkpoints remain explicitly rejected while
the hosted policy and pending transport are not serialized.

A valid bulk OUT NAK means the controller's finite receive slot is occupied.
Policy3 retains the same fragment bytes and DATA toggle, schedules an explicit
100,000-machine-clock wait and retries. NAK does not consume the three-attempt
malformed/error reply limit. A shared budget permits at most 100,000,000 wait
clocks across the entire bounded opaque reply, including all of its fragments.
It is not restarted per fragment. Raw packet transfers add actual virtual time;
the independent scenario retains its separate 120,000,000-cycle and 900-second
bounds. STALL is terminal. Only an actual ACK advances the toggle/fragment.
Budget exhaustion, disconnect or error never creates a guest success receipt.
The peer's actual barrier and persistent receipt/deduplication state continue to
control durable success. Lost responses are reconciled with the same retained
writer/transaction identity before a receipt is delivered.

Explicit archived guest reuse is separate from archived native reuse. USB6
`--guest-source-root` requires an explicit audited guest build when preparing a
registry. Its complete original `lemma-usb-guest-source-archive/1` sidecar binds
every source input, source commit and dirty inventory, build/provenance/image,
tool versions and Lean source realization. Validation rejects missing, surplus,
changed or symlinked archived files and duplicate metadata. It independently
enumerates the complete archived input tree with the ordinary build validator,
checks all original generated artifacts and requires the original strict audit
to pass for this exact image/configuration. It checks the realized Lean UInt
source and archived toolchain declaration, plus immutable original tool paths,
versions and executable hashes. The new association binds the original audit
hash and all these identities without modifying the original sidecar. A registry
prepared with this option requires the explicit same source root on launch;
there is no fallback to changed current target sources. Default preparation
still requires current sources. This is unchanged genuine guest execution with
a new host policy, not fresh target compilation.

The implemented preparation and actual initialization check are:

```sh
nix develop --no-write-lock-file --command python3 scripts/lemmasim_usb.py build \
  --output-dir build/usb/NEW-HOST
nix develop --no-write-lock-file --command ./scripts/lemmasim build \
  --backend rtl --profile lemma-silicon-dev/0.6.0 --workload initializer \
  --guest-build build/kernel/task006-usb-initialize-a5 \
  --guest-source-root build/kernel/task006-usb-initialize-a5/consumed-source-root \
  --rtl-build build/silicon/task006-usb-runtime-a4 \
  --rtl-source-root build/silicon/task006-usb-runtime-a4/consumed-source-root
python3 scripts/check_guest_usb_store.py \
  --host-prepared build/usb/NEW-HOST/prepared.json \
  --guest-source-root build/kernel/task006-usb-initialize-a5/consumed-source-root \
  --rtl-source-root build/silicon/task006-usb-runtime-a4/consumed-source-root \
  --work-dir build/usb/NEW-STORE --lost-write-ack
```

The check starts an independent persistent peer. It requests a lost reply after
the first persisted guest format write, then restarts that peer and checks
receipt reconciliation, guest acknowledgment, actual opaque transaction order,
and journal root bytes with an independent oracle. It fails immediately when
the actual initializer task exits unsuccessfully, preserving its status and
captured guest output. Results qualify only the scenarios actually observed;
initialization is distinct from notebook Ready, Save and cold document recovery.

The retained policy3 Store scenario completed at 56,000,000 target cycles in
339.090 host seconds, within those unchanged bounds. The actual guest issued two
mount reads followed by three write/barrier pairs. The first write's reply was
lost after peer persistence; restart/reconciliation produced six durable effects
without duplication before the guest's initialization acknowledgment. Both
root-slot bytes passed the independent journal oracle. The original Power-v1
configuration failure and policy2 NAK failure remain separate retained FAILs.
See `docs/evidence/006-usb-store-pending-policy3.json` for exact source, tool,
artifact and observation identities. Peak RSS was not measured in this campaign.

Focused qualifiers use private task-owned copies and do not alter the original
guest/native artifacts:

```sh
python3 scripts/check_guest_source_archive.py \
  --guest-build build/kernel/task006-usb-initialize-a5 \
  --guest-source-root build/kernel/task006-usb-initialize-a5/consumed-source-root \
  --work-dir build/usb/NEW-GUEST-ARCHIVE-CHECK
python3 -m unittest discover -s tests/lemmasim -p '*source_archive.py' -v
nix develop --no-write-lock-file --command env \
  LEAN_PATH=build/usb/NEW-HOST:build/usb/NEW-HOST/companion \
  LEMMA_USB_PENDING_WORK=build/usb/NEW-PENDING-FIXTURE \
  lake env lean tests/usb/PendingPolicy.lean
```

-->
