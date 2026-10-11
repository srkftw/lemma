# Task 005 checkpoint

Active branch: `task/005-open-silicon-bringup`, based on main
`23b19296f5938821cdc5c092c3921e55e0067a28`. The exact specification from
draft PR #6 was cherry-picked with attribution as `ef635f55916277c91ee51ab7adf10476bf444669`.
PR #6 remains a separate dependency. Task 004 PR #5 is merged; its historical
publication report retains the state observed when that report was written.

Implementation is in progress. The selected processor is CVW
`20f2af74e7aa76513e94012231d16567fa42648a`, configured for one RV64IM hart,
Zicsr/Zifencei/Zicntr, M/S/U and Sv39. Its 4 KiB instruction cache is enabled;
its data cache is disabled. The silicon profile, real RTL controllers and
shared Lean platform seam are described in
[the development binding](../contracts/005-silicon-dev-0.1.0.md).
The current development binding selects 1,024 owned frames, quota128 and four-page
stacks, with a real 4 MiB RTL DMA window. Its expanded layout supports the short
notebook configuration; it does not claim the canonical 32 MiB capacity floor.

Earlier observed development prerequisites (their original identities and failures are retained):

| Observation | Retained output | Meaning |
|---|---|---|
| Existing Lean scalar on 4 KiB register RAM | `build/silicon/scalar-register-canonical` | Fresh O0/O2 strict audits and 20 independent-reference cases; architectural ROM reset and finisher, no external 128 MiB RAM |
| Existing Lean monitor, canonical RTL O0/O2 | `build/silicon/monitor-canonical-O0`, `build/silicon/monitor-canonical-O2` | Eleven independent response checks, arithmetic/control flow, one synchronous trap and three real timer traps in each run; unchanged historical Lean monitor image identities |
| RTL device tests | `build/silicon/device-unit6` | Pen FIFO/loss, paper latch/Busy/reset including repeated reset and final-pixel reset, block DMA/FLUSH/error, bounded RAM; literal bus stimuli, not guest gate C |
| Corrected paper synthesis/map | `build/silicon/physical/paper-fourth` | 76,687 cells, 5,480 flip-flops, 1,036,021.455 µm²; same controller source as device-unit6; external target/latch/panel excluded |
| Register RAM synthesis/map | `build/silicon/physical/register-ram-first` | Explicit 32,768 storage bits mapped to flip-flops; not an SRAM macro claim |
| Existing isolated services, incomplete campaign | `build/silicon/service-canonical-short1` | Real M/S/U, IPC, exact opaque-byte write/read, 53 checked math preemptions and held-buffer quota denial; FAIL at 1,800 seconds before architectural fault |
| Expanded-pool initializer, incomplete campaign | `build/silicon/initialize-rtl1` | FAIL at 900 seconds / 48 million observed cycles in S-mode allocation; no format/FLUSH acknowledgement |
| New development configuration host checks | `build/silicon/platform-1024-checks.json` | Genuine elaboration and 512/8192/1024 Action fixtures, 311 kernel / 80 LemmaSim / 25 silicon host tests; forbidden DeviceProbe import rejected before lowering, not RTL acceptance |

The first uncached service run exhausted its cycle budget before User startup;
`build/silicon/service-first` is retained as incomplete/FAIL. The cached short run
reached real User IPC and retention, but contained-fault/reap and post-fault
continuation are still pending. Its cleanup killed/reaped the process group;
the failed-protocol UART quiescence deadline remains a cleanup error. Strict
guest-audit failures from incomplete exact selector/source-edge updates remain
retained; none is an accepted image. Obsolete/terminated display synthesis
attempts remain failures with their original source identities.
The monitor's O0/O2 runs have independently validated their different observed
work/interrupt schedules, rather than requiring identical cycle counts. The
native QEMU model's repeated warm-reset handling was also corrected to retain
Interrupted; all 80 LemmaSim host tests passed, including a mutation reverting
that fix. Those host tests do not replace a guest boot or durability session.
The alternate explicit host -O3 build produced identical monitor observations
but measured slower; the canonical build remains selected. Earlier source-bound
artifacts retain their original identities after the 1,024-frame binding change.

Current integrated observation: `build/silicon/service-final2-acceptance-detached/result.json`
is **PASS**, SHA256 `eb35e51953059f0bb935d496c57d1c3f623a52d8ee524cf046412e612f79af9c`.
The genuine Lean service image is from clean `b6a843454fb758327a4a5e34709e69107fcd1e52`,
SHA256 `fc6e94e212fa9d7fd697bae0920aca94f72b9734420d76070580f7a195653d2c`.
The independent existing buffer checker verified all five actors through actual
RTL M/S/U execution, Sv39, capability/IPC denials, generation reuse, 109 arithmetic
preemptions, an audited read-only-text store fault (cause15, stval0x10000),
reap/containment, and exact CLI and Peer reads after the fault. It replayed all
1,648 complete UART frames and verified image/audit/source identity before and
after bounded process cleanup. Elapsed2,220.609575 seconds; its frozen source lease
has ended. Earlier short-service and interrupted runs remain FAIL.

`build/silicon/scalar-register-b6a8434/result.json` passed20 fresh O0/O2
Lean scalar cases on the real4 KiB register-memory configuration.
`build/silicon/physical/compute-81d26d2/result.json` passed actual generic
and SG13G2 mapping:261,179 cells,51,770 flip-flops,5,116,861.864798 µm²,
no residual memories, latches or unresolved cells. This is the compute/fabric
slice with real instruction cache/register file/TLB; external working RAM,
ROM and custom peripherals are excluded. It is not full-SoC synthesis.

The native regression at `build/lemmasim/native-confirmation-6e96485/result.json`
passed fresh O0/O2 write and cold reopen with unchanged, identified `b6a8434`
guest images. Its corrected host workflow waits for the actual explicit guest
Save/Compact Pending-to-Saved confirmation rather than a stale Saved observation.
The earlier local native writing failure is retained; the successful rerun does
not relabel it. PR7 CI at `b6a8434` passed nine jobs and failed the independent
architecture observer's stale boot-selector expectation. The closed selector
repair has passed focused host checks; a fresh integrated architecture run is pending.

The RTL initializer reached real User execution but returned the existing
Store Format.readOnly223 status. Its unsuccessful run is retained at
`build/silicon/initialize-b6a8434-rtl1`; no format/FLUSH acknowledgement occurred.
Inspection found that CVW replicates SW across64-bit HWDATA and the bridge failed
to mask the selected MMIO width, so QueueNum8 could reach the controller as
0x0000000800000008. The bridge and narrow DMA return lane are being corrected
and checked through literal bus tests and fresh guest traffic. The full short
RTL notebook workflow is **not yet passed**.

The pinned headless OpenROAD build completed successfully. The first real
paper place/CTS/global-route run failed detailed routing on a disconnected
constant alias. A guarded removal preserves connected constants; a fresh
routed-controller attempt is running. SG13G2 process DRC/LVS and extracted
post-route timing remain NOT_RUN. Physical conformance, implementable large
working memory, nonvolatile physical boot and foundry acceptance remain
UNVERIFIED. No merge is authorized for Task005.
