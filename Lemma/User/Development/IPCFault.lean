import Lemma.User.IPC
import Lemma.User.CapabilityConsole

/-! Late fault/death acceptance actor. Mode4 faults its own readonly text with
an outstanding Call after a real sleep. Mode5 requests the server's quarantined
fault operation and observes ordinary peer-death completion through CallWait.
The host must independently observe actual acceptance before claiming that
specific death order; elapsed sleep alone is not evidence. -/
namespace Lemma.User.Development.IPCFault
open Lemma.Core0.Memory
open Lemma.User

def failed : Action := .done 95 0

def main (nonce : UInt64) : Action :=
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (IPC.callBegin endpoint 0 0 nonce 5000000) fun status transaction =>
  .bind (CapabilityConsole.record console 0x250 id nonce status.toUInt64 transaction) fun s _ => if s = 0 then
  if status = 0 then if transaction = 0 then failed else
  if nonce % 256 = 4 then
    .bind (Syscall.sleep 1000000) fun s _ => if s = 0 then
    .bind (Memory.write64 0x10000 nonce) fun _ _ => failed else failed
  else if nonce % 256 = 5 then
    .bind (IPC.callWait transaction 0x20500 256) fun status value =>
    .bind (CapabilityConsole.record console 0x251 id nonce status.toUInt64 value) fun s _ =>
    if s = 0 then if status = IPCABI.peerDied then if value = 0 then Syscall.exit 0 else failed else failed else failed
  else failed
  else failed
  else failed else failed else failed else failed else failed

end Lemma.User.Development.IPCFault
