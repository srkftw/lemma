<!--
# Independent boot backing I/O, version 1

Profile `lemma-silicon-dev/0.7.0` gives BootNV a separate 65,544-sector,
512-byte medium. It does not share request IDs, storage state, fault tapes or
files with the user VirtIO journal medium. The native adapter transports raw
bytes and actual backing outcomes; image selection, validation, installation,
confirmation and recovery remain guest responsibilities.

Each retained controller `(reset-origin, request-id)` owns exactly one read,
write or barrier request. The runtime reserves a bounded capture record before
submitting it, polls at explicit 1,000-cycle boundaries, and captures the actual
returned bytes, prefix length and error before asserting controller completion.
`LMNVLOG2` uses the existing versioned backing-record encoding and exact runtime
identity, with a distinct magic from user-medium `LMIOLOG2`. Cross-namespace,
incomplete, incompatible and mismatched tapes reject before adoption.

A failed write may persist a prefix. A failed barrier does not acknowledge
durability. The accepted-medium view includes actual observed prefixes even
when the command fails, is cancelled or belongs to a reset orphan. Cancellation
within a live controller returns the actual outcome to its retained request;
domain reset makes the old request an orphan, retains external ownership until
its outcome arrives, and never publishes that outcome to a new controller.
Reset origins change at the declared reset edge. Outstanding orphan work keeps
the external-busy input asserted.

The accepted view is sampled once before execution through bounded passive
reads. Snapshots subsequently use this view without reading, polling, draining,
resubmitting or flushing the backing medium. Container version 7 preserves the
logical request, next poll boundary, controller identity, reset origin, counters,
accepted medium and generated RTL state. Capture-file synchronization only
persists the observational log; it cannot acknowledge a guest medium barrier.
Historical disabled-profile wrapper formats retain their conditional fields.

Restore validates the complete container and ownership relation before replacing
the live machine. It creates a separate sparse, privately backed boot medium.
An inherited Pending request suspends the private fork before cycle advancement
until an exact recorded outcome tape covers that request and poll phase.
Continuation applies captured prefixes only to the private medium and never
contacts or resubmits to the original backing platform. The original live request
continues unchanged. Raw host pointers are not serialized. Rewinding capture
starts a new exclusive log. `export-boot-medium` exports accepted bytes; a live
Pending export rejects, while a suspended private fork may export its accepted
view without contacting the original medium.

Product mode admits only host installation of immutable ROM and the hardware
descriptor. RAM ELF/preload installation rejects. Real declared RAM-loss events
erase volatile kernel and DTB bytes; product reset does not reinstall retained
preload pages. The ROM must load them through actual BootNV transactions.
Attached USB external-policy state is still outside checkpoint admission.
Browser product backing, fast product parity and product boot/update qualification
are separate obligations and are not established by the literal runtime checks.

Native command surface (the ROM and boot medium must be independently qualified):

```sh
build/silicon/task006-product-runtime-a2/obj/lemma-rtl \
  --rom ROM.bin --descriptor descriptor.bin --boot-medium boot.raw \
  --boot-io-capture boot.nvio --medium user.raw \
  --uart-output uart.log --session
```

Session commands include `snapshot PATH`, `restore PATH`, `boot-outcomes TAPE`
and `export-boot-medium PATH`; restore owns its private boot fork. The exact
command-line syntax is implemented by `sim/rtl/host/main.cpp`.

Focused qualification:

```sh
nix-shell tooling/silicon/sim.nix --run \
  'python3 scripts/check_native_boot_pending.py \
   --rtl-build build/silicon/task006-product-runtime-a2 \
   --work-dir build/silicon/task006-product-pending-a4'
```

This check exercises literal controller state, actual POSIX failures and exact
native continuation. It does not execute a product ROM or qualify guest boot.

-->
