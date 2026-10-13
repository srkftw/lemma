<!--
# Lemma digital power/control v1

`lemma-silicon-dev/0.3.0` extends the preserved 0.2 binding with a digital
power/control subwindow at `0x10010500`, 256 bytes, and PLIC source14. It uses
descriptor ABI4; word25 is the power base. The existing descriptor, paper
aperture, memory, geometry, durable records and device ABIs remain unchanged.
The DTB declares `lemma,power-v1`. Historical profiles do not expose this device.

All registers use aligned little-endian 64-bit accesses. Unsupported offsets,
sizes and writes produce a bus error and error2; malformed writes have no
requested power effect. Magic is `0x4c505752`; version is1.

| Offset | Read | Write |
|---|---|---|
| 0 | Magic | Invalid |
| 8 | Version | Invalid |
| 16 | State:0 RUN,1 SUSPENDED | Invalid |
| 24 | Error:0 none,1 BUSY,2 invalid | Invalid |
| 32 | Reset cause:1 cold,2 warm,3 legacy Laboratory cut | Invalid |
| 40 | Raw button level0/1 | Invalid |
| 48 | Events:bit0 suspend request,bit1 wake | Invalid |
| 56 | Button rising-edge epoch, saturating u64 | Invalid |
| 64 | Wake cause:0 none,1 button,2 authorized resume | Invalid |
| 72 | Zero | Command1 suspend,2 resume |
| 80 | Zero | W1C event mask0..3 |
| 88 | Zero | Clear error, value1 only |

An admitted timestamped raw `button LEVEL` event changes only an external
digital level. A rising edge increments the epoch, sets the request event in
RUN, or changes SUSPENDED to RUN and sets wake event/cause1. A new rising event
wins simultaneous acknowledgement. No host gesture or command requests guest
suspend. PLIC14 is level asserted while events are pending.

At one delivery cycle, the last admitted button level is sampled once. All raw
rows remain captured in admission order. A paused press and release assigned
the same delivery cycle therefore produce no rising edge. Pen ingress at that
boundary uses the state before the button sample, including on wake.
The successor admits any delivery cycle at or after virtual now and inserts it
into the bounded device queue in timestamp order. Equal-time admission order
is stable, so an earlier future button can be admitted while later pen samples
are queued. Historical fast profiles retain their original monotone admission
restriction. The wrapper records admission time separately from delivery time.

Command1 rejects with BUSY if already suspended, a block queue/transfer,
unconsumed block completion, paper update or fabric transaction is pending.
The Lean driver additionally checks its pending request/completion state before
issuing this command. Rejection neither drains nor cancels that operation.
Successful suspend retains RAM, CPU and task contexts, timer/time phase,
target/latch/visible panel state, durable base and volatile medium overlay.
It does not save, flush, acknowledge storage or complete a refresh. The pen gets
an explicit loss/resynchronization boundary through its existing RESET1
semantics; its old head cannot become a new stroke without loss acknowledgement
and a fresh release/contact boundary. Unadmitted pen/UART queues and future
scheduled pen/UART events are canceled; scheduled raw button events remain.
New pen/UART input arriving while suspended is captured but discarded at its
device boundary. Other device registers are not reset.

The kernel consumes power-button requests, reports acceptance/BUSY, and enters
cooperative suspend by withholding User dispatch and executing the existing
S-mode WFI path until a wake is admitted. Timers and controller clocks continue.
Spurious WFI/timer returns do not resume User tasks. This is a functional
cooperative suspend policy, not CPU clock gating, electrical sequencing,
battery-life measurement or watchdog implementation. The separately named
power endpoint and syscall68 authorize notebook control; arbitrary endpoints
and the store's block grant confer no power authority.
The power-enabled boot selects volatile object-table version2, with word24
equal to5 and a five-endpoint limit. Historical version1 requires word24 zero
and retains its four-endpoint limit. Other versions/limits fail validation.
The global sixteen-object budget, eight-Reply budget, key generations, row
layout and capability rights are unchanged. The fifth object is the separately
granted power authority; it does not alias surface, input, block or document
authority. This volatile successor changes no durable notebook format.
An accepted syscall68 suspend stores the advanced User PC and reply, marks the
task ready, and returns the actual supervisor continuation before any User
instruction can execute. Command2 in RUN is a harmless no-op clearing error.
An observed wake takes priority over an older simultaneously observed request.
The kernel acknowledges those observed bits and does not reissue suspend from
that old request; a new edge at the acknowledgement boundary remains pending.

Warm reset clears RUN/error/events/wake state and reports cause2, retaining the
button epoch/physical level. Cold reset reports cause1, epoch0 and level0.
Existing machine reset retention/cancellation rules still apply. Snapshot state
includes every controller field, physical button level, scheduled button event,
event cursor and execution/time phase; live host handles remain external.

The preserved RTL-only raw Laboratory `reset` event reports cause3: it performs the
historical processor/controller reset, clears the volatile medium overlay,
and retains wrapper RAM. It is distinct from the lifecycle cold power cycle,
which creates cold device state from permitted durable backing.

Actual Lean observation records are `0x440 SOURCE STATUS STATE EPOCH` for
request decisions (source1 raw button,2 authorized syscall; status0 accepted,
196 BUSY,197 invalid), `0x441 WAKE_CAUSE EPOCH TIME 0` for wake, and
`0x442 RESET_CAUSE EPOCH BUTTON_LEVEL 0` after validated boot initialization.
They are guest UART output, not fabricated host completion records.

-->
