import Lemma.Core0.Memory

/-! Finite S-owned WFI/timer diagnostic. Existing Kernel4 operations only;
all intervals, pending checks, records and verdicts are ordinary Lean Actions.
The startup keeps SIE clear. A notification is not a delivered S trap. -/
namespace Lemma.Platform.RiscV.Development.WfiTimerPolicy
open Lemma.Core0.Memory

def recordBase : UInt64 := 0x80410000
def recordMagic : UInt64 := 0x57464954494d4501
def completeMagic : UInt64 := 0x574649444f4e4501
def failure : UInt8 := 51
def read (address : UInt64) : Action :=
  .platform .physicalRead64 address 0 0 0 0 0 fun s v => .done s v
def write (address value : UInt64) : Action :=
  .platform .physicalWrite64 address value 0 0 0 0 fun s v => .done s v
def word (slot value : UInt64) : Action := write (recordBase + slot * 8) value
def call (number payload : UInt64) : Action :=
  .platform .firmwareCall number payload 0 0 0 0 fun s v => .done s v
def time : Action := call 2 0
def count : Action := call 4 0
def pending : Action :=
  .platform .readSupervisorPending 0 0 0 0 0 0 fun s v => .done s v
def wait : Action :=
  .platform .waitInterrupt 0 0 0 0 0 0 fun s v => .done s v

def interval (i : UInt32) : UInt64 :=
  if i = 0 then 8192 else if i = 3 then 4096 else 1000 + (i.toUInt64 - 1)

def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (word i.toUInt64 0) fun s _ => .done s acc

/-- Count every completed WFI call. Spurious returns are allowed; an actual
pending observation alone terminates the finite attempt. -/
def waitStep (_i _n : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind wait fun s _ => if s = 0 then
  .bind pending fun s value => if s = 0 then
  if value = 1 then .done Status.iterationStop (acc + 1) else
  if value = 0 then .done 0 (acc + 1) else .done failure 0
  else .done s 0 else .done s 0

def awaitNotification : Action :=
  .boundedFoldU64 65536 waitStep 65536 0 0 0 0 0 fun s calls =>
  if s = Status.iterationStop then .done 0 calls else
  if s = 0 then .done 23 calls else .done s calls

def recordCase (i : UInt32) (ticks before deadline after irqBefore irqAfter
    beforePending calls afterPending afterPendingTime afterPendingCount : UInt64) : Action :=
  let slot := 32 + i.toUInt64 * 16
  .bind (word slot i.toUInt64) fun s _ => if s = 0 then
  .bind (word (slot + 1) ticks) fun s _ => if s = 0 then
  .bind (word (slot + 2) before) fun s _ => if s = 0 then
  .bind (word (slot + 3) deadline) fun s _ => if s = 0 then
  .bind (word (slot + 4) after) fun s _ => if s = 0 then
  .bind (word (slot + 5) irqBefore) fun s _ => if s = 0 then
  .bind (word (slot + 6) irqAfter) fun s _ => if s = 0 then
  .bind (word (slot + 7) beforePending) fun s _ => if s = 0 then
  .bind (word (slot + 8) calls) fun s _ => if s = 0 then
  .bind (word (slot + 9) afterPending) fun s _ => if s = 0 then
  .bind (word (slot + 10) afterPendingTime) fun s _ => if s = 0 then
  .bind (word (slot + 11) afterPendingCount) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

def timerStep (i _n : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let ticks := interval i
  .bind time fun s before => if s = 0 then
  .bind count fun s irqBefore => if s = 0 then
  .bind (call 5 ticks) fun s deadline => if s = 0 then
  .bind (word 2 (0x10 + i.toUInt64)) fun s _ => if s = 0 then
  .bind pending fun s beforePending => if s = 0 then
  if beforePending < 2 then
  .bind awaitNotification fun s calls => if s = 0 then
  .bind time fun s after => if s = 0 then
  .bind count fun s irqAfter => if s = 0 then
  if irqAfter = irqBefore + 1 then
  if before < deadline then if deadline ≤ after then
  .bind (word 2 (0x20 + i.toUInt64)) fun s _ => if s = 0 then
  .bind wait fun s _ => if s = 0 then
  .bind pending fun s afterPending => if s = 0 then
  .bind time fun s afterPendingTime => if s = 0 then
  .bind count fun s afterPendingCount => if s = 0 then
  if afterPending = 1 then if afterPendingCount = irqAfter then
  if after ≤ afterPendingTime then
  .bind (recordCase i ticks before deadline after irqBefore irqAfter
    beforePending calls afterPending afterPendingTime afterPendingCount) fun s _ =>
  .done s (acc + 1)
  else .done failure 0 else .done failure 0 else .done failure 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0
  else .done failure 0 else .done failure 0 else .done failure 0
  else .done s 0 else .done s 0 else .done s 0
  else .done failure 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0

def run (boot : UInt64) : Action :=
  .boundedFoldU64 4096 clearStep 4096 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (word 0 recordMagic) fun s _ => if s = 0 then
  .bind (word 1 boot) fun s _ => if s = 0 then
  .bind (call 3 0) fun s witness => if s = 0 then
  if witness = 0x534543414c4c0001 then
  .bind (word 7 witness) fun s _ => if s = 0 then
  .bind (call 5 999) fun low _ => if low = 22 then
  .bind (word 5 low.toUInt64) fun s _ => if s = 0 then
  .bind (call 5 10000001) fun high _ => if high = 22 then
  .bind (word 6 high.toUInt64) fun s _ => if s = 0 then
  .boundedFoldU64 4 timerStep 4 0 0 0 0 0 fun s completed => if s = 0 then
  if completed = 4 then
  .bind (word 4 completed) fun s _ => if s = 0 then
  .bind (word 2 0x30) fun s _ => if s = 0 then
  .bind (word 3 completeMagic) fun s _ => .done s completed
  else .done s 0 else .done s 0
  else .done failure 0 else .done s 0
  else .done s 0 else .done failure 0 else .done s 0
  else .done failure 0 else .done s 0 else .done failure 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Only this guest-owned epoch word survives its own record clear. M startup
clears the independent128-byte boot handoff, not this diagnostic RAM interval. -/
def main : Action :=
  .bind (read recordBase) fun s magic => if s = 0 then
  .bind (read (recordBase + 8)) fun s prior => if s = 0 then
  if magic = recordMagic then
    if prior < 16 then run (prior + 1) else .done failure 0
  else run 1
  else .done s 0 else .done s 0

/-- SIE remains clear. Any delivered S trap is a distinct controlled failure. -/
def dispatch (_frame _cause _value : UInt64) : Action := .done 50 0

end Lemma.Platform.RiscV.Development.WfiTimerPolicy
