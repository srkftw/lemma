import Lemma.Core0.Timer

/-!
A small finite policy model for the Gate 8 deadline and event-accounting rules.

This is deliberately not a simulator of QEMU, `mtime`, `mtimecmp`, CSRs, or
asynchronous delivery.  Hardware observations come from target execution.  The
model only specifies the source policy applied after one real timer interrupt:
validated non-wrapping phase-reset rearming, separate skipped-period accounting,
and a bounded drop-on-full event buffer with explicit overflow.
-/

namespace Lemma.Core0.Timer.Model

def maximumPeriod : Nat := 1000000
def maximumTime : Nat := 0x7fffffffffffffff

/-- Source precondition checked before deadline arithmetic. -/
def ValidDeadline (now period : Nat) : Prop :=
  0 < period ∧ period ≤ maximumPeriod ∧
    period ≤ maximumTime ∧ now ≤ maximumTime - period

structure CatchUp where
  nextDeadline : Nat
  skippedPeriods : Nat
  deriving BEq, Inhabited, Repr

/-- O(1) phase-reset catch-up after a due hardware event.  The caller establishes
`oldDeadline ≤ now` and `ValidDeadline now period`; skipped periods are metadata,
not fabricated hardware-interrupt observations. -/
def catchUp (now oldDeadline period : Nat) : CatchUp := {
  nextDeadline := now + period
  skippedPeriods := (now - oldDeadline) / period
}

theorem valid_nextDeadline_greater {now oldDeadline period : Nat}
    (h : ValidDeadline now period) :
    now < (catchUp now oldDeadline period).nextDeadline := by
  exact Nat.lt_add_of_pos_right h.1

theorem valid_nextDeadline_noWrap {now oldDeadline period : Nat}
    (h : ValidDeadline now period) :
    (catchUp now oldDeadline period).nextDeadline ≤ maximumTime := by
  exact Nat.add_le_of_le_sub h.2.2.1 h.2.2.2

structure Event where
  sequence : Nat
  time : Nat
  deriving BEq, Inhabited, Repr

structure Ring where
  capacity : Nat
  events : Array Event := #[]
  overflowCount : Nat := 0
  hardwareInterrupts : Nat := 0
  skippedPeriods : Nat := 0
  deriving BEq, Inhabited, Repr

/-- Account exactly one observed hardware interrupt.  If the fixed-capacity
buffer is full the new record is dropped and overflow is incremented; skipped
periods remain a separate counter in both cases. -/
def enqueueHardwareEvent (state : Ring) (time skipped : Nat) : Ring :=
  let updated : Ring := {
    state with
    hardwareInterrupts := state.hardwareInterrupts + 1
    skippedPeriods := state.skippedPeriods + skipped
  }
  if state.events.size < state.capacity then
    { updated with events := state.events.push {
        sequence := state.hardwareInterrupts + 1
        time
      } }
  else
    { updated with overflowCount := state.overflowCount + 1 }

theorem enqueue_counts_one_hardware_interrupt (state : Ring) (time skipped : Nat) :
    (enqueueHardwareEvent state time skipped).hardwareInterrupts =
      state.hardwareInterrupts + 1 := by
  by_cases hSpace : state.events.size < state.capacity
  · simp [enqueueHardwareEvent, hSpace]
  · simp [enqueueHardwareEvent, hSpace]

theorem enqueue_keeps_skipped_separate (state : Ring) (time skipped : Nat) :
    (enqueueHardwareEvent state time skipped).skippedPeriods =
      state.skippedPeriods + skipped := by
  by_cases hSpace : state.events.size < state.capacity
  · simp [enqueueHardwareEvent, hSpace]
  · simp [enqueueHardwareEvent, hSpace]

theorem enqueue_preserves_capacity (state : Ring) (time skipped : Nat)
    (hBounded : state.events.size ≤ state.capacity) :
    (enqueueHardwareEvent state time skipped).events.size ≤ state.capacity := by
  by_cases hSpace : state.events.size < state.capacity
  · simp [enqueueHardwareEvent, hSpace]
    exact hSpace
  · simp [enqueueHardwareEvent, hSpace]
    exact hBounded

theorem enqueue_overflow_accounting (state : Ring) (time skipped : Nat) :
    (enqueueHardwareEvent state time skipped).overflowCount =
      if state.events.size < state.capacity then state.overflowCount
      else state.overflowCount + 1 := by
  by_cases hSpace : state.events.size < state.capacity
  · simp [enqueueHardwareEvent, hSpace]
  · simp [enqueueHardwareEvent, hSpace]

end Lemma.Core0.Timer.Model
