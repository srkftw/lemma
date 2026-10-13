<!--
# Pinned QEMU checkpoint observation

`check_fast_state_equivalence.py` compares complete saved machine files. The
relation admits unequal values in exactly two eight-byte fields:
`timer.cpu_ticks_offset` and `timer.cpu_clock_offset`. It reports their original
values, offsets, raw file hashes and every differing byte. All other bytes must
agree, including CPU registers/private state, RAM/ROM, device state, controller
timers, `timer/icount.qemu_icount_bias` and `timer/icount.qemu_icount`. It does
not modify serialization or snapshots. Unequal containers remain unequal.

The observer is deliberately limited to QEMU 11.1.1 machine
`lemma-silicon-fast`, the exact fixed `shift=3,align=off,sleep=off` configuration
in `scripts/lemmasim_fast.py`, the admitted RV64IM/MSU/Sv39/PMP CPU string, and
binary SHA256
`87d7282df1de259a3560fee369ef1f303a644654793726fc9da12009d639d467`.
The session manifest binds the implementation, guest, DTB and descriptor; both
checkpoints must have equal identities, exact virtual nanosecond phase and
external-event cursor, with individually validated lengths/checksums. A future
QEMU binary, adaptive instruction clock, realtime device or different schema
requires new review; this observation relation cannot be assumed for it.

The reviewed Power-v1 successor uses profile `lemma-silicon-dev/0.3.0` and
binary SHA256
`80e54f2095774ecdbfe3bcd36e52e7c55b1c5e566ecf869b4c6ed3f8c857b43a`,
from `/nix/store/pgmq625gkqpsav85l32jkjdfp3z4z7lq-lemmasim-qemu-11.1.1`.
It uses the same pinned upstream source, scalar CPU string and fixed instruction
clock. The reviewed repository changes add Power-v1 to device VMState version2,
raw button queue kinds, stable bounded future-event insertion, its level IRQ
and passive panel inspection/saving.
Controller and input timers continue to use `QEMU_CLOCK_VIRTUAL`; none of those
changes consumes the two host clock statistics. The older binary/profile
admissions retain their original meanings. The selected executable must match
the checkpoint's exact runtime hash. The counter-clock successor below is also
reviewed; no arbitrary binary is admitted.

The profile0.3 counter-clock successor has SHA256
`6dc0c7f66bbf3c118da5486c6b000772f1854cda0e235dca57941b4d48b3f6a8`.
The immutable-source-guarded host patch
`tooling/lemmasim/patch_counter_clock.py` consumes the declared100MHz clock.
It scales absolute precise instruction-clock nanoseconds before subtracting
counter baselines, preserving fractional phase, writes and inhibit behavior.
Selected warm reset zeros fixed counters and their baselines at the current
clock. Existing PMU counter state and the added version1
`cpu/lemma-counter-clock` subsection retain the frequency marker, configuration
words and all fixed-counter private arrays. Missing/wrong-frequency state rejects;
the public session separately rejects a different implementation identity.
Every added byte participates in exact comparison. No counter exemption exists.

The same narrowly selected patch resets the UART FIFO control to zero. The
upstream reset cleared IIR but left the previous FCR; restore then derived a
different IIR from that stale FCR. Actual warm-reset/restore caught that mismatch;
the corrected machine preserves both actual UART state and its complete suffix.
Historical profile0.1/0.2 derivations and executables are unchanged.

`check_counter_state.py` executes actual cold/warm, fractional-phase,
write/inhibit/wrap and private-state continuation checks with a genuine audited
Lean probe. Its writes invoke QEMU's real debugger CSR handlers. Guest-issued
counter CSR instruction/privilege qualification is absent. QEMU's completed
paused RESET and RTL's eight reset edges have explicitly different boundaries;
these checks do not establish whole-machine architectural equivalence.

The selected pen/reset successor has SHA256
`927bef771d31134b73b76a2c219d1717144feec6986b07df5c58ef85d08ad6e5`.
It retains the counter/UART repairs and resets the complete pen controller on
hardware reset. Software RESET1 still enters loss/resynchronization. Device
VMState version3 adds a mandatory aligned `pen_clock_origin_ns`, mapping the
watchdog and mouse timestamps onto actual reset-local MTIME without changing
the fractional instruction-clock phase. Missing, stale version2, misaligned,
future and inconsistent deadline state reject. The independent wire decoder
and mutation check include the origin; no new field exemptions exist. Ordinary
warm notebook writing/Save/new cold recovery passed using identical old/new
raw stimulus. See [the focused boundary](WARM_PEN_STATE.md). Paper warm reset
state parity and full processor/reset-duration equivalence remain unqualified.

All seven power words, enable flag and queued button state are exact comparison
bytes. The additional independent mutation checks change each power word and
require failure. The wire decoder requires the fixed device prefix and the
complete seven-word Power-v1 schema; it never calls the controller's state
transition code. Save and inspection do not advance the new panel controller.
The authoritative virtual timer performs its completion, including after restore.

The historical absent-version wrapper is recognized explicitly with origin
zero for retained observations. `lemmasim-fast-adapter/2` additionally requires
`clock.json`, schema `lemmasim-fast-clock/1`, a bounded integer
`time_origin_ns`, its manifest length/SHA256 and exact left/right file bytes.
Missing, unknown-version or altered wrapper state rejects the comparison.
Both selected durable bases are independently hashed and must also agree.
There is no exemption for wrapper clock state.

Adapter2 keeps session time monotone through cold cycles using
`virtual_ns = time_origin_ns + local_virtual_ns`. Controller/event deadlines
are translated to the fresh QEMU process clock; all admitted sample fields
remain unchanged. Actual CLINT MTIME supplies `ticks`/`local_ticks`: warm reset
zeroes it while QEMU's instruction-clock phase remains. Warm reset waits for
the real RESET event. The old `-no-reboot` option previously converted even
QMP reset requests to shutdown; the retained warm probe records that defect.
The final seven nanoseconds of the signed clock range are reserved before
run/event admission so the next instruction boundary cannot overflow it.
The historical executions do not qualify cycle/instret reset semantics. The
reviewed counter successor qualifies the narrower selected behavior above.

## Unserialized cached state

QEMU11.1.1 `hw/core/cpu-system.c:cpu_common_post_load` calls `tlb_flush(cpu)`.
Cached Sv39 software translations and TCG translation blocks are not in the
CPU migration stream. This observer compares every serialized guest byte,
but cannot detect an omitted cache entry. Actual supported guest suffixes
passed; arbitrary cached-translation continuation remains unfinished.
`target/riscv/machine.c` explicitly serializes `env.load_res`/`env.load_val`;
selected RV64IM excludes A and does not exercise LR/SC. The Lean address-space
operations issue declared SFence primitives, but that source observation is
not a proof covering every possible processor/memory state. RTL's savable
model captures its cache/TLB circuits. Cross-backend microstate migration and
a portable architectural checkpoint boundary remain absent.

## Source reason for the two fields

The pinned source archive is QEMU 11.1.1, SHA256
`079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482`,
realized as
`/nix/store/5fncyn7ha91mjhrxsl6id2wdi6zlgbnb-qemu-11.1.1.tar.xz`
by the repository Nixpkgs pin `7dd199b0e2993e37b4775ed66b1c291699608c9f`.
The following are direct inspections of that source, rather than deductions
from the differing values:

* `system/cpu-timers.c:43–135` defines `cpu_ticks_offset` in host CPU-cycle
  units and `cpu_clock_offset` in host monotonic nanoseconds. Start/stop adds
  `cpu_get_host_ticks()` / `get_clock()` so they measure elapsed host running
  time. Different host execution durations necessarily produce different
  values. Lines 202–234 serialize them in timer version 2, around an unused
  eight-byte field, and separately serialize the two instruction-clock fields
  in timer/icount version 1.
* `accel/tcg/tcg-accel-ops.c:211–214` selects `icount_get` for both virtual
  clock and elapsed guest ticks when instruction counting is enabled.
  `system/cpus.c:225–256` dispatches those selected operations.
  `util/qemu-timer.c:650–662` sends `QEMU_CLOCK_VIRTUAL` through that virtual
  clock; the host-offset clock belongs to `QEMU_CLOCK_VIRTUAL_RT`.
* `accel/tcg/icount-common.c:448–468` creates the realtime warp timer only
  with sleep enabled. A numeric shift enables precise counting and returns
  before creating the adaptive realtime adjustment timers. With sleep and
  alignment disabled here, idle advancement follows virtual deadlines;
  elapsed host offsets do not drive it. The fast stop-boundary guard in
  `tooling/lemmasim/apply_qemu.py` prevents further idle advancement after a
  bounded run has requested its stop.
* `target/riscv/tcg/csr.c:1298–1303` reads the admitted cycle/instret counters
  from `icount_get` / `icount_get_raw`. Time reads use the CLINT callback;
  `hw/intc/riscv_aclint.c:53` derives that from `QEMU_CLOCK_VIRTUAL`.
  The selected scalar CPU has no admitted filtered-PMU extension.
* All custom pen/paper/block timers and timestamps in `sim/host/lemma_qemu.c`
  and `lemma_fast_block.c`, plus the selected UART timers in
  `hw/char/serial.c`, use `QEMU_CLOCK_VIRTUAL`. The fast machine excludes the
  unused RTC/PCI/other virt devices. Host clock statistics may be printed by
  a host observer such as `info jit`; such output is distinct from guest time.

Relevant unpatched source SHA256 values:

| Source | SHA256 |
|---|---|
| system/cpu-timers.c | dc7d022db8e17a6323285e78897f9f8f15c537931f7bcd46094373f494758671 |
| accel/tcg/tcg-accel-ops.c | 79a918acaf0e6c770b2095036c06c513a567beb478a3aed113edb738d00151a2 |
| accel/tcg/icount-common.c | 1e75ed69fa6cf45701e631db75b71d859af865ea78b06a3f7358f496b225bc7d |
| target/riscv/tcg/csr.c | 631294ef82387021c1a40d2125b636b4097a9350a2bc50d299ff38d5aa856360 |
| scripts/analyze-migration.py | 30cc780aecc662d695bdb32d20715c854bead5172fc2bc45a54456cbe4669d35 |

## Independent decoding and negative checks

The observer requires the exact embedded timer descriptor, unique full-section
header, versioned icount subsection, unused bytes and matching footer. An
ambiguous section-looking string in RAM causes rejection. No entire timer,
CPU, counter or metadata section is omitted.

The retained public workflow's raw-container comparison remains FAIL in
`build/l6-native1/result.json`. A separately recorded observation is PASS in
`build/l6-native1-state-equivalence-a1/result.json`: exactly nine bytes differ
inside the two named host fields; all other 25,696,738 bytes match at virtual
time 106368000276 ns. The official decoder from the immutable source archive
independently reads both timer sections in
`build/l6-native1-state-equivalence-a1/archive-timer-decoder.json`.
Its source is executed only as a host observer; it never enters the target.
The original raw files and failed result remain unchanged.

`--mutation-checks` changes one byte in each named host field and verifies that
the difference is retained/named. Independent one-byte changes in either
private instruction-clock field, CPU x1 and an actual RAM-page payload must
FAIL. The focused unittest fixtures also reject unknown/missing subsections,
schema changes, ambiguous headers, truncated/trailing data and resource bounds.
These serializer tests establish observer behavior, not guest execution.
The additional actual lifecycle checker executes a genuine Lean notebook boot
prefix, snapshots computation in progress, captures warm/cold/input operations,
and replays through isolated restored processes. Its result
`build/lemmasim/fast-lifecycle-clock-a2/result.json` is PASS with exact wrapper,
CPU/RAM/controller and durable state under the declared relation. It is not a
notebook-ready or cold-journal-recovery claim. The first attempt's retained
FAIL was an observer expecting fixed HMP spacing; the corrected parser checks
the independently reported numeric PC0x1000. No machine change hid that result.

```sh
python3 conformance/lemmasim/check_fast_state_equivalence.py \
  --left build/l6-native1/final-original/machine.chk \
  --right build/l6-native1/final-replayed/machine.chk \
  --qemu build/lemmasim/qemu-task006-fast-full-a6/bin/qemu-system-riscv64 \
  --output build/l6-native1-state-equivalence-new/result.json --mutation-checks
python3 -m unittest discover -s tests/lemmasim -p test_checkpoint_observer.py -v
python3 conformance/lemmasim/check_fast_lifecycle.py \
  --work-dir build/lemmasim/fast-lifecycle-new --timeout 30
```

This compares same-backend authoritative checkpoint state. It neither defines
cross-backend microstate migration nor closes the unmatched timing/ISA or
unfinished whole-machine capabilities.


## Opt-in logical SoftTLB data increment

The separately named experimental `lemma-silicon-fast-softtlb/0.1.0` binding
retains the original full-continuation `GAP_CONFIRMED`. Its current narrow
qualification is recorded in
[`006-qemu-logical-softtlb.json`](../../docs/evidence/006-qemu-logical-softtlb.json)
and the [versioned contract](../../docs/contracts/006-qemu-logical-softtlb-v1.md).
Historical binaries, public Fast/Session adapters, profile 0.3 hardware and
VMState 3 remain unchanged; actual default derivation equality passed.

A genuinely elaborated Lean RV64IM guest warmed a data translation, changed its
PTE without SFENCE and stopped at a predeclared 1,000,000 ns boundary. The saved
logical cache actually retained old physical page A. Both the original and its
fresh private restored fork subsequently read 111 without SFENCE and 222 after
an actual guest SFENCE, reaching 300,000,000 ns within the 120 s bound. Every final
logical cache slot, comparator/flag, mapping, capacity/eviction/resize field,
flush/dirty counter and admitted pending CPU witness agreed exactly. Raw files
retain their separate ordinary-file hashes and checksums. No whole-state
byte-mask extension or new binary admission to this document's historical
observer is made.

This work also found that ordinary migration dirty-log setup commits the memory
listener and flushes the **original** through `tcg_commit_cpu`. That actual
failed observation remains retained. Only the new paired paused operation
copies every initially-dirty RAM page without starting/stopping that logging
transaction; it does not flush or restore the original cache to force a match.
The selected derivative uses a side-effect-free precise icount resize clock,
explicit nullable region identities and complete physical-page segment/hole
hashes, with fresh host-reference rebinding. These are explicit experimental
backend semantics. The first full host completion took 563.135 s within 1,200 s;
guarded source preparation reproduces its tested latest source exactly.

TB/jump-cache bypass, executable translation, self-modifying instruction
visibility/code dirty tracking/FENCE.I, actual interrupt-handler suffixes and
remaining acceleration pending state are still unqualified. A failed ordinary
VMState load is not transactional and its private fork must be discarded.
Unrepresented queued CPU work rejects rather than being drained. The actual
data suffix establishes only its stated property; total QEMU continuation,
public adapter adoption and cross-backend microstate migration remain absent.

-->
