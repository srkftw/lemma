import Lemma.Documents.Mathematics

/-! Bounded decimal entry1 for the existing typed submission. This is explicit
user input, never recognition of raw ink. Revisions and execution invalidation
are the ordinary Mathematics operations; histories and learner events retain
their existing format. Caller stages privately before durable publication. -/
namespace Lemma.Documents.MathematicsEntry
open Lemma.Core0.Memory

def set (buffer offset value : UInt64) : Action :=
  if offset < 56 then .done 234 0 else if 88 < offset then .done 234 0 else
  if offset % 8 = 0 then if value < 100 then
  .bind (Mathematics.field buffer offset) fun s previous => if s = 0 then
  if previous = value then .done 0 0 else
  .bind (Mathematics.revise buffer) fun s _ => if s = 0 then
  .bind (Mathematics.put buffer offset value) fun s _ => .done s 1
  else .done s 0 else .done s 0
  else .done 234 0 else .done 234 0

/-- Keys0..9 append decimal digits,10 clears,11 removes the last digit.
Result2 means a valid digit would exceed99: no write or revision occurs.
An invalid field/key/current value rejects before mutation. -/
def press (buffer key : UInt64) : Action :=
  if 11 < key then .done 234 0 else
  .bind (Mathematics.field buffer 160) fun s selected => if s = 0 then
  let offset := if selected = 0 then 56 else selected
  if offset < 56 then .done 234 0 else if 88 < offset then .done 234 0 else
  if offset % 8 = 0 then
  .bind (Mathematics.field buffer offset) fun s value => if s = 0 then
  if value < 100 then
  if key < 10 then
    if 99 < value * 10 + key then .done 0 2 else set buffer offset (value * 10 + key)
  else if key = 10 then set buffer offset 0 else set buffer offset (value / 10)
  else .done 234 0 else .done s 0 else .done 234 0 else .done s 0

end Lemma.Documents.MathematicsEntry
