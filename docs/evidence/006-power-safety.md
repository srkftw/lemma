<!--
# Power-v2 connected digital qualification

`006-power-safety.json` binds the observed artifacts and exact source/tool
identities. The opt-in `lemma-silicon-dev/0.4.0` profile preserves canonical
geometry/capacity while exposing Power-v2. Historical 0.3 remains Power-v1.

The genuine Lean S-mode policy configures a 100000-clock watchdog, rearms its
supervisor timer and enters actual WFI. Native RTL observed stopped instruction
retirement before expiry at cycle7402157, exactly100000 clocks after arm.
The supervised compute/controller domains reset for eight clocks. The guest
then reads discovery and reports cause4/epoch1. Actual digital power-good loss
and brownout produce guest restart records6/2 and5/3; held brownout does not
repeat the loss epoch. This run took191.831 host seconds with a predeclared
450-second bound. It started at cycle0 through the public source-valid launcher
and exited/reaped its owner successfully.

The observational preterminal snapshot took0.955 seconds and145176550 bytes.
Restoring it and executing the same7491165-cycle suffix produced identical
complete checkpoint bytes, including architectural/circuit state, watchdog and
reset phase, raw-event cursor and retained UART text. Snapshot restore used a
private medium branch; this guest scenario had no attached user medium.

Separate native literal-state tests qualify RAM retained by watchdog, actual
RAM/overlay erasure on unsafe supply, completed synthetic optical retention,
incomplete scan cancellation, blocked DMA and pen loss/resynchronization.
Separate actual OS-fault tests submit a write at byte1536 under RLIMIT_FSIZE1538:
two bytes persist before EFBIG. They also observe fsync EBADF on a closed file.
Brownout cancels the guest controller while those operations are Pending.
Snapshot does not poll/read/drain them; restored forks reject stepping without
their outcome tape. Accepted orphan outcomes preserve the partial backing
prefix and do not DMA into erased guest RAM. The complete suffixes compare
exactly. These fixtures initialize controller state literally and do not claim
guest-issued storage transactions. Both old/new literal Power circuit suites
pass. Target, fixture and observer failures remain separately retained.

Rebuild using unused output directories; do not reinterpret retained artifacts
as current builds:

```sh
nix develop --no-write-lock-file --command ./scripts/build-kernel.sh \
  --configuration lemmasim-silicon-power-safety-probe --stage supervisor \
  --opt-level O2 --output-dir build/kernel/power-v2 --clean
nix develop --no-write-lock-file --command ./scripts/audit-kernel.sh build/kernel/power-v2
python3 scripts/silicon_compute.py build --profile lemma-silicon-dev/0.4.0 \
  --output-dir build/silicon/power-v2 --jobs 2
nix develop --no-write-lock-file --command scripts/lemmasim build \
  --backend rtl --profile lemma-silicon-dev/0.4.0 --workload power \
  --guest-build build/kernel/power-v2 --rtl-build build/silicon/power-v2
scripts/lemmasim session --backend rtl --profile lemma-silicon-dev/0.4.0 \
  --workload power --mode laboratory --headless --paused \
  --session-dir build/power/live --timeout 45
```

The persistent command surface accepts digital fault input only in Laboratory:

```sh
scripts/lemmasim session-control --session-dir build/power/live \
  --request '{"action":"inject","kind":"pgood","level":0}'
scripts/lemmasim session-control --session-dir build/power/live \
  --request '{"action":"inject","kind":"pgood","level":1}'
scripts/lemmasim session-control --session-dir build/power/live \
  --request '{"action":"inject","kind":"brownout","level":1}'
```

The JSON control interface is authoritative if CLI action parsing changes:
`{"action":"inject","kind":"pgood","level":0}` and
`{"action":"inject","kind":"brownout","level":1}`. The maintained
`python3 scripts/check_guest_power_safety.py --work-dir build/power/guest-v2`
executes the bounded actual guest, raw supply events and snapshot scenario;
`python3 scripts/check_power_safety.py --work-dir build/power/circuit-v2`
executes the literal old/new circuit boundary.

The boot path remains development ELF preload. Power loss erases working RAM
and reinstalls immutable preloaded boot pages explicitly; no production boot,
image authentication, A/B update or notebook document-preservation scenario is
qualified here. QEMU 0.4 admission remains rejected. Wasm, physical reset-domain
crossings, actual retention cells and electrical supply qualification remain
separate. The ordinary notebook continues using its established 0.3 profile.

-->
