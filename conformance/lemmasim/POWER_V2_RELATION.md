# Power-v2 partial fast/RTL relation

The reference is profile `lemma-silicon-dev/0.4.0` RTL. Its immutable audited
Power probe, descriptor ABI5 and DTB are identical in the two runs. QEMU executes
that guest through its existing scalar instruction-counting backend; this is
not a pipeline, memory-bus or cache timing model.

The admitted observation is exact: guest K1 report kind0x445 with cause/epoch
pairs (1,0), (4,1), (6,2), (5,3), in that order, and zero remaining fields.
Watchdog expiry occurs after its configured number of independent 10ns Power
clock edges, including genuine WFI with unchanged PC/minstret. Terminal valid
heartbeat wins; disarm/malformed input does not. Reset is held for eight edges.
Unsafe raw levels cannot repeatedly increment the reset epoch. Brownout wins
simultaneous loss of power-good. Eight consecutive safe edges release reset.
MTIME is zero while held and its first tick follows ten clocks after release,
with MTIMECMP reset to all ones. This relation has no adjustable tolerance.

The literal controller checks additionally require watchdog RAM retention,
actual RAM loss on unsafe input, future raw supply/button retention, and pen
resynchronization on release. Controller target/active scan state resets;
completed synthetic optical state remains retained. Real external backing
outcomes remain independent of reset and cannot become guest acknowledgments.
The original POSIX/orphan qualification and the guest reports are separate
properties; the Power probe performs no notebook save.

The fast Power clock stores its edge identity, raw inputs, one pending MMIO
write and exact publication edge. A write issues between digital edges and
publishes at the next rising edge. The CPU has no modeled RTL bus stall; a
second pending write halts this fast backend with an explicit unsupported-scope
reason. It retains the original pending write, does not invent controller error
or success, and cannot resume through the normal launcher after internal-error.
The exact RTL path remains available. The profile4 public workload is only the
checked Power probe; the ordinary notebook remains profile3.

A held supervised domain can serialize its logical clock, counter phase,
CPU/controller state, queued raw inputs and timer state. A queued but unprocessed
QEMU system-reset request is rejected before admitting a snapshot, rather than
omitting it. Existing fast Pending external-I/O snapshots remain rejected.
Qtest creates no ACLINT in this pinned virt machine. Its literal checks cover
Power/controller state only; the actual TCG guest separately checks MTIME.
Qtest's separately controlled clock is a fixture input; its fork clock
must be set to the declared saved boundary before migration load. This does not
simulate guest execution or alter the original machine.

Migration load still rebuilds QEMU soft TLB and translation/jump caches. A
passing device-clock suffix cannot establish arbitrary same-backend cached-state
continuation, whole CPU timing equivalence, portable microstate migration or
cold journal recovery. Native RTL retains its separately qualified arbitrary
Pending checkpoint path. ELF preload and subsequent immutable development
image reinstall after RAM loss do not establish production boot/update recovery.

The selected TCG timer-phase continuation qualifies a different property from
qtest: genuine reset-ROM/guest instructions execute, a warm reset releases at
1080ns, a snapshot at1152ns retains MTIME0 and the origin1080ns, and the admitted
five-cycle suffix reaches1208ns/MTIME1 with identical architectural registers
and controller observations after isolated restore. The snapshot is observed
without a fence, guest mutation or clock advance. Stable immutable fetches in
this short suffix do not exercise changed page tables or stale instruction
visibility; those cached-state obligations remain open.
