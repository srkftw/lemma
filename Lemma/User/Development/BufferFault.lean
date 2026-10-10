import Lemma.User.BufferClient
import Lemma.User.Discovery
import Lemma.User.CapabilityConsole

/-! Quarantined third service client. Its bounded probe retains one successful
creation while requesting a second: a free-slot race cannot let this caller
continually create/destroy the last slot without seeing global-quota204.
After the actual denial it releases that buffer, obtains a fresh generation,
and verifies real bytes before a store into its own read-only text. Kernel and
Server policy contain no knowledge of its requests or instruction address. -/
namespace Lemma.User.Development.BufferFault
open Lemma.Core0.Memory
open Lemma.User

def scratch : UInt64 := 0x20600
private def heldAddress : UInt64 := 0x20800
private def phaseAddress : UInt64 := 0x20808
def failed : Action := .done 95 0
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

private def checked (value bytes : UInt64) : Action :=
  if BufferClient.applicationStatus value = 0 then
  if BufferClient.packetBytes value = bytes then .done 0 value else failed else failed

private def discard (id console endpoint epoch handle request : UInt64) : Action :=
  .bind (BufferClient.destroy endpoint epoch handle request) fun s value => if s = 0 then
  .bind (checked value 128) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x345 id handle epoch request) fun s _ => if s = 0 then
  .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else failed
  else failed else failed else failed

private def retryDenied (id console request phase : UInt64) : Action :=
  .bind (CapabilityConsole.record console 0x346 id request 204 phase) fun s _ =>
  if s = 0 then
  .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else failed
  else failed

private def created (id console epoch phase : UInt64) : Action :=
  .bind (BufferClient.responseField 32) fun s handle => if s = 0 then
  if 0 < handle then
  .bind (CapabilityConsole.record console 0x341 id handle 64 epoch) fun s _ => if s = 0 then
    if phase = 0 then
      .bind (Memory.write64 heldAddress handle) fun s _ => if s = 0 then
      .bind (Memory.write64 phaseAddress 1) fun s _ => if s = 0 then .done 0 0 else failed
      else failed
    else if phase = 2 then
      .bind (Memory.read64 heldAddress) fun s held => if s = 0 then
      if (handle &&& 3) = (held &&& 3) then
      if (held >>> 2) < (handle >>> 2) then .done Status.iterationStop handle else failed
      else failed else failed
    else failed
  else failed else failed else failed

private def denied (id console endpoint epoch request phase : UInt64) : Action :=
  if phase = 0 then retryDenied id console request phase else
  if phase = 2 then retryDenied id console request phase else
  if phase = 1 then
  .bind (Memory.read64 heldAddress) fun s handle => if s = 0 then
  if 0 < handle then
  .bind (CapabilityConsole.record console 0x343 id request 204 handle) fun s _ => if s = 0 then
  .bind (discard id console endpoint epoch handle (request + 1)) fun s _ => if s = 0 then
  .bind (Memory.write64 phaseAddress 2) fun s _ => if s = 0 then .done 0 0 else failed
  else failed else failed else failed else failed
  else failed

private def allocateStep (i _ : UInt32) (_acc id console endpoint epoch : UInt64) : Action :=
  let request := i.toUInt64 * 2 + 1
  .bind (Memory.read64 phaseAddress) fun s phase => if s = 0 then
  if phase ≤ 2 then
  .bind (BufferClient.create endpoint epoch 64 request) fun s value =>
  if s = 0 then
    let app := BufferClient.applicationStatus value
    if app = 204 then
      if BufferClient.packetBytes value = 128 then denied id console endpoint epoch request phase else failed
    else if app = 0 then
      if BufferClient.packetBytes value = 128 then
        if phase = 0 then created id console epoch phase
        else if phase = 2 then created id console epoch phase else failed
      else failed
    else failed
  else failed
  else failed else failed

private def verifiedFault (id seed console epoch handle digest : UInt64) : Action :=
  .boundedFoldU64 16 compareStep 16 1469598103934665603 seed id 0 0 fun s actual =>
  if s = 0 then if actual = digest then
  .bind (CapabilityConsole.record console 0x342 id handle actual 16) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x344 id handle epoch seed) fun s _ => if s = 0 then
  .bind (Memory.write64 0x10000 (seed ^^^ id)) fun _ _ => failed
  else failed else failed else failed else failed

private def readBack (id seed console endpoint epoch handle digest : UInt64) : Action :=
  .bind (BufferClient.read endpoint epoch handle 0 16 258) fun s value => if s = 0 then
  .bind (checked value 144) fun s _ => if s = 0 then
    verifiedFault id seed console epoch handle digest else failed else failed

private def finish (id seed console endpoint epoch handle digest : UInt64) : Action :=
  .bind (BufferClient.write endpoint epoch handle 0 16 scratch 257) fun s value => if s = 0 then
  .bind (checked value 128) fun s _ => if s = 0 then
    readBack id seed console endpoint epoch handle digest else failed else failed

private def run (id seed console directory : UInt64) : Action :=
  .bind (Discovery.endpoint directory) fun s endpoint => if s = 0 then
  .bind (Discovery.epoch directory) fun s epoch => if s = 0 then
  .bind (Memory.write64 0x20000 seed) fun s _ => if s = 0 then
  .bind (Memory.write64 heldAddress 0) fun s _ => if s = 0 then
  .bind (Memory.write64 phaseAddress 0) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x340 id epoch endpoint seed) fun s _ => if s = 0 then
  .boundedFoldU64 16 fillStep 16 1469598103934665603 seed id 0 0 fun s digest =>
  if s = 0 then
  .boundedFoldU64 128 allocateStep 128 0 id console endpoint epoch fun s handle =>
  if s = Status.iterationStop then finish id seed console endpoint epoch handle digest else failed
  else failed else failed else failed else failed else failed else failed else failed

def main (seed : UInt64) : Action :=
  .bind (Memory.read64 0x20008) fun s version => if s = 0 then
  if version = ABI.version then
  .bind (Memory.read64 0x20010) fun s bss => if s = 0 then if bss = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s directory => if s = 0 then
  .bind (Capability.check console CapabilityABI.consoleType 2) fun s _ => if s = 0 then
  .bind (Capability.check directory CapabilityABI.directoryType 1024) fun s _ => if s = 0 then
  run id seed console directory
  else failed else failed else failed else failed else failed
  else failed else failed else failed else failed

end Lemma.User.Development.BufferFault
