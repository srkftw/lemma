# Lemma Task 002 — From the scalar compiler slice to an interrupt-capable freestanding machine foundation

## Mission

Continue implementing Lemma in the existing repository. This is a substantial, multi-part construction assignment, not a planning exercise, review-only pass, or request for another scaffold.

The intended result is a real progression from Task 001's scalar demonstration to a tested freestanding machine foundation: broader source-to-target conformance, compiler-defect detection, correct control flow, bounded loops, checked fixed-region memory, compiled Lean device routines, synchronous traps, timer interrupts, and a small interactive bare-metal monitor integrating those capabilities.

Work through the gates below in dependency order. Implement a gate, execute its checks, inspect its actual evidence, correct failures, and only then advance to work that depends on it. Continue after a passing gate without waiting for another user message. Do not stop merely because one useful subtask is finished.

Do not aim to consume a particular number of hours. Aim to complete verified construction units. Do not idle, inflate test counts, or run redundant work to fill time. If an external execution limit ends the session, leave the highest passing prefix of this assignment committed, reproducible, and precisely resumable.

## Repository and starting point

Expected local checkout: `/home/sreekumaar/Downloads/lemma`.
Expected origin: `https://github.com/srkftw/lemma.git`.
Leave `/home/sreekumaar/Downloads/USGCE` untouched.

Task 001 was published on `task/001-core0-freestanding-slice` in draft PR #1. Its known implementation/evidence head is `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`. This is a reference identity, not permission to reset a newer checkout.

Inspect the actual repository, status, refs, and ancestry first. Read `AGENTS.md`, the architecture, all contracts, Task 001, its evidence, its audits, and the construction backlog. Inspect the actual implementation before designing extensions.

Do not start from the old starter-only `main`. If Task 001 has been merged, use the current `main` containing that work. Otherwise, base this assignment on the latest locally verified Task 001 implementation, preferably its current remote branch tip. Record the chosen base.

Use `task/002-machine-foundation`, or resume that assignment's existing branch. Preserve relevant uncommitted work; do not discard, silently stash, or overwrite it. Isolate unrelated work in another worktree when needed. Do not merge PR #1, force-push, rewrite published history, or modify USGCE.

This assignment expressly extends the previous Task 001-only scope to the features named here. Update task-scoped guidance to distinguish the assignments, but preserve the project's architectural and evidence constraints. Old comments saying Task 001 must not implement traps are not a reason to refuse Task 002's explicitly requested trap work.

## Non-negotiable architecture

1. The target remains RISC-V, using LLVM and the pinned freestanding QEMU `virt` path with `-bios none`. Keep a single hart. Preserve the current integer-only target profile unless a narrowly justified, audited extension is necessary. Do not quietly enable floating point, vectors, compressed instructions, or atomics.

2. Maintained project compiler logic, models, target programs, runtime primitives, and drivers remain Lean 4. Shell, Python, Nix, and workflow configuration may orchestrate host builds, tests, inspection, and publication. They must not become an alternative compiler or target implementation.

3. No target Linux, default OpenSBI, upstream Lean target runtime, libc, libm, libgcc, compiler-rt, foreign allocator, or maintained target C/C++/Rust/Zig/handwritten assembly. Narrow Lean-generated machine instructions for entry, CSR operations, barriers, context preservation, and trap return are permitted and must be audited. Do not conceal a complete assembly program in a Lean string.

4. Programs under test must originate in genuine elaborated Lean declarations. A source generator must emit Lean source and send it through elaboration; it must not supply a preconstructed demonstration IR to bypass the frontend.

5. Compiler-recognized primitives require exact identity, checked signatures, declared effects, semantics, and machine lowerings. No arbitrary extern registration, missing-definition stubs, dummy runtime helpers, or unsound pure wrappers around effects.

6. Preserve `core0-v0.1` and its regression tests. Add explicit new profiles/contracts for new operations. A formerly rejected feature may become supported in a new profile without silently making the original rejection suite meaningless.

7. No `sorry`, `admit`, introduced axioms, or `native_decide` used to certify trusted properties. Keep intentional invalid-source fixtures isolated. Record dependencies of actual proved results.

8. No scheduler, managed heap, general-purpose runtime, page-table isolation, filesystem, proof checker, notebook, recognition, networking, or tutor in this assignment. The integrated finish line is a single-address-space M-mode foundation, not the complete OS.

9. Keep trusted machine glue small. The purpose is to move real algorithms and device logic into compiled Lean, not grow `Harness.lean` into a separately hand-constructed operating system.

## Execution discipline and durable checkpoints

Save this assignment as `codex/prompts/002-machine-foundation.md` on the working branch so it remains available after context compaction. After a resume, reread that file, `AGENTS.md`, and the session checkpoint; verify the recorded source state and continue from the first unfinished gate rather than restarting.

Maintain `docs/plan/002-session-state.md` and a machine-readable gate ledger. Keep the human checkpoint short: base/working branch, latest passing gate, exact commands, current failure, next executable action, and important design decisions.

For each gate, record `not-started`, `in-progress`, `passed`, `failed`, or `blocked`, together with source identity, commands, exit codes, artifact locations, and test counts. A gate with skipped mandatory checks is not passed. A cached result from different source is not a passing result for the current source.

Use the existing pinned Nix environment. Initially reproduce these commands:

```sh
python3 scripts/check_scaffold.py
python3 -m unittest discover -s tests/scaffold -v
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
```

Choose and document coherent commands for the new checks, such as `scripts/check-foundation.sh --phase N` and `--all`; these are requested interfaces to implement, not commands presumed to exist already. Commands must fail closed and produce fresh, attributable results.

Use targeted tests during development, complete affected suites at each gate, and the cumulative suite at major checkpoints and final verification. Commit coherent passing checkpoints instead of leaving a night of work only staged. Investigate failures before continuing. Do not alter expected values or weaken checks to make implementation defects disappear.

Use available parallel workers only for independent, nonconflicting tasks, such as reference tests, documentation review, or adversarial review. Do not assume parallel-worker tools exist, and do not make dependent gates run against unverified interfaces. The primary worker owns integration and reruns.

Prefer existing abstractions. Choose reasonable implementation details autonomously and record consequential decisions. Do not ask the user to choose filenames, library organization, or routine compiler internals. Do not abandon the implementation because an upstream interface is inconvenient.

If a genuine external blocker occurs, preserve passing work, record a minimal reproducer and exact resume command, and continue only independent work that does not assume the blocked result. Never relabel an implementation bug as an external blocker. Never claim the complete assignment passed when only a prefix passed.

# Gate 0 — Establish and repair the tested baseline

Reproduce Task 001 before extending it. Inspect the reported acceptance JSON, the tests that generated it, and retained target output. The previously reported 18 scaffold and 21 harness tests are historical expectations to check, not numbers to print without executing.

Close the earlier evidence-review findings if they remain present:

- The runtime fixture's first eight bytes are `4c 45 4d 4d 41 30 30 31`, ASCII `LEMMA001`. Their little-endian integer interpretation is `0x313030414d4d454c`. Distinguish that wire value from the separately named corpus tag `0x4c454d4d41303031`. Verify host packing, generated guest comparison, and actual bytes. Correct documentation, not a working protocol merely to match a mistaken paragraph.

- Preserve the historical clean run at `800d35963cb63c754584f5b8b0d53244c29c7018`. Distinguish the later report-bearing head `b8e9c593...`, any actual clean local verification of it, and CI's synthetic merge revision. Do not invent a local record that is not available.

- Identify whether the working tree already contains subsequent corrections. Retain them and avoid creating competing versions.

Inspect source-input provenance and build determinism. Record what is covered by source hashes, which files are deliberately excluded, and how generated outputs are tied to the source state. Do not treat a commit ID naming only the starter as the identity of later staged code.

EXIT EVIDENCE: The baseline actually passes in the pinned environment; relevant documentation is accurate; the new task branch contains the implementation rather than the scaffold; existing work is preserved. Then continue immediately.

# Gate 1 — Make the test system detect incorrect compilers

Implement a quarantined compiler-fault injection suite. This must go beyond the existing source-mutation test.

Keep source declarations, runtime inputs, and reference semantics unchanged. Apply a narrowly scoped, Lean-authored test transformation to the lowering or structured output in an isolated build. Produce valid LLVM, a valid ELF, a booting guest, and a well-formed output frame whose mathematical result is wrong.

Include at least six non-equivalent defects with deliberately distinguishing inputs:

- unsigned `<` lowered as `≤`, including equal operands;
- unsigned comparison lowered as signed comparison, including high-bit values;
- addition lowered as subtraction, with asymmetric operands;
- zero extension replaced by sign extension, with the source width's top bit set;
- wrong truncation width or wrong selected bits;
- swapped scalar-call arguments or an incorrect conditional arm.

Choose exact mutations compatible with the existing typed IR. A defect that makes the IR malformed does not satisfy a behavioral fault test. A mutation optimized away does not count as detected; select a source/input that exposes it, or report it as non-distinguishing and repair the test.

Run clean controls and mutants at O0 and O2. For every required mutant, verify compilation, linking, boot, protocol validation, and then a mismatch against the unchanged oracle. A compile error, timeout, provenance rejection, missing file, or malformed UART frame is the wrong failure category for these tests.

Keep mutant identity and provenance honest. Do not weaken the production audit to hide the mutation. Use an explicitly test-only artifact category with normal architecture/dependency checks and a separate expected-behavioral-mismatch outcome. Mutants must never be normal release artifacts or selectable by a production input packet.

Add adversarial tests for forged, incomplete, stale, and tampered manifests; misleading PASS output followed by process failure; and negative fixtures that fail for an unrelated diagnostic. Require the intended rejection reason, not merely nonzero exit.

EXIT EVIDENCE: All clean controls pass; every required mutant produces a verified behavioral mismatch; other failure modes are classified distinctly; no mutant enters the ordinary compiler path. Record the matrix and continue.

# Gate 2 — Test the frontend, not just the checked IR and one root

Generalize the source-to-target runner so it can compile and execute multiple declared roots and supported scalar signatures. Remove the effective dependency on one hardcoded `entry : UInt64 -> UInt64 -> UInt64 -> UInt64` demonstration, while preserving the legacy harness as a regression mode.

Define a versioned typed test ABI. Host descriptors must carry root identity, signature, argument values, and expected result type. Reject inconsistent metadata, invalid Boolean encodings, excess arguments, truncation, and inappropriate out-of-range values. Any widening into a transport word must be explicit and agree at both ends.

Establish three comparisons:

1. Direct host evaluation of the original elaborated Lean function, without routing through the custom Core0 checker/interpreter to compute the expected value.

2. The independent checked-Core0 reference evaluator.

3. Actual compiled RV64 execution.

This distinguishes frontend translation errors from lowering/code-generation errors. Document shared assumptions, including the pinned host Lean implementation; do not claim three absolutely independent proof systems. For small primitive anchors, use kernel reduction or mathematical lemmas where practical.

Cover every currently admitted operation and conversion with actual target execution. Add at least 24 meaningful source roots spanning `Bool`, `UInt8`, `UInt32`, `UInt64`, nested lets, nested conditionals, direct calls, cross-module helpers, shared dependency graphs, multiple return types, and mixed-width internal signatures. Include empty-argument constant functions if admitted, and otherwise explicitly reject them.

Add call-boundary cases with more than eight integer arguments so stack-passed arguments are exercised. Preserve inspectable calls in a dedicated ABI-test configuration; an O2-inlined expression is not evidence for the call boundary. Check parameter/result extension rules and stack alignment against the selected RISC-V ABI. Do not silently widen the guest ABI to hide mistakes.

Use deterministic, recorded source-generation seeds and runtime-input seeds. Reach at least 1,024 distinct meaningful target cases per O0/O2 profile, distributed across the source roots rather than concentrated in one trivial expression. Use batching to avoid thousands of unnecessary emulator startups, but the batch runner must still execute each compiled function and record each result.

Exhaustively compare direct-source and model results over all 65,536 UInt8 input pairs for a small, named set of arithmetic/comparison primitives. Use stratified boundaries and generated cases for wider types. Log actual coverage, not just one aggregated number. Keep resource use bounded and avoid exponential generated expressions.

Add source-preserving metamorphic checks: alpha-renaming, helper extraction/inlining where valid, harmless module reorganization, equivalent let nesting, and adding an unreachable host-only import. These must not change semantics or accidentally introduce target-runtime dependencies.

EXIT EVIDENCE: Source evaluation, the checked model, and RV64 agree across the declared matrix; every admitted operation has target coverage; ABI tests exercise real call paths; mismatches have reproducible inputs. Continue without expanding into managed Lean.

# Gate 3 — Correct control flow and complete the systems-relevant scalar operations

The current scalar lowering eagerly computes both branches before LLVM `select`. Do not carry that approach into effectful or potentially unsafe operations.

Implement structured basic-block lowering with conditional branches and merge values. Validate block termination, dominance, predecessor sets, and phi operands. Preserve pure `select` only when its legality is established; do not require LLVM's optimizer to retain your exact textual block structure if it preserves semantics.

Introduce explicit profile/version changes for the new behavior. In the new profile, implement complement, left/right shifts, and unsigned division/remainder for the supported widths, using the actual pinned Lean semantics over the entire admitted input domain.

Inspect upstream definitions and run direct-source probes. Do not guess what division by zero or an oversized shift means. Implement the correct guards, masking, reductions, or result rules. Never execute LLVM division with a zero divisor or a shift outside its legal range merely because a later `select` discards its result. Do not add signed arithmetic as a casual extension.

Do not add emitter assertions such as `nsw`, `nuw`, `inbounds`, alignment, or aliasing promises without establishing their premises. Distinguish unsupported emitter promises from flags legitimately inferred later by the pinned optimizer.

Keep the old v0.1 rejection fixtures meaningful. Run them under the old profile; add new positive and rejection tests under the new profile. Record the profile in every manifest and fail on unsupported versions.

Test zero divisors, zero numerators, maximum values, width-minus-one/width/width-plus-one shift counts, very large counts, and branch-dependent operations. Add mutation tests for wrong guards and wrong count handling. Require correct source/model/target results at O0 and O2.

Add a small number of actual mathematical lemmas used by the implementation or model: fixed-width normalization, conversion round trips under stated bounds, or another nontrivial invariant directly needed here. Do not prove unrelated identities merely to increase theorem counts. Record theorem statements and axiom dependencies without presenting them as a proof of the full compiler.

EXIT EVIDENCE: CFG validation succeeds, old-profile behavior remains intact, new scalar semantics match the pinned source over the declared tests, and dangerous operations are never executed outside their valid LLVM domain. Reuse this control-flow path in subsequent gates.

# Gate 4 — Compile bounded iteration from real Lean source

Add an explicit bounded-iteration facility that compiles to actual target loops rather than compile-time repetition proportional to the requested runtime count.

Choose a narrowly defined source construct: a designated finite-fold/countdown combinator, a recognized bounded recursion shape, or an equivalently precise library interface. Its body must pass through normal Lean elaboration and the same transitive checker. A callback resolved statically to a closed function is acceptable under a documented rule; arbitrary runtime closures and higher-order dispatch remain rejected.

Specify counter width, iteration order, accumulator representation, maximum execution budget, and what exceeding a declared budget means. Distinguish semantic exhaustion from compiler/model traversal fuel and from a host timeout. Do not silently clamp input or return a fabricated normal answer when a budget is exhausted.

Start with scalar loop-carried values and add only the small fixed-layout state representation actually necessary for later gates. No heap-backed tuples, arrays, or closure allocation may leak into the target. Inspect generated object code and stack usage; runtime iteration must use bounded stack rather than recursive stack growth.

Implement and test runtime-counted summation, a bit-mixing fold, nested bounded iteration, and a closed helper as the loop body. Cover zero, one, several, maximum-allowed, and over-budget counts. Demonstrate that changing the source loop body changes guest results. Reject forbidden operations reached inside the body, including through another helper.

Model loop behavior independently. Prove a directly useful iteration-bound or simple fold-correctness lemma where feasible within the chosen representation. Do not add a general recursion escape hatch to get the example working.

EXIT EVIDENCE: Actual loops consume runtime-provided counts, agree with source/model behavior, terminate or report the defined budget outcome, preserve stack limits in measured tests, and add no hidden runtime. Continue to memory.

# Gate 5 — Add checked fixed-region memory and explicit effects

Construct the first real target memory API. This is not a general allocator or hardware isolation system.

Define named, statically configured regions with base, length, permitted widths, alignment, read/write permissions, and purpose. Separate ordinary scratch RAM, input records, output/event buffers, image storage, stacks, and MMIO. Keep device regions out of the general RAM-access interface.

Expose operations through an explicit effectful Lean interface whose elaborated use can be checked and lowered. A syntactically pure `UInt64 -> UInt64` function must not conceal memory writes or device effects. Compute effects transitively through calls and loop bodies. Statically eliminable tokens or combinators are acceptable only with a precise representation/erasure argument, not as permission to import a managed state monad.

Implement loads/stores at 8, 32, and 64 bits, explicit little-endian interpretation where relevant, and recoverable checked failure for invalid requests. Define errors through a bounded scalar or fixed-layout result representation. Do not introduce a heap-backed exception mechanism.

Use overflow-safe checks. Establish the region interval's validity before access; validate width before subtracting it from length; validate offset against the remaining length; validate alignment and permissions. Do not let `offset + width` wrap into an apparently valid range. Do not claim a type alone prevents forging authority: check the actual source path and runtime values admitted by this profile.

Provide a finite-memory Lean model with observable read/write events. Test ordinary round trips, overlapping in-region operations, each width, endianness, the last valid access, one-past-end, misalignment, read-only writes, maximum UInt64 offsets, unknown/forged region identifiers, and denied accesses to stack/image/device regions. Rejected operations must not access the forbidden address or modify guard bytes.

Add genuine local proofs connecting the model's bounds predicate to interval containment and showing a rejected modeled write preserves memory. State the gap between those lemmas and emitted machine code. Check that runtime access guards dominate the actual loads/stores in the lowering and test them on the guest.

Compile real source routines for a bounded buffer fill, bytewise checksum, and small overlap-aware copy if the semantics are fully specified. Do not satisfy the gate by performing those algorithms on the host or by emitting a separate hardcoded LLVM implementation.

EXIT EVIDENCE: Source-level algorithms perform actual RAM operations, agree with the model, deny invalid accesses, preserve canaries, and pass object/dependency audits at O0/O2. State explicitly that this is checked access within a trusted M-mode image, not isolation against arbitrary privileged machine code.

# Gate 6 — Move device work into compiled Lean

Extend the memory/effect model with separate declared MMIO operations and the required compiler/hardware ordering boundaries. Document register widths and side effects. Do not mark device access as ordinary pure memory or assume `volatile` alone proves every required ordering property.

Use the exact pinned LemmaVM/DTB information. Do not copy unverified physical-board addresses or build a physical hardware port. A correct pinned-machine implementation is the objective; a general device-tree parser is not a prerequisite for this assignment.

Implement source-level UART transmit, receive, status polling, bounded timeout behavior, and hexadecimal or bounded packet encoding. Move substantial existing machine-harness formatting/polling logic into normal elaborated Lean declarations where the new profile supports it. Leave only genuine machine-entry, CSR, fence, and interface primitives in the generated glue.

Support runtime host-to-guest interaction after boot, not only the initial loader fixture. The guest should receive at least two different requests in one session and return independently computed answers without rebuilding its image.

Test malformed input, truncated packets, invalid lengths, unsupported commands, receive/transmit timeout, and recovery or defined terminal failure. A polling loop that never exits is a failed test, not a usable driver. Inspect the optimized code and effect manifests for accidentally eliminated, duplicated, or reordered device operations.

Add branch-effect tests: only the chosen branch writes its designated RAM marker or performs its permitted device action. Verify helper calls and loop bodies do not bypass the effect checker. Preserve the original Task 001 harness as a regression until replacement equivalence is demonstrated.

EXIT EVIDENCE: Actual compiled Lean routines exchange runtime data with QEMU's UART, respect bounds and effects, and remain independent of hosted IO or a managed runtime. Continue to traps.

# Gate 7 — Build synchronous trap entry, dispatch, and return

Implement a minimal but real machine-mode trap substrate. Audit the pinned RISC-V privileged specification and QEMU behavior; cite exact source/spec revisions in repository documentation.

Required pieces: boot-time interrupt masking, a valid direct-mode trap vector, a documented trap-frame layout, a dedicated bounded trap stack or an equally explicit stack strategy, CSR snapshots, dispatch to compiled Lean, controlled return, and a fatal path for unexpected traps.

The low-level entry/exit sequence must come from the Lean-authored structured machine representation. Do not write an assembly file and merely move it into a string.

Save interrupted state before using it. Preserve all integer registers whose values must survive asynchronous interruption, not just the ordinary ABI's callee-saved subset. Include the interrupted stack pointer and critical machine state. Establish ABI alignment before calling compiled code. Keep floating-point/vector instructions forbidden so their state is outside this declared profile.

Use actual synchronous traps such as an M-mode environment call and a breakpoint in controlled fixtures. Check cause, faulting PC, and relevant status fields. Treat trap-value fields according to the specification, including cases in which zero is permitted. Resume only from explicitly authorized test sites with known instruction lengths; do not blindly add four to every trap PC.

Unknown causes or unexpected PCs must take a bounded fatal diagnostic path. Do not repeatedly retry the faulting instruction, swallow the trap, or make the host print a success line on behalf of a dead guest.

Keep trap handling non-allocating and initially non-nested. Define the double-fault behavior. Run target register-sentinel and stack-canary tests, then compare foreground computation before and after repeated synchronous traps. Add at least one deliberately broken save/restore test that the target register checks detect.

Recheck earlier invalid-memory tests with the trap substrate active: a software-denied access should remain a checked error, not become a silently recovered hardware fault.

EXIT EVIDENCE: Real traps enter the vector, reach compiled Lean dispatch, preserve the declared context, return correctly at approved sites, and terminate diagnostically at unapproved sites. No scheduler or privilege transition is required.

# Gate 8 — Deliver actual timer interrupts during useful computation

Bring up the timer hardware provided by the exact pinned QEMU machine. Determine its interface, addresses, timebase, and interrupt configuration from the corresponding source/DTB. Do not assume another board's CLINT/ACLINT arrangement or depend on an SBI call.

Implement timer arming/rearming and a minimal ISR using the established trap path. Account for compare-update behavior, pending interrupts, masking, deadline arithmetic, and permitted spurious/delayed observations. Use fixed-width arithmetic with a stated deadline range; do not make wraparound an implicit undefined case.

Keep the ISR short and non-allocating. Defer formatting and UART output. Add a fixed-capacity event ring or another bounded event buffer with explicit overflow accounting. Define the single-hart interrupt/foreground synchronization mechanism, including compiler visibility and memory ordering. Small critical sections are acceptable; enabling an atomic extension or importing a threading runtime is not an automatic solution.

Run a known foreground checksum/fold while real timer interrupts occur. Verify the final foreground result against an interrupt-disabled control. Observe tick/event progression, sequence consistency, and register/stack integrity.

Test masked delivery, unmasking with a pending event, repeated rearming, event-buffer overflow, bounded catch-up, and shutdown. Demand hundreds of observed timer events across stress configurations without choosing exact wall-clock spacing as a correctness oracle.

Include two distinguishing failures: an omitted/corrupted saved register must be caught by context checks, and disabled timer arming must fail the required-event observation. Host sleeps, injected software counters, and manually calling the ISR are not evidence of hardware timer interrupts.

EXIT EVIDENCE: Foreground compiled Lean and actual interrupts coexist without observed state corruption under the declared tests; event overflow is visible; no unbounded ISR work or undeclared runtime is introduced. This is not a scheduler or a hard-real-time latency result.

# Gate 9 — Integrate a useful freestanding diagnostic monitor

Build one coherent demonstration image, primarily from compiled Lean source, that uses the capabilities already verified. Do not replace integration with separate test banners.

Define a small versioned, bounded UART protocol with request IDs, lengths, status codes, and unambiguous framing. Implement these command classes or exact equivalents:

- `HELLO`/`STATUS`: protocol, Core0/machine profile, and current counters;
- `EVAL`: dispatch to selected compiled scalar routines on fresh runtime arguments;
- `FILL`: update an allowed scratch-buffer interval;
- `CHECKSUM`: return the checksum of an allowed interval;
- `TRAP_TEST`: invoke and recover from a specifically authorized synchronous trap;
- `TIMER_START`/`TIMER_STOP`/`TICKS`: control and observe the tested timer path;
- `EXIT`: orderly test completion through the declared VM termination mechanism.

Command dispatch, parsing, validation, buffer algorithms, and formatting must use the new compiled source path. The host may generate requests and validate outputs; it must not implement the guest algorithm or precompute answers into its image.

Run a scripted session combining valid requests, malformed requests, buffer boundary cases, event overflow, trap recovery, and foreground work while timer interrupts are active. Send inputs after the image is built and after boot. Reuse the same ELF for differing request streams.

Provide compact sample transcripts and the actual command used to interact with the image. Preserve raw frames and protocol-level results. Ensure the normal success result requires the guest's computation, not merely a startup banner or nonempty serial output.

EXIT EVIDENCE: One bare-metal RV64 image handles a mixed interactive session with correct calculations, checked buffer access, actual trap recovery, and real timer events. That is the primary end-to-end finish line for this assignment.

# Gate 10 — Qualify the integrated result, including its failure paths

Run the full cumulative suite in the pinned environment at O0/O2, including legacy Task 001. Add a bounded extended stress profile rather than making every developer invocation unmanageably slow. Keep seeds and manifests reproducible, and minimize any discovered failure to a permanent regression.

Strengthen the artifact audit for the expanded image. Every added object, section, helper, intrinsic, CSR operation, special symbol, and machine primitive needs a named role and source provenance. Do not simply weaken the former two-object check into an arbitrary-object allowance. Check ELF attributes, actual disassembly, entry/layout, relocations, dynamic dependencies, undefined symbols, optimized code, initialization, and stack/resource assumptions.

Verify new tests fail when the corresponding feature is intentionally broken. Preserve distinct outcomes for behavioral mismatches, denied accesses, expected traps, fatal traps, missing interrupts, malformed protocol, process failure, and timeout. An expected negative test passing is different from its intentionally faulty guest passing.

Keep report generation transactional or otherwise resistant to stale PASS files. Inject an early failure after an old successful run and verify no consumer mistakes the old report for new success. Missing mandatory output or missing retained evidence must fail verification.

Repeat clean builds within each optimization profile and compare the intended reproducible artifacts. Explain intentional provenance or timestamp differences instead of deleting evidence to force identical hashes. Do not require O0 and O2 images to match one another.

Add/update pinned CI to run the real checks, retain artifacts even on failure, and enforce bounded runtime. Separate metadata checks from guest execution. A workflow that cannot run the new target checks is not green evidence for those features. Use narrow workflow permissions and no new secrets or external paid infrastructure.

Commit the implementation, then verify it from a separate clean detached worktree without copying prior build output. Capture full source identities and artifact hashes. Avoid a self-referential evidence-commit loop: record the tested implementation revision/tree and, separately, the later report-bearing revision or CI checkout identity. A synthetic PR merge checkout must be labeled as such.

EXIT EVIDENCE: The integrated feature set reproduces from clean source, expected failures are distinguishable, legacy behavior remains supported, and the retained evidence matches the exact tested source.

# Gate 11 — Publish a reviewable milestone and an exact continuation point

Keep Task 001 history and historical evidence intact. Write `docs/evidence/002-machine-foundation.md`, a compact machine-readable summary, and full hash inventory. Map each completed gate to the Stage I/early Stage II units it actually advances. Keep uncompleted obligations open.

Include the implemented profiles, source APIs, models/proofs and their limits, compiler route, tested machine contract, memory/effect policy, trap-frame convention, timer assumptions, commands, toolchain pins, executed tests, actual output, artifact locations, and unresolved risks.

Update README and `AGENTS.md` with commands that exist and have run. Correct obsolete scaffold-only wording without claiming that the complete OS now exists. Retain a short resume file even when all requested gates finish.

Push the task branch normally and configure its upstream. Do not force-push, change credentials/settings, or merge automatically. Open a draft PR when authenticated tooling permits. If PR #1 is still unmerged, use a clearly labeled stacked PR against its implementation branch so reviewers see only the new work. If Task 001 is already in `main`, target `main`. Record the base relationship rather than modifying PR #1 yourself.

If publication or CI is unavailable, preserve the local commit and report the exact blocker. Continue independent local verification rather than pretending remote success. If CI is available, inspect actual failures and repair assignment-owned problems; do not merely report that a workflow file exists.

## Required final handoff

Return a compact, evidence-bearing report with:

- repository, base, working branch, full final commit, pushed state, and PR URL;
- a gate table distinguishing passed, failed, blocked, and not-run work;
- what now executes on RV64 that Task 001 could not execute;
- exact test commands and observed counts/results, including mutant detection;
- the interactive monitor transcript or the last completed integration transcript;
- proof/model claims separately from target tests and artifact audits;
- clean-worktree verification and actual CI state;
- remaining limitations, the highest passing gate, and the next executable task.

Do not claim G1 or G2 complete merely because this assignment's monitor works. Do not claim general Lean support, hardware memory isolation, a managed runtime, a scheduler, physical-board compatibility, or proved compiler correctness.

Success means verified new compiler and machine capability, not the length of the report. Start with Gate 0 now, and keep implementing through the dependent gates while their prerequisites pass.