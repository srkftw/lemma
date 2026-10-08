import examples.foundation.TimerConformance
import Lemma.Core0.TimerModel

/-! Direct evaluation of the elaborated timer policy, plus the small finite
deadline/ring model. These are not a model of hardware delivery and do not prove
that the compiler or QEMU implements the source. Target evidence is separate. -/

open Lemma.Examples.Foundation.Timer

#guard timerPolicy timerCause 0x80001000 0x1880 0 0x80 = true
#guard timerPolicy timerCause 0x80001000 0xa00001880 0 0x80 = true
#guard timerPolicy 11 0x80001000 0x1880 0 0x80 = false
#guard timerPolicy 0x800000000000000b 0x80001000 0x1880 0 0x80 = false
#guard timerPolicy timerCause 0x7ffffffc 0x1880 0 0x80 = false
#guard timerPolicy timerCause 0x807f0000 0x1880 0 0x80 = false
#guard timerPolicy timerCause 0x80001002 0x1880 0 0x80 = false
#guard timerPolicy timerCause 0x80001000 0x1888 0 0x80 = false
#guard timerPolicy timerCause 0x80001000 0x1800 0 0x80 = false
#guard timerPolicy timerCause 0x80001000 0x880 0 0x80 = false
#guard timerPolicy timerCause 0x80001000 0x21880 0 0x80 = false
#guard timerPolicy timerCause 0x80001000 0x1880 1 0x80 = false
#guard timerPolicy timerCause 0x80001000 0x1880 0 0 = false
#guard timerPolicy timerCause 0x80001000 0x1880 0 0x88 = false
#guard validPc 0x80000000 = true
#guard validPc 0x807efffc = true
#guard validPc 0x7ffffffc = false
#guard validPc 0x80000001 = false
#guard syncResume 11 0x80001000 0x1880 0 0x80
  0x80001000 0x80001004 0x80002000 0x80002004 = 0x80001004
#guard syncResume 3 0x80002000 0x1880 0x80002000 0x80
  0x80001000 0x80001004 0x80002000 0x80002004 = 0x80002004
#guard syncResume 11 0x80001004 0x1880 0 0x80
  0x80001000 0x80001004 0x80002000 0x80002004 = 0
#guard syncResume 2 0x80001000 0x1880 0 0x80
  0x80001000 0x80001004 0x80002000 0x80002004 = 0
#guard syncResume 11 0x80001000 0x1880 0 0x88
  0x80001000 0x80001004 0x80002000 0x80002004 = 0
#guard syncResume 11 0x80001000 0x21880 0 0x80
  0x80001000 0x80001004 0x80002000 0x80002004 = 0
#guard syncResume 11 0x80001000 0x1888 0 0x80
  0x80001000 0x80001004 0x80002000 0x80002004 = 0
#guard syncResume 11 0x80001000 0x1880 1 0x80
  0x80001000 0x80001004 0x80002000 0x80002004 = 0

open Lemma.Core0.Timer.Model

#guard (catchUp 11 2 3).nextDeadline = 14
#guard (catchUp 11 2 3).skippedPeriods = 3
#guard (catchUp 11 11 3).skippedPeriods = 0

private def emptyRing : Ring := { capacity := 1 }
private def firstEvent : Ring := enqueueHardwareEvent emptyRing 10 4
private def droppedEvent : Ring := enqueueHardwareEvent firstEvent 20 7

#guard firstEvent.hardwareInterrupts = 1 && firstEvent.skippedPeriods = 4 &&
  firstEvent.events.size = 1 && firstEvent.overflowCount = 0 &&
  firstEvent.events[0]!.sequence = 1 && firstEvent.events[0]!.time = 10
#guard droppedEvent.hardwareInterrupts = 2 && droppedEvent.skippedPeriods = 11 &&
  droppedEvent.events.size = 1 && droppedEvent.overflowCount = 1
#guard droppedEvent.events == firstEvent.events

#print axioms valid_nextDeadline_greater
#print axioms valid_nextDeadline_noWrap
#print axioms enqueue_counts_one_hardware_interrupt
#print axioms enqueue_keeps_skipped_separate
#print axioms enqueue_preserves_capacity
#print axioms enqueue_overflow_accounting

#eval IO.println "TIMER_POLICY_PROBES:26 MODEL_PROBES:6 CONDITIONAL_LEMMAS:6"
