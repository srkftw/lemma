import Lemma.User.Syscall
import Lemma.User.IPCABI
import Lemma.User.Memory

/-! Reusable User IPC bindings. The send buffer contains only application
payload; receive and call-wait return the authenticated packet byte count.
Request identifiers are application scalars, not authority or sender identity.
-/
namespace Lemma.User.IPC
open Lemma.Core0.Memory

def send (endpoint pointer length request : UInt64) : Action :=
  Syscall.call IPCABI.send endpoint pointer length request 0

def tryReceive (endpoint pointer capacity : UInt64) : Action :=
  Syscall.call IPCABI.receive endpoint pointer capacity 0 IPCABI.nonblocking

def receive (endpoint pointer capacity ticks : UInt64) : Action :=
  Syscall.call IPCABI.receive endpoint pointer capacity ticks IPCABI.blocking

def callBegin (endpoint pointer length request ticks : UInt64) : Action :=
  Syscall.call IPCABI.callBegin endpoint pointer length request ticks

def callWait (transaction pointer capacity : UInt64) : Action :=
  Syscall.call IPCABI.callWait transaction pointer capacity 0 0

def reply (handle pointer length applicationStatus : UInt64) : Action :=
  Syscall.call IPCABI.reply handle pointer length applicationStatus 0

def cancel (transaction : UInt64) : Action :=
  Syscall.call IPCABI.cancel transaction 0 0 0 0

def field (packet offset : UInt64) : Action :=
  if offset % 8 = 0 then
    if offset < IPCABI.headerBytes then
      if 0xffffffffffffffff - offset < packet then .done IPCABI.invalidArgument 0
      else Memory.read64 (packet + offset)
    else .done IPCABI.invalidArgument 0
  else .done IPCABI.invalidArgument 0

/-- Validate a returned packet before application dispatch. This is User-side
framing hygiene; the kernel independently owns authority and copy validation. -/
def validate (packet bytes : UInt64) : Action :=
  if bytes < IPCABI.headerBytes then .done IPCABI.invalidPacket 0 else
  if IPCABI.maximumPacket < bytes then .done IPCABI.invalidPacket 0 else
  .bind (field packet IPCABI.magicOffset) fun s magic =>
  if s = 0 then
  if magic = IPCABI.messageMagic then
  .bind (field packet IPCABI.kindOffset) fun s kind =>
  if s = 0 then
  if (if kind = IPCABI.sendKind then true else if kind = IPCABI.callKind then true
      else if kind = IPCABI.replyKind then true else false) = true then
  .bind (field packet IPCABI.lengthOffset) fun s length =>
  if s = 0 then
  if length ≤ IPCABI.maximumPayload then
  if bytes = IPCABI.headerBytes + length then
  .bind (field packet IPCABI.reservedOffset) fun s reserved =>
  if s = 0 then if reserved = 0 then
  .bind (field packet IPCABI.statusOffset) fun s status =>
  if s = 0 then
    if status ≤ 255 then
      if kind = IPCABI.replyKind then .done 0 kind else
      if status = 0 then .done 0 kind else .done IPCABI.invalidPacket 0
    else .done IPCABI.invalidPacket 0
  else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0

end Lemma.User.IPC
