<!--
# Task 003 — supervisor kernel and isolated volatile service

Lemma now has a compiled RISC-V M/S/U system with reusable owned memory, Sv39 address spaces, task scheduling, capabilities and copied blocking IPC. Separately linked U programs operate a U-mode Buffer Server while an independent CPU-bound competitor is preempted. The practical CLI supports binary create/write/read/append/status/destroy operations; a separate client exercises isolation and progress. The Server owns real allocated backing pages, enforces authenticated callers and leases, and reports explicit transport and application errors. Buffers are volatile; restart loses their contents.

**Technical Gates A–K are verified at implementation commit `14cc79be8914a349b729347cc05091aba6ac7ca7`, tree `7a3a5d25c7bdb0e599e8c1ade0771f5533c09224`, against current main `a899ccbb3c880e44ab529b65131cf6ea49a198d2`.** Both current push and PR runs completed successfully with all eight jobs each. The evidence-only report-bearing head checks, user-authorized confirmed merge and post-merge CI remain pending at this snapshot. The completed service and architectural observations below retain their exact historical sources. The frozen implementation/legacy source is `c3b71eaf1568cc5eb0fc9b03500523b76c8adfdb`, tree `cc36063ff26a154b7c792317a8a1c9554235e7a3`. Its first fresh cold run completed every target/qualification command successfully but the external post-command validator failed because `llvm-nm` was absent from its host PATH. That original FAIL is retained. The second fully cold campaign, running the unchanged wrapper inside the whole pinned Nix environment, completed PASS in 920.036302811s and passed independent full raw/artifact/qualification review. Current-base14 complete GitHub integration passed; final report-head checks and merge followup remain pending.

## Source-specific verification

| Scope | Actual result and source |
| --- | --- |
| A–I complete cold prefix | PASS at f24: 28 images, 32 checker reports and 36 actual QEMU sessions, independently reviewed. |
| Buffer service J | PASS at clean64: four normal/development O0/O2 sessions; 1,224 ordinary commands. Ten independent User images matched 140 byte bindings. |
| Architectural K subset | PASS at clean64: 12 cases/36 attack instances; faults remain contained and managed peers continue. Halfword ECALL is a real hardware ECALL at a PC rejected by the kernel ABI; U SRET/MRET are actual illegal-instruction faults. |
| Canonical source negatives | PASS at clean64: four cases/eight control-plus-mutant guests. Timer-disabled and Append-last-byte mutants produced retained genuine inner failures. |
| First cold c3 legacy | Task001 PASS: 23 fresh boots. Task002 cumulative/stress PASS: 482 fresh boots. Maintained qualification PASS: 26 raw replays, two reproducible profiles and five failure experiments. All nine commands exited 0; outer host validator FAIL `llvm-nm` missing. |
| New whole-pinned c3 campaign | PASS: Task001 23 fresh boots, Task002 482 fresh boots, qualification 26 replays/66 artifact roles/16 deterministic artifacts per profile/two reproductions/five failure experiments. All 470 source inputs and 4,166 original files stayed unchanged; cleanup was fully reaped/empty. |
| Initial d4 GitHub checks | Both push and PR completed FAIL, eight jobs each. A–E failed on path-fetch disk exhaustion, Foundation on a stale Trap binding; push J failed strict frame-count accounting while PR J passed. Original failures are retained. |
| Old-base c3 checks | Push38032283197 and PR38032285139 were both automatically CANCELLED by the existing workflow after six successful/two cancelled jobs each; neither is a complete pass. The successor supersedes it. |
| Current-base14 checks | [Push38033677526](https://github.com/srkftw/lemma/actions/runs/38033677526) / [PR38033679993](https://github.com/srkftw/lemma/actions/runs/38033679993) both completed SUCCESS, all eight jobs each, at actual API head14. The PR artifacts use exact synthetic4f/tree7a3a; all eight independent PR artifact lane reviews also passed and are bound in the CI catalog. |

The c3 PR synthetic merge `e9c7b8a25dc1c52c830c9c9248b24a4911c788f1` has exact parents `ff4045a79a6fda45f9cd8198587357846530a806` and c3 and the same tree as c3. This evidence covers the old Task002 base. Current main advanced to docs-only `a899ccbb3c880e44ab529b65131cf6ea49a198d2`, tree `cdccca7edf0cad1365659f8b702614bb4db1e24f`, through LemmaSim PR4; normal integration is now committed as `14cc79be8914a349b729347cc05091aba6ac7ca7`, tree `7a3a5d25c7bdb0e599e8c1ade0771f5533c09224`, with exact parents c3 and a899. Its nine changed paths are documentation only. All eight actual new push/PR job conclusions are SUCCESS in both runs. The final evidence-only report-bearing head CI remains required. Historical merged Task002 base is `ff4045a79a6fda45f9cd8198587357846530a806`, reviewed tree `5a0df7b44d7b71c6966b8363399acdba41c73bbc`.

No tracked Lean, examples, Lake configuration, toolchain pins, flake/lock or workflow changed between the clean64 target observations and c3. The intervening host repairs correct dependency realization/provenance, exact closure guards, strict replay and source realization. This continuity does not rebind old artifacts or establish a new head's acceptance.

## Reusable interfaces and execution boundary

`Kernel.Memory.Frames`, `AddressSpace` and `Loader` provide checked owner/purpose/generation handles, real Sv39 mappings, prevalidated package loading, zero-before-publication and rollback. `Task`/`Scheduler` provide provisional managed construction, integer context preservation, timer preemption, sleep and IPC blocking, termination and inactive reclaim. `UserCopy` preflights a complete bounded range before mutation or consuming input. `Capability`/`Objects` enforce caller-local types/rights, attenuation, serial/generation retirement, alias withdrawal and one-shot Reply authority. `IPC` copies packets, stamps the actual full sender and handles cancel/timeout/death. `Directory` and `KernelInput` provide checked live discovery, epochs and one granted framed UART reader.

Ordinary programs share `User.Memory`, `Syscall`, `Capability`, `IPC`, `Discovery` and `BufferClient`. The kernel handles authority and IPC packets; Buffer opcodes remain in the separately linked Server. The normal service has Server/CLI/Peer/CPUBound images and no Development imports, restart selector or adversarial startup. The development package is separate.

The compiled M firmware owns PMP/CLINT and validates saved S-origin calls; compiled S policy owns allocation, page tables and scheduling; independently linked U images have isolated text/data/BSS/stacks. Generated typed primitives save the complete integer frame and sanitize return state. Each task owns two contiguous 4KiB kernel-stack frames; teardown runs from a stable supervisor continuation. The largest reviewed selected O0 trap call chain is 8080/8192 bytes, including the 288-byte vector, leaving a 112-byte static margin. This is an artifact call-graph bound, not a physical stack measurement. Trusted S policy retains a RW pool direct-map alias for frames whose U text leaf is RX; User-PTE W^X does not establish strict whole-kernel W^X. The build uses genuine Lean elaboration and the versioned Core0 lowering through pinned LLVM/LLD, with exact code/table/primitive provenance and stack audits. No target upstream Lean runtime, libc or foreign runtime is linked.

Nine source-level ownership/rights model statements were checked by the pinned Lean kernel in fresh private output paths. They are separate from host fixtures, compiled-artifact audits and QEMU observations; they do not prove the compiler or complete kernel. These are single-hart virtual-platform results, with no physical-board/display measurements. A managed Lean runtime, persistence/filesystem, networking, UI/notebook and device proof-checker/tutor remain future work.

## Actual two-client recovery

This excerpt is the unchanged clean64 J-development-O0 wire, source `64ca4f5254170c07989d1788bf9c2714004443e3`. Full IDs are CLI550, Peer572, Busy596 and Fault6251. The [retained wire transcript](003-kernel-isolated-services-transcript.json) contains the exact source, records, raw offsets and RPC bytes. Result SHA256 `7255365a42c304778bac307f471198cc449080b6620fc682f3e6c96e6692a346`; received raw SHA256 `44b5b0c9178d06dfe2d25fff48e3a55b67057eb3f219c8730db74c09b1180695`; sent raw SHA256 `0a496d8831c991dd52687ac010e1e99e31e4e34cf3597302c3c1be5ad043e332`.

| Actual wire index | Retained observation |
| --- | --- |
| 26 | Busy596 timer preemption at arithmetic PC0x10230, actualIRQ5. |
| 231 | Independent Peer572 reads its private handle4, digest2dfef9a915f311e3. |
| 1785 →1787 →1789 | Actual store-pagefault15 →Fault6251 termination44 →22 task frames reclaim383→405. |
| RPC1869 and10582 | Same live CLIhandle6 reads identical128 actual bytes after fault/reclaim and before the dead client's lease expires. |
| 10680 | Server expires the dead client's own handle11. No subsequent same-handle survivor read before restart is claimed. |
| 11003 →11006 | Replacement Server1039 publishes epoch2; the pending CLI Call returns transport96. |
| 11160 | Peer rejects its old epoch tuple with application200, then recovers. |
| RPC11436 | Reconnected CLI reads128 fresh epoch2 bytes, including binary00/FF. |

## Build and use

```sh
nix develop --no-write-lock-file --command ./scripts/build-kernel.sh \
  --configuration service-normal --stage supervisor --opt-level O2 \
  --output-dir build/kernel/service-normal --clean --timeout 300
nix develop --no-write-lock-file --command python3 scripts/buffer-cli.py \
  --image build/kernel/service-normal/image.elf \
  --output-dir build/kernel/service-terminal --timeout 3600
```

The terminal waits for real service publication and continuously drains output while reading input. Use actual returned handles with `buffer create`, `write`, `append`, `read`, `status` and `destroy`; `hex:00ff` is binary and ordinary text is UTF-8. Transfers are bounded128 bytes. Use fresh output paths to retain failed attempts. Read each BufferClient response before a later call reuses its response buffer.

The [final artifact index](003-kernel-isolated-services-artifact-index.json) binds the installed report package and current CI/review records. The [compact report JSON](003-kernel-isolated-services.json) links key source-specific reports, independent reviews, helper/provenance hashes and preserved historical failures. The [detailed report JSON](003-kernel-isolated-services-detail.json) retains the complete history, and the [CI catalog](003-kernel-isolated-services-ci.json) binds the actual completed run records. Full Gate K technical qualification is complete at tested implementation14: both actual current-base push and PR runs have all eight jobs SUCCESS. Local historical source labels remain64/f24/c3 and are not rebound to14. The complete c3 cold campaign is independently validated, with its source kept distinct from docs-integrated14. The final report-bearing commit must then pass its own complete checks before the merge. The user explicitly authorized merging; the original draft-only milestone instruction is superseded by that authorization. A guarded merge, actual resulting main SHA and post-merge CI must then be confirmed. USGCE is untouched. No next implementation task is started.

The current LemmaSim canonical machine contract is planned and unimplemented. Task003 observations use the historical pinned QEMU profile and establish no canonical LemmaSim conformance or physical equivalence.

The [acceptance command catalog](003-kernel-isolated-services-commands.json) gives the exact maintained A–E, F–I, J, architectural/source-negative and legacy/qualification interfaces. For example:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_kernel.py --work-dir build/kernel/verify-A-E --clean --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_cumulative.py --lane F-I --work-dir build/kernel/verify-F-I --clean --deadline 2400
nix develop --no-write-lock-file --command python3 scripts/check_kernel_cumulative.py --lane J --work-dir build/kernel/verify-J --clean --deadline 2400
```

These controllers retain source, compiled audits, full raw bytes and kill/reap evidence; missing evidence or deadline expiry fails. A clean committed source is mandatory for final qualification and the fresh isolated mutation campaign.

The fully pinned cold outer report is SHA256 `0489515d2a1fae118bfe5f4bcd2ff02a719107a8845222dc1ecf17d1bfa9575f`; independent complete review `27bed71a1e5492a9a25cb7674b66c87b6be0ad9430f72480fcaf20a6f64147e8`. The earlier same-source outer FAIL `ea4129e022ddda75243b525efa42c1c69e2ab8ce1df4f021ce12325f81dc5d04` is retained separately. No old FAIL was relabeled.

The complete [base hash inventory](003-kernel-isolated-services-hashes.json) and [source-specific extension](003-kernel-isolated-services-inventory-extension.json) are both retained. Together they bind 21 original and seven added trees: 14,415 unique files / 1,181,412,055 bytes, including 8,493 added rows. The base keeps its full non-tree source/model/report metadata. An independent read-only review rehashed every listed file and all 66 absolute references and checked clean f24/c3 source snapshots, unchanged Lean and the exact three host-source repairs; review SHA256 `b76e6a4b41480b92ed79efdeebbc17df77ceaf42c36ae548273963a6effb4b1c`. Historical source labels and failed reports remain distinct.

The original maintained [pre-final Markdown](history/003-kernel-isolated-services-pre-final.md) and [pre-final JSON](history/003-kernel-isolated-services-pre-final.json) are preserved verbatim, with SHA256 `22403e45f128483c585f2746ab4f121fc98e4c5a46b8dafb5ac5c89bfcc5ccc4` and `be42279f0f7af6c4223a9b2ab3e00cb906e0b26ac92e6a37ec7adb11089254e0`. Their historical observations keep their original scope.

Current-base14 artifact review is complete: six lanes index SHA256 `9a82c6937df7728244ec96ef98797907f6c5c7000894218d2b69a15b29c0f64a`, architecture/source-negative index `65d2b1332054613db949e34fd39cac728da3e736bef2ec9753a80be47741d913`. They bind all eight exact PR artifact IDs and actual checkout `4f47423e19321356d44c35ce8e4643421990ad32` / tree `7a3a5d25c7bdb0e599e8c1ade0771f5533c09224`; both run API records have head14 and eight successful jobs. A separate read-only binding review rehashed 13,897 declared downloaded files / 1,172,732,472 bytes. Remote process absence cannot be inspected locally, and unuploaded legacy olean bytes cannot be rehashed; exact recorded wait/reap evidence, genuine source/elaboration commands and completed remote jobs retain those limits. Original mutant inner failures and external-reader failures remain unchanged.

-->
