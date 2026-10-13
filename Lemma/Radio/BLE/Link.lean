import Lemma.Radio.BLE.Packet

/-! `lemma-ble-manual-link/1`: bounded SN/NESN transitions for an explicitly
supplied ACL context. This does not establish or authenticate a connection.
Opaque pending bytes remain immutable in the caller until ACK or cancellation.
The same pure transitions serve hosted Lean peers and checked RV64 callers. -/
namespace Lemma.Radio.BLE.Link
open Lemma.Core0.Memory

def stateMask : UInt64 := 0x30f
def initial : UInt64 := 0
def acknowledged : UInt64 := 0x10000
def newReceive : UInt64 := 0x20000
def duplicate : UInt64 := 0x40000
def backpressure : UInt64 := 0x80000

/-- State bits0/1 are TX SN/expected RX SN, bit2 is outstanding, bit3 frozen;
bits8..9 are attempts. Idle/frozen states have zero attempts. -/
def validState (state : UInt64) : Bool :=
  if state &&& stateMask = state then
    if state &&& (8 : UInt64) = 0 then
      if state &&& (4 : UInt64) = 4 then
        if (state >>> 8) &&& (3 : UInt64) = 0 then false else true
      else (state >>> 8) &&& (3 : UInt64) = 0
    else if state &&& (4 : UInt64) = 0 then (state >>> 8) &&& (3 : UInt64) = 0 else false
  else false

/-- Upper32 bits carry status; lower24 bits carry state plus observation flags.
This is a scalar result, without a second interpreter or foreign runtime. -/
def failure (status state : UInt64) : UInt64 := (status <<< 32) ||| state
def beginResult (state : UInt64) : UInt64 :=
  if validState state = true then
    if state &&& (12 : UInt64) = 0 then state ||| 0x104 else failure 196 state
  else failure 197 0

def headerResult (state llid length : UInt64) : UInt64 :=
  if validState state = true then if state &&& (8 : UInt64) = 0 then
    let header := llid ||| (((state >>> 1) &&& (1 : UInt64)) <<< 2) |||
      ((state &&& (1 : UInt64)) <<< 3)
    if llid = 1 then if Packet.validHeader header length = true then header else failure 197 0
    else if llid = 2 then if Packet.validHeader header length = true then header else failure 197 0
    else failure 197 0
  else failure 199 state else failure 197 0

/-- Call only with an immutable, CRC-validated controller head. NESN differing
from local TX SN acknowledges the pending payload. A duplicate SN never admits
its payload twice. Full receive space retains NESN and requests peer retry.
Acknowledgment is link receipt, never companion durability or authentication. -/
def receiveResult (state header length space : UInt64) : UInt64 :=
  if validState state = true then if Packet.validHeader header length = true then
  if space ≤ 1 then if state &&& (8 : UInt64) = 0 then
    let ack : Bool := if state &&& (4 : UInt64) = 4 then
      if (header >>> 2) &&& (1 : UInt64) = state &&& (1 : UInt64) then false else true else false
    let afterTX := if ack = true then ((state &&& (3 : UInt64)) ^^^ 1) ||| acknowledged else state
    if (header >>> 3) &&& (1 : UInt64) = (state >>> 1) &&& (1 : UInt64) then
      if space = 1 then (afterTX ^^^ 2) ||| newReceive else afterTX ||| backpressure
    else afterTX ||| duplicate
  else failure 199 state else failure 197 0 else failure 197 0 else failure 197 0

/-- At most three transmissions retain exactly the same SN and opaque bytes.
Exhaustion freezes the context: the peer may already have accepted the payload.
New work requires explicit external reconciliation and a fresh context. -/
def retryResult (state : UInt64) : UInt64 :=
  if validState state = true then if state &&& (8 : UInt64) = 0 then
    if state &&& (4 : UInt64) = 4 then
      if ((state >>> 8) &&& (3 : UInt64)) < 3 then state+256
      else failure 198 ((state &&& (3 : UInt64)) ||| 8)
    else failure 196 state
  else failure 199 state else failure 197 0

def cancelResult (state : UInt64) : UInt64 :=
  if validState state = true then failure 200 ((state &&& (3 : UInt64)) ||| 8)
  else failure 197 0

private def result (packed : UInt64) : Action := .done (packed >>> 32).toUInt8 (packed &&& 0xffffff)
def begin (state : UInt64) : Action := result (beginResult state)
def packetHeader (state llid length : UInt64) : Action := result (headerResult state llid length)
def receive (state header length space : UInt64) : Action := result (receiveResult state header length space)
def retry (state : UInt64) : Action := result (retryResult state)
def cancel (state : UInt64) : Action := result (cancelResult state)
end Lemma.Radio.BLE.Link
