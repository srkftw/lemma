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

Observed development prerequisites, not final clean-source qualification:

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

Next work follows the assignment order: finish actual isolated User service
execution; run the shared compiled device probe; initialize a fresh raw medium
through Lean on RTL; then stroke/edit/save and cold reopen. The original OpenROAD
tool preparation exceeded its actual 5,400-second bound; a changed, pinned
headless build is running with a 3,600-second bound. Actual layout is NOT_RUN. Do not
infer gates B–F from source existence or the table above. Physical conformance,
SRAM/DRAM integration, nonvolatile physical boot and foundry acceptance remain
UNVERIFIED. No merge is authorized for Task 005.
