import Lemma.Core0.Memory

/-! `lemma-ble-packet/1`: bounded, ordinary Lean packet algorithms for the
explicit LE1M recovered-bit interface. This is not a connection, L2CAP service,
GFSK modem, security implementation or complete Bluetooth5.4 controller. -/
namespace Lemma.Radio.BLE.Packet
open Lemma.Core0.Memory

def invalid : UInt8 := 16
def maximumPayload : UInt64 := 27
/-- The unencrypted, no-CTE LL Data header admitted by this slice. -/
def validHeader (value length : UInt64) : Bool :=
  if value ≤ 31 then if length ≤ maximumPayload then
    if value &&& (3 : UInt64) = 1 then true else if value &&& (3 : UInt64) = 2 then
      if length = 0 then false else true
    else false
  else false else false

def crcBit (state bit : UInt64) : UInt64 :=
  let shifted := (state <<< 1) &&& (0xffffff : UInt64)
  if ((state >>> 23) ^^^ bit) &&& (1 : UInt64) = 0 then shifted else shifted ^^^ 0x65b

/-- PDU octets enter least-significant bit first; final24-bit register emits
most-significant bit first. Initialization is the supplied ACL CRCInit. -/
def crcByte (state byte : UInt64) : UInt64 :=
  let r0 := crcBit state (byte &&& (1 : UInt64))
  let r1 := crcBit r0 ((byte >>> 1) &&& (1 : UInt64))
  let r2 := crcBit r1 ((byte >>> 2) &&& (1 : UInt64))
  let r3 := crcBit r2 ((byte >>> 3) &&& (1 : UInt64))
  let r4 := crcBit r3 ((byte >>> 4) &&& (1 : UInt64))
  let r5 := crcBit r4 ((byte >>> 5) &&& (1 : UInt64))
  let r6 := crcBit r5 ((byte >>> 6) &&& (1 : UInt64))
  crcBit r6 ((byte >>> 7) &&& (1 : UInt64))

def whiteningInitial (channel : UInt64) : UInt64 := (channel &&& (63 : UInt64)) ||| 64
def whiteningStep (state : UInt64) : UInt64 :=
  if state &&& (1 : UInt64) = 0 then state >>> 1 else (state >>> 1) ^^^ 0x44

/-- Lower8bits are transformed octet; upper7bits are nextLFSR state. The same
routine whitens and dewhitens. Channel validation belongs to the public caller. -/
def whiteningByte (state byte : UInt64) : UInt64 :=
  let s1 := whiteningStep state
  let s2 := whiteningStep s1
  let s3 := whiteningStep s2
  let s4 := whiteningStep s3
  let s5 := whiteningStep s4
  let s6 := whiteningStep s5
  let s7 := whiteningStep s6
  let mask : UInt64 := state % 2 + (s1 % 2)*2 + (s2 % 2)*4 + (s3 % 2)*8 +
    (s4 % 2)*16 + (s5 % 2)*32 + (s6 % 2)*64 + (s7 % 2)*128
  (whiteningStep s7 <<< 8) ||| ((byte ^^^ mask) &&& (255 : UInt64))

def payloadByte (index word0 word1 word2 word3 : UInt64) : UInt64 :=
  let value := if index < 8 then word0 else if index < 16 then word1 else
    if index < 24 then word2 else word3
  (value >>> ((index % 8) * 8)) &&& (255 : UInt64)

private def crcPayloadStep (index _count : UInt32) (state word0 word1 word2 word3 : UInt64) : Action :=
  .done 0 (crcByte state (payloadByte index.toUInt64 word0 word1 word2 word3))

/-- Explicit27-byte resource ceiling and error precedence. No wrapped length
or invalid header can produce a packet CRC. No host runtime enters lowering. -/
def pduCRC (header length word0 word1 word2 word3 initial : UInt64) : Action :=
  if validHeader header length = true then if initial ≤ 0xffffff then
  .boundedFoldU64 27 crcPayloadStep length.toUInt32
    (crcByte (crcByte initial header) length) word0 word1 word2 word3 fun s value => .done s value
  else .done invalid 0 else .done invalid 0

private def addressStep (index _count : UInt32) (state address _c1 _c2 _c3 : UInt64) : Action :=
  let bit : UInt64 := (address >>> index.toUInt64) &&& (1 : UInt64)
  let difference : UInt64 := bit ^^^ (((0x8e89bed6 : UInt64) >>> index.toUInt64) &&& (1 : UInt64))
  let distance : UInt64 := ((state >>> 9) &&& (63 : UInt64)) + difference
  let transition : UInt64 := if index = 0 then 0 else if state &&& (1 : UInt64) = bit then 0 else 1
  let run : UInt64 := if index = 0 then 1 else if transition = 1 then 1 else ((state >>> 1) &&& (7 : UInt64))+1
  let transitions : UInt64 := ((state >>> 4) &&& (31 : UInt64))+transition
  let most : UInt64 := ((state >>> 15) &&& (7 : UInt64))+(if (27 : UInt32) ≤ index then transition else 0)
  if (6 : UInt64) < run then .done invalid 0 else
  .done 0 (bit ||| (run <<< 1) ||| (transitions <<< 4) ||| (distance <<< 9) ||| (most <<< 15))

private def addressResult (status : UInt8) (state address : UInt64) : Action :=
  if status = 0 then if ((state >>> 9) &&& (63 : UInt64)) < 2 then .done invalid 0 else
    if (24 : UInt64) < ((state >>> 4) &&& (31 : UInt64)) then .done invalid 0 else
      if ((state >>> 15) &&& (7 : UInt64)) < 2 then .done invalid 0 else .done 0 address
  else .done status 0

def equalOctets (address : UInt64) : Bool :=
  if address &&& (255 : UInt64) = (address >>> 8) &&& (255 : UInt64) then
    if address &&& (255 : UInt64) = (address >>> 16) &&& (255 : UInt64) then
      address &&& (255 : UInt64) = (address >>> 24) &&& (255 : UInt64) else false else false

/-- Static uncoded data-address constraints only. Generating random addresses,
connection uniqueness and LE Coded additional constraints are not implemented. -/
def validateAddress (address : UInt64) : Action :=
  if address ≤ 0xffffffff then if equalOctets address = false then
    .boundedFoldU64 32 addressStep 32 0 address 0 0 0 fun s state => addressResult s state address
  else .done invalid 0 else .done invalid 0

end Lemma.Radio.BLE.Packet
