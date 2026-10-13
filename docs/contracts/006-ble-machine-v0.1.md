# BLE manual-link machine development binding 0.5

`lemma-silicon-dev/0.5.0` is an opt-in development machine. It retains the canonical 1650×2200 Gray4 display, 128 MiB external simulation RAM, 8192-frame guest pool, 100 MHz machine clock and 10 MHz MTIME, and inherits Power-v2. Historical bindings retain their byte meanings.

Binding5 uses descriptor ABI6, feature word 7, a copied-PIO packet controller at `0x10010600` with a `0x400` aperture, PLIC source 15, and at most 27 opaque payload bytes. Each LE1M sampled bit spans 100 machine clocks. The declared context is manual, unauthenticated, preconfigured AA `aa08192b`, CRC initialization `c4c181`, channel 16. Connection establishment, encryption, GFSK sampling, analog RF, full Bluetooth 5.4 and durable companion receipts remain separate requirements.

The machine contains two independently clocked instances of the maintained packet RTL. Host code routes only generated one-bit sample strobes, copies a CRC-validated immutable RX head to the genuine hosted Lean policy, and schedules actual accepted peer replies through the second controller's PIO. The host does not encode packets, compute CRC/whitening or decide SN/NESN. A lost packet control discards a complete generated peer wire packet, rather than changing a shared success flag.

The live hosted interface has nonblocking bounded request/response framing. Complete actual responses are recorded before their effects enter the machine, with stable request IDs, issued/accepted cycles, exact header and opaque bytes, and complete logical-state trailers. The state carries both RTL instances, clock/sample phases, pending wires, coex grant, queued PIO beats and the previous accepted outcome. No host pointers enter checkpoints.

Current checkpoint container4 admits resolved hosted-policy boundaries, including an in-flight generated packet. Unresolved startup/data responses reject observationally. Restored resolved branches remain suspended until a tape proves the exact prior accepted context and applicable future requests; continuation consumes captured responses without contacting or restarting the original peer. No tape means no clock advancement. Wrong context, request, boundary, implementation or corrupt state rejects before adoption.

A future separately qualified container successor may retain an unresolved data request. It must retain the actual original issued request and next poll phase; a private branch must not resubmit it. This paragraph is an outstanding implementation obligation, not a current checkpoint claim.

The privileged guest probe configures the actual controller and PLIC15, sends the opaque LMCMP001 prefix, consumes a decoded empty ACK, and performs bounded retry. A link ACK is not a storage durability receipt. This does not provide a guest notebook companion driver, USB, radio-backed Save or a production boot path.

## Qualified native path

`docs/evidence/006-ble-machine.json` records actual checked RV64 execution. The changed SoC relative-offset decoder is exercised by the guest's identity/version reads at base/+8, configuration writes at +24/+32/+40, copied payload and command registers, and source15 claim/completion. The two generated packet streams are compared to an independent CRC/whitening reference. One complete peer ACK is dropped, causing one retry; the genuine hosted Lean peer accepts the opaque payload once and records one duplicate. A checkpoint during that first ACK retains the complete generated endpoints and pending sampled wire, with a byte-exact applicable suffix from recorded external responses.

These source-bound commands were executed; use unused output/session paths for a new run:

```sh
nix develop --no-write-lock-file --command python3 scripts/silicon_compute.py build \
  --profile lemma-silicon-dev/0.5.0 \
  --output-dir build/silicon/task006-ble-wire-runtime-a4 --jobs 2
python3 scripts/lemmasim build --backend rtl \
  --profile lemma-silicon-dev/0.5.0 --workload ble \
  --guest-build build/kernel/task006-ble-guest-a4 \
  --rtl-build build/silicon/task006-ble-wire-runtime-a4 --opt-level O2
python3 scripts/check_guest_ble_link.py \
  --work-dir build/radio/task006-ble-machine-a2 --boot-cycles 20000000 --deadline 360
```

Ordinary launch of the prepared probe and the independent hosted Lean peer:

```sh
python3 scripts/lemmasim session --backend rtl \
  --profile lemma-silicon-dev/0.5.0 --workload ble \
  --mode developer --session-dir build/radio/manual-ble --headless --paused \
  --ble-peer "$(command -v nix)" \
  --ble-peer-arg=develop --ble-peer-arg=--no-write-lock-file \
  --ble-peer-arg=--command --ble-peer-arg=lake --ble-peer-arg=env \
  --ble-peer-arg=lean --ble-peer-arg=--run --ble-peer-arg=sim/radio/ble_peer.lean
python3 scripts/lemmasim session-control --session-dir build/radio/manual-ble \
  --request '{"action":"run","cycles":10000000}'
```

Add `--ble-drop-packets 1` in Laboratory mode to select the demonstrated lost-ACK wire case. Raw `ble-rx` and `ble-coex` inputs are Laboratory/Developer device inputs; the machine owns their cycle ordering. An ordinary Developer resolved snapshot/restore uses the shared `snapshot --to` and `restore --from` commands. After restoring an attached-peer checkpoint, bind the original complete captured suffix with `session-control --request '{"action":"ble-outcomes","path":"ABSOLUTE_OUTCOME_PATH"}'` before `run`. The restored owner never resumes the original process. A complete capture is needed; a log ending in a pending request fails closed.

The same-binary fixed-prefix host-pool comparison uses `python3 scripts/check_native_host_threads.py --work-dir UNUSED_OUTPUT --cycles 2000000`. It proved byte equality for default14 versus one host thread, including a100000-cycle restore suffix. Its single short sample did not show a speedup; the default was about7% faster, with a340KiB larger peak RSS. Host thread counts do not alter virtual clock frequency.

Original failures are preserved. The first integrated guest stopped with fatal50 at7,870,065cycles after successful FDT parsing: the SoC had passed low address bits for an unaligned1KiB aperture. The subsequent changed-source build subtracts BLE_BASE. The old observer's generic first-packet bound error is not reclassified as a timeout or harmless failure. The first host-suite invocation outside Nix failed because tools were unavailable; the pinned host suite separately passed146tests.
