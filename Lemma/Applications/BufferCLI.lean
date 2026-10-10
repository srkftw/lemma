import Lemma.User.BufferClient
import Lemma.User.Discovery
import Lemma.User.CapabilityConsole

/-! Ordinary command client. Input is a byte stream from its Console Read
grant; it interprets the forty-byte command and forwards Buffer methods through
copied IPC. The loop has no command-count limit or restart authority. -/
namespace Lemma.Applications.BufferCLI
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Services.Buffer

def commandAddress : UInt64 := 0x20600
def outputAddress : UInt64 := 0x20700
def stateAddress : UInt64 := 0x20800
def failed : Action := .done 95 0

private def reset : Action :=
  .bind (Memory.write64 (stateAddress + 16) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (stateAddress + 24) 40) fun s _ =>
  if s = 0 then .done 0 0 else failed else failed

private def sendOutput (console bytes : UInt64) : Action :=
  if 64 ≤ bytes then if bytes ≤ 192 then
  .bind (Memory.write64 outputAddress ((0x314f4d4c : UInt64) ||| ((1 : UInt64) <<< 32) ||| (bytes <<< 48))) fun s _ => if s = 0 then
  .bind (Capability.consoleWrite console outputAddress (8 + bytes)) fun s count =>
  if s = 0 then if count = 8 + bytes then reset else failed else failed
  else failed else failed else failed

private def output (console operation epoch handle length count detail app transport : UInt64) : Action :=
  if detail ≤ 0xffffffff then if app ≤ 255 then if transport < 254 then
  .bind (Protocol.header (outputAddress + 8) operation epoch handle length count
    (detail ||| (app <<< 32) ||| (transport <<< 40))) fun s _ =>
  if s = 0 then sendOutput console 64 else failed
  else failed else failed else failed

private def transportError (console operation epoch : UInt64) (status : UInt8) : Action :=
  output console operation epoch 0 0 0 0 0 status.toUInt64

private def serviceOutput (console : UInt64) (status : UInt8) (value : UInt64) : Action :=
  if status = 0 then
  .bind (BufferClient.responseField 16) fun s operation => if s = 0 then
  .bind (BufferClient.responseField 24) fun s epoch => if s = 0 then
  .bind (BufferClient.responseField 32) fun s handle => if s = 0 then
  .bind (BufferClient.responseField 40) fun s length => if s = 0 then
  .bind (BufferClient.responseField 48) fun s count => if s = 0 then
  .bind (BufferClient.responseField 56) fun s detail => if s = 0 then
  let app := BufferClient.applicationStatus value
  .bind (Protocol.header (outputAddress + 8) operation epoch handle length count
    (detail ||| (app <<< 32))) fun s _ => if s = 0 then
  if app = 0 then if operation = 3 then
    .bind (Protocol.copy BufferClient.responseData (outputAddress + 72) count) fun s _ =>
    if s = 0 then sendOutput console (64 + count) else failed
  else sendOutput console 64 else sendOutput console 64
  else failed else failed else failed else failed else failed else failed else failed
  else failed

private def information (console directory operation : UInt64) : Action :=
  if operation = 7 then output console operation 0 0 0 0 1 0 0 else
  if operation = 8 then
    .bind (Discovery.instances directory) fun s value =>
    if s = 0 then output console operation 0 0 0 0 value 0 0 else transportError console operation 0 s
  else if operation = 9 then
    .bind (Discovery.frames directory) fun s value =>
    if s = 0 then output console operation 0 0 0 0 value 0 0 else transportError console operation 0 s
  else if operation = 10 then
    .bind (Discovery.endpoint directory) fun s endpoint => if s = 0 then
    .bind (Discovery.epoch directory) fun s epoch =>
    if s = 0 then output console operation epoch endpoint 0 0 0 0 0 else transportError console operation 0 s
    else transportError console operation 0 s
  else transportError console 7 0 17

private def service (console directory operation requestedEpoch handle offset count : UInt64) : Action :=
  .bind (Discovery.endpoint directory) fun s endpoint => if s = 0 then
  .bind (Discovery.epoch directory) fun s currentEpoch => if s = 0 then
  let epoch := if requestedEpoch = 0 then currentEpoch else requestedEpoch
  .bind (Memory.read64 (stateAddress + 32)) fun s request => if s = 0 then
  if request < 0xffffffffffffffff then
  .bind (Memory.write64 (stateAddress + 32) (request + 1)) fun s _ => if s = 0 then
  .bind (BufferClient.call endpoint epoch operation handle offset
    (if operation = 1 then 0 else count) (if operation = 1 then count else 0)
    (commandAddress + 40) request) fun status value =>
  if status = 0 then serviceOutput console status value
  else transportError console operation epoch status
  else failed else failed else failed
  else transportError console operation 0 s
  else transportError console operation 0 s

private def execute : Action :=
  .bind (Memory.read64 stateAddress) fun s console => if s = 0 then
  .bind (Memory.read64 (stateAddress + 8)) fun s directory => if s = 0 then
  .bind (Memory.read64 commandAddress) fun s operation => if s = 0 then
  .bind (Memory.read64 (commandAddress + 8)) fun s epoch => if s = 0 then
  .bind (Memory.read64 (commandAddress + 16)) fun s handle => if s = 0 then
  .bind (Memory.read64 (commandAddress + 24)) fun s offset => if s = 0 then
  .bind (Memory.read64 (commandAddress + 32)) fun s count => if s = 0 then
  if 1 ≤ operation then if operation ≤ 6 then service console directory operation epoch handle offset count
  else information console directory operation else transportError console 7 0 17
  else failed else failed else failed else failed else failed else failed else failed

private def complete (filled desired : UInt64) : Action :=
  if filled = desired then
    if desired = 40 then
      .bind (Memory.read64 commandAddress) fun s operation => if s = 0 then
      if (if operation = 2 then true else if operation = 4 then true else false) = true then
        .bind (Memory.read64 (commandAddress + 32)) fun s count => if s = 0 then
        if count ≤ 128 then
          if count = 0 then execute else
            .bind (Memory.write64 (stateAddress + 24) (40 + count)) fun s _ =>
            if s = 0 then .done 0 0 else failed
        else
          .bind (Memory.read64 stateAddress) fun s console =>
          if s = 0 then transportError console operation 0 16 else failed
        else failed
      else execute
      else failed
    else execute
  else .done 0 0

private def step : Action :=
  .bind (Memory.read64 stateAddress) fun s console => if s = 0 then
  .bind (Memory.read64 (stateAddress + 16)) fun s filled => if s = 0 then
  .bind (Memory.read64 (stateAddress + 24)) fun s desired => if s = 0 then
  if 40 ≤ desired then if desired ≤ 168 then if filled < desired then
  .bind (Capability.consoleRead console (commandAddress + filled) (desired - filled)) fun status count =>
  if status = ABI.noByte then
    if count = 0 then
      .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else failed
    else failed
  else if status = 0 then
    if 0 < count then if count ≤ desired - filled then
      .bind (Memory.write64 (stateAddress + 16) (filled + count)) fun s _ =>
      if s = 0 then complete (filled + count) desired else failed
    else failed else failed
  else failed
  else failed else failed else failed
  else failed else failed else failed

def main (nonce : UInt64) : Action :=
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s directory => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 stateAddress console) fun s _ => if s = 0 then
  .bind (Memory.write64 (stateAddress + 8) directory) fun s _ => if s = 0 then
  .bind (Memory.write64 (stateAddress + 32) 1) fun s _ => if s = 0 then
  .bind reset fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x310 id nonce console directory) fun s _ =>
  if s = 0 then .loop step else failed
  else failed else failed else failed else failed else failed else failed else failed

end Lemma.Applications.BufferCLI
