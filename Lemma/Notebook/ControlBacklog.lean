import Lemma.User.Memory

/-! Bounded mathematical-control backlog v1. This is private User BSS in the
same owned4KiB page as the notebook's other fixed scratch. The Store reply
packet ends at0x20d00. Eight64-byte entries and32-byte metadata end at0x20f20.
These provisional taps are not durable learner/document events. The notebook
must validate each saved view context before executing it. -/
namespace Lemma.Notebook.ControlBacklog
open Lemma.Core0.Memory

def version : UInt64 := 1
def base : UInt64 := 0x20d00
def capacity : UInt64 := 8
def malformed : UInt8 := 243
def full : UInt8 := 242

private def get (offset : UInt64) : Action := Lemma.User.Memory.read64 (base + offset)
private def put (offset value : UInt64) : Action := Lemma.User.Memory.write64 (base + offset) value

def clear : Action :=
  .bind (put 0 0) fun s _ => if s = 0 then
  .bind (put 8 0) fun s _ => if s = 0 then put 16 0 else .done s 0
  else .done s 0

def reset : Action :=
  .bind clear fun s _ => if s = 0 then put 24 0 else .done s 0

def deferFailure (status : UInt8) : Action :=
  .bind clear fun s _ => if s = 0 then
  .bind (get 24) fun s previous => if s = 0 then
  if previous = 0 then put 24 status.toUInt64 else .done 0 0
  else .done s 0 else .done s 0

def takeFailure : Action :=
  .bind (get 24) fun s status => if s = 0 then
  .bind (put 24 0) fun s _ => if s = 0 then
  if status ≤ 255 then .done 0 status else .done 0 malformed.toUInt64
  else .done s 0 else .done s 0

def count : Action :=
  .bind (get 0) fun s head => if s = 0 then
  .bind (get 8) fun s tail => if s = 0 then
  .bind (get 16) fun s amount => if s = 0 then
  if head < capacity then if tail < capacity then if amount ≤ capacity then
    if (head + amount) % capacity = tail then .done 0 amount else .done malformed 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0

def push (x y ns page identity edition crc node : UInt64) : Action :=
  if x < 4096 then if y < 4096 then
  .bind count fun s amount => if s = 0 then
  if amount = capacity then .done full 0 else
  .bind (get 8) fun s tail => if s = 0 then
  let row := 32 + tail * 64
  .bind (put row x) fun s _ => if s = 0 then
  .bind (put (row + 8) y) fun s _ => if s = 0 then
  .bind (put (row + 16) ns) fun s _ => if s = 0 then
  .bind (put (row + 24) page) fun s _ => if s = 0 then
  .bind (put (row + 32) identity) fun s _ => if s = 0 then
  .bind (put (row + 40) edition) fun s _ => if s = 0 then
  .bind (put (row + 48) crc) fun s _ => if s = 0 then
  .bind (put (row + 56) node) fun s _ => if s = 0 then
  .bind (put 8 ((tail + 1) % capacity)) fun s _ => if s = 0 then
  put 16 (amount + 1)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0

def front : Action :=
  .bind count fun s amount => if s = 0 then
  if amount = 0 then .done 0 0 else
  .bind (get 0) fun s head => if s = 0 then .done 0 (base + 32 + head * 64)
  else .done s 0 else .done s 0

def pop : Action :=
  .bind count fun s amount => if s = 0 then
  if amount = 0 then .done malformed 0 else
  .bind (get 0) fun s head => if s = 0 then
  .bind (put 0 ((head + 1) % capacity)) fun s _ => if s = 0 then
  put 16 (amount - 1) else .done s 0 else .done s 0 else .done s 0

end Lemma.Notebook.ControlBacklog
