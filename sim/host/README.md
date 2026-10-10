# LemmaSim host hardware boundary

`lemma_model.c/.h` implement only project-owned pen/paper register transitions,
FIFO/raw samples, controller target/visible RAM, bounded refresh completion and
contact-loss policy. They contain no notebook, brush, document codec or recovery.
`lemma_qemu.c` adapts those transitions to pinned QEMU MMIO, real PLIC lines,
virtual-clock timers, graphic console and input callbacks. These maintained C
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
and named machine; an empty Nix output is an error. Native launch includes
`-machine lemmasim-virt -cpu rv64,smrnmi=false,smdbltrp=false -m 128M -smp 1
-bios none -nodefaults -global virtio-mmio.force-legacy=false`, an explicitly
attached block at`bus=virtio-mmio-bus.0`, and
`-rtc base=2026-10-10T00:00:00,clock=vm`. The maintained launch command lives above
this hardware layer; hardware tests do not substitute for a guest notebook.

Properties on QOM type`lemma-paper-pen`:

* `width/height`: runtime screen geometry; default1650×2200.
* `pressure-max`: default4095, synthetic/raw capability.
* `raw-input`: optional fixed72-byte little-endian raw sample stream, scheduled
  at guest10MHz ticks through the same controller FIFO.
* `trace-file`: optional **new** file for normalized virtual-time hardware events.
* read-only `device-state`: JSON string for pen FIFO/loss/epoch and controller
  busy/completion plus packed target/visible SHA256 values. Use QMP`qom-get` on
  the actual device path discovered by`qom-list`; no guest memory modification.

QEMU ordinary pointer events enter its input/replay system and then the modeled
FIFO. Mouse pressure is half-range and explicitly Synthetic. No physical pressure
input has been exercised. Native display presents the controller's visible RAM;
headless screendump uses the same graphic console. Frontend rendering never owns
strokes or pages. Standard QMP stop/cont and system_reset are external Developer
controls. Whole-machine snapshots are unsupported by this adapter; CPU/RAM-only
save state cannot be advertised as a coherent snapshot.

```
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/lemmasim -v
python3 sim/host/check_qemu_devices.py --qemu build/lemmasim/qemu/bin/qemu-system-riscv64 --output build/lemmasim/new-device-check
```

Literal host boundary checks are independently specified assertions, including
faulty busy/loss source variants that must fail them. Actual QEMU checking observes
registers, real PLIC pending lines and virtual-time completion. These are hardware
observations, distinct from real compiled guest drivers, notebook persistence,
replay acceptance and physical conformance. See the normative
[device ABI](../../docs/contracts/004-devices-v1.md) and
[profile](../../docs/contracts/004-machine-profile-0.1.0.md).
