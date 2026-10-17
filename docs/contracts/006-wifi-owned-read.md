# Owned CommonOFDM opaque read experiment

This is an opt-in privileged Lean client for one companion-v1 READ512. It uses
the existing `lemma-silicon-dev/0.12.0`, descriptor ABI13/features47 and
`core0-kernel-v0.8` authority. It adds no MMIO aperture, interrupt source, User
capability, BootNV grant or accepted language feature. Historical selections
and the original Common12 queue probe retain their exact authority and results.

The client constructs the complete72-byte request in a live Kernel-owned
data-purpose frame. Writer is nonzero, sequence is zero, offset is512-aligned
and wholly inside the268435456-byte opaque medium, payload length is512 and
error is zero. It uses the existing companion-v1 magic/version and CRC64-ECMA
over little-endian bytes. No host constructs the guest request.

A separate owned data frame carries five physical DATA fragments:16,16,16,16,8
bytes, seed93. The trusted four-slot Queue retains its ordinary generation,
purpose, pin and actual TX-completion checks. The client uses one slot at a
time. Its request cursor advances only after genuine TX completion; a delayed
completion is pending, not success. The context has one retained pin throughout
the pending transaction and cannot be released. No new request overwrites it.

The independently executed hosted-Lean `sim/companion/Peer.lean` receives the
actual decoded request bytes and reads opaque medium bytes. Host adapters only
move decoded bytes and raw peer PIO/sample stimuli. The peer does not interpret
documents, ink, guest journals, recovery or mathematical content. A successful
response is584 bytes:8 header words,512 payload bytes and8 CRC bytes. Its37
physical DATA fragments are36 times16 bytes and one8-byte fragment, seed127.
Packet alignment and these length/seed expectations are explicitly configured;
there is no acquisition, PLCP/MAC, HE, RF or standard timing claim.

The client copies each immutable RX head into the retained owned context before
releasing that head. At64 bytes it checks magic/version, response kind3, exact
writer, sequence0, exact offset and response shape. Success requires length512
and error0. A nonzero error up to4095 admits only a zero-length72-byte reply,
whose CRC must also validate; it quarantines the transaction with its error and
cannot produce a read result. All other identities/shapes fail closed.

Publication requires the complete response and CRC64 over its entire header
and payload. Then the512 bytes are copied to the owned result region, the
packet frame is released, the context pin is removed, and the completion phase
is committed. Only the validated result API returns its owned address. Caller
ownership lasts until explicit frame release. READ success does not establish
a durable write/commit, a saved notebook, a User service or notebook integration.

Context offsets are: magic0, phase8, TX cursor16, RX cursor24, writer32,
offset40, poison48, RX armed56, packet handle64, result flag72, in-flight TX
length80, reply total88, peer error96. Request bytes start128, received reply768,
result1536 within the same4096-byte owned frame. Phase0 is fresh,1 transmitting,
2 receiving,3 validated. Poison never clears. Contexts/packet frames and Queue
metadata are part of ordinary RAM and exact checkpoints; all raw peer events,
pending samples and controller state remain in the existing wrapper9 boundary.

Missing/lost traffic stays pending until an actual controller fault, including
its RX watchdog, then remains quarantined and pinned. There is no implicit retry
or timeout-to-success. A bounded caller must report exhaustion honestly. Faults,
invalid fragments, corruption and uncertain post-enqueue writes retain pins
and partial bytes in quarantine. Cancellation/recovery of uncertain ownership,
durable receipt/outbox write policy, external coexistence/reset/power recovery,
User IPC/capability integration and full Wi-Fi6 remain separate unfinished work.

If storing a newly allocated packet handle fails before pin/queue/device work,
`beginRead` returns that distinct packet handle with its error. The caller still
owns the original context and can release both unpinned frames; the finite host
fixture checks that cleanup. A failure after the validated data was copied can
leave the context unpinned before its final phase commits. Poison still prevents
the result API from exposing it. This does not qualify general fault reclamation.

Qualification is prospective: finite host boundary fixtures, genuine Lean
lowering/object inspection and actual same-machine sample/queue/PLIC traffic
have separate receipts. Initial CPU budget is30000000 clocks/600 host seconds;
new private pending suffixes are2000000 clocks/120 host seconds each. Original
FAILs and exact consumed sources/tools remain retained. No masked state fields,
forced clean boundaries, parent-owner changes or cross-backend restore are
admitted. The old Common12 probe/configuration is not relabelled as this client.

The actual initial request reached an in-flight RX-arm checkpoint at12282160
clocks. Its software armed flag was0 while hardware RX was active; the PC lay in
the genuine checked IO.write64 routine. The saved instruction/RTL state is kept
intact. The original2000000-clock reply suffix failed at14282160 with528 reply
bytes/33 packets, retaining both frames and the context pin. That result remains
FAIL. A separately declared1000000-clock/120-second tail admitted only the final
56 bytes/four packets, ran the bounded72-word CRC and64-word copy, and completed
the read with explicit release. This is functional completion with two measured
phases, not a rewritten original bound or a claimed broad3000000-clock pass.

Independent private tails from that same14282160 checkpoint produced exact
complete-checkpoint/UART equality, rejected corrupted final CRC in guest policy,
and observed a real RX watchdog when the remaining traffic was withheld. Failure
cases retain both frames and the context pin. No qualified cancellation or
reclamation API exists. The proposed follow-up was stopped after automatic
review rejection; no cancellation implementation or executable experiment landed.

The ordinary target builder remains reusable with its exact opt-in selection:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_wifi_common_target.py \
  --configuration lemmasim-silicon-wifi-common-read-probe \
  --work-dir build/kernel/unused-wifi-read
```

`scripts/check_wifi_owned_read.py` retains the original30M/600 initial and2M/120
reply limits and supports an independently qualified pending observation without
repeating the CPU/request prefix. The separately scoped successful tail entry is
`scripts/check_wifi_owned_read_tail.py`; the checked receipt contains its actual
full command and source/archive associations. Use unused output directories.
