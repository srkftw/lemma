# Task006 companion opaque backing development increment

This increment implements a separate persistent hosted-Lean peer and client,
and attaches it to the existing native RTL `Machine` through `BackingPlatform`.
The existing RV64 block driver and guest journal remain the storage authority.
This is `lemma-companion-backing-dev/1`, **not** modeled USB, the companion
controller/service, finished companion storage, authentication or an
asynchronous disconnected writing path.

Ordinary Lean elaboration compiled `Protocol`, `HostIO`, `Peer` and `Client`
with Lean4.34.1 from immutable host prefix
`/nix/store/ysdqz5kaw8paig5v5q8d94yg6lkk0pkf-lean4-4.34.1`. Its
`--githash` is unavailable and is recorded as null, rather than invented.
`build/companion/task006-peer-a4/prepared.json` records every consumed local
source, compiler/tool hash, generated host object and binary. Hosted runtime
objects are confined to those host executables; zero objects are added to any
RV64 link. The protocol, ordering, retry, outbox and receipt policy execute in
Lean; Python and C++ provide raw bytes and OS primitives only.

Observed compiled host identities:

| Artifact | SHA256 |
| --- | --- |
| companion peer a4 | `d691e2724bb03d86404b258dcf7006f1d5c6c2240c7638b902f784b86480b883` |
| companion client a4 | `adeb98408315457a8fe8d001f9e8cfbfa2ffb25902ff952d374876ce074e4ab7` |
| native RTL runtime a3 | `44442fc19ba05bc6ff315116fcad84421e1d851464cb080267da3409982c10b9` |

Native a3 implementation identity is
`255030a218bf67acc26a5807e1b3eb8ab97ff2d768501df0d037775e50abf90e`.
The existing native a1/a2 and browser artifacts are retained. The reusable core
runtime body and shared backing-I/O source bytes were unchanged by this native
transport increment.

Six focused tests passed through the actual compiled peer/client and strict
C++ raw adapter:

```sh
nix develop --no-write-lock-file --command \
  env LEMMA_COMPANION_PREPARED=build/companion/task006-peer-a4/prepared.json \
  python3 -m unittest discover -s tests/lemmasim -p test_companion_peer.py -v
```

Observed12.071s under concurrent native build work; the earlier same Lean policy
a3 test took7.664s. These are host suite durations, not guest performance claims.
The independent CRC oracle includes ECMA known answer `123456789` ->
`6c40df5f0b497347`. Endpoint observations establish these specific properties:

- A write and its transaction identity occupy one592-byte complete record.
  The8-byte log plus one write is600 bytes. A duplicate same-ID/same-byte retry
  leaves it600; different bytes and sequence gaps return protocol error.
- The raw server discards an actual response after peer `fsync` and exits.
  Client replies `PENDING` and exits with its durable outbox intact. Restarting
  both processes reconciles the same writer/sequence; journal remains600 bytes.
  A subsequent real barrier increases it to680, rather than duplicating data.
- An actual `fsync` on a closed OS descriptor yields EBADF. The peer returns
  error and the full observed write prefix; reads and restart preserve bytes.
  A same-ID retry with working sync obtains a receipt without a second record.
- Actual RLIMIT_FSIZE100 causes a partial append. Lean reconstructs the actual
  incomplete tail and truncates it before another request; no complete opaque
  sector or receipt is manufactured.
- A passive Read after failed sync observes bytes without retrying the outbox
  or performing a hidden medium barrier. Pending state remains durable.
- The C++ platform performs real reads/writes/barriers through the compiled
  Lean client and rejects external-peer recorded replay.

The first peer build failed linking because generated module initializer names
used the repository root while imports used the peer package root. The retained
a1 failure was corrected with `lean -R sim/companion`; a2–a4 compiled. No guest
test or CI was weakened. Scaffold metadata and all18 scaffold tests also passed.

The ordinary `scripts/lemmasim companion init/serve` and
`scripts/lemmasim session --companion ...` command surface was executed at
`build/companion/task006-launch-a1`. The independently running Lean peer and
current audited RV64 image were attached successfully, inspected at paused
cycle0 and destroyed cleanly. Its receipt explicitly claims launch/attachment
only. **Canonical RTL peer Ready/Save/cold recovery is not claimed by this
launch check.** Launch commands and failure/continuation semantics are specified
in `docs/contracts/006-companion-backing-dev-v1.md`.

Two synchronous2-second sends can block host machine evaluation. Unknown remote
persistence leaves a poisoned pending capture and requires explicit outbox
reconciliation/restart. This cannot qualify offline pen responsiveness or an
arbitrary-boundary pending external checkpoint. Same-user socket checks and
CRC are not owner authentication. Explicit queues/DMA, USB, radio, async
completion/cancellation, multi-writer epochs and bounded compaction remain open.
