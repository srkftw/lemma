import Lemma.User.IPC
import Lemma.User.CapabilityConsole

/-! Two separately linked acceptance clients. The payloads come from independent
launch nonces. Queue, call and blocking cases use ordinary reusable IPC syscalls;
only their finite corpus and observations live in this development module. -/
namespace Lemma.User.Development.IPCClients
open Lemma.Core0.Memory
open Lemma.User

def failed : Action := .done 95 0
def outgoing : UInt64 := 0x20300
def incoming : UInt64 := 0x20500

def payloadByte (nonce index : UInt64) : UInt64 :=
  ((nonce >>> ((index % 8) * 8)) ^^^ (index * 37)) &&& 255

private def fillStep (i _ : UInt32) (acc nonce _ _ _ : UInt64) : Action :=
  .bind (Memory.write8 (outgoing + i.toUInt64) (payloadByte nonce i.toUInt64)) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else failed

private def fill (nonce length : UInt64) : Action :=
  .boundedFoldU64 192 fillStep length.toUInt32 0 nonce 0 0 0 fun s count =>
  if s = 0 then if count = length then .done 0 count else failed else failed

private def compareStep (i _ : UInt32) (acc nonce mask _ _ : UInt64) : Action :=
  .bind (Memory.read8 (incoming + IPCABI.payloadOffset + i.toUInt64)) fun s byte =>
  if s = 0 then
    if byte = (payloadByte nonce i.toUInt64 ^^^ mask) then
      .done 0 ((acc * 1099511628211) ^^^ byte)
    else failed
  else failed

private def expect (console id number : UInt64) (status : UInt8)
    (value : UInt64) (wanted : UInt8) (rule : UInt64) : Action :=
  .bind (CapabilityConsole.record console 0x230 id number status.toUInt64 value) fun s _ =>
  if s = 0 then if status = wanted then
    if rule = 0 then if value = 0 then .done 0 value else failed else
    if rule = 1 then if value = 0 then failed else .done 0 value else .done 0 value
  else failed else failed

private def packet (console id request nonce length kind mask : UInt64) : Action :=
  .bind (IPC.validate incoming (IPCABI.headerBytes + length)) fun s actualKind => if s = 0 then
  if actualKind = kind then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actualRequest => if s = 0 then
  if actualRequest = request then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  if 512 ≤ sender then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  if reply = 0 then
  .boundedFoldU64 192 compareStep length.toUInt32 1469598103934665603 nonce mask 0 0 fun s digest =>
  if s = 0 then
  .bind (CapabilityConsole.record console 0x231 id request sender (IPCABI.headerBytes + length)) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x232 id request length digest) fun s _ =>
  if s = 0 then .done 0 sender else failed else failed
  else failed
  else failed else failed else failed else failed else failed else failed else failed else failed

private def echo (console id endpoint nonce request length number : UInt64) : Action :=
  .bind (fill nonce length) fun s _ => if s = 0 then
  .bind (IPC.callBegin endpoint outgoing length request 10000000) fun status transaction =>
  .bind (expect console id number status transaction 0 1) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction incoming IPCABI.maximumPacket) fun status bytes =>
  .bind (expect console id (number + 1) status bytes 0 1) fun s _ => if s = 0 then
  if bytes = IPCABI.headerBytes + length then
    packet console id request nonce length IPCABI.replyKind 0xa5
  else failed else failed else failed else failed

private def snapshot (console id manager endpoint marker : UInt64) : Action :=
  .bind (Capability.inspect manager 0 1) fun s objects => if s = 0 then
  .bind (Capability.inspect manager 0 2) fun s frames => if s = 0 then
  .bind (Capability.inspect manager endpoint 0) fun s refs => if s = 0 then
  .bind (Capability.targetEntryCount manager) fun s entries => if s = 0 then
  .bind (CapabilityConsole.record console 0x233 id marker objects frames) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x234 id marker refs entries) fun s _ =>
  if s = 0 then .done 0 0 else failed else failed else failed else failed else failed else failed

private def invalidCases (console id primary probe manager : UInt64) : Action :=
  .bind (snapshot console id manager probe 1) fun s _ => if s = 0 then
  .bind (IPC.send 0 0 0 0) fun status value =>
  .bind (expect console id 1 status value 80 0) fun s _ => if s = 0 then
  .bind (IPC.send console 0 0 0) fun status value =>
  .bind (expect console id 2 status value 81 0) fun s _ => if s = 0 then
  .bind (IPC.tryReceive primary incoming 256) fun status value =>
  .bind (expect console id 3 status value 72 0) fun s _ => if s = 0 then
  .bind (IPC.send probe outgoing 193 0) fun status value =>
  .bind (expect console id 4 status value 16 0) fun s _ => if s = 0 then
  .bind (IPC.send probe 0 1 0) fun status value =>
  .bind (expect console id 5 status value 71 0) fun s _ => if s = 0 then
  .bind (IPC.tryReceive probe incoming 256) fun status value =>
  .bind (expect console id 6 status value 12 0) fun s _ => if s = 0 then
  snapshot console id manager probe 2
  else failed else failed else failed else failed else failed else failed else failed

private def enqueue (console id endpoint pointer length request number : UInt64) : Action :=
  .bind (IPC.send endpoint pointer length request) fun status value =>
  expect console id number status value 0 0

private def receiveProbe (console id endpoint nonce length request number capacity : UInt64) : Action :=
  .bind (IPC.tryReceive endpoint incoming capacity) fun status bytes =>
  .bind (expect console id number status bytes 0 1) fun s _ => if s = 0 then
  if bytes = IPCABI.headerBytes + length then
  .bind (packet console id request nonce length IPCABI.sendKind 0) fun s sender =>
  if s = 0 then if sender = id then .done 0 0 else failed else failed
  else failed else failed

private def drainProbe (console id probe nonce request : UInt64) : Action :=
  .bind (IPC.tryReceive probe 0 256) fun status value =>
  .bind (expect console id 17 status value 71 0) fun s _ => if s = 0 then
  .bind (receiveProbe console id probe nonce 0 (request + 16) 18 256) fun s _ => if s = 0 then
  .bind (IPC.tryReceive probe incoming 64) fun status value =>
  .bind (expect console id 19 status value 98 0) fun s _ => if s = 0 then
  .bind (receiveProbe console id probe nonce 192 (request + 17) 20 256) fun s _ => if s = 0 then
  .bind (receiveProbe console id probe nonce 24 (request + 18) 21 256) fun s _ => if s = 0 then
  .bind (receiveProbe console id probe (nonce ^^^ 0x5a5a5a5a) 24 (request + 19) 22 256) fun s _ => if s = 0 then
  .bind (IPC.tryReceive probe incoming 256) fun status value =>
  expect console id 23 status value 12 0
  else failed else failed else failed else failed else failed else failed

private def queueCases (console id probe manager nonce request : UInt64) : Action :=
  .bind (enqueue console id probe 0 0 (request + 16) 10) fun s _ => if s = 0 then
  .bind (fill nonce 192) fun s _ => if s = 0 then
  .bind (enqueue console id probe outgoing 192 (request + 17) 11) fun s _ => if s = 0 then
  .bind (enqueue console id probe outgoing 24 (request + 18) 12) fun s _ => if s = 0 then
  .bind (fill (nonce ^^^ 0x5a5a5a5a) 24) fun s _ => if s = 0 then
  .bind (enqueue console id probe outgoing 24 (request + 19) 13) fun s _ => if s = 0 then
  .bind (snapshot console id manager probe 3) fun s _ => if s = 0 then
  .bind (IPC.send probe 0 0 0) fun status value =>
  .bind (expect console id 14 status value 92 0) fun s _ => if s = 0 then
  .bind (IPC.callBegin probe 0 0 0 1000000) fun status value =>
  .bind (expect console id 15 status value 92 0) fun s _ => if s = 0 then
  .bind (snapshot console id manager probe 4) fun s _ => if s = 0 then
  drainProbe console id probe nonce request
  else failed else failed else failed else failed else failed else failed else failed else failed else failed else failed

private def queuedCancel (console id probe : UInt64) : Action :=
  .bind (IPC.callBegin probe 0 0 48 1000000) fun status transaction =>
  .bind (expect console id 30 status transaction 0 1) fun s _ => if s = 0 then
  .bind (IPC.callBegin probe 0 0 49 1000000) fun status value =>
  .bind (expect console id 31 status value 99 0) fun s _ => if s = 0 then
  .bind (IPC.cancel transaction) fun status value =>
  .bind (expect console id 32 status value 0 0) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction incoming 256) fun status value =>
  .bind (expect console id 33 status value 94 0) fun s _ => if s = 0 then
  .bind (IPC.cancel transaction) fun status value =>
  .bind (expect console id 34 status value 97 0) fun s _ => if s = 0 then
  .bind (IPC.tryReceive probe incoming 256) fun status value =>
  expect console id 35 status value 12 0
  else failed else failed else failed else failed else failed

private def queuedTimeout (console id probe : UInt64) : Action :=
  .bind (IPC.callBegin probe 0 0 50 20000) fun status transaction =>
  .bind (expect console id 36 status transaction 0 1) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction incoming 256) fun status value =>
  .bind (expect console id 37 status value 93 0) fun s _ => if s = 0 then
  .bind (IPC.tryReceive probe incoming 256) fun status value =>
  expect console id 38 status value 12 0
  else failed else failed

private def deliveredCases (console id primary nonce request : UInt64) : Action :=
  .bind (echo console id primary nonce (request + 1) 192 40) fun s _ => if s = 0 then
  .bind (echo console id primary nonce (request + 2) 24 42) fun s _ => if s = 0 then
  .bind (echo console id primary nonce (request + 3) 8 44) fun s _ => if s = 0 then
  .bind (IPC.callBegin primary 0 0 (request + 4) 2000000) fun status transaction =>
  .bind (expect console id 46 status transaction 0 1) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction incoming 256) fun status value =>
  .bind (expect console id 47 status value 93 0) fun s _ => if s = 0 then
  .bind (echo console id primary nonce (request + 257) 24 48) fun s _ => if s = 0 then
  .bind (IPC.callBegin primary 0 0 (request + 260) 5000000) fun status transaction =>
  .bind (expect console id 50 status transaction 0 1) fun s _ => if s = 0 then
  .bind (Syscall.sleep 1000000) fun s _ => if s = 0 then
  .bind (IPC.cancel transaction) fun status value =>
  .bind (expect console id 51 status value 0 0) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction incoming 256) fun status value =>
  .bind (expect console id 52 status value 94 0) fun s _ => if s = 0 then
  echo console id primary nonce (request + 513) 24 53
  else failed else failed else failed else failed else failed else failed else failed else failed else failed else failed

private def readyRetry (console id primary nonce request : UInt64) : Action :=
  .bind (fill nonce 24) fun s _ => if s = 0 then
  .bind (IPC.callBegin primary outgoing 24 (request + 769) 5000000) fun status transaction =>
  .bind (expect console id 55 status transaction 0 1) fun s _ => if s = 0 then
  .bind (Syscall.sleep 1000000) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction 0 256) fun status value =>
  .bind (expect console id 56 status value 71 0) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction incoming 64) fun status value =>
  .bind (expect console id 57 status value 98 0) fun s _ => if s = 0 then
  .bind (IPC.cancel transaction) fun status value =>
  .bind (expect console id 58 status value 100 0) fun s _ => if s = 0 then
  .bind (IPC.callWait transaction incoming 256) fun status bytes =>
  .bind (expect console id 59 status bytes 0 1) fun s _ => if s = 0 then
  if bytes = 88 then packet console id (request + 769) nonce 24 IPCABI.replyKind 0xa5 else failed
  else failed else failed else failed else failed else failed else failed else failed

private def idleStep : Action := Syscall.sleep 100000

private def revokeStep : Action :=
  .bind (Memory.read64 0x20100) fun s console => if s = 0 then
  .bind (Memory.read64 0x20108) fun s id => if s = 0 then
  .bind (Memory.read64 0x20118) fun s probe => if s = 0 then
  .bind (Memory.read64 0x20120) fun s manager => if s = 0 then
  .bind (Capability.inspect manager probe 5) fun s waiting => if s = 0 then
  if waiting = 1 then
    .bind (Capability.revoke probe) fun status value =>
    .bind (expect console id 70 status value 0 0) fun s _ => if s = 0 then
    .bind (Memory.read64 0x20000) fun s nonce => if s = 0 then
    .bind (CapabilityConsole.record console 0x2af id nonce 0 0) fun s _ =>
    if s = 0 then .loop idleStep else failed else failed else failed
  else if waiting = 0 then Syscall.sleep 1000 else failed
  else failed else failed else failed else failed else failed

private def transferProbe (console id probe manager inbox : UInt64) : Action :=
  .bind (Capability.scopedTarget manager) fun s peer => if s = 0 then
  .bind (Capability.transfer manager probe peer CapabilityABI.endpointReceive) fun status handle =>
  .bind (expect console id 60 status handle 0 1) fun s _ => if s = 0 then
  .bind (Memory.write64 outgoing handle) fun s _ => if s = 0 then
  .bind (IPC.send inbox outgoing 8 2) fun status value =>
  .bind (expect console id 61 status value 0 0) fun s _ =>
  if s = 0 then .loop revokeStep else failed else failed else failed else failed

private def «initialize» (nonce : UInt64) : Action :=
  .bind (Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s primary => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 0x20100 console) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20108 id) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20110 primary) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x240 id nonce console primary) fun s _ =>
  if s = 0 then .done 0 id else failed else failed else failed else failed else failed else failed else failed else failed

def clientA (nonce : UInt64) : Action :=
  .bind («initialize» nonce) fun s id => if s = 0 then
  .bind (Memory.read64 0x20100) fun s console => if s = 0 then
  .bind (Memory.read64 0x20110) fun s primary => if s = 0 then
  .bind (Capability.bootGrant 2) fun s probe => if s = 0 then
  .bind (Capability.bootGrant 3) fun s manager => if s = 0 then
  .bind (Capability.bootGrant 4) fun s inbox => if s = 0 then
  .bind (Memory.write64 0x20118 probe) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20120 manager) fun s _ => if s = 0 then
  .bind (invalidCases console id primary probe manager) fun s _ => if s = 0 then
  .bind (queueCases console id probe manager nonce (nonce * 256)) fun s _ => if s = 0 then
  .bind (queuedCancel console id probe) fun s _ => if s = 0 then
  .bind (queuedTimeout console id probe) fun s _ => if s = 0 then
  .bind (Memory.write64 outgoing nonce) fun s _ => if s = 0 then
  .bind (IPC.send inbox outgoing 8 1) fun status value =>
  .bind (expect console id 39 status value 0 0) fun s _ => if s = 0 then
  .bind (deliveredCases console id primary nonce (nonce * 256)) fun s _ => if s = 0 then
  .bind (readyRetry console id primary nonce (nonce * 256)) fun s _ => if s = 0 then
  transferProbe console id probe manager inbox
  else failed else failed else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed else failed else failed else failed

private def receiveInbox (console id inbox request number : UInt64) : Action :=
  .bind (IPC.receive inbox incoming 256 10000000) fun status bytes =>
  .bind (expect console id number status bytes 0 1) fun s _ => if s = 0 then
  if bytes = 72 then
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.sendKind then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actual => if s = 0 then
  if actual = request then
  .bind (Memory.read64 (incoming + IPCABI.payloadOffset)) fun s value =>
  if s = 0 then .done 0 value else failed else failed else failed else failed else failed else failed else failed

private def peerRevoke (console id inbox : UInt64) : Action :=
  .bind (receiveInbox console id inbox 2 80) fun s handle => if s = 0 then
  .bind (Capability.check handle CapabilityABI.endpointType CapabilityABI.endpointReceive) fun status value =>
  .bind (expect console id 81 status value 0 0) fun s _ => if s = 0 then
  .bind (IPC.send handle 0 0 0) fun status value =>
  .bind (expect console id 82 status value 72 0) fun s _ => if s = 0 then
  .bind (IPC.receive handle incoming 256 10000000) fun status value =>
  .bind (expect console id 83 status value 83 0) fun s _ => if s = 0 then
  .bind (Memory.read64 0x20000) fun s nonce => if s = 0 then
  .bind (CapabilityConsole.record console 0x2bf id nonce 0 0) fun s _ =>
  if s = 0 then .loop idleStep else failed else failed else failed else failed else failed else failed

def clientB (nonce : UInt64) : Action :=
  .bind («initialize» nonce) fun s id => if s = 0 then
  .bind (Memory.read64 0x20100) fun s console => if s = 0 then
  .bind (Memory.read64 0x20110) fun s primary => if s = 0 then
  .bind (Capability.bootGrant 2) fun s inbox => if s = 0 then
  .bind (receiveInbox console id inbox 1 1) fun s peerNonce => if s = 0 then
  if peerNonce = 0 then failed else
  .bind (echo console id primary nonce (nonce * 256 + 1) 192 2) fun s _ => if s = 0 then
  .bind (echo console id primary nonce (nonce * 256 + 2) 24 4) fun s _ => if s = 0 then
  .bind (echo console id primary nonce (nonce * 256 + 3) 0 6) fun s _ => if s = 0 then
  peerRevoke console id inbox
  else failed else failed else failed else failed else failed else failed else failed else failed

end Lemma.User.Development.IPCClients
