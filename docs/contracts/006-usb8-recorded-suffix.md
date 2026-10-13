# USB8 recorded native suffix checks

USB8 inherits the container-6 raw continuation relation from
`006-usb-raw-continuation-v1.md`. The implementation identity and every native
build input remain load-bearing. A restored attachment is suspended until a
complete matching tape is admitted; it never starts a host, contacts the
original peer or resubmits an external transaction. Crossing the tape horizon
rejects before advancing the virtual clock.

The actual USB8 notebook produced two retained properties on the fully audited
`task006-usb-next-a1` native package. At 440 million cycles a configured link
had raw `WAIT 100000` command 15892 pending. Its private 20-million-cycle suffix
matched every authoritative snapshot byte in 163.536 seconds. At 570 million
cycles a real USB packet was queued while the panel scanned. Its private
75-million-cycle suffix admitted the four original recorded pen requests at
600 million cycles and matched the retained 645-million-cycle checkpoint in
327.157 seconds. This second suffix reproduced failed Save status 227, including
disconnect state. It does not establish successful lost-reply reconciliation.

Snapshot RPC costs were 3.006 and 0.949 seconds respectively. Their archives
were about 146 MB, separate from guest RAM. No-tape and prefix/full-horizon
crossing attempts rejected without changing inspection state. Restoring and
binding the tapes did not change the initial snapshot bytes. Original source
and fixture hashes, retained observer/host-bound failures and exact resource
measurements are in `docs/evidence/006-usb8-recorded-suffix.json`.

`scripts/check_retained_usb_suffix.py` extracts the reusable private replay
interface. It validates both public checkpoint inventories, preserves exactly
the recorded raw pen admissions, restores with no external peer arguments,
checks horizon rejection, advances in at most five-million-cycle groups and
compares complete final native checkpoint bytes. Its initial input-negative
tests qualify malformed/missing/corrupt inventory, unsupported profile,
symbolic files, event order/cursor and unaccepted or non-pen requests. The
measured properties above retain their original fixture identities; they are
not relabeled as an execution of the extracted checker.

The equivalent reusable command for the retained longer property is:

```sh
python3 scripts/check_retained_usb_suffix.py \
  --native-bundle build/native/task006-usb-next-a1 \
  --snapshot build/usb/usb8-pending-live-a2/cut-1 \
  --prefix-tape build/usb/usb8-pending-live-a2/prefix.tape \
  --prefix-cycle 575000000 \
  --tape build/usb/notebook-next-workflow-a1/live-failure.usb.tape \
  --final-snapshot build/usb/notebook-next-workflow-a1/live-failure.snapshot \
  --external-log build/usb/usb8-pending-live-a2/external.jsonl \
  --expect-failed-save 227 --work-dir build/usb/retained-suffix-NEW
```

The default 200-million-cycle/1800-second resource ceiling comes from the
previous measured five-million-cycle groups. It is a bounded host workload,
not a processor timing WCET. Original live cold/action ceilings remain
unchanged. Exact raw replay is separate from cold journal recovery, open-ended
private live-peer continuation, QEMU cached-state continuation and USB PHY
conformance.

The live lost-reply observer now requires the initial document-root durable
receipt before fault eligibility. Ready can precede that receipt in ordinary
guest code. Both Ready and this prerequisite must fit the original
1.6-billion-cycle/7200-second cold ceiling. The observer records the actual
pre-fault receipt/Saved baselines and restart-thread exception; it never uses
an unrelated initial Saved acknowledgment as evidence for the new stroke.
