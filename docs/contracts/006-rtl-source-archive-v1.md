# Explicit original RTL source reuse v1

`--rtl-source-root` is an explicit native USB6 preparation/launch option. It
qualifies an unchanged compiled native runtime against its complete original
source archive while a newly compiled guest retains its separate current Lean
source, provenance and strict audit identity. It does not claim fresh hardware
compilation or functional success. Historical default launches still require
current native inputs. Product7 continues to use its separate ROM/native
validator; this option does not substitute ELF preload for product boot.

The source directory contains every original preparation input at its original
repository-relative path. Its parent contains `consumed-source-archive.json`
(`lemma-usb-native-source-archive/1`) and the retained original public registry
`consumed-runtime-receipt.json`. Validation reconstructs the native compiler
inventory, including RTL/CVW sources, configuration includes, host transport and
runtime, binding generator, pinned toolchain inputs and generated headers. The
original receipt supplies the preparation-only dependency declaration absent
from the native compiler manifest. Conflicting, missing, surplus, changed or
symlinked source inputs reject before launch. The selected profile JSON must
still match the original manifest.

Validation checks the original manifest, binary, generated runtime identity and
recomputes the implementation identity. It checks the complete original receipt
against that inventory and every archived file against its digest. The prepared
registry binds both archival metadata files, original native manifest and binary.
A registry prepared with this option requires the explicit same source directory
on subsequent launch; there is no fallback to changed current sources. The
session records the archival backend association separately from its newly
prepared guest identity. Guest preparation continues to use the full current
maintained Lean/compiler/profile input inventory and strict audit.

The implemented command surface is:

```sh
./scripts/lemmasim build --backend rtl --profile lemma-silicon-dev/0.6.0 \
  --workload initializer --guest-build build/kernel/task006-usb-initialize-a5 \
  --rtl-build build/silicon/task006-usb-runtime-a4 \
  --rtl-source-root build/silicon/task006-usb-runtime-a4/consumed-source-root

./scripts/lemmasim session --backend rtl --profile lemma-silicon-dev/0.6.0 \
  --workload initializer --session-dir build/usb/NEW/session --headless --paused \
  --rtl-source-root build/silicon/task006-usb-runtime-a4/consumed-source-root \
  --usb-host-prepared USB_HOST_PREPARED_JSON --usb-peer-directory PEER_DIRECTORY \
  --usb-peer-socket PEER_SOCKET --usb-host-state RETAINED_HOST_OUTBOX
```

The independent hosted Lean opaque peer must be running at `PEER_SOCKET`; neither
command formats media on the host. The guest performs journal initialization
through the modeled USB controller. The command examples identify the source
association; actual execution outcomes remain in their separate receipts.

The focused actual-archive qualifier copies only task-owned source/artifact bytes
before corrupting them. It leaves the original native runtime and archive intact:

```sh
python3 scripts/check_native_source_archive.py \
  --rtl-build build/silicon/task006-usb-runtime-a4 \
  --rtl-source-root build/silicon/task006-usb-runtime-a4/consumed-source-root \
  --work-dir build/usb/NEW-ARCHIVE-CHECK
python3 -m unittest discover -s tests/lemmasim -p test_rtl_source_archive.py -v
```

These are source/artifact admission checks. They do not qualify arbitrary USB
checkpoint continuation, USB PHY conformance, notebook Save or cold recovery.
