import Lemma.Radio.BLE.Packet
import Lemma.Platform.LemmaSim.IO

/-! Kernel-only PIO routines for `lemma-ble-packet/1`. The device base is an
explicit future binding input; no address/device is added to profile0.3/0.4.
Genuine lowering is qualified separately from real machine integration. -/
namespace Lemma.Radio.BLE.Controller
open Lemma.Core0.Memory

def invalid : UInt8 := 197
def busy : UInt8 := 196
def read (base offset : UInt64) : Action := Lemma.Platform.LemmaSim.IO.read64 (base+offset)
def write (base offset value : UInt64) : Action := Lemma.Platform.LemmaSim.IO.write64 (base+offset) value

def «initialize» (base : UInt64) : Action :=
  .bind (read base 0) fun s magic => if s = 0 then
  .bind (read base 8) fun s version => if s = 0 then
  if magic = 0x31544b50454c4d4c then if version = 1 then .done 0 27
    else .done invalid 0 else .done invalid 0 else .done s 0 else .done s 0

def configure (base access initial channel : UInt64) : Action :=
  if initial ≤ 0xffffff then if channel ≤ 36 then
  .bind (Packet.validateAddress access) fun s _ => if s = 0 then
  .bind (read base 16) fun s state => if s = 0 then
  if state &&& (3 : UInt64) = 0 then
  .bind (write base 24 access) fun s _ => if s = 0 then
  .bind (write base 32 initial) fun s _ => if s = 0 then write base 40 channel
    else .done s 0 else .done s 0
  else .done busy 0 else .done s 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0

private def putStep (index _count : UInt32) (base word0 word1 word2 word3 : UInt64) : Action :=
  .bind (write base (256+index.toUInt64*8)
    (Packet.payloadByte index.toUInt64 word0 word1 word2 word3)) fun s _ => .done s base

/-- A finite single owned PIO buffer, without DMA or hidden host framing. This
guest routine admits the same27-byte physical controller ceiling.
Return only submission status, never a durable receipt or a connection claim. -/
def submit (base header length word0 word1 word2 word3 : UInt64) : Action :=
  if Packet.validHeader header length = true then if length ≤ 27 then
  .bind (read base 16) fun s state => if s = 0 then
  if state &&& (11 : UInt64) = 0 then if state &&& (16 : UInt64) = 16 then
  .bind (write base 48 header) fun s _ => if s = 0 then
  .bind (write base 56 length) fun s _ => if s = 0 then
  .boundedFoldU64 27 putStep length.toUInt32 base word0 word1 word2 word3 fun s _ => if s = 0 then
  .bind (write base 64 1) fun s _ => if s = 0 then
  .bind (read base 80) fun s fault => if s = 0 then
  if fault = 0 then .done 0 1 else if fault = 3 then .done busy 0 else .done invalid 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done busy 0 else .done busy 0 else .done s 0 else .done invalid 0 else .done invalid 0

def receivedHeader (base : UInt64) : Action :=
  .bind (read base 16) fun s state => if s = 0 then
  if state &&& (4 : UInt64) = 4 then read base 88 else .done busy 0 else .done s 0

def receivedByte (base index : UInt64) : Action :=
  if index < 27 then
  .bind (receivedHeader base) fun s header => if s = 0 then
  if index < (header >>> 8) then read base (512+index*8) else .done invalid 0 else .done s 0
  else .done invalid 0

def releaseReceived (base : UInt64) : Action := write base 64 2
def cancel (base : UInt64) : Action := write base 64 3
def events (base : UInt64) : Action := read base 72
def acknowledge (base mask : UInt64) : Action :=
  if mask ≤ 15 then write base 72 mask else .done invalid 0

end Lemma.Radio.BLE.Controller
