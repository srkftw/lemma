import Lemma.Services.Store.Format

/-! Bounded service-owned latest-object index. It is rebuilt once at mount.
No input sample performs a history scan. An object is a replacement record;
ink assigns independent stable objects to original strokes and edit summaries. -/
namespace Lemma.Services.Store.Index
open Lemma.Core0.Memory

def row (base slot : UInt64) : UInt64 := base + slot * Format.indexRowBytes
def keySlot (ns object : UInt64) : UInt64 :=
  ((ns * 0x9e3779b185ebca87) ^^^ (object * 0xc2b2ae3d27d4eb4f)) % 1024

private def clearStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write64 (base + i.toUInt64 * 8) 0) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else .done s 0

def clear (base : UInt64) : Action :=
  if base % 8 = 0 then if base ≤ 0xffffffffffffffff - Format.indexBytes then
  .boundedFoldU64 6144 clearStep 6144 0 base 0 0 0 fun s count =>
  if s = 0 then if count = 6144 then .done 0 0 else .done Format.malformed 0 else .done s 0
  else .done Format.malformed 0 else .done Format.malformed 0

private def findStep (i _ : UInt32) (_ base ns object start : UInt64) : Action :=
  let slot := (start + i.toUInt64) % 1024
  let address := row base slot
  .bind (Lemma.User.Memory.read64 address) fun s observedNs => if s = 0 then
  if observedNs = 0 then .done 10 (slot + 1) else
  .bind (Lemma.User.Memory.read64 (address + 8)) fun s obj =>
  if s = 0 then
    if observedNs = ns then if obj = object then .done 10 (slot + 1) else .done 0 0
    else .done 0 0
  else .done s 0 else .done s 0

/-- Success identifies either the matching row or an empty insertion row.
The caller verifies the namespace/object before reading its value. -/
def find (base ns object : UInt64) : Action :=
  if 0 < ns then if 0 < object then
  .boundedFoldU64 1024 findStep 1024 0 base ns object (keySlot ns object) fun s found =>
  if s = 10 then if 0 < found then .done 0 (found - 1) else .done Format.malformed 0
  else if s = 0 then .done Format.indexFull 0 else .done s 0
  else .done Format.malformed 0 else .done Format.malformed 0

def publish (base slot ns object sector sectors sequence kind : UInt64) : Action :=
  if slot < 1024 then if 0 < ns then if 0 < object then
  if 2 ≤ sectors then if sectors ≤ 66 then if 0 < sequence then
  if Format.kindValid kind = 1 then
  let address := row base slot
  .bind (Lemma.User.Memory.write64 (address + 8) object) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (address + 16) sector) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (address + 24) sectors) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (address + 32) sequence) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (address + 40) kind) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 address ns) fun s _ => .done s slot
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done Format.malformed 0 else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0 else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0

end Lemma.Services.Store.Index
