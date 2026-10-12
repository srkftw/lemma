# Selected 0.3 counter clock and exact state checks

The `lemma-silicon-dev/0.3.0` fast binding consumes the declared 100 MHz
clock. Its `mcycle` source is `floor(local_virtual_ns / 10)`, with the
existing writable and inhibited counter baseline applied. Scaling the
absolute clock before subtracting baselines preserves fractional phase.
`minstret` continues to use actual QEMU instruction accounting and its
existing exception adjustment. It is not equated with RTL retirement.
Historical 0.1/0.2 QEMU derivations remain unchanged.

The selected CPU requires precise icount and rejects filtered or
programmable PMU configurations. Completed paused QMP reset zeros fixed
counters and inhibit state. The new `cpu/lemma-counter-clock/v1` subsection
retains the frequency marker, counter configuration and all fixed-counter
privilege snapshots, alongside existing counter baselines and icount state.
Missing or incompatible counter state rejects. This is same-backend state;
it does not permit RTL/QEMU microstate migration.

The selected 16550 reset also clears FIFO control and sets its threshold to
one. The pinned upstream reset cleared IIR while retaining FCR, so restore
changed a guest-visible register. The original failing observation is retained
under `build/task006-counter-plan/actual-a1`; the fix does not add an allowed
checkpoint difference.

Prepare the genuine Lean power probe through the ordinary launcher, then run
the bounded checker with an unused output directory:

```sh
nix develop --no-write-lock-file --command ./scripts/lemmasim build \
  --backend qemu --profile lemma-silicon-dev/0.3.0 --workload power
nix develop --no-write-lock-file --command python3 \
  conformance/lemmasim/check_counter_state.py \
  --output-dir build/lemmasim/counter-state-new
```

The checker validates the current prepared source and reviewed binary identity.
It requires cold clock, warm reset, UART reset registers, repeated passive
inspection, fractional-phase continuation, writable/inhibited counters, wrap,
unsupported configuration and missing/mismatched state checks. Every serialized
CPU, RAM and device byte must agree under the existing
[two named host elapsed-time fields](QEMU_STATE_EQUIVALENCE.md). It never filters
guest counters or UART registers. Processes and host deadlines are bounded;
each restore runs in an isolated disposable machine.

An optional historical comparison requires the explicitly reviewed A5 binary:

```sh
nix develop --no-write-lock-file --command python3 \
  conformance/lemmasim/check_counter_state.py \
  --historical-reference /path/to/reviewed-A5/qemu-system-riscv64 \
  --output-dir build/lemmasim/counter-reference-new
```

Without that binary, only the historical comparison is `NOT_RUN`; current
clock and state checks remain mandatory. The reference SHA is
`80e54f2095774ecdbfe3bcd36e52e7c55b1c5e566ecf869b4c6ed3f8c857b43a`.
The reviewed current SHA is
`6dc0c7f66bbf3c118da5486c6b000772f1854cda0e235dca57941b4d48b3f6a8`.

Actual maintained runs passed at
`build/lemmasim/task006-counter-current-a1/result.json` and
`build/lemmasim/task006-counter-reference-a1/result.json`. At 100,000,000 ns,
the current cycle counter was 10,000,000, while the historical reference was
100,000,000; both retained 12,499,999 instructions and MTIME 1,000,000 for the
identical probe. Warm restored UART FCR/IIR were 0/1. The current run also
rejected a removed counter subsection.

Counter writes use the pinned debugger's real CSR handlers. The current Lean
primitive catalog does not admit guest-issued `mcycle`, `minstret` or
`mcountinhibit` operations, so instruction/privilege qualification for those
operations remains unexecuted. RTL holds reset for eight actual clock edges;
QEMU completes its paused reset immediately. Reset-duration parity and full
architectural equivalence remain unqualified.
