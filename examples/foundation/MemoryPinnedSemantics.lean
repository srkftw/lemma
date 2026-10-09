import Lemma.Core0.MemoryModel
import examples.foundation.MemoryConformance

/-!
Direct host-Lean probes for the finite checked-memory semantics and the genuine
source Actions.  This file intentionally does not import the custom frontend or
LLVM lowering.
-/

namespace Lemma.Examples.Foundation.Memory

open Lemma.Core0.Memory
open Lemma.Core0.Memory.Model

private def evaluateOrFail (label : String) (state : State) (action : Action) :
    IO Evaluation :=
  match evaluateDefault state action with
  | .ok result => pure result
  | .error diagnostic =>
      throw <| IO.userError s!"PINNED_MEMORY:{label}:model-error:{repr diagnostic}"

private def emitChecked (label : String) (result : Evaluation)
    (expectedStatus : Nat) (expectedValue : Nat) (expectedEvents : Nat) : IO Unit := do
  let status := result.outcome.status.toNat
  let value := result.outcome.value.toNat
  let events := result.state.events.size
  unless status == expectedStatus && value == expectedValue && events == expectedEvents do
    throw <| IO.userError
      s!"PINNED_MEMORY:{label}:expected:{expectedStatus}:{expectedValue}:{expectedEvents}:got:{status}:{value}:{events}"
  IO.println s!"PINNED_MEMORY:{label}:{status}:{value}:{events}"

def memoryPinnedSemanticsProbe : IO Unit := do
  let initial := State.zeroed

  let roundTrip ← evaluateOrFail "roundtrip32" initial
    (roundTrip32 RegionId.scratch 4 0x78563412)
  emitChecked "roundtrip32" roundTrip Status.ok.toNat 0x78563412 2

  let lastValid ← evaluateOrFail "last-valid64" initial
    (load64Value RegionId.input 0xff8)
  emitChecked "last-valid64" lastValid Status.ok.toNat 0 1

  let onePast ← evaluateOrFail "one-past" initial
    (load8Value RegionId.scratch 0x1000)
  emitChecked "one-past" onePast Status.outOfBounds.toNat 0 0

  let misaligned ← evaluateOrFail "misaligned32" initial
    (load32Value RegionId.scratch 1)
  emitChecked "misaligned32" misaligned Status.misaligned.toNat 0 0

  let orderedDenial ← evaluateOrFail "oob-before-alignment" initial
    (store64Status RegionId.scratch 0xff9 1)
  emitChecked "oob-before-alignment" orderedDenial Status.outOfBounds.toNat 0 0

  let readOnly ← evaluateOrFail "read-only-write" initial
    (store8Status RegionId.input 0 0xaa)
  emitChecked "read-only-write" readOnly Status.writeDenied.toNat 0 0

  let reserved ← evaluateOrFail "reserved-image" initial
    (load8Value RegionId.image 0)
  emitChecked "reserved-image" reserved Status.reservedRegion.toNat 0 0

  let device ← evaluateOrFail "device-uart" initial
    (load8Value RegionId.uart 0)
  emitChecked "device-uart" device Status.deviceRegion.toNat 0 0

  let unknown ← evaluateOrFail "unknown-region" initial
    (load8Value 0xff 0)
  emitChecked "unknown-region" unknown Status.unknownRegion.toNat 0 0

  let maximum ← evaluateOrFail "maximum-offset" initial
    (load8Value RegionId.output 0xffffffffffffffff)
  emitChecked "maximum-offset" maximum Status.outOfBounds.toNat 0 0

  let wrongWidth ← evaluateOrFail "event-byte-width" initial
    (store8Status RegionId.events 0 0x55)
  emitChecked "event-byte-width" wrongWidth Status.widthDenied.toNat 0 0

  let preflight ← evaluateOrFail "range-preflight" initial
    (bufferFill RegionId.output 0xffa 8 0x11)
  emitChecked "range-preflight" preflight Status.outOfBounds.toNat 0 0

  let emptyRange ← evaluateOrFail "empty-range-at-end" initial
    (byteChecksum RegionId.scratch 0x1000 0)
  emitChecked "empty-range-at-end" emptyRange Status.ok.toNat 0 0

  let exhausted ← evaluateOrFail "fold-budget" initial (foldWrite 17 0 1)
  emitChecked "fold-budget" exhausted Status.budgetExceeded.toNat 0 0

  let filled ← evaluateOrFail "fill-four" initial (bufferFill RegionId.scratch 16 4 0x2a)
  emitChecked "fill-four" filled Status.ok.toNat 168 4
  let checksum ← evaluateOrFail "checksum-four" filled.state
    (byteChecksum RegionId.scratch 16 4)
  emitChecked "checksum-four" checksum Status.ok.toNat 168 8

  let seeded ← evaluateOrFail "copy-seed" initial (foldWrite 4 32 10)
  emitChecked "copy-seed" seeded Status.ok.toNat 46 4
  let copied ← evaluateOrFail "overlap-copy" seeded.state
    (overlapCopy RegionId.scratch 32 RegionId.scratch 34 4)
  emitChecked "overlap-copy" copied Status.ok.toNat 46 12

#eval memoryPinnedSemanticsProbe

end Lemma.Examples.Foundation.Memory
