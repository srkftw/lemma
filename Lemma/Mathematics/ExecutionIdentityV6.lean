import Lemma.User.Memory
import Lemma.Mathematics.ExecutionIdentityV5

/-! Version6 closed execution registry: bounded ordinary owned scalar-closure execution
is distinct from retained record, sum and byte origins2/3/4/5/6. IDs name
contracts, never artifact hashes. The selected deployment requires independently audited full implementation preimages. -/
namespace Lemma.Mathematics.ExecutionIdentityV6
open Lemma.Core0.Memory Lemma.User

def extensionMagic : UInt64 := 0x314558454d4d454c
def extensionVersion : UInt64 := 6
def bytes : UInt64 := 2496
def current : UInt64 := 1920
def attempts : UInt64 := 1984
def implementation : UInt64 := 0x0007000100000001
def lowering : UInt64 := 0x0007000000000001
def runtime : UInt64 := 0x0001000500000001
def resources : UInt64 := 0x000500000000001f

def field (buffer offset : UInt64) : Action := Memory.read64 (buffer + offset)
def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer + offset) value

private def zeroStep (i _ : UInt32) (acc buffer base _ _ : UInt64) : Action :=
  .bind (put buffer (base + i.toUInt64 * 8) 0) fun s _ => .done s acc

/-- A migration knows neither the old request nor its execution implementation.
Only the strictly validated original record is extended; no old slot receives
new implementation authority. -/
def createExtension (buffer : UInt64) : Action :=
  .boundedFoldU64 80 zeroStep 80 0 buffer 1856 0 0 fun s _ => if s = 0 then
  .bind (put buffer 1856 extensionMagic) fun s _ => if s = 0 then
  put buffer 1864 extensionVersion else .done s 0 else .done s 0

def clearCurrent (buffer : UInt64) : Action :=
  .boundedFoldU64 8 zeroStep 8 0 buffer current 0 0 fun s _ => .done s 0

private def zeroCheckStep (i _ : UInt32) (acc slot _ _ _ : UInt64) : Action :=
  .bind (field slot (i.toUInt64 * 8)) fun s value => if s = 0 then
  if value = 0 then .done 0 acc else .done 234 0 else .done s 0

private def validateKnown (slot budget : UInt64) : Action :=
  .bind (field slot 0) fun s request => if s = 0 then
  if request = 0 then .done 234 0 else if 0x7ffffffffffffffe < request then .done 234 0 else
  .bind (field slot 8) fun s actual => if s = 0 then if actual = implementation then
  .bind (field slot 16) fun s actual => if s = 0 then if actual = lowering then
  .bind (field slot 24) fun s actual => if s = 0 then if actual = runtime then
  .bind (field slot 32) fun s actual => if s = 0 then if actual = resources then
  .bind (field slot 40) fun s actual => if s = 0 then if actual = budget then
  .bind (field slot 48) fun s status => if s = 0 then if status = 0 then .done 0 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0 else .done s 0

/-- All-zero is explicitly unknown legacy execution identity. A partially
specified identity never inherits authority from the current implementation. -/
def validateSlot (slot budget active : UInt64) : Action :=
  .bind (field slot 56) fun s origin => if s = 0 then
  if origin = 0 then .boundedFoldU64 8 zeroCheckStep 8 0 slot 0 0 0 fun s _ => .done s 0 else
  if active = 0 then .done 234 0 else if origin = 2 then
    Lemma.Mathematics.ExecutionIdentityV2.validateSlot slot budget active else
  if origin = 3 then Lemma.Mathematics.ExecutionIdentityV2.validateSlot slot budget active else
  if origin = 4 then Lemma.Mathematics.ExecutionIdentityV3.validateSlot slot budget active else
  if origin = 5 then Lemma.Mathematics.ExecutionIdentityV4.validateSlot slot budget active else
  if origin = 6 then Lemma.Mathematics.ExecutionIdentityV5.validateSlot slot budget active else
  if origin = 7 then validateKnown slot budget else .done 234 0
  else .done s 0

private def validateReservedStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (field buffer (1872 + i.toUInt64 * 8)) fun s value => if s = 0 then
  if value = 0 then .done 0 acc else .done 234 0 else .done s 0

private def validateAttemptStep (i _ : UInt32) (_ buffer count _ _ : UInt64) : Action :=
  let slot := buffer + attempts + i.toUInt64 * 64
  if count ≤ i.toUInt64 then validateSlot slot 0 0 else
  .bind (field buffer (320 + i.toUInt64 * 72)) fun s budget => if s = 0 then
  validateSlot slot budget 1 else .done s 0

private def sameStep (i _ : UInt32) (acc first second _ _ : UInt64) : Action :=
  .bind (field first (i.toUInt64 * 8)) fun s actual => if s = 0 then
  .bind (field second (i.toUInt64 * 8)) fun s expected => if s = 0 then
  if actual = expected then .done 0 acc else .done 234 0 else .done s 0 else .done s 0

private def validateCurrent (buffer count : UInt64) : Action :=
  .bind (field (buffer + current) 56) fun s origin => if s = 0 then
  if origin = 0 then .done 0 0 else if count = 0 then .done 234 0 else
  let entry := buffer + 256 + (count - 1) * 72
  .bind (field buffer 40) fun s revision => if s = 0 then
  .bind (field entry 0) fun s actual => if s = 0 then if actual = revision then
  .bind (field buffer 48) fun s goal => if s = 0 then
  .bind (field entry 8) fun s actual => if s = 0 then if actual = goal then
  .bind (field buffer 96) fun s outcome => if s = 0 then
  .bind (field entry 56) fun s actual => if s = 0 then if actual = outcome then
  .boundedFoldU64 8 sameStep 8 0 (buffer + current) (buffer + attempts + (count - 1) * 64) 0 0 fun s _ => .done s 0
  else .done 234 0 else .done s 0 else .done s 0 else .done 234 0 else .done s 0
  else .done s 0 else .done 234 0 else .done s 0 else .done s 0 else .done s 0

/-- The caller separately validates original goal/revision/domain/assumptions
and exact semantic results. The extension binds the implementation and resource
contracts without claiming to reconstruct cached machine state or proof terms. -/
def validate (buffer : UInt64) : Action :=
  .bind (field buffer 1856) fun s magic => if s = 0 then if magic = extensionMagic then
  .bind (field buffer 1864) fun s version => if s = 0 then if version = extensionVersion then
  .boundedFoldU64 6 validateReservedStep 6 0 buffer 0 0 0 fun s _ => if s = 0 then
  .bind (field buffer 96) fun s outcome => if s = 0 then
  .bind (field buffer 136) fun s budget => if s = 0 then
  .bind (validateSlot (buffer + current) budget (if outcome = 0 then 0 else 1)) fun s _ => if s = 0 then
  .bind (field buffer 144) fun s count => if s = 0 then
  if count ≤ 8 then
  .boundedFoldU64 8 validateAttemptStep 8 0 buffer count 0 0 fun s _ => if s = 0 then
  validateCurrent buffer count else .done s 0
  else .done 234 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done 234 0 else .done s 0 else .done 234 0 else .done s 0

private def writeKnown (slot request budget : UInt64) : Action :=
  .bind (put slot 0 request) fun s _ => if s = 0 then
  .bind (put slot 8 implementation) fun s _ => if s = 0 then
  .bind (put slot 16 lowering) fun s _ => if s = 0 then
  .bind (put slot 24 runtime) fun s _ => if s = 0 then
  .bind (put slot 32 resources) fun s _ => if s = 0 then
  .bind (put slot 40 budget) fun s _ => if s = 0 then
  .bind (put slot 48 0) fun s _ => if s = 0 then
  put slot 56 7 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

/-- Call only after the complete immutable copied reply has been admitted.
Capacity and identity are checked before writes; error/cancel paths never call
this operation or create a mathematical attempt. -/
def publish (buffer request index budget : UInt64) : Action :=
  if request = 0 then .done 234 0 else if 0x7ffffffffffffffe < request then .done 234 0 else
  if 8 ≤ index then .done 235 0 else if (if budget = 0 then true else budget = 8) = true then
  .bind (writeKnown (buffer + attempts + index * 64) request budget) fun s _ => if s = 0 then
  writeKnown (buffer + current) request budget else .done s 0 else .done 234 0

end Lemma.Mathematics.ExecutionIdentityV6
