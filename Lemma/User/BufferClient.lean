import Lemma.User.IPC
import Lemma.Services.Buffer.Protocol

/-! Reusable typed Buffer calls. A nonzero Action status is the actual IPC
transport failure. Success packs applicationStatus in bits56..63 and the
validated packet byte count below it. Response memory remains valid until
the next call. A failed call is never retried as an exactly-once operation. -/
namespace Lemma.User.BufferClient
open Lemma.Core0.Memory
open Lemma.Services.Buffer

def outgoing : UInt64 := 0x20300
def incoming : UInt64 := 0x20500
def responseAddress : UInt64 := incoming + 64
def responseData : UInt64 := incoming + 128
def applicationStatus (value : UInt64) : UInt64 := value >>> 56
def packetBytes (value : UInt64) : UInt64 := value &&& 0x00ffffffffffffff
def responseField (offset : UInt64) : Action := Protocol.field responseAddress offset

private def validateApplication (operation epoch app bytes : UInt64) : Action :=
  .bind (Protocol.field outgoing 32) fun s requestedHandle => if s = 0 then
  .bind (Protocol.field outgoing 48) fun s requestedCount => if s = 0 then
  .bind (Protocol.field outgoing 56) fun s requestedCapacity => if s = 0 then
  .bind (responseField 0) fun s magic => if s = 0 then
  .bind (responseField 8) fun s version => if s = 0 then
  .bind (responseField 16) fun s observedOperation => if s = 0 then
  .bind (responseField 24) fun s observedEpoch => if s = 0 then
  .bind (responseField 32) fun s handle => if s = 0 then
  .bind (responseField 40) fun s length => if s = 0 then
  .bind (responseField 48) fun s count => if s = 0 then
  .bind (responseField 56) fun s detail => if s = 0 then
  if magic = Protocol.magic then if version = 1 then
  if observedOperation = operation then
  if 0 < observedEpoch then
    if app = 0 then
      if observedEpoch = epoch then
      if count ≤ 128 then
      if (if operation = 3 then 128 + count else 128) = bytes then
      if operation = 6 then
        if handle = 0 then if length = 0 then if count = 0 then if detail = 0 then
          .done 0 bytes else .done IPCABI.invalidPacket 0
        else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
      else if 0 < handle then
        if detail ≤ 4096 then if 0 < detail then if length ≤ detail then
          if operation = 1 then
            if detail = requestedCapacity then
            if length = 0 then if count = 0 then .done 0 bytes else .done IPCABI.invalidPacket 0
            else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
          else if operation = 5 then
            if handle = requestedHandle then
            if count = 0 then .done 0 bytes else .done IPCABI.invalidPacket 0
            else .done IPCABI.invalidPacket 0
          else if handle = requestedHandle then
            if count = requestedCount then .done 0 bytes else .done IPCABI.invalidPacket 0
          else .done IPCABI.invalidPacket 0
        else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
      else .done IPCABI.invalidPacket 0
      else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
    else if 200 ≤ app then if app ≤ 208 then
      -- Shape validation precedes epoch validation in the service. Its
      -- malformed-request reply can therefore also report the current epoch.
      let epochMatches := if app = 200 then (1 : UInt64) else if app = 206 then 1
        else if observedEpoch = epoch then 1 else 0
      if epochMatches = 1 then
      if bytes = 128 then if handle = 0 then if length = 0 then if count = 0 then
        if app = 208 then
          if Protocol.allocationError detail = 1 then
            .done 0 (bytes ||| (app <<< 56)) else .done IPCABI.invalidPacket 0
        else if detail = 0 then .done 0 (bytes ||| (app <<< 56)) else .done IPCABI.invalidPacket 0
      else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
      else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
      else .done IPCABI.invalidPacket 0
    else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

private def validateReply (operation epoch request bytes : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.replyKind then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actualRequest => if s = 0 then
  if actualRequest = request then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  if 0 < sender then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  if reply = 0 then
  .bind (IPC.field incoming IPCABI.statusOffset) fun s app => if s = 0 then
  if 128 ≤ bytes then validateApplication operation epoch app bytes
  else .done IPCABI.invalidPacket 0
  else .done s 0 else .done IPCABI.invalidPacket 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0

private def transport (endpoint epoch operation count request : UInt64) : Action :=
  .bind (IPC.callBegin endpoint outgoing
    (if operation = 2 then 64 + count else if operation = 4 then 64 + count else 64)
    request IPCABI.maximumTicks) fun s transaction =>
  if s = 0 then
    .bind (IPC.callWait transaction incoming IPCABI.maximumPacket) fun s bytes =>
    if s = 0 then validateReply operation epoch request bytes else .done s 0
  else .done s 0

def call (endpoint epoch operation handle offset count argument source request : UInt64) : Action :=
  if count ≤ 128 then if 1 ≤ operation then if operation ≤ 6 then
  .bind (Protocol.header outgoing operation epoch handle offset count argument) fun s _ =>
  if s = 0 then
    if operation = 2 then
      .bind (Protocol.copy source (outgoing + 64) count) fun s _ =>
      if s = 0 then transport endpoint epoch operation count request else .done s 0
    else if operation = 4 then
      .bind (Protocol.copy source (outgoing + 64) count) fun s _ =>
      if s = 0 then transport endpoint epoch operation count request else .done s 0
    else transport endpoint epoch operation count request
  else .done s 0
  else .done IPCABI.invalidArgument 0 else .done IPCABI.invalidArgument 0 else .done IPCABI.invalidArgument 0

def create (endpoint epoch capacity request : UInt64) : Action := call endpoint epoch 1 0 0 0 capacity 0 request
def write (endpoint epoch handle offset count source request : UInt64) : Action := call endpoint epoch 2 handle offset count 0 source request
def read (endpoint epoch handle offset count request : UInt64) : Action := call endpoint epoch 3 handle offset count 0 0 request
def append (endpoint epoch handle count source request : UInt64) : Action := call endpoint epoch 4 handle 0 count 0 source request
def status (endpoint epoch handle request : UInt64) : Action := call endpoint epoch 5 handle 0 0 0 0 request
def destroy (endpoint epoch handle request : UInt64) : Action := call endpoint epoch 6 handle 0 0 0 0 request

end Lemma.User.BufferClient
