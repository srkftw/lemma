# Fast raw UART ingress1

This opt-in host transport connects the existing canonical fast machine's
16550 receive callback to Developer/Laboratory raw UART events. It does not
parse course packets, install packages, modify documents or produce guest
receipts. Those operations remain in the same audited Lean RV64 guest.
The base QEMU derivation and historical prepared binaries remain unchanged.

`LEMMA_FAST_RAW_UART=1` selects `tooling/lemmasim/qemu_uart.nix` during explicit
fast build/preparation and chooses a separate `fast-uart1-prepared-0.3.0.json`.
Other values/profiles reject. A packaged session negotiates the actual backend
property at reset and before target clocks; it does not depend on the build
environment variable. Old binaries retain adapter4. A backend advertising
`lemma-raw-uart/1` uses adapter5 and is enabled only with a reset paused canonical
CPU and its real, empty `serial0` frontend. This enables an external byte port;
it does not configure the guest UART, USB or any authentication state.

Each accepted request contains bounded virtual nanoseconds and nonempty even
hexadecimal bytes. The ingress owns at most65536 pending bytes. Malformed,
over-capacity, exhausted-counter, running-CPU and past-time requests reject
before any byte/count/timer mutation. Future requests are inserted by delivery
time; equal-time requests retain admission order and packet byte order.
The existing session raw-event recorder captures requests before execution
resumes. Admission means queued external input, never guest receipt or Saved.

At a due boundary the adapter asks `qemu_chr_be_can_write` and supplies one byte
through `qemu_chr_be_write`. The existing serial device performs register/FIFO/
interrupt behavior, and Lean reads it through ordinary guest instructions and
drivers. A full FIFO retains the remaining bytes. Polling offers are separated
by at least10 virtual nanoseconds, including across an empty-queue boundary.
Actual instruction-clock dispatch can be later; this is a declared fast
functional transport, not proof of RTL pipeline or UART timing parity.

Reset cancels the not-yet-offered queue and resets its polling phase; it does
not retry the byte stream. Standard serial reset independently resets its own
FIFO/IRQ state. The reset epoch and accepted/delivered/canceled byte totals are
maintained, with `accepted = delivered + canceled + pending`. Delivered means
accepted by the emulated serial frontend, not parsed by the guest. No packet
delivery or durable-success guarantee follows from these counters.

The opt-in device uses required state version4. Its complete byte/deadline ring,
head/count, enabled state, counters/reset epoch, earliest-next-offer phase and
timer expiration are mandatory fields. Missing state cannot be reconstructed as
an empty optional subsection. Timers are preallocated host references and rebound
through QEMU's timer VMState codec; raw pointers are never serialized. State
validation checks bounds, ordering, accounting and timer/phase consistency.
Saving does not feed/drain the queue. The existing serial VMState retains its
actual RX/TX FIFO/register/interrupt/timer state separately. Restore remains a
private candidate with isolated backing before replacing a live session.
The saved QEMU global lifecycle must be present and paused/prelaunch. The
opt-in loader applies that stored lifecycle through pinned valid transitions,
without CPU execution, reset, device drain or backing flush. Unsupported
terminal lifecycle states reject. The default historical loader is unchanged.
Inspection exposes pure receive capacity and actual first deadline/timer phase;
it never reads the guest's consuming receive-data register.

The pinned primary source is QEMU11.1.1 from the existing Nix derivation. Its
character frontend API requires capacity checks before receive writes. The
audited serial post-load setter restores FCR/trigger/IIR bits without flushing
the loaded RX FIFO; no additional serial-reset workaround is introduced here.
Tests must still exercise nonempty hardware FIFO and external queue states,
future delivery/phase, backpressure, reset cancellation and actual guest bytes.
Serialized-byte equality alone is insufficient.

The actual compiled backend passes fresh guest initialization, installation,
nonempty UART backpressure plus pending external input, exact private-fork
suffixes, reset cancellation, queue exhaustion and required-state rejection.
The complete course/math/learner/ink/Save/independent-cold workflow passes.
The ordinary `scripts/lemmasim-course` command selects the existing RTL path or
the negotiated fast port, with exact guest/image/profile and local-owner mode
checks. It admits bytes only; Installed/Saved remain guest barrier receipts.
The original `lemmasim course-install` spelling retains its RTL-only admission.
Actual identities, original failures and bounded observations are recorded in
[the evidence](../evidence/006-fast-uart-ingress-v1.json). QEMU's
general TLB/TB/jump-cache/instruction-visibility and exact timing obligations
remain open. This extension does not close arbitrary-boundary continuation,
the full USB/companion path, browser workflow or whole-machine completeness.
