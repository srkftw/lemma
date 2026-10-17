# Guest WFI/timer execution diagnostic v1

This development diagnostic uses the existing Kernel0.4 and Firmware0.1
checked Actions, genuine elaboration, LLVM and audited freestanding RV64. It
adds no language profile, processor extension or production image selector.
`WfiTimerPolicy` runs in S mode with SIE clear; the maintained M firmware
programs MTIMECMP and forwards SSIP. WFI notification is distinguished from a
delivered S trap. The supervisor dispatcher treats a delivered trap as failure.

The guest rejects relative timer requests999 and10000001, then requests8192,
1000,1001 and4096 ticks. It records each real deadline, pending observation,
WFI-call count, IRQ-count transition and time ordering in32768 bytes of owned
diagnostic RAM. The four actual M trap frames add256 bytes. It allows bounded
spurious returns, requires notification before advancing, and executes WFI again
with SSIP already pending without manufacturing an extra timer IRQ. An ordinary
Lean epoch word distinguishes warm retention from loss. No debugger CSR writes
supply these observations.

Build a new diagnostic artifact in the pinned environment:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_guest_wfi_timer.py \
  --work-dir build/silicon/wfi-new --build-only --timeout 120
nix develop --no-write-lock-file --command env LEAN_NUM_THREADS=2 \
  lake env lean -j2 tests/kernel/WfiTimerExecutionCompile.lean
nix develop --no-write-lock-file --command python3 -m unittest discover \
  -s tests/silicon -p test_wfi_timer.py -v
```

The build command establishes artifact provenance and audits, not execution.
The [execution evidence](../evidence/006-wfi-timer-execution-v1.json) binds the
actual121-input/45-project-Lean producer, unchanged native/fast cores, guest
records, independent host oracle, resource supervision and retained failures.
Native execution reached its genuine waiting cut at462000 cycles with a future
comparator, SIE clear and nonzero fractional timer phase. The original and a
private restored fork then executed identical600000-cycle suffixes and matched
all145145686 authoritative bytes. The original machine was not flushed,
drained or rearmed for comparison. This qualifies that specific native cut.

Literal reset stimuli separately initialized peripheral state and checked
requested held edges1,2,8,17, first release, cancellation, RAM/overlay/controller
retention and reset origin. Full guest reboot completion failed in each original
600000-cycle window: three interrupts had occurred and the fourth deadline was
still future. Those failures remain failures. The missing-only observer corrected
an import error after CPU execution without rerunning it. No660000-cycle
replacement bound was adopted.

The same ELF on the pinned fast backend completed original/warm/new-cold epochs
1/2/1 under the original50000000ns/120s bounds. Its paused reset advanced no
virtual time, retained the complete diagnostic RAM and exposed actual MTIME0
and M privilege before guest execution. Original host Path-type and numeric
privilege-format failures are retained separately from the corrected observation.
Fast WFI semantics do not establish native pipeline timing, native held-reset
duration, arbitrary cached-state continuation, U-mode WFI/TW or complete ISA
qualification. The rejected QEMU instruction-cache experiment remains stopped.
