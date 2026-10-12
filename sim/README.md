# LemmaSim

Permanent virtual Lemma One. Task004 implements the native reference binding,
project-owned pen/paper devices and volatile/durable block transport, with a
compiled Lean notebook and isolated record service. Its bounded qualification
is recorded in the [evidence report](../docs/evidence/004-lemmasim-durable-ink.md)
and [checkpoint](../docs/plan/004-session-state.md); this does not finish the
canonical machine.

The canonical machine contract is [../LEMMA_MACHINE_CONTRACT.md](../LEMMA_MACHINE_CONTRACT.md). Historic tested QEMU `virt` boot profiles remain in [../docs/contracts/LEMMA_VM.md](../docs/contracts/LEMMA_VM.md).

The separately pinned QEMU `lemmasim-virt` runs the real M/S/U RV64 path.
Host pointer or recorded samples enter the pen FIFO and PLIC; guest drivers,
ink, rasterization and toolbar produce controller pixels. The record service
uses guest VirtIO writes and flush publication. The host never draws strokes,
parses live documents or reconstructs a notebook for recovery. Student,
Developer and Laboratory modes share that machine. Developer controls and
Laboratory faults operate outside guest authority.

The [profile](profiles/lemmasim-virt-0.1.0.json),
[descriptor/register ABI](../docs/contracts/004-devices-v1.md),
[block medium](../docs/contracts/004-block-medium-v1.md) and
[host boundary](host/README.md) bind discovery, state transitions, virtual
timing, failure and capture. The maintained command is `scripts/lemmasim`;
ordinary launch uses prepared tools/images and an existing persistent disk.
See the [runnable workflow](../README.md#task004-native-durable-notebook).

Headless and native display consume the same controller state. Mouse pressure
and refresh timing are synthetic. Automated GTK mouse capture, exact replay,
cold recovery and Busy reset were exercised with dedicated Xvfb 21.1.24 from
the pinned Nix input. Its optional recipe and executable SHA are retained in
the evidence archive; it is a test environment, not a runtime installer.
Manual visible interaction and physical tablet input are NOT_RUN. Physical conformance remains unverified;
networking, managed Lean runtime and mathematics/tutor remain unfinished.
Task006 adds the same-backend machine sessions below; these do not qualify
the complete machine. The future machine is governed by
[LEMMASIM.md](../docs/plan/LEMMASIM.md), not completed by this bounded notebook.

## Persistent machine sessions

`scripts/lemmasim session` uses the reusable RTL runtime or the matched QEMU
`lemma-silicon-fast` binding. The new `lemma-silicon-dev/0.2.0` profile uses
1650×2200 pixels and a checked 32MiB allocator pool within external simulation
RAM. It includes an explicitly synthetic digital panel sequencer. Historical
profiles retain their original geometry, quotas and meaning.

The command owns a long-lived machine with pause, bounded run, inspection,
raw input, snapshot, restore, recorded-suffix replay, warm reset and cold cycle.
The native window presents controller-produced pixels; toolbar operations,
ink, editing, page/document changes and Save still execute in the Lean guest.
Tk is available in the pinned host-only `tooling/lemmasim/session.nix` shell.
See [launch and lifecycle commands](../README.md#task006-persistent-machine-sessions),
the [state boundary](../docs/contracts/006-machine-session.md), and the
[RTL serialization inventory](../docs/contracts/006-rtl-runtime-v1.md).

Exact checkpoints are bound to their backend, implementation, guest and
discovery bytes. Restore uses an isolated medium and never overwrites the
source notebook. Live adapter handles disconnect on restore. Simulator
pause/resume are distinct from the still-unimplemented guest suspend service.
Nonvolatile recovery boot, companion transport, digital radio, browser/Wasm
and finished mathematics applications remain part of the destination.

## Native raw tablet transport

`python3 scripts/lemmasim_tablet.py --list` reads Linux input-device names without
reading their event streams. A selected real digitizer can feed an existing
persistent session:

```sh
python3 scripts/lemmasim_tablet.py --device /dev/input/eventN --session-dir build/lemmasim/my-session --record build/lemmasim/my-session/tablet-raw.jsonl
```

The current adapter supports Linux x86_64 evdev. It requires reported absolute
X/Y, contact and a pen/eraser tool; touchpads and ordinary mice are rejected.
The capability report includes actual ranges, pressure support, tool/buttons,
reported but untransported axes, and an explicit integer coordinate/pressure
normalization. Absent pressure is reported `UNAVAILABLE` and transports zero;
no contact pressure or tilt is invented. Pen-v1 cannot carry tilt. Full physical
registration/calibration and physical digitizer compatibility remain unverified.

Each `SYN_REPORT` transports one raw sample at the session's authoritative
virtual time. Kernel timestamps and complete raw frame events are preserved
separately; host wall time does not become guest time. `SYN_DROPPED` produces
an explicit guest stream-loss boundary, discards incomplete events, and queries
actual kernel state after the next synchronization. Disconnect/cancel also
produces stream loss, allowing the real guest to cancel/resynchronize a stroke.
Frames, capture size and lifetime are bounded, and capture paths are exclusive.
The adapter performs no gesture, notebook, ink, journal or mathematical work.
SIGTERM/SIGINT stop the input thread and attempt an explicit loss event before
closing; bounded RPCs and teardown expose a blocked or failed sink. An operating
system device handle is an external connection, not snapshot state. Snapshot
creation does not drain input or inject a cancellation. Restore/replay must
disconnect the live adapter before applying machine state; reconnection and
loss are separately recorded external decisions.

Eight independent host fixtures include a real byte-pipe with fragmented event
records, EOF cancellation, literal session admission and real child-process
SIGTERM teardown. A physical tablet was not present in the observed
Linux input inventory, so manual tablet writing/registration is **NOT_RUN**.
EOF fixtures are transport tests, not physical-input evidence.
