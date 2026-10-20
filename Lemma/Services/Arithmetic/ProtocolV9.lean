import Lemma.Services.Arithmetic.ReductionV1
import Lemma.Services.Arithmetic.Protocol
import Lemma.User.IPCABI

/-! Additive copied local-tool protocol. 144-byte request and176-byte reply
fit the unchanged192-byte IPC payload. No proof or tutoring authority. -/
namespace Lemma.Services.Arithmetic.ProtocolV9
open Lemma.Core0.Memory Lemma.User

def magic : UInt64 := 0x31434452
def version : UInt64 := 1
def requestBytes : UInt64 := 144
def replyBytes : UInt64 := 176
def serviceIdentity : UInt64 := 0x0001000052444331

def validContext (source edition object node revision ns page request session policy : UInt64) : Bool :=
  if ns = 0 then false else if 2 < ns then false else
  if page = 0 then false else if 64 < page then false else
  if object = (0x504b000000000000 ||| page) then
  if revision = 0 then false else if 0x7ffffffffffffffe < revision then false else
  if request = 0 then false else if 0x7ffffffffffffffe < request then false else
  if 0x7ffffffffffffffe < session then false else if 0x7ffffffffffffffe < policy then false else
  if (if session = 0 then (if policy = 0 then true else false) else if policy = 0 then false else true) = true then
  if source = 0 then if edition ||| node = 0 then true else false else
  if source = 60000 then false else if source = 60001 then false else if 65535 < source then false else if edition = 0 then false else if 0xffffffff < edition then false else
  if node = 0 then false else if 16 < node then false else true
  else false else false

def request (output source edition object node revision ns page n d request session policy : UInt64) : Action :=
  if validContext source edition object node revision ns page request session policy = true then
  .bind (Memory.write64 (output+0) (magic)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+8) (version)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+16) (1)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+24) (source)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+32) (edition)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+40) (object)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+48) (node)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+56) (revision)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+64) (ns)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+72) (page)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+80) (n)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+88) (d)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+96) (request)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+104) (session)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+112) (policy)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+120) (ReductionV1.requiredBudget)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+128) (0)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+136) (0)) fun s _ => if s = 0 then
  .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 234 0

def evaluate (input : UInt64) : Action :=
  .bind (Memory.read64 (input+0)) fun s tag => if s = 0 then
  .bind (Memory.read64 (input+8)) fun s v => if s = 0 then
  .bind (Memory.read64 (input+16)) fun s op => if s = 0 then
  .bind (Memory.read64 (input+24)) fun s source => if s = 0 then
  .bind (Memory.read64 (input+32)) fun s edition => if s = 0 then
  .bind (Memory.read64 (input+40)) fun s object => if s = 0 then
  .bind (Memory.read64 (input+48)) fun s node => if s = 0 then
  .bind (Memory.read64 (input+56)) fun s revision => if s = 0 then
  .bind (Memory.read64 (input+64)) fun s ns => if s = 0 then
  .bind (Memory.read64 (input+72)) fun s page => if s = 0 then
  .bind (Memory.read64 (input+80)) fun s n => if s = 0 then
  .bind (Memory.read64 (input+88)) fun s d => if s = 0 then
  .bind (Memory.read64 (input+96)) fun s request => if s = 0 then
  .bind (Memory.read64 (input+104)) fun s session => if s = 0 then
  .bind (Memory.read64 (input+112)) fun s policy => if s = 0 then
  .bind (Memory.read64 (input+120)) fun s budget => if s = 0 then
  .bind (Memory.read64 (input+128)) fun s reserved0 => if s = 0 then
  .bind (Memory.read64 (input+136)) fun s reserved1 => if s = 0 then
  if tag = magic then if v = version then if op = 1 then
  if reserved0 ||| reserved1 = 0 then
  if validContext source edition object node revision ns page request session policy = true then
    ReductionV1.calculate n d budget
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def copyStep (i _ : UInt32) (acc source output _ _ : UInt64) : Action :=
  .bind (Memory.read64 (source+i.toUInt64*8)) fun s value => if s = 0 then
  .bind (Memory.write64 (output+i.toUInt64*8) value) fun s _ => .done s acc else .done s 0

def reply (input output packed status : UInt64) : Action :=
  .boundedFoldU64 18 copyStep 18 0 input output 0 0 fun s _ => if s = 0 then
  .bind (Memory.read64 (input+80)) fun s oldN => if s = 0 then
  .bind (Memory.read64 (input+88)) fun s oldD => if s = 0 then
  let n := ((packed >>> 32) &&& 0x7fffffff) ||| (packed &&& Lemma.Mathematics.Exact.sign)
  let d := packed &&& 0xffffffff
  .bind (Memory.write64 (output+144) (if status = 0 then n else 0)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+152) (if status = 0 then d else 0)) fun s _ => if s = 0 then
  .bind (Memory.write64 (output+160) (if status = 0 then if n = oldN then if d = oldD then 2 else 1 else 1 else 0)) fun s _ => if s = 0 then
  Memory.write64 (output+168) serviceIdentity
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
end Lemma.Services.Arithmetic.ProtocolV9
