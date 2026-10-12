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

## Connected RV64 fast guest, actual lost receipt and cold recovery

The next increment connects QEMU's existing real block controller to the same
`BackingPlatform` through a host-only C ABI. `lemma-fast-block/2` captures actual
POSIX or peer outcomes before controller completion; failed barriers retain
observed bytes and volatile sectors. Passive export and private restored media
use the platform boundary. Pending or ambiguous external work rejects snapshots.
No host transport runtime objects enter the RV64 image. QEMU cached-translation
and instruction-visibility continuation remains open; this is cold recovery,
not an exact-checkpoint claim.

`build/companion/task006-guest-peer-a3/result.json` passed the connected scenario.
The small checked-in receipt is `006-companion-guest.json`. The actual command was:

```sh
python3 scripts/check_companion_session.py \
  --disk build/silicon/task006-canonical-cold-a2/medium.raw \
  --peer-prepared build/companion/task006-peer-a5/prepared.json \
  --work-dir build/companion/task006-guest-peer-a3 \
  --timeout 120 --boot-seconds 40 --action-seconds 20 --deadline 900
```

The original guest-initialized medium was only copied; ordinary raw pen input
made50 actual samples/two strokes. Guest journal recovery and controller pixels
passed the independent workflow observer, with explicit Saved at sequence8.
Four real brush-root edits cycle back to the original setting, providing exact
expected cold bytes and complete pixels. The original action labels assumed
initial256; an independent root-byte observation establishes initial512 and
actual settings1024/2048/256/512. Future labels are neutral; the original report
is retained and its exact four-cycle byte/pixel checks remain valid.
An earlier completed equal-size root
edit predeclared response ordinal6: its final Barrier. On the fourth edit the
peer synced that transaction78, its actual response was lost and the peer exited.
The guest emitted no Saved after the loss. The live capture retained80 complete
outcomes plus its pending marker, and snapshot pre-save rejected that state.

Both machines restarted. The durable outbox reconciled the same writer17 /
transaction78 before the new guest executed. Peer log size remained33896 bytes;
no duplicate transaction was appended. The independent cold guest recovered
sequence12, exactly the original committed object bytes and the complete expected
1650x2200 controller display. It did not rewrite the peer log. Cold recovery used
an independent CPU and real device reads, without a snapshot or host journal fix.

Cold Ready took11.000000008 virtual seconds /25.131 host seconds; recovery Ready
took11.65 virtual seconds /27.961 host seconds. Each25-sample raw stroke occupied
0.85 virtual seconds /8.47 and8.23 host seconds, including ordinary save/display
settling. The explicit clean Save took0.25 virtual seconds /0.576 host seconds.
The full campaign, including two256MiB passive exports and independent oracles,
took235.011 host seconds and allocated about43MiB of sparse artifacts. These are
fast execution coordinates; they do not establish RTL pipeline timing parity.

Original failures remain: a1 wrongly assumed that clean explicit Save must issue
new medium I/O, failing before fault injection; a2 exceeded the declared120s
passive-export operation bound. Actual hosted-Lean CRC lookup and dense ASCII
byte-array conversion fixed the transport hot path with unchanged wire semantics
and deadlines. Seven compiled peer tests passed, including an independent
bitwise CRC over the maximum1MiB arbitrary-byte response. Under the same8192-byte
raw-pipe buffer, two1MiB responses measured a4:0.664/0.249s and a5:0.245/0.148s;
peak peer RSS decreased from127876KiB to24592KiB. Concurrent workload affects these
host measurements; the retained receipt pins each executable and source hash.

QEMU binary SHA256 is
`2874932d1816b47d98ed5884a124087bbcd41a6d57c212be624b4dbcc4537716`;
the genuinely elaborated/strict-audited joint RV64 guest is
`b79b020dd52428bb2a115b5a81cb07df9ab64079cab66a0a9655ce3e38b40af7`.
Hosted peer/client a5 hashes and exact sources/tools are in the receipt and
`build/companion/task006-peer-a5/prepared.json`. Two shared C-boundary actual-OS
failure tests,168 silicon host tests, metadata checks and18 scaffold tests passed
separately. No CI result is inferred from those runs.

This usable development backing path still pauses the whole synchronous machine
on unknown persistence. Offline ink while external work remains pending,
fork-safe pending continuation, guest companion driver/controller, USB,
authentication and complete companion storage remain unfinished.


## Asynchronous pending ink and reconciliation

The connected fast development path now consumes the shared submit/poll boundary.
The hosted Lean client retains its durable outbox and receipt policy while the
raw adapter polls without blocking virtual CPU, pen or panel execution.
`006-companion-pending.json` records the actual PASS from
`build/companion/task006-guest-pending-a1/result.json`: a preselected final
barrier reply was lost after peer persistence; writer17/transaction78 remained
Pending without poison or Saved. During that disconnect the real guest consumed
25 more raw samples and produced controller ink, advancing cycle coordinates
2305000006→2350000006. Explicit same-ID reconciliation after peer restart retained
one receipt, then the guest acknowledged sequence15 with all75 exact samples
and3 strokes. An independent cold CPU recovered the exact acknowledged object
bytes and complete1650×2200 controller display. No host document recovery entered
the machine.

The campaign used the declared120s control,40s boot,20s action and900s host
bounds, completing in275.024s. Initial cold Ready took11.600000016 virtual seconds
/21.147 host seconds; recovered Ready took16.900000164 virtual seconds/31.309 host
seconds. These are QEMU execution coordinates, not RTL timing. The receipt keeps
allocated disk bytes and a sampled105120KiB live QEMU RSS observation distinct
from a peak-memory measurement. Timed capture records both immutable submissions
and actual completion acceptance; snapshots of unresolved external work reject
without a hidden retry/barrier. Reset orphan and Power-v1 busy handling are
implemented but have no new guest-issued reset/watchdog acceptance in this run.

The actual backend SHA256 is
`5800c55dd37e6245ee74b0bbd2806cea0cca68d3e0ac2d4d562f75b204fcc9dd`.
`build --guest-bundle` fully revalidates the immutable archived compiler, audit
and workload closure at preparation and launch while binding current backend
sources/output. The unchanged genuinely elaborated guest remains
`b79b020dd52428bb2a115b5a81cb07df9ab64079cab66a0a9655ce3e38b40af7`; this is
new backend execution, not fresh target compilation. Nine compiled hosted-Lean
peer/C-boundary tests, two actual POSIX error tests,168 silicon host tests,18
scaffold tests and metadata checks passed separately. Native RTL execution is
still synchronous in this increment. The USB/controller/guest-driver, complete
disconnected product policy, pending private fork continuation, fast timed-outcome
replay consumer and QEMU cached-state continuation obligations remain open.


## Shared native asynchronous boundary and exact timed outcome replay

Native RTL now consumes submit/poll through the same BackingPlatform. Immediate
POSIX/OPFS operations preserve submission-cycle handshakes; peer polls use the
declared1000-cycle cadence. The wrapper retains medium ownership and flush
cursor; issued work survives reset as an orphan until its actual outcome, with
no canceled DMA completion. A modeled external-media busy input reaches the
existing Power-v1 guard. Native capture/replay uses LMIOLOG2 target-cycle
boundaries, distinct from fast virtual nanoseconds.

`006-native-backing-pending.json` retains the actual literal RTL/runtime PASS
from`build/companion/native-pending-a5/result.json`: held external medium work
continued alongside genuine instruction retirement and raw pen ingress, pending snapshot/restore/export rejected
observationally, private timed replay reproduced the complete checkpoint bytes,
and a global-reset orphan completed without DMA. The fixture initializes the
controller's held state directly, so this is not a guest-driver/notebook claim.
Two compile setup failures and a failed retirement assertion without boot
artifacts remain retained. The assertion was kept; the corrected fixture loads
the full validated archived reset ROM/guest artifacts before clocking. The new native build took
54.184s; its binary SHA256 is
`ac95c4abcf0a474e0e4ab545ce2b6b01d16d98b7a42719ca1c11b8304a60b4c2`.
The exact source-bound fixture completed in8.082s. The168 silicon host tests,18
scaffold tests and metadata check passed separately. Pending external forks,
native notebook/peer cold acceptance, complete power domains and QEMU cached
state remain separate unfinished obligations.
