import Lemma.User.CapabilityConsole

/-! Separately executing peer. Its local table fills through genuine duplicate
syscalls, then object-wide revocation frees one slot for a scoped transfer.
Polling waits use real sleep; no cross-task User pointer is shared. -/
namespace Lemma.User.Development.CapabilitiesPeer
open Lemma.Core0.Memory
open Lemma.User

def failed : Action := .done 95 0
def note (console id number : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (CapabilityConsole.record console 0x120 id number status.toUInt64 value) fun s _ =>
  if s = 0 then .done 0 value else failed

private def fillStep (i _ : UInt32) (acc console id _ _ : UInt64) : Action :=
  .bind (Capability.duplicate console CapabilityABI.consoleWrite) fun s handle =>
  .bind (note console id (i.toUInt64 + 1) s handle) fun _ _ =>
  if s = 0 then .done 0 (acc + 1) else failed

private def firstRevoked (console id : UInt64) : Action :=
  .bind (Memory.read64 0x20118) fun s handle => if s = 0 then
  .bind (Capability.check handle CapabilityABI.endpointType CapabilityABI.endpointSend) fun status value =>
  if status = CapabilityABI.invalidHandle then
    .bind (note console id 30 status value) fun s _ => if s = 0 then
    .bind (Memory.write64 0x20120 1) fun s _ =>
    if s = 0 then .done 0 0 else failed else failed
  else if status = 0 then Syscall.sleep 100000 else failed
  else failed

private def retainOwnerEndpoint (console id : UInt64) : Action :=
  .bind (Capability.bootGrant 1) fun status handle =>
  if status = CapabilityABI.invalidHandle then Syscall.sleep 100000 else
  if status = 0 then
    .bind (Memory.read64 0x20118) fun s prior => if s = 0 then
    if handle = prior then failed else
    .bind (Capability.check handle CapabilityABI.endpointType CapabilityABI.endpointSend) fun s value =>
    if s = 0 then if value = 0 then
    .bind (Memory.write64 0x20128 handle) fun s _ => if s = 0 then
    .bind (Memory.write64 0x20120 2) fun s _ => if s = 0 then
    .bind (CapabilityConsole.record console 0x125 id handle 15 0) fun s _ =>
    if s = 0 then .done 0 handle else failed else failed else failed
    else failed else failed else failed
  else failed

private def ownerDetached (console id : UInt64) : Action :=
  .bind (Memory.read64 0x20128) fun s handle => if s = 0 then
  .bind (Capability.check handle CapabilityABI.endpointType CapabilityABI.endpointSend) fun status value =>
  if status = CapabilityABI.invalidHandle then
    .bind (note console id 31 status value) fun s _ => if s = 0 then
    .bind (Memory.read64 0x20000) fun s nonce => if s = 0 then
    .bind (CapabilityConsole.record console 0x12f id nonce 0 0) fun s _ => if s = 0 then
    Syscall.exit 0 else failed else failed else failed
  else if status = 0 then Syscall.sleep 100000 else failed
  else failed

/-- The first transfer is explicitly revoked. The second remains live until
its owning Tester exits; only a checked invalid-handle reply ends the Peer.
These phases reuse one existing loop, so no additional loop nesting is added. -/
private def finishStep : Action :=
  .bind (Memory.read64 0x20100) fun s console => if s = 0 then
  .bind (Memory.read64 0x20108) fun s id => if s = 0 then
  .bind (Memory.read64 0x20120) fun s phase => if s = 0 then
  if phase = 0 then firstRevoked console id else
  if phase = 1 then retainOwnerEndpoint console id else
  if phase = 2 then ownerDetached console id else failed
  else failed else failed else failed

private def replacementStep : Action :=
  .bind (Memory.read64 0x20100) fun s console => if s = 0 then
  .bind (Memory.read64 0x20108) fun s id => if s = 0 then
  .bind (Capability.bootGrant 1) fun status handle =>
  if status = CapabilityABI.invalidHandle then Syscall.sleep 100000 else
  if status = 0 then
    .bind (Capability.check handle CapabilityABI.endpointType CapabilityABI.endpointSend) fun status value =>
    .bind (note console id 20 status value) fun s _ => if s = 0 then
    if status = 0 then
    .bind (Capability.check handle CapabilityABI.endpointType CapabilityABI.endpointReceive) fun status value =>
    .bind (note console id 21 status value) fun s _ => if s = 0 then
    if status = CapabilityABI.denied then
    .bind (Capability.revoke handle) fun status value =>
    .bind (note console id 22 status value) fun s _ => if s = 0 then
    if status = CapabilityABI.denied then
    .bind (Capability.bootGrant 15) fun s last => if s = 0 then
    .bind (Capability.close last) fun status value =>
    .bind (note console id 23 status value) fun s _ => if s = 0 then
    if status = 0 then
    .bind (Memory.write64 0x20118 handle) fun s _ => if s = 0 then
    .bind (CapabilityConsole.record console 0x124 id handle 15 0) fun s _ => if s = 0 then
    .loop finishStep else failed else failed else failed else failed else failed
    else failed else failed else failed else failed else failed else failed
  else failed
  else failed else failed

private def revokeStep : Action :=
  .bind (Memory.read64 0x20110) fun s old => if s = 0 then
  .bind (Capability.check old CapabilityABI.endpointType CapabilityABI.endpointSend) fun status _ =>
  if status = CapabilityABI.invalidHandle then .loop replacementStep else
  if status = 0 then Syscall.sleep 100000 else failed
  else failed

def main (nonce : UInt64) : Action :=
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20100 console) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20108 id) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20110 endpoint) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20120 0) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20128 0) fun s _ => if s = 0 then
  .boundedFoldU64 14 fillStep 14 0 console id 0 0 fun s count =>
  if s = 0 then if count = 14 then
    .bind (CapabilityConsole.record console 0x122 id nonce endpoint count) fun s _ => if s = 0 then
    .loop revokeStep else failed
  else failed else failed
  else failed else failed else failed else failed else failed else failed else failed
  else failed else failed

end Lemma.User.Development.CapabilitiesPeer
