# core0-kernel-v0.6 — decoded USB packet controller authority

This additive profile inherits the scalar source membership, checked physical memory,
Action calling convention and machine boundary of core0-kernel-v0.5. The only new
primitive authority is the PLIC priority 16 word: the exclusive priority-window bound
is 0x0c000044, permitting the aligned 32-bit word at 0x0c000040. Older kernel
profiles retain their original exclusive bounds. The existing checked 64-bit
LemmaSim aperture already contains the new USB controller at 0x10010a00..0x10010e00;
it gains no unchecked pointer or DMA operation. All existing alignment, range,
error precedence, I/O-fence and volatile-access semantics remain unchanged.

The exact selected configuration is lemmasim-silicon-usb-link-probe, with
lemma-silicon-dev/0.6.0, descriptor ABI 7/features 15, PLIC 16 sources, a genuinely
configured 8192-frame pool and canonical 1650x2200 display. Kernel software validates
the actual handed DTB and reads actual controller identity/version before frame
allocation. It requires the USB node, fixed aperture/IRQ/compatible/ABI and declared
64-byte payload, three endpoints, 1000000-clock reset and decoded-packet boundary.
Duplicate, missing, altered or undeclared device inventories fail closed.

The USB development slice exposes decoded packet bytes. Its RTL implements
PID/token/data/handshake processing, CRCs, control/status transactions, addressing,
configuration, endpoint queues, toggles, retry, STALL and disconnect/reset behavior.
The guest admits control requests and owns bulk buffers; transport delivery is
separate from an opaque peer's validated durable receipt. NRZI, bit stuffing, the
physical 12 MHz signalling boundary, comprehensive USB conformance and complete
USB-enabled machine checkpoint continuation remain unfinished. USB-enabled snapshot
and restore must reject explicitly until their complete future-relevant state is
retained; historical profile snapshots retain their existing separate scope.

This contract authorizes no Boolean conjunction extension, managed runtime, foreign
target helper, host document recovery or host-set configured/authenticated flag.
The first full probe export rejected an unsupported Bool.and dependency; that
failed observation is retained. Component tests and artifact audits are separate
from actual guest transactions and notebook/companion acceptance.
