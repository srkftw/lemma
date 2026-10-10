import Lemma.Kernel.Objects

/-! Quarantined H generation exhaustion fixtures. Only the development boot
policy/control path imports this module. No User syscall exposes either write;
the ordinary object/entry code still performs actual publication and retirement. -/
namespace Lemma.Kernel.Development.CapabilityGeneration
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.User

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 255 0

def seedResult : Action :=
  .bind Objects.table fun s base =>
  if failed s = true then fatal else .done 0 (base + 128)

private def freeStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let index := i.toUInt64
  if index < 3 then .done 0 acc else
  let address := Objects.row base index
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = Objects.free then .done Status.iterationStop index else
  if state = Objects.live then .done 0 acc else
  if state = Objects.retired then .done 0 acc else fatal

/-- Monotonically advances the first genuinely free endpoint generation to its
last legal value. The returned tuple contains observations, not expected logs. -/
def seedOneFree : Action :=
  .bind Objects.table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 freeStep 16 Objects.capacity base 0 0 0 fun s index =>
  if s = Status.iterationStop then
  let address := Objects.row base index
  .bind (Objects.get (address + 8)) fun s before =>
  if failed s = true then fatal else
  if 0 < before then if before < Objects.maxGeneration then
  .bind (Objects.get (address + 24)) fun s refs =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 32)) fun s payload =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 40)) fun s owner =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 48)) fun s pinned =>
  if failed s = true then fatal else
  if refs ||| payload ||| owner ||| pinned = 0 then
  .bind (Objects.put (address + 8) Objects.maxGeneration) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 8)) fun s after =>
  if failed s = true then fatal else
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  .bind (Objects.put (base + 128) index) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + 136) before) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + 144) after) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + 152) state) fun s _ =>
  if failed s = true then fatal else .done 0 index
  else fatal else .done CapabilityABI.invalidArgument 0 else fatal
  else if s = 0 then .done CapabilityABI.objectFull 0 else fatal

/-- Exactly one legal serial publication remains. Never moves a serial backward
and refuses an already exhausted counter. Entry enforces zero command operands. -/
def advance : Action :=
  .bind Objects.nextSerial fun s before =>
  if failed s = true then .done s 0 else
  if before ≤ Objects.maxSerial then
  .bind Objects.table fun s base =>
  if failed s = true then fatal else
  .bind (Objects.put (base + 16) Objects.maxSerial) fun s _ =>
  if failed s = true then fatal else Objects.nextSerial
  else .done CapabilityABI.generationExhausted 0

end Lemma.Kernel.Development.CapabilityGeneration
