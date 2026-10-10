import Lemma.Services.Buffer.Protocol
import Lemma.User.IPC
import Lemma.User.CapabilityConsole

/-! Separately linked volatile Buffer server. Four private metadata rows refer
to real pages obtained through User allocation. Ownership comes only from the
kernel-stamped full IPC sender. Buffer methods are ordinary compiled Lean. -/
namespace Lemma.Services.Buffer.Server
open Lemma.Core0.Memory
open Lemma.User

def incoming : UInt64 := 0x20500
def outgoing : UInt64 := 0x20700
def rows : UInt64 := 0x20800
def rowBytes : UInt64 := 96
def row (slot : UInt64) : UInt64 := rows + slot * rowBytes
def page (slot : UInt64) : UInt64 := 0x40000 + slot * 4096
def failed : Action := .done Protocol.failure 0

private def response (operation epoch handle length count detail : UInt64) : Action :=
  Protocol.header outgoing operation epoch handle length count detail

private def reject (operation epoch : UInt64) (status : UInt8) (detail : UInt64) : Action :=
  .bind (response operation epoch 0 0 0 detail) fun s _ =>
  if s = 0 then .done status 0 else failed

private def initializeStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (rows + i.toUInt64 * 8)
    (if i.toUInt64 % 12 = 1 then 1 else 0)) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else failed

private def clearRow (slot generation : UInt64) : Action :=
  let address := row slot
  .bind (Memory.write64 (address + 16) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 24) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 32) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 40) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 8)
    (if generation = Protocol.maximumGeneration then generation else generation + 1)) fun s _ => if s = 0 then
  .bind (Memory.write64 address (if generation = Protocol.maximumGeneration then 2 else 0)) fun s _ =>
  if s = 0 then .done 0 0 else failed
  else failed else failed else failed else failed else failed

private def release (console id slot generation : UInt64) : Action :=
  let va := page slot
  .bind (Syscall.releasePage va) fun status value =>
  .bind (CapabilityConsole.record console 0x324 id va status.toUInt64 value) fun s _ =>
  if s = 0 then if status = 0 then if value = va then
    clearRow slot generation
  else failed else failed else failed

private def expireStep (i _ : UInt32) (acc console id now _ : UInt64) : Action :=
  let slot := i.toUInt64
  let address := row slot
  .bind (Memory.read64 address) fun s state => if s = 0 then
  if state = 1 then
    .bind (Memory.read64 (address + 40)) fun s deadline => if s = 0 then
    if deadline ≤ now then
      .bind (Memory.read64 (address + 8)) fun s generation => if s = 0 then
      .bind (Memory.read64 (address + 16)) fun s owner => if s = 0 then
      .bind (release console id slot generation) fun s _ => if s = 0 then
      .bind (CapabilityConsole.record console 0x325 id ((generation <<< 2) ||| slot) owner deadline) fun s _ => if s = 0 then
      .bind (CapabilityConsole.record console 0x326 id now slot generation) fun s _ =>
      if s = 0 then .done 0 (acc + 1) else failed
      else failed else failed else failed else failed
    else .done 0 acc
    else failed
  else if state = 0 then .done 0 acc else if state = 2 then .done 0 acc else failed
  else failed

/-- One packed scalar carries first-free slot+1, per-owner count and live count.
The fold only observes metadata; quota rejection has no resource effects. -/
private def inventoryStep (i _ : UInt32) (acc owner _ _ _ : UInt64) : Action :=
  let address := row i.toUInt64
  .bind (Memory.read64 address) fun s state => if s = 0 then
  if state = 1 then
    .bind (Memory.read64 (address + 16)) fun s observedOwner =>
    if s = 0 then .done 0 (acc + 65536 + (if observedOwner = owner then 256 else 0)) else failed
  else if state = 0 then
    if acc &&& 255 = 0 then .done 0 (acc ||| (i.toUInt64 + 1)) else .done 0 acc
  else if state = 2 then .done 0 acc else failed
  else failed

private def publish (slot generation owner capacity deadline : UInt64) : Action :=
  let address := row slot
  .bind (Memory.write64 (address + 16) owner) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 24) capacity) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 32) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (address + 40) deadline) fun s _ => if s = 0 then
  .bind (Memory.write64 address 1) fun s _ =>
  if s = 0 then .done 0 ((generation <<< 2) ||| slot) else failed
  else failed else failed else failed else failed

private def create (console id operation epoch owner capacity deadline : UInt64) : Action :=
  if capacity = 0 then reject operation epoch Protocol.bounds 0 else
  if Protocol.maximumCapacity < capacity then reject operation epoch Protocol.bounds 0 else
  .boundedFoldU64 4 inventoryStep 4 0 owner 0 0 0 fun s inventory =>
  if s = 0 then
  if (2 : UInt64) ≤ ((inventory >>> 8) &&& 255) then reject operation epoch Protocol.clientQuota 0 else
  if (4 : UInt64) ≤ ((inventory >>> 16) &&& 255) then reject operation epoch Protocol.globalQuota 0 else
  if inventory &&& 255 = 0 then reject operation epoch Protocol.exhausted 0 else
  let slot := (inventory &&& 255) - 1
  let address := row slot
  let va := page slot
  .bind (Memory.read64 (address + 8)) fun s generation => if s = 0 then
  if 0 < generation then if generation ≤ Protocol.maximumGeneration then
  .bind (Syscall.allocatePage va) fun status value =>
  .bind (CapabilityConsole.record console 0x322 id va status.toUInt64 value) fun s _ =>
  if s = 0 then
    if status = 0 then if value = va then
      .bind (publish slot generation owner capacity deadline) fun s handle =>
      if s = 0 then response operation epoch handle 0 0 capacity else failed
    else failed
    else if Protocol.allocationError status.toUInt64 = 1 then
      reject operation epoch Protocol.allocationFailed status.toUInt64
    else failed
  else failed
  else failed else failed else failed else failed

private def renew (address deadline : UInt64) : Action :=
  .bind (Memory.write64 (address + 40) deadline) fun s _ =>
  if s = 0 then .done 0 0 else failed

private def write (operation epoch handle slot offset count capacity length deadline : UInt64) : Action :=
  if length < offset then reject operation epoch Protocol.bounds 0 else
  if capacity < offset then reject operation epoch Protocol.bounds 0 else
  if capacity - offset < count then reject operation epoch Protocol.bounds 0 else
  .bind (Protocol.copy (incoming + 128) (page slot + offset) count) fun s _ => if s = 0 then
  let newLength := if length < offset + count then offset + count else length
  .bind (Memory.write64 (row slot + 32) newLength) fun s _ => if s = 0 then
  .bind (renew (row slot) deadline) fun s _ => if s = 0 then
  response operation epoch handle newLength count capacity
  else failed else failed else failed

private def read (operation epoch handle slot offset count capacity length deadline : UInt64) : Action :=
  if length < offset then reject operation epoch Protocol.bounds 0 else
  if length - offset < count then reject operation epoch Protocol.bounds 0 else
  .bind (Protocol.copy (page slot + offset) (outgoing + 64) count) fun s _ => if s = 0 then
  .bind (renew (row slot) deadline) fun s _ => if s = 0 then
  response operation epoch handle length count capacity
  else failed else failed

private def existing (console id operation epoch handle owner offset count deadline : UInt64) : Action :=
  let slot := handle &&& 3
  let generation := handle >>> 2
  let address := row slot
  if generation = 0 then reject operation epoch Protocol.staleHandle 0 else
  .bind (Memory.read64 address) fun s state => if s = 0 then
  if state = 1 then
  .bind (Memory.read64 (address + 8)) fun s actualGeneration => if s = 0 then
  if actualGeneration = generation then
  .bind (Memory.read64 (address + 16)) fun s actualOwner => if s = 0 then
  if actualOwner = owner then
  .bind (Memory.read64 (address + 24)) fun s capacity => if s = 0 then
  .bind (Memory.read64 (address + 32)) fun s length => if s = 0 then
  if length ≤ capacity then if capacity ≤ 4096 then if 0 < capacity then
    if operation = 2 then write operation epoch handle slot offset count capacity length deadline
    else if operation = 3 then read operation epoch handle slot offset count capacity length deadline
    else if operation = 4 then write operation epoch handle slot length count capacity length deadline
    else if operation = 5 then
      .bind (renew address deadline) fun s _ => if s = 0 then
      response operation epoch handle length 0 capacity else failed
    else if operation = 6 then
      .bind (release console id slot generation) fun s _ => if s = 0 then
      response operation epoch 0 0 0 0 else failed
    else reject operation epoch Protocol.malformed 0
  else failed else failed else failed
  else failed else failed
  else reject operation epoch Protocol.wrongOwner 0 else failed
  else reject operation epoch Protocol.staleHandle 0 else failed
  else reject operation epoch Protocol.staleHandle 0 else failed

private def application (console id currentEpoch sender payloadBytes : UInt64) : Action :=
  if payloadBytes < 64 then reject 0 currentEpoch Protocol.malformed 0 else
  .bind (Protocol.field (incoming + 64) 0) fun s magic => if s = 0 then
  .bind (Protocol.field (incoming + 64) 8) fun s version => if s = 0 then
  .bind (Protocol.field (incoming + 64) 16) fun s operation => if s = 0 then
  .bind (Protocol.field (incoming + 64) 24) fun s epoch => if s = 0 then
  .bind (Protocol.field (incoming + 64) 32) fun s handle => if s = 0 then
  .bind (Protocol.field (incoming + 64) 40) fun s offset => if s = 0 then
  .bind (Protocol.field (incoming + 64) 48) fun s count => if s = 0 then
  .bind (Protocol.field (incoming + 64) 56) fun s argument => if s = 0 then
  if magic = Protocol.magic then if version = 1 then
  if Protocol.requestShape operation handle offset count argument payloadBytes = 1 then
    if epoch = currentEpoch then
      .bind Syscall.time fun s now => if s = 0 then
      if now ≤ 0xffffffffffffffff - Protocol.leaseTicks then
        .boundedFoldU64 4 expireStep 4 0 console id now 0 fun s scanned =>
        if s = 0 then
        if scanned ≤ 4 then
        if operation = 1 then create console id operation currentEpoch sender argument (now + Protocol.leaseTicks)
        else existing console id operation currentEpoch handle sender offset count (now + Protocol.leaseTicks)
        else failed else failed
      else reject operation currentEpoch Protocol.bounds 0 else failed
    else reject operation currentEpoch Protocol.wrongEpoch 0
  else reject operation currentEpoch Protocol.malformed 0
  else reject operation currentEpoch Protocol.malformed 0
  else reject operation currentEpoch Protocol.malformed 0
  else failed else failed else failed else failed
  else failed else failed else failed else failed

private def replyObserved (console id request reply : UInt64) (app : UInt8) : Action :=
  .bind (Protocol.field outgoing 16) fun s operation => if s = 0 then
  .bind (Protocol.field outgoing 48) fun s count => if s = 0 then
  let bytes := if app = 0 then if operation = 3 then 64 + count else 64 else 64
  .bind (CapabilityConsole.record console 0x323 id request app.toUInt64 bytes) fun s _ => if s = 0 then
  .bind (IPC.reply reply outgoing bytes app.toUInt64) fun status value =>
  .bind (CapabilityConsole.record console 0x327 id request status.toUInt64 value) fun s _ =>
  if s = 0 then if value = 0 then
    if status = 0 then .done 0 0
    else if status = CapabilityABI.invalidHandle then .done 0 0 else failed
  else failed else failed else failed else failed else failed

private def dispatch (console id epoch bytes : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.callKind then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s request => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  .bind (IPC.field incoming IPCABI.lengthOffset) fun s length => if s = 0 then
  if 0 < sender then if 16 ≤ reply then
  .bind (CapabilityConsole.record console 0x321 id request sender reply) fun s _ => if s = 0 then
  .bind (application console id epoch sender length) fun app _ =>
  if app = 0 then replyObserved console id request reply app else
  if 200 ≤ app then if app ≤ 208 then replyObserved console id request reply app else failed else failed
  else failed else failed else failed
  else failed else failed else failed else failed
  else .done 0 0 else failed

private def step : Action :=
  .bind (Memory.read64 0x20100) fun s console => if s = 0 then
  .bind (Memory.read64 0x20108) fun s id => if s = 0 then
  .bind (Memory.read64 0x20110) fun s endpoint => if s = 0 then
  .bind (Memory.read64 0x20000) fun s epoch => if s = 0 then
  .bind Syscall.time fun s now => if s = 0 then
  .boundedFoldU64 4 expireStep 4 0 console id now 0 fun s _ => if s = 0 then
  .bind (IPC.receive endpoint incoming IPCABI.maximumPacket 1000000) fun s bytes =>
  if s = IPCABI.timeout then .done 0 0 else
  if s = 0 then
    .bind Syscall.time fun s receivedAt => if s = 0 then
    .boundedFoldU64 4 expireStep 4 0 console id receivedAt 0 fun s _ =>
    if s = 0 then dispatch console id epoch bytes else failed
    else failed
  else failed
  else failed else failed else failed else failed else failed else failed

def main (epoch : UInt64) : Action :=
  if 0 < epoch then
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 0x20000 epoch) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20100 console) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20108 id) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20110 endpoint) fun s _ => if s = 0 then
  .boundedFoldU64 48 initializeStep 48 0 0 0 0 0 fun s count =>
  if s = 0 then if count = 48 then
    .bind (CapabilityConsole.record console 0x320 id epoch endpoint console) fun s _ =>
    if s = 0 then .loop step else failed
  else failed else failed
  else failed else failed else failed else failed else failed else failed else failed
  else failed

end Lemma.Services.Buffer.Server
