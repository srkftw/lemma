# Paper-v2 staging and modern hardware successors

The USB notebook and Product notebook exposed a real device-map collision:
historical Paper-v1 staging is `0x10010800..0x100109ff`, inside the enabled BLE
window `0x10010600..0x100109ff`. The motherboard gives BLE priority. A Paper
staging store therefore reaches a read-only BLE receive register and faults.
The retained USB cold failure and independently captured Product store-access
fault keep their original meanings. Hardware profiles 0.1 through 0.7 retain
their mappings and snapshot identities.

`lemma-silicon-dev/0.8.0` is the USB successor, descriptor ABI9/features15.
`lemma-silicon-dev/0.9.0` is the Product successor, descriptor ABI10/features31.
Both select Paper-v2 with the complete 512-byte staging window at
`0x10010e00..0x10010fff`. BLE ends at`0x10010a00`; USB ends at`0x10010e00`;
Pen begins at`0x10011000`. The controller aperture remains 4096 bytes. Display
geometry, packed Gray4 bytes, upload dimensions, framebuffer transactions,
panel sequence and synthetic scan timing retain their earlier semantics.

Paper-v2 reports version2 at offset8 and its actual staging offset3584 at the
new read-only offset184. The new Lean driver validates both through real MMIO
after validating the selected descriptor/discovery. Version1 still reports1;
its previously zero offset184 remains zero. New profiles do not alias the old
staging addresses back to Paper. BLE and USB continue to own their full declared
windows, including error and retained receive-head behavior.

The common generated constants are `PAPER_VERSION` and `PAPER_STAGE_OFFSET`.
Historical profiles default to1/2048. Successors require2/3584, including the
512-byte end at4096. `lemma_paper` uses those parameters only for discovery and
staging admission; its existing eight byte banks retain 64 rows each. The
512-byte alignment keeps their row/lane address interpretation unchanged.
Transfers crossing the staging end fail without changing staged bytes.

The exact register region is already inside the maintained Kernel6/Kernel7
checked MMIO, Sv39 and PMP boundaries. This is a hardware ABI successor, with
new explicitly selected software roots; it grants no new User MMIO privilege
or language feature. Canonical hardware 0.3 and all historical target roots
remain separate selections.

The focused check uses the actual motherboard and all real controllers,
replacing the CPU only with explicitly declared raw MMIO stimuli:

```sh
nix-shell tooling/silicon/sim.nix --run \
  'python3 scripts/check_paper_staging_soc.py --profile lemma-silicon-dev/0.8.0 \
    --work-dir build/usb/paper-staging-NEW --jobs 2 --timeout 180'
```

It preserves the actual 1650×2200 framebuffer clear, checks every staged 64-bit
word, first/last-word and end-crossing behavior, neighboring BLE/USB ownership,
and an independently calculated 1024-pixel 32×32 upload. The same interface on
profiles 0.6/0.7 reproduces the retained collision. This literal circuit check
does not establish actual guest Ready, notebook durability, update recovery,
physical panel qualification or new-profile checkpoint continuation. Those
require their own source-bound machine and guest observations.

The USB8 native package is a distinct RTL-only schema4 deployment. It validates
both exact `usb-next-bulk-notebook` and `usb-next-bulk-initializer` guest roles,
all original compiler/unit/object/ELF artifacts and source bytes, compiled native
implementation identity and full native source inventory, and pinned host
libraries. It contains the actual machine and guest artifacts, not a new host
notebook. Canonical schema1–3 bundles and historical USB6 launches retain their
admission rules. Product9 uses its separate immutable-ROM/boot-medium launcher.

Prepared native8/guest-pair inputs can be archived with:

```sh
python3 scripts/lemmasim native-bundle-build \
  --profile lemma-silicon-dev/0.8.0 --output-dir build/native/usb8-NEW \
  --rtl-build build/silicon/task006-usb-next-runtime-a1 \
  --rtl-source-root build/usb/native8-consumed-source-archive-a1/source
```

The current qualified package is `build/native/task006-usb-next-a1`. Guest
execution and the durable peer are exercised by the supervised connected path:

```sh
python3 scripts/supervise_usb_notebook.py launch \
  --profile lemma-silicon-dev/0.8.0 \
  --native-bundle build/native/task006-usb-next-a1 \
  --host-prepared build/usb/host-pending-policy3-a1/prepared.json \
  --formatted-peer build/usb/store-initialize-a3/peer \
  --formatted-outbox build/usb/store-initialize-a3/outbox \
  --work-dir build/usb/notebook-next-NEW
```

The independent peer and its outbox are copied privately before launch. The
supervisor retains the original absolute deadline, does not restart a failed
run, and reaps only its owned process identities on cancellation or timeout.
The launch itself does not establish Ready, Save or cold recovery. The native
host boundary remains decoded USB packets; physical USB PHY and full USB
conformance remain unfinished.
