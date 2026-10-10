import Lemma.User.CapabilityConsole

/-! Actual managed U syscall corpus. Every record serializes the real reply,
not the desired answer. A wrong reply aborts; source/object snapshots surround
failed publications. The final perpetual phase waits for a quarantined trusted
serial advance, then observes the last real grant and closed exhaustion. -/
namespace Lemma.User.Development.Capabilities
open Lemma.Core0.Memory
open Lemma.User

def failed : Action := .done 95 0
def state : UInt64 := 0x20100
def handles : UInt64 := 0x20500
def note (console id number : UInt64) (actual : UInt8) (value : UInt64) : Action :=
  .bind (CapabilityConsole.record console 0x110 id number actual.toUInt64 value) fun s _ =>
  if s = 0 then .done 0 value else failed
def observed (console id number : UInt64) (expected actual : UInt8) (value : UInt64) : Action :=
  .bind (note console id number actual value) fun s _ =>
  if s = 0 then if actual = expected then .done 0 value else failed else failed

private def waitStep (_ _ : UInt32) (acc manager wanted _ _ : UInt64) : Action :=
  .bind (Capability.targetEntryCount manager) fun s count =>
  if s = 0 then if count = wanted then .done Status.iterationStop count else
    .bind (Syscall.sleep 100000) fun s _ => if s = 0 then .done 0 acc else failed
  else failed
def waitPeer (manager wanted : UInt64) : Action :=
  .boundedFoldU64 1024 waitStep 1024 0 manager wanted 0 0 fun s count =>
  if s = Status.iterationStop then .done 0 count else failed

private def snapshotStep (i _ : UInt32) (acc manager subject address _ : UInt64) : Action :=
  .bind (Capability.inspect manager (if i = 0 then subject else 0) i.toUInt64) fun s value =>
  if s = 0 then
    .bind (Memory.write64 (address + i.toUInt64 * 8) value) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else failed
  else failed
def snapshot (console id manager subject address phase : UInt64) : Action :=
  .boundedFoldU64 3 snapshotStep 3 0 manager subject address 0 fun s count =>
  if s = 0 then if count = 3 then
  .bind (Memory.read64 address) fun s refs => if s = 0 then
  .bind (Memory.read64 (address + 8)) fun s objects => if s = 0 then
  .bind (Memory.read64 (address + 16)) fun s frames => if s = 0 then
  .bind (CapabilityConsole.record console 0x140 id phase refs (objects <<< 32 ||| frames)) fun s _ =>
  if s = 0 then .done 0 refs else failed else failed else failed else failed
  else failed else failed
private def compareStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.read64 (0x20800 + i.toUInt64 * 8)) fun s before => if s = 0 then
  .bind (Memory.read64 (0x20840 + i.toUInt64 * 8)) fun s after => if s = 0 then
  if before = after then .done 0 (acc + 1) else failed else failed else failed
def equalSnapshots : Action :=
  .boundedFoldU64 3 compareStep 3 0 0 0 0 0 fun s count =>
  if s = 0 then if count = 3 then .done 0 count else failed else failed

private def fillStep (i _ : UInt32) (acc console id _ _ : UInt64) : Action :=
  .bind (Capability.duplicate console CapabilityABI.consoleWrite) fun status handle =>
  .bind (note console id (100 + i.toUInt64) status handle) fun s _ => if s = 0 then
  if status = 0 then
    .bind (Memory.write64 (handles + i.toUInt64 * 8) handle) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else failed
  else if status = CapabilityABI.tableFull then .done Status.iterationStop acc else failed
  else failed
private def closeStep (i _ : UInt32) (acc console id address _ : UInt64) : Action :=
  .bind (Memory.read64 (address + i.toUInt64 * 8)) fun s handle => if s = 0 then
  .bind (Capability.close handle) fun status value =>
  .bind (observed console id (150 + i.toUInt64) 0 status value) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else failed else failed

def basic (console id manager endpoint : UInt64) : Action :=
  .bind (Capability.check 0 CapabilityABI.consoleType 2) fun s v =>
  .bind (observed console id 1 80 s v) fun s _ => if s = 0 then
  .bind (Capability.info 0xffffffffffffffff) fun s v =>
  .bind (observed console id 2 80 s v) fun s _ => if s = 0 then
  .bind (Capability.check console CapabilityABI.endpointType 4) fun s v =>
  .bind (observed console id 3 81 s v) fun s _ => if s = 0 then
  .bind (Capability.consoleRead console 0 0) fun s v =>
  .bind (observed console id 4 72 s v) fun s _ => if s = 0 then
  .bind (Capability.consoleWrite console 0 0) fun s v =>
  .bind (observed console id 5 0 s v) fun s _ => if s = 0 then
  .bind (Syscall.consoleWrite 0 0) fun s v =>
  .bind (observed console id 6 72 s v) fun s _ => if s = 0 then
  .bind (Capability.duplicate console 1) fun s v =>
  .bind (observed console id 7 72 s v) fun s _ => if s = 0 then
  .bind (Capability.duplicate console 2048) fun s v =>
  .bind (observed console id 8 16 s v) fun s _ => if s = 0 then
  .bind (Syscall.call CapabilityABI.info console 0 0 1 0) fun s v =>
  .bind (observed console id 9 16 s v) fun s _ => if s = 0 then
  .bind (Capability.duplicate console 2) fun status first =>
  .bind (observed console id 10 0 status first) fun s _ => if s = 0 then
  .bind (Capability.info first) fun s v =>
  .bind (observed console id 11 0 s v) fun s _ => if s = 0 then
  .bind (Capability.duplicate first 34) fun s v =>
  .bind (observed console id 12 72 s v) fun s _ => if s = 0 then
  .bind (Capability.close first) fun s v =>
  .bind (observed console id 13 0 s v) fun s _ => if s = 0 then
  .bind (Capability.check first 1 2) fun s v =>
  .bind (observed console id 14 80 s v) fun s _ => if s = 0 then
  .bind (Capability.duplicate console 2) fun status second =>
  .bind (observed console id 15 0 status second) fun s _ => if s = 0 then
  if second = first then failed else
  .bind (Capability.check first 1 2) fun s v =>
  .bind (observed console id 16 80 s v) fun s _ => if s = 0 then
  .bind (Capability.close second) fun s v =>
  .bind (observed console id 17 0 s v) fun s _ => if s = 0 then
  .bind (Capability.duplicate manager 512) fun status weakManager =>
  .bind (observed console id 18 0 status weakManager) fun s _ => if s = 0 then
  .bind (Capability.createEndpoint weakManager) fun s v =>
  .bind (observed console id 19 72 s v) fun s _ => if s = 0 then
  .bind (Capability.close weakManager) fun s v =>
  .bind (observed console id 20 0 s v) fun s _ => if s = 0 then
  .bind (Capability.duplicate endpoint 124) fun status full =>
  .bind (observed console id 21 0 status full) fun s _ => if s = 0 then
  .bind (Capability.duplicate endpoint 36) fun status weak =>
  .bind (observed console id 22 0 status weak) fun s _ => if s = 0 then
  .bind (Capability.close endpoint) fun s v =>
  .bind (observed console id 23 0 s v) fun s _ => if s = 0 then
  .bind (Capability.check weak 2 4) fun s v =>
  .bind (observed console id 24 0 s v) fun s _ => if s = 0 then
  .bind (Capability.check weak 2 8) fun s v =>
  .bind (observed console id 25 72 s v) fun s _ => if s = 0 then
  .bind (Capability.revoke weak) fun s v =>
  .bind (observed console id 26 72 s v) fun s _ => if s = 0 then
  .bind (Capability.close weak) fun s v =>
  .bind (observed console id 27 0 s v) fun s _ => if s = 0 then
  .bind (Capability.transfer manager full id 36) fun s v =>
  .bind (observed console id 28 72 s v) fun s _ => if s = 0 then
  .bind (Memory.write64 (state + 24) full) fun s _ =>
  if s = 0 then .done 0 full else failed
  else failed else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed else failed else failed

def tableRollback (console id manager : UInt64) : Action :=
  .boundedFoldU64 16 fillStep 16 0 console id 0 0 fun s count =>
  if s = Status.iterationStop then if count = 13 then
  .bind (snapshot console id manager console 0x20800 1) fun s _ => if s = 0 then
  .bind (Capability.duplicate console 2) fun s v =>
  .bind (observed console id 120 89 s v) fun s _ => if s = 0 then
  .bind (Capability.createEndpoint manager) fun s v =>
  .bind (observed console id 121 89 s v) fun s _ => if s = 0 then
  .bind (snapshot console id manager console 0x20840 2) fun s _ => if s = 0 then
  .bind equalSnapshots fun s _ => if s = 0 then
  .boundedFoldU64 16 closeStep count.toUInt32 0 console id handles 0 fun s closed =>
  if s = 0 then if closed = count then .done 0 closed else failed else failed
  else failed else failed else failed else failed else failed
  else failed else failed

private def endpointStep (i _ : UInt32) (acc console id manager _ : UInt64) : Action :=
  .bind (Capability.createEndpoint manager) fun status handle =>
  .bind (observed console id (200 + i.toUInt64) 0 status handle) fun s _ => if s = 0 then
  .bind (Memory.write64 (0x20700 + i.toUInt64 * 8) handle) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else failed else failed
def objectRollback (console id manager subject : UInt64) : Action :=
  .boundedFoldU64 3 endpointStep 3 0 console id manager 0 fun s count =>
  if s = 0 then if count = 3 then
  .bind (snapshot console id manager subject 0x20800 3) fun s _ => if s = 0 then
  .bind (Capability.createEndpoint manager) fun s v =>
  .bind (observed console id 203 90 s v) fun s _ => if s = 0 then
  .bind (snapshot console id manager subject 0x20840 4) fun s _ => if s = 0 then
  .bind equalSnapshots fun s _ => if s = 0 then
  .boundedFoldU64 3 closeStep 3 0 console id 0x20700 0 fun s closed =>
  if s = 0 then if closed = 3 then .done 0 closed else failed else failed
  else failed else failed else failed else failed else failed else failed

def transferRevoke (console id manager subject : UInt64) : Action :=
  .bind (Capability.scopedTarget manager) fun s peer => if s = 0 then
  .bind (snapshot console id manager subject 0x20800 5) fun s _ => if s = 0 then
  .bind (Capability.transfer manager subject peer 36) fun s v =>
  .bind (observed console id 210 89 s v) fun s _ => if s = 0 then
  .bind (snapshot console id manager subject 0x20840 6) fun s _ => if s = 0 then
  .bind equalSnapshots fun s _ => if s = 0 then
  .bind (Capability.revoke subject) fun s v =>
  .bind (observed console id 211 0 s v) fun s _ => if s = 0 then
  .bind (Capability.check subject 2 4) fun s v =>
  .bind (observed console id 212 80 s v) fun s _ => if s = 0 then
  .bind (Capability.inspect manager 0 3) fun status retired =>
  .bind (observed console id 213 0 status retired) fun s _ => if s = 0 then
  if retired = 1 then
  .bind (waitPeer manager 15) fun s _ => if s = 0 then
  .bind (Capability.createEndpoint manager) fun status fresh =>
  .bind (observed console id 214 0 status fresh) fun s _ => if s = 0 then
  .bind (Capability.transfer manager fresh peer 36) fun status targetHandle =>
  .bind (observed console id 215 0 status targetHandle) fun s _ => if s = 0 then
  .bind (Capability.check targetHandle 2 4) fun s v =>
  .bind (observed console id 216 80 s v) fun s _ => if s = 0 then
  .bind (Capability.inspect manager fresh 0) fun status refs =>
  .bind (observed console id 217 0 status refs) fun s _ => if s = 0 then
  if refs = 2 then
  .bind (waitPeer manager 15) fun s _ => if s = 0 then
  .bind (Capability.revoke fresh) fun s v =>
  .bind (observed console id 218 0 s v) fun s _ => if s = 0 then .done 0 fresh else failed
  else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed else failed else failed
  else failed else failed else failed

/-! Leave one actual owned endpoint, with a surviving peer alias, for the
kernel's ordinary owner-death cleanup. The final generation phase exits without
explicitly closing or revoking this endpoint. -/
def ownerDeathEndpoint (console id manager : UInt64) : Action :=
  .bind (Capability.scopedTarget manager) fun s peer => if s = 0 then
  .bind (waitPeer manager 14) fun s _ => if s = 0 then
  .bind (Capability.createEndpoint manager) fun status fresh =>
  .bind (observed console id 219 0 status fresh) fun s _ => if s = 0 then
  .bind (Capability.transfer manager fresh peer 36) fun status targetHandle =>
  .bind (observed console id 220 0 status targetHandle) fun s _ => if s = 0 then
  .bind (waitPeer manager 15) fun s _ => if s = 0 then
  .bind (Capability.inspect manager fresh 0) fun status refs =>
  .bind (observed console id 221 0 status refs) fun s _ => if s = 0 then
  if refs = 2 then .done 0 fresh else failed
  else failed else failed else failed else failed else failed else failed

private def generationStep : Action :=
  .bind (Memory.read64 state) fun s console => if s = 0 then
  .bind (Memory.read64 (state + 8)) fun s id => if s = 0 then
  .bind (Capability.duplicate console 2) fun status handle =>
  if status = 0 then
    .bind (Memory.write64 (state + 40) handle) fun s _ => if s = 0 then
    .bind (Capability.close handle) fun s _ => if s = 0 then
    if handle >>> 4 = 0x0fffffffffffffff then
      .bind (Memory.read64 (state + 16)) fun s manager => if s = 0 then
      .bind (snapshot console id manager console 0x20800 7) fun s _ => if s = 0 then
      .bind (CapabilityConsole.record console 0x1fd id handle (handle >>> 4) 0) fun s _ =>
      if s = 0 then Syscall.yield else failed else failed else failed
    else Syscall.yield
    else failed else failed
  else if status = CapabilityABI.generationExhausted then
    .bind (Memory.read64 (state + 40)) fun s last => if s = 0 then
    .bind (Memory.read64 0x20000) fun s nonce => if s = 0 then
    .bind (Memory.read64 (state + 16)) fun s manager => if s = 0 then
    .bind (snapshot console id manager console 0x20840 8) fun s _ => if s = 0 then
    .bind equalSnapshots fun s _ => if s = 0 then
    .bind (CapabilityConsole.record console 0x1ff id nonce status.toUInt64 last) fun s _ =>
    if s = 0 then Syscall.exit 0 else failed else failed else failed else failed else failed else failed
  else failed
  else failed else failed

def main (nonce : UInt64) : Action :=
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s manager => if s = 0 then
  .bind (Capability.bootGrant 2) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Memory.write64 state console) fun s _ => if s = 0 then
  .bind (Memory.write64 (state + 8) id) fun s _ => if s = 0 then
  .bind (Memory.write64 (state + 16) manager) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x100 id nonce console manager) fun s _ => if s = 0 then
  .bind (basic console id manager endpoint) fun s full => if s = 0 then
  .bind (waitPeer manager 16) fun s _ => if s = 0 then
  .bind (tableRollback console id manager) fun s _ => if s = 0 then
  .bind (objectRollback console id manager full) fun s _ => if s = 0 then
  .bind (transferRevoke console id manager full) fun s _ => if s = 0 then
  .bind (ownerDeathEndpoint console id manager) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x1fe id nonce 0 0) fun s _ => if s = 0 then
  .loop generationStep
  else failed else failed else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed else failed else failed else failed

end Lemma.User.Development.Capabilities
