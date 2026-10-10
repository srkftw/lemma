import Lemma.User.Memory

/-! Buffer application protocol v1. These scalar declarations and bounded
byte-copy routines are compiled independently into each participating User
image. Kernel-stamped IPC sender identity remains outside this payload. -/
namespace Lemma.Services.Buffer.Protocol
open Lemma.Core0.Memory

def magic : UInt64 := 0x31524642414d454c
def version : UInt64 := 1
def headerBytes : UInt64 := 64
def maximumChunk : UInt64 := 128
def maximumCapacity : UInt64 := 4096
def maximumGeneration : UInt64 := 0x3fffffffffffffff
def leaseTicks : UInt64 := 100000000
def failure : UInt8 := 95
def wrongEpoch : UInt8 := 200
def staleHandle : UInt8 := 201
def wrongOwner : UInt8 := 202
def clientQuota : UInt8 := 203
def globalQuota : UInt8 := 204
def bounds : UInt8 := 205
def malformed : UInt8 := 206
def exhausted : UInt8 := 207
def allocationFailed : UInt8 := 208

/-- Public allocation failures supported by the User page ABI. Keeping the
predicate scalar also keeps byte-status representation out of its decision. -/
def allocationError (status : UInt64) : UInt64 :=
  if status = 16 then 1 else if status = 33 then 1 else if status = 38 then 1
  else if status = 71 then 1 else if status = 72 then 1
  else if status = 73 then 1 else if status = 74 then 1 else 0

def field (packet offset : UInt64) : Action :=
  if offset % 8 = 0 then if offset < headerBytes then
    if packet ≤ 0xffffffffffffffff - offset then
      Lemma.User.Memory.read64 (packet + offset)
    else .done failure 0
  else .done failure 0 else .done failure 0

private def copyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read8 (source + i.toUInt64)) fun s byte =>
  if s = 0 then
    .bind (Lemma.User.Memory.write8 (target + i.toUInt64) byte) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else .done s 0
  else .done s 0

def copy (source target count : UInt64) : Action :=
  if count ≤ maximumChunk then
  if source ≤ 0xffffffffffffffff - count then
  if target ≤ 0xffffffffffffffff - count then
    .boundedFoldU64 128 copyStep count.toUInt32 0 source target 0 0 fun s copied =>
    if s = 0 then if copied = count then .done 0 copied else .done failure 0
    else .done s 0
  else .done failure 0 else .done failure 0 else .done failure 0

def header (packet operation epoch handle offset count argument : UInt64) : Action :=
  .bind (Lemma.User.Memory.write64 packet magic) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 8) version) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 16) operation) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 24) epoch) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 32) handle) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 40) offset) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 48) count) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 56) argument) fun s _ =>
  .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

/-- Shape validation precedes epoch/handle/owner checks in the Server. -/
def requestShape (operation handle offset count argument bytes : UInt64) : UInt64 :=
  if operation = 1 then
    if handle = 0 then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0
  else if operation = 2 then
    if argument = 0 then if count ≤ 128 then if bytes = 64 + count then 1 else 0 else 0 else 0
  else if operation = 3 then
    if argument = 0 then if count ≤ 128 then if bytes = 64 then 1 else 0 else 0 else 0
  else if operation = 4 then
    if offset = 0 then if argument = 0 then if count ≤ 128 then
      if bytes = 64 + count then 1 else 0 else 0 else 0 else 0
  else if operation = 5 then
    if offset = 0 then if count = 0 then if argument = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0
  else if operation = 6 then
    if offset = 0 then if count = 0 then if argument = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0
  else 0

end Lemma.Services.Buffer.Protocol
