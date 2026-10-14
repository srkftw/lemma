<!--
# CommonOFDM same-machine binding0.12 / Kernel8

The scoped native transaction and exact private continuation are qualified by
`docs/evidence/006-wifi-common-same-machine.json`. This is the aligned common
legacy20MHz BPSK/rate1/2 DATA construction dependency of Wi-Fi6. HE, acquisition,
complete preamble/PLCP, MAC/security/association, RF and physical conformance
remain unfinished. The earlier07402f5 leaf coding/loss/corruption evidence keeps
its own scope. Integrated loss/corruption recovery is not qualified here.

The opt-in hardware profile inherits USBWire11, Paper3,1650x2200 Gray4,
128MiB external simulation RAM, the32MiB/8192-frame owned pool and100MHz clock.
Its registered complex sample boundary is20Msample/s. BootNV is disabled. The
new aperture is0x10013000..0x100133ff with PLIC source18. Descriptor ABI13/features47
adds CommonOFDM featurebit32 to USBWire11's15; BootNV bit16 stays clear. Existing
profiles and immutable binaries retain their versioned identities. Inherited
USB11 sample-jitter limitations remain open; radio digital evidence is not RF.

core0-kernel-v0.8 inherits Kernel6 ISA/scalar/Action/UART and physical memory
semantics, adding only aligned64-bit accesses to that Wi-Fi aperture and the
32-bit PLIC priority18 word0x0c000048..0x0c00004b. Priority17, the NV aperture and
boot scratch remain rejected; Kernel7 retains its separate NV authority. The
versioned default-false CommonOFDM startup grants exactly one1KiB NAPOT PMPentry8,
RW/NX/unlocked, with actual address/configuration readback and mismatch-to-fatal
checks. Readbacks at0x804e01f0/1f8 precede device MMIO and queue initialization.
The ProductNV selector is mutually exclusive. Retained Wire11 and Product10
startup.S bytes were independently re-rendered unchanged; all11 old generated
bindings were checked unchanged. No new ordinary source syntax is admitted.

Both endpoints are registered circuitry inside the existing CVW/LemmaSim
machine. Host transport supplies raw external peer PIO writes and signed16-bit
I/Q sample strobes. Expected length/seed and aligned DATA start remain external
metadata; the host does not encode/decode packets, access chip MMIO, construct
guest buffers or ACK the guest. The peer's immutable decoded heads are observed
before explicit raw peer-side ACK writes. No competing emulator is introduced.

Raw events are `cycle wifi-peer-pio offset value`, `cycle wifi-rx Ibits Qbits`
and `cycle wifi-coex 0|1`. Admission is profile-gated and validated before input
mutation. One raw peer write is consumed per clock from a32-entry ordered queue.
Signed sample values use their unsigned16-bit two's-complement bit patterns.
Simultaneous raw and pending peer-wire samples reject. These commands are a
digital environment boundary, not an on-air MAC or RF interface.

Compiled Lean owns a four-slot packet queue at0x804e0000..0x804e01ff. Enqueue
requires kernel owner1, live generation, data purpose, bounded offset/length,
seed1..127 and an initially unpinned frame. It retains one pin before publishing
an entry; that pin blocks release. Real TXevent1/inactive hardware completion
releases the pin before caller release. Failed metadata mutations quarantine
state. Broader cancellation/fault recovery and a User radio API remain open.
RX copies a verified immutable hardware head into a live owned data frame before
head ACK, frame release and actual PLIC completion. The probe uses polled real
PLIC18 claim/completion; S-mode external interrupt trap servicing is not claimed.

Actual guest execution reached an active four-buffer/pin1/pending-IQ cut at
12,175,051 clocks within the original20M/300s bound. It transmitted eight ordered
16-byte payloads, received the reverse16-byte peer payload into owned RAM, issued
nine real PLIC18 claim/completions and returned every owned frame. An independent
final scan checked all8192 owner and pin cells, pool availability8192 and queue
completed8/count0/active0. These are actual RV64/RTL observations, not host models.

Native wrapper9 preserves all ordinary machine/CPU/RAM/display/device state,
raw event order, peer PIO queue, pending signed I/Q samples, coexistence/input
phase and both generated endpoint coding/DFT/Viterbi states. Restoration validates
complete candidate bytes before mutation and creates private own-backend forks.
Two forks from the active cut ran exactly1,000,003 clocks to13,175,054 within120s;
their entire145,215,438-byte snapshots and external UART suffixes matched. No
field masks, tolerance, migration, reset, flush, drain or clean boundary was used.
The original cut stayed unchanged, and the peer's TXevent1 remained retained.
A corrected public checker reproduced the same final complete snapshot hash.
Original event-length and observer failures remain retained with separate repairs.

Native build uses600s/two jobs; target build uses300s/command; actual initial
CPU has20M clocks/300s, and continuation has1,000,003 clocks/120s. The public
`check_wifi_common_guest.py` defaults to those bounds and refuses existing output.
Its `--resume-observation` verifies the retained cut, immutable audited executable
ELF/ROM bytes and actual queue owner/purpose/generation/pins before creating owners.
The first observer omitted25 inherited BLE scalar words; the corrected observation
read the same cut without CPU advance, prefix repetition or input reinjection.

Fast/QEMU/browser profile12 counterparts, notebook/companion radio integration,
complete power/reset/coexistence service and physical timing are NOT_RUN. This
scoped native result does not establish complete Wi-Fi6 or process signoff.
-->
