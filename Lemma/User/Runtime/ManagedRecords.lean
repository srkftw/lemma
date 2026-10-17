import Lemma.User.Runtime.Arena

namespace Lemma.User.Runtime.ManagedRecords
open Lemma.Core0.Memory
open Lemma.User.Runtime

def allocate (shape bytes : UInt64) : Action :=
  if shape = 0 then .done Arena.invalid 0 else
  if bytes < 8 then .done Arena.invalid 0 else if 64 < bytes then .done Arena.invalid 0 else
  if bytes % 8 = 0 then
  .bind Arena.ensure fun s _ => if s = 0 then
  .bind (Arena.newBytes bytes) fun s handle => if s = 0 then
  .bind (Arena.bytesWriteWord handle 0 shape) fun s _ => if s = 0 then .done 0 handle else
  .bind (Arena.release handle) fun _ _ => .done s 0
  else .done s 0 else .done s 0 else .done Arena.invalid 0

def readField (handle shape bytes offset : UInt64) : Action :=
  if bytes < 8 then .done Arena.invalid 0 else if 64 < bytes then .done Arena.invalid 0 else
  if offset < 8 then .done Arena.invalid 0 else
  if offset % 8 = 0 then if offset ≤ bytes - 8 then
  .bind (Arena.bytesLength handle) fun s length => if s = 0 then
  if length = bytes then
  .bind (Arena.bytesReadWord handle 0) fun s actual => if s = 0 then
  if actual = shape then Arena.bytesReadWord handle offset else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done Arena.invalid 0 else .done Arena.invalid 0

def writeField (handle shape bytes offset value : UInt64) : Action :=
  .bind (readField handle shape bytes offset) fun s _ =>
  if s = 0 then Arena.bytesWriteWord handle offset value else .done s 0

end Lemma.User.Runtime.ManagedRecords
