# LemmaSim host hardware boundary

`lemma_model.c/.h` implement only project-owned pen/paper register transitions,
FIFO/raw samples, controller target/visible RAM, bounded refresh completion and
contact-loss policy. They contain no notebook, brush, document codec or recovery.
`lemma_qemu.c` adapts those transitions to pinned QEMU MMIO, real PLIC lines,
virtual-clock timers, graphic console and input callbacks. `lemma_durable.c`
models volatile sector writes and explicit stable flushes through the real block
path; it has no guest record parser. These maintained C
files are **host-only** and never an input to any RV64 object/link. Files are
GPL-2.0-or-later to integrate with QEMU; upstream QEMU and pinned dependencies
retain their existing licenses. The target compiler/kernel/software remain Lean.

Prepare the separate host binary once:

```
nix-build tooling/lemmasim/qemu.nix -o build/lemmasim/qemu
```

The derivation uses the existing immutable nixpkgs and QEMU source pins, only
`riscv64-softmmu`, GTK/VNC, and explicit pinned build packages. It preserves the
historical pinned QEMU output. Build/install each require the actual executable
and named machine; an empty Nix output is an error. Added host inputs are pinned
by the existing nixpkgs lock: qemu-qmp0.0.6 (LGPL2-or-later/GPL2-only) for offline
configuration and pixman0.46.4 (MIT) for graphic console support. Native launch includes
`-machine lemmasim-virt -cpu rv64,smrnmi=false,smdbltrp=false -m 128M -smp 1
-bios none -nodefaults -global virtio-mmio.force-legacy=false`, an explicitly
attached block at`bus=virtio-mmio-bus.0`, and
`-rtc base=2026-10-10T00:00:00,clock=vm -seed 0x4c454d4d413031`. The maintained launch command lives above
this hardware layer; hardware tests do not substitute for a guest notebook.

Properties on QOM type`lemma-paper-pen`:

* `width/height`: runtime screen geometry; default1650×2200.
* `pressure-max`: default4095, synthetic/raw capability.
* `raw-input`: optional fixed72-byte little-endian raw sample stream, scheduled
  at guest10MHz ticks through the same controller FIFO.
* `raw-output`: **new** file capturing every external ingress record in that
  same source schema, including rejected samples. Controller sequence/epoch
  are separately assigned and observable; capture does not bypass loss.
* `trace-file`: optional **new** file for normalized virtual-time hardware events.
* read-only `device-state`: JSON string for pen FIFO/loss/epoch and controller
  busy/completion plus packed target/visible SHA256 values. Use QMP`qom-get` on
  `/machine/lemma-hardware`; no guest memory modification.
* read-only `storage-state`: volatile-sector count/capacity and block write,
  flush and durable-flush counters. Document sequences remain guest state.

QEMU ordinary pointer events enter its input/replay system and then the modeled
FIFO. Mouse pressure is half-range and explicitly Synthetic. No physical pressure
input has been exercised. Native display presents the controller's visible RAM;
headless screendump uses the same graphic console. Frontend rendering never owns
strokes or pages. Standard QMP stop/cont and system_reset are external Developer
controls. Whole-machine snapshots are unsupported by this adapter; CPU/RAM-only
save state cannot be advertised as a coherent snapshot.
Native replay uses QEMU's recorded input; feeding captured raw-output a second
time would duplicate ingress. Raw-file sessions preserve their scheduled input
as an explicit identity-bound source. See the
[stable/volatile backend](../../docs/contracts/004-block-medium-v1.md).

```
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/lemmasim -v
python3 sim/host/check_qemu_devices.py --qemu build/lemmasim/qemu/bin/qemu-system-riscv64 --output build/lemmasim/new-device-check
python3 sim/host/check_qemu_medium.py --qemu build/lemmasim/qemu/bin/qemu-system-riscv64 --output build/lemmasim/new-medium-check
python3 sim/host/check_qemu_replay.py --qemu build/lemmasim/qemu/bin/qemu-system-riscv64 --image PATH_TO_COMPILED_LEAN_GUEST --output build/lemmasim/new-transport-replay
```

Literal host boundary checks are independently specified assertions, including
faulty busy/loss source variants that must fail them. Actual QEMU checking observes
registers, real PLIC pending lines and virtual-time completion. These are hardware
observations, distinct from real compiled guest drivers, notebook persistence,
replay acceptance and physical conformance. See the normative
[device ABI](../../docs/contracts/004-devices-v1.md) and
[profile](../../docs/contracts/004-machine-profile-0.1.0.md).

The transport replay checker records actual native pointer ingress and compares
raw bytes, device events/state, block observations, supplied guest serial output,
controller pixels and stable media after a replay breakpoint at the recorded
instruction count. A bringup guest with blank pixels passes only that transport
scope; notebook ink/edit/recovery acceptance remains necessary. The pinned
QEMU record/replay configuration uses `shift=3,align=off,sleep=on`: its
`icount_account_warp_timer` does not process asynchronous replay events with
`sleep=off`. Record/replay clock and warp inputs belong to the session identity.

Read-only initial boot observations can be exported while the machine starts
with `-S`: QMP `pmemsave` at `0x10010400`, length256 yields the binary descriptor.
Its words26/27 give the actual reset DTB address/length for a second `pmemsave`.
The exporter must validate descriptor magic/version/checksum and bounded DTB
header/length before reading that region. This captures actual handed boot bytes,
without turning a host manifest into guest authority.
