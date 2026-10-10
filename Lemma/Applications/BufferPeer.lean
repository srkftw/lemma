import Lemma.User.BufferClient
import Lemma.User.Discovery
import Lemma.User.CapabilityConsole

/-! Ordinary independent buffer client. Persistent capacity128/data32 and
temporary capacity64/data16 contain a private full-identity-derived pattern.
Every read is checked before another RPC overwrites the response. Service loss
ends the current operation; reconnect observes a new epoch or expired handle,
without claiming that a mutation whose Reply was lost was rolled back. -/
namespace Lemma.Applications.BufferPeer
open Lemma.Core0.Memory
open Lemma.User

def metadata : UInt64 := 0x20a00
def scratch : UInt64 := 0x20600
def failed : Action := .done 95 0
private def get (offset : UInt64) : Action := Memory.read64 (metadata + offset)
private def put (offset value : UInt64) : Action := Memory.write64 (metadata + offset) value

def pattern (seed id index : UInt64) : UInt64 :=
  (((seed ^^^ id) >>> ((index % 8) * 8)) ^^^ (index * 37)) &&& 255

private def fillStep (i _ : UInt32) (acc seed id _ _ : UInt64) : Action :=
  let byte := pattern seed id i.toUInt64
  .bind (Memory.write8 (scratch + i.toUInt64) byte) fun s _ =>
  if s = 0 then .done 0 ((acc * 1099511628211) ^^^ byte) else failed
private def compareStep (i _ : UInt32) (acc seed id _ _ : UInt64) : Action :=
  .bind (Memory.read8 (BufferClient.responseData + i.toUInt64)) fun s byte =>
  if s = 0 then if byte = pattern seed id i.toUInt64 then
    .done 0 ((acc * 1099511628211) ^^^ byte) else failed else failed
private def compare (count : UInt64) : Action :=
  .bind (get 0) fun s id => if s = 0 then
  .bind (get 8) fun s seed => if s = 0 then
  .boundedFoldU64 32 compareStep count.toUInt32 1469598103934665603 seed id 0 0
    fun s digest => .done s digest
  else failed else failed
private def record (tag a b c : UInt64) : Action :=
  .bind (get 0) fun s id => if s = 0 then
  .bind (get 16) fun s console => if s = 0 then
  CapabilityConsole.record console tag id a b c else failed else failed
private def request : Action :=
  .bind (get 72) fun s value => if s = 0 then
  if 0 < value then if value < 0xffffffffffffffff then
    .bind (put 72 (value + 1)) fun s _ => if s = 0 then .done 0 value else failed
  else failed else failed else failed

-- Only service loss/epoch mismatch is recoverable. Timeout is not retried as
-- an ambiguous mutation; malformed responses and all other errors fail closed.
private def checked (value bytes : UInt64) : Action :=
  let app := BufferClient.applicationStatus value
  if app = 0 then
    if BufferClient.packetBytes value = bytes then .done 0 value else failed
  else if app = 200 then .done 200 0
  else if app = 201 then .done 201 0 else failed
private def nap (ticks : UInt64) : Action :=
  .bind (get 56) fun s round => if s = 0 then
  .bind (Syscall.sleep ticks) fun s deadline => if s = 0 then
  .bind Syscall.time fun s now => if s = 0 then
  if deadline ≤ now then record 0x33b deadline now round else failed
  else failed else failed else failed
private def recover (status : UInt64) : Action :=
  .bind (get 24) fun s directory => if s = 0 then
  .bind (get 40) fun s oldEpoch => if s = 0 then
  .bind (get 48) fun s oldHandle => if s = 0 then
  .bind (Discovery.epoch directory) fun s epoch =>
  if s = 96 then nap 1000000 else if s = 0 then
    if (if oldEpoch < epoch then true else if status = 201 then true else false) = true then
    .bind (record 0x339 status oldEpoch oldHandle) fun s _ => if s = 0 then
    .bind (put 88 oldHandle) fun s _ => if s = 0 then
    .bind (put 96 oldEpoch) fun s _ => if s = 0 then
    .bind (put 32 0) fun s _ => if s = 0 then
    .bind (put 48 0) fun s _ => if s = 0 then
    .bind (put 80 0) fun s _ => if s = 0 then nap 10000 else failed
    else failed else failed else failed else failed else failed
    else failed
  else failed else failed else failed else failed
private def oldTuple (endpoint epoch : UInt64) : Action :=
  .bind (get 88) fun s handle => if s = 0 then
  if handle = 0 then .done 0 0 else
  .bind (get 96) fun s oldEpoch => if s = 0 then
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.status endpoint oldEpoch handle req) fun s value => if s = 0 then
  let app := BufferClient.applicationStatus value
  if app = (if oldEpoch < epoch then 200 else 201) then
    .bind (record 0x33a handle app epoch) fun s _ => if s = 0 then
    .bind (put 88 0) fun s _ => if s = 0 then put 96 0 else failed else failed
  else failed
  else .done s 0 else failed else failed else failed

private def writePersistent (endpoint epoch handle : UInt64) : Action :=
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.write endpoint epoch handle 0 32 scratch req) fun s value => if s = 0 then
  .bind (checked value 128) fun s _ => if s = 0 then
  .bind (get 64) fun s digest => if s = 0 then record 0x333 handle digest 32 else failed
  else .done s 0 else .done s 0 else failed
private def publishPersistent (endpoint epoch handle : UInt64) : Action :=
  if 0 < handle then
  .bind (put 32 endpoint) fun s _ => if s = 0 then
  .bind (put 40 epoch) fun s _ => if s = 0 then
  .bind (put 48 handle) fun s _ => if s = 0 then
  .bind (record 0x332 handle 128 epoch) fun s _ => if s = 0 then
  .bind (oldTuple endpoint epoch) fun s _ => if s = 0 then
    writePersistent endpoint epoch handle else .done s 0
  else failed else failed else failed else failed else failed
private def connectAt (endpoint epoch seed : UInt64) : Action :=
  .bind (record 0x331 epoch endpoint seed) fun s _ => if s = 0 then
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.create endpoint epoch 128 req) fun s value => if s = 0 then
  if BufferClient.applicationStatus value = 204 then
    .bind (record 0x338 req 204 epoch) fun s _ => if s = 0 then nap 1000000 else failed
  else
    .bind (checked value 128) fun s _ => if s = 0 then
    .bind (BufferClient.responseField 32) fun s handle => if s = 0 then
      publishPersistent endpoint epoch handle else failed
    else .done s 0
  else .done s 0 else failed else failed
private def connect : Action :=
  .bind (get 24) fun s directory => if s = 0 then
  .bind (get 8) fun s seed => if s = 0 then
  .bind (Discovery.endpoint directory) fun s endpoint =>
  if s = 96 then nap 1000000 else if s = 0 then
  .bind (Discovery.epoch directory) fun s epoch => if s = 0 then
    connectAt endpoint epoch seed else .done s 0
  else .done s 0 else failed else failed

private def destroyTemporary (endpoint epoch handle round : UInt64) : Action :=
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.destroy endpoint epoch handle req) fun s value => if s = 0 then
  .bind (checked value 128) fun s _ => if s = 0 then
  .bind (put 80 0) fun s _ => if s = 0 then record 0x337 handle epoch round else failed
  else .done s 0 else .done s 0 else failed
private def verifyTemporary (endpoint epoch handle round digest : UInt64) : Action :=
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.read endpoint epoch handle 0 16 req) fun s value => if s = 0 then
  .bind (checked value 144) fun s _ => if s = 0 then
  .bind (compare 16) fun s actual => if s = 0 then
  if actual = digest then destroyTemporary endpoint epoch handle round else failed
  else failed else .done s 0 else .done s 0 else failed
private def holdTemporary (endpoint epoch handle round : UInt64) : Action :=
  .bind (get 8) fun s seed => if s = 0 then
  .bind (get 0) fun s id => if s = 0 then
  .boundedFoldU64 16 fillStep 16 1469598103934665603 seed id 0 0 fun s digest =>
  if s = 0 then
  .bind (record 0x336 handle digest 16) fun s _ => if s = 0 then
  .bind (nap 1000000) fun s _ => if s = 0 then
    verifyTemporary endpoint epoch handle round digest else failed
  else failed else failed else failed else failed
private def writeTemporary (endpoint epoch handle round : UInt64) : Action :=
  .bind (put 80 handle) fun s _ => if s = 0 then
  .bind (record 0x335 handle 64 epoch) fun s _ => if s = 0 then
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.write endpoint epoch handle 0 16 scratch req) fun s value => if s = 0 then
  .bind (checked value 128) fun s _ => if s = 0 then
    holdTemporary endpoint epoch handle round else .done s 0
  else .done s 0 else failed else failed else failed
private def temporary (endpoint epoch round : UInt64) : Action :=
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.create endpoint epoch 64 req) fun s value => if s = 0 then
  if BufferClient.applicationStatus value = 204 then
    .bind (record 0x338 req 204 epoch) fun s _ => if s = 0 then nap 1000000 else failed
  else
    .bind (checked value 128) fun s _ => if s = 0 then
    .bind (BufferClient.responseField 32) fun s handle => if s = 0 then
    if 0 < handle then writeTemporary endpoint epoch handle round else failed
    else failed else .done s 0
  else .done s 0 else failed

private def verifiedRound (endpoint epoch handle round digest : UInt64) : Action :=
  .bind (get 64) fun s expected => if s = 0 then
  if digest = expected then
  .bind (record 0x334 handle digest round) fun s _ => if s = 0 then
  .bind (put 56 (round + 1)) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20018 (round + 1)) fun s _ => if s = 0 then
  .bind (record 0x33c (round + 1) handle epoch) fun s _ => if s = 0 then
    temporary endpoint epoch (round + 1) else failed
  else failed else failed else failed else failed else failed
private def readPersistent (endpoint epoch handle round : UInt64) : Action :=
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.read endpoint epoch handle 0 32 req) fun s value => if s = 0 then
  .bind (checked value 160) fun s _ => if s = 0 then
  .bind (compare 32) fun s digest => if s = 0 then
    verifiedRound endpoint epoch handle round digest else failed
  else .done s 0 else .done s 0 else failed
private def cycle (handle : UInt64) : Action :=
  .bind (get 32) fun s endpoint => if s = 0 then
  .bind (get 40) fun s epoch => if s = 0 then
  .bind (get 56) fun s round => if s = 0 then
  if round < 0xffffffffffffffff then
  .bind request fun s req => if s = 0 then
  .bind (BufferClient.status endpoint epoch handle req) fun s value => if s = 0 then
  .bind (checked value 128) fun s _ => if s = 0 then
    readPersistent endpoint epoch handle round else .done s 0
  else .done s 0 else failed else failed else failed else failed else failed

def step : Action :=
  .bind (get 48) fun s handle => if s = 0 then
  .bind (if handle = 0 then connect else cycle handle) fun s _ =>
  if s = 0 then .done 0 0 else
  if (if s = 80 then true else if s = 83 then true else if s = 96 then true
      else if s = 200 then true else if s = 201 then true else false) = true then
    recover s.toUInt64 else failed
  else failed

def main (seed : UInt64) : Action :=
  .bind (Memory.read64 0x20008) fun s version => if s = 0 then
  if version = ABI.version then
  .bind (Memory.read64 0x20010) fun s bss => if s = 0 then if bss = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s directory => if s = 0 then
  .bind (Capability.check console CapabilityABI.consoleType 2) fun s _ => if s = 0 then
  .bind (Capability.check directory CapabilityABI.directoryType 1024) fun s _ => if s = 0 then
  .bind (put 0 id) fun s _ => if s = 0 then
  .bind (put 8 seed) fun s _ => if s = 0 then
  .bind (put 16 console) fun s _ => if s = 0 then
  .bind (put 24 directory) fun s _ => if s = 0 then
  .bind (put 72 1) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20000 seed) fun s _ => if s = 0 then
  .boundedFoldU64 32 fillStep 32 1469598103934665603 seed id 0 0 fun s digest =>
  if s = 0 then
  .bind (put 64 digest) fun s _ => if s = 0 then .loop step else failed
  else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed

end Lemma.Applications.BufferPeer
