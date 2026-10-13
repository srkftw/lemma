# USB6 Surface-v2 notebook deployment

`lemmasim-silicon-usb-bulk-notebook` and
`lemmasim-silicon-usb-bulk-initialize` are explicit software selections on the
unchanged `lemma-silicon-dev/0.6.0` hardware. The public workload names are
`usb-bulk-notebook` and `usb-bulk-initializer`. Historical defaults and USB6's
original notebook/initializer selections retain their dispatchers and meanings.
The hosted decoded-packet peer is presently exposed in Developer/Laboratory
mode. This is a development transport deployment, not the finished Student
companion permission or distribution experience.

The deployment is `lemma-managed-sums-bulk-usb-deployment-v1`: the real Store
User1 image, `Notebook.mainSumsBulk` User2 image and isolated Sums Arithmetic3
User3 image. Image numbers do not imply runtime versions. Kernel6's exact
`dispatchUSBBulk` selection admits Surface-v2 operation5 through
`dispatchModernBulk 6`. The existing owned-buffer USB block driver, Power-v2
policy and real guest Store journal remain the storage path. The bounded
Surface-v2 layout, complete User-source preflight, seven-tile limit and
controller error-prefix behavior are specified in `006-paper-bulk-v2.md`.

USB enumeration, configuration, DATA toggles and occupied-slot NAK behavior
remain controller/guest/host protocol operations. Raw native transport does
not mark the controller configured. Hosted Lean policy3 carries the specified
opaque backing frames to an independently persistent hosted Lean peer; only
the peer's actual barrier and retained receipt permit durable acknowledgment.
`006-usb-backing-policy3.md` specifies that boundary and its separately observed
Store initialization result. The host never constructs or recovers documents.

The connected checker is `scripts/check_guest_usb_notebook.py`. It starts from
a private copy of actual guest-formatted empty media and resolved writer state,
then requires canonical cold Ready and every expected controller pixel. It
supplies original raw pen events, exercises Undo/Redo/page navigation and an
explicit Save. An earlier autosave cannot satisfy explicit Save: a newly
admitted Pending report must precede a matching new Saved report. The native
seven-word ingress log is compared without fabricating sequence/epoch words;
the full nine-word identity is independently checked in the guest's immutable
raw objects.

Before the first stroke, the checker selects raw reply ordinal6 after restarting
the peer. The independently inspected peer log must establish that this was
the raw-chunk publication barrier, following exactly
`write, write, write, barrier, write, barrier`. If actual traffic differs, the
checker fails rather than selecting a different lost reply after observing it.
No Saved may precede reconciliation. Restart/retry must use the same retained
writer/transaction and leave one durable barrier effect. This tests live guest
continuation with peer restart. It does not claim a simultaneous guest/host
restart at that uncertain boundary.

A later independent cold CPU must recover all acknowledged journal bytes and
the complete expected display without formatting or manufacturing a new Save
on clean reopening. A disconnected subsequent write must report Failed,
preserve ordinary raw ink through the actual controller, retain prior
acknowledged bytes and produce no new Saved. The private offline backing
observer includes every actually retained write prefix; it does not interpret
an error as rollback. The disconnected-before-request scenario separately
expects no new peer effects.

Declared resource ceilings, fixed before machine launch, are:

| Phase | Target cycles | Host seconds |
| --- | ---: | ---: |
| Each cold Ready/full redraw | 1,600,000,000 | 7,200 |
| Raw stroke and receipt reconciliation | 200,000,000 | 7,200 |
| Each edit/navigation/Save or failed-save redraw | 1,600,000,000 | 7,200 |

These ceilings use the retained canonical cold/redraw observations and the
56-million-cycle USB Store workload to bound resources. They are not a proved
WCET or timing parity. The checker records each phase's actual cycles/duration,
sampled owned process-tree resident/thread highwaters, individual process
highwaters and observer memory. Host backing/presentation memory remains
separate from target RAM and the actual 8192-frame guest pool. Owned children
are terminated and reaped on failure; cleanup failure cannot yield PASS.

Preparation admits fully audited genuine guests and the exact native4 machine
only through their complete explicit source archives. No changed-source
fallback, fresh-compilation claim or new default backend is introduced. The
new whole-image audits and connected scenario need their own observed receipts;
component checks and earlier Store evidence do not establish notebook success.
USB whole-machine snapshots remain rejected because complete hosted policy and
pending transport state are not serialized. Physical USB encoding/full USB
conformance, browser hosted-process transport and owner authentication remain
open.
