import Lemma.Kernel.Memory.Access
import Lemma.Kernel.Console

/-! Reusable private firmware ABI bridge. Normal S-mode initialization validates
the actual startup readbacks and exercises the hardware timer notification.
Supervisor execution stays nonpreemptible; a pending SSIP is not a delivered
S trap or scheduler decision. No SBI compatibility is claimed. -/
namespace Lemma.Kernel.MachineServices
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def call (number payload : UInt64) : Action :=
  .platform .firmwareCall number payload 0 0 0 0 fun s v => .done s v
def time : Action := call 2 0
def interruptCount : Action := call 4 0
def pending : Action :=
  .platform .readSupervisorPending 0 0 0 0 0 0 fun s v => .done s v
def wait : Action :=
  .platform .waitInterrupt 0 0 0 0 0 0 fun s v => .done s v
def failed (s : UInt8) : Bool := if s = 0 then false else true
def invariantFailure : UInt8 := 51
def quantum : UInt64 := 1000000 -- 100ms on the pinned 10MHz machine timer

def rearm (ticks : UInt64) : Action :=
  if 1000 ≤ ticks then
    if ticks ≤ 10000000 then
      .bind time fun s now =>
      if failed s = true then .done s 0 else
      if now ≤ 0xffffffffffffffff - ticks then call 1 (now + ticks)
      else .done 22 0
    else .done 22 0
  else .done 22 0

/-- Deadline calculation takes place in the private M service, so the smallest
admitted relative interval does not shrink while S executes its call boundary. -/
def rearmRelative (ticks : UInt64) : Action := call 5 ticks

def expectedPmp (index : UInt64) : UInt64 :=
  if index = 0 then 0x20001fff
  else if index = 1 then 0x20041fff
  else if index = 2 then 0x20ffffff
  else if index = 3 then 0x0400001f
  else 0x000401ff

private def pmpStep (i _count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (0x80400020 + i.toUInt64 * 8)) fun s value =>
  if failed s = true then .done s 0 else
  if value = expectedPmp i.toUInt64 then .done 0 acc
  else .done invariantFailure 0

/-- BootInfo is already validated. These fields were read from actual M CSRs
by the typed startup before MRET; later origin is independently checked by the
M trap policy on the S ECALL witness. H's fixed read-only mideleg mask is pinned
to QEMU rv64; no extra enabled virtual interrupt source is admitted. -/
def validateReadbacksFor (expectedInterrupts : UInt64) : Action :=
  .bind (Access.read64 0x80400018) fun s pmp =>
  if failed s = true then .done s 0 else
  if (if pmp = 0x1b1b1f1818 then false else true) = true then .done invariantFailure 0 else
  .boundedFoldU64 5 pmpStep 5 0 0 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 0x80400048) fun s exceptions =>
  if failed s = true then .done s 0 else
  if (if exceptions = 0xb1ff then false else true) = true then .done invariantFailure 0 else
  .bind (Access.read64 0x80400050) fun s interrupts =>
  if failed s = true then .done s 0 else
  if (if interrupts = expectedInterrupts then false else true) = true then .done invariantFailure 0 else
  .bind (Access.read64 0x80400058) fun s status =>
  if failed s = true then .done s 0 else
  if (if status &&& 0x1baa = 0x800 then false else true) = true then .done invariantFailure 0 else
  if (if (status >>> 32) &&& 15 = 10 then false else true) = true then .done invariantFailure 0 else
  .bind (Access.read64 0x80400060) fun s translation =>
  if failed s = true then .done s 0 else
  if translation = 0 then .done 0 0 else .done invariantFailure 0

def validateReadbacks : Action := validateReadbacksFor 0x1446

private def awaitStep (_i _count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind pending fun s notification =>
  if failed s = true then .done s 0 else
  if notification = 1 then .done Status.iterationStop 1 else
  if notification = 0 then
    .bind wait fun s _ => .done s acc
  else .done invariantFailure 0

/-- WFI may return spuriously, so only the actual pending bit terminates this
bounded attempt. Missing timer progress also fails the host's finite deadline. -/
def awaitNotification : Action :=
  .boundedFoldU64 1024 awaitStep 1024 0 0 0 0 0 fun s value =>
  if s = Status.iterationStop then .done 0 value
  else if s = 0 then .done 23 0 else .done s 0

def initFor (expectedInterrupts probeTicks : UInt64) : Action :=
  .bind (validateReadbacksFor expectedInterrupts) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (call 3 0) fun s witness =>
  if failed s = true then .done s 0 else
  if (if witness = 0x534543414c4c0001 then false else true) = true then .done invariantFailure 0 else
  .bind (Lemma.Kernel.Console.record 0xc0 witness 0x1b1b1f1818 0xb1ff expectedInterrupts) fun s _ =>
  if failed s = true then .done s 0 else
  .bind interruptCount fun s before =>
  if failed s = true then .done s 0 else
  .bind (call 0xffffffffffffffff 0) fun unknown _ =>
  if (if unknown = 17 then false else true) = true then .done invariantFailure 0 else
  .bind (call 1 0) fun past _ =>
  if (if past = 22 then false else true) = true then .done invariantFailure 0 else
  .bind time fun s now =>
  if failed s = true then .done s 0 else
  if 0xffffffffffffffff - 20000000 < now then .done 22 0 else
  .bind (call 1 (now + 20000000)) fun tooFar _ =>
  if (if tooFar = 22 then false else true) = true then .done invariantFailure 0 else
  .bind (rearm probeTicks) fun s _ =>
  if failed s = true then .done s 0 else
  .bind awaitNotification fun s notification =>
  if failed s = true then .done s 0 else
  .bind interruptCount fun s after =>
  if failed s = true then .done s 0 else
  if (if after = before + 1 then false else true) = true then .done invariantFailure 0 else
  .bind (rearm probeTicks) fun s nextDeadline =>
  if failed s = true then .done s 0 else
  .bind pending fun s acknowledged =>
  if failed s = true then .done s 0 else
  if (if acknowledged = 0 then false else true) = true then .done invariantFailure 0 else
  .bind (Lemma.Kernel.Console.record 0xc1 before after notification acknowledged) fun s _ =>
  if failed s = true then .done s 0 else
  Lemma.Kernel.Console.record 0xc2 unknown.toUInt64 past.toUInt64 tooFar.toUInt64 nextDeadline

def init : Action := initFor 0x1446 quantum

end Lemma.Kernel.MachineServices
