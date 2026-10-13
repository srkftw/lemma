import Protocol

/-! Hosted Lean USB FS packet generation/checking at the selected decoded-byte
boundary. No target image imports this hosted ByteArray representation. -/
namespace LemmaSim.USB
open LemmaSim.Companion
def maxPacket : Nat := 67
def validPID (pid : UInt8) : Bool := (pid >>> 4) = ((~~~pid) &&& 15)
def crc5 (bits : UInt16) : UInt8 := Id.run do
  let mut c : UInt8 := 31
  for i in [0:11] do
    let mix := ((c >>> 4) ^^^ (bits >>> i.toUInt16).toUInt8) &&& 1
    c := (c <<< 1) &&& 31
    if mix = 1 then c := c ^^^ 5
  let mut reflected : UInt8 := 0
  for i in [0:5] do reflected := (reflected <<< 1) ||| ((c >>> i.toUInt8) &&& 1)
  return reflected ^^^ 31
def crc16 (bytes : ByteArray) : UInt16 := Id.run do
  let mut c : UInt16 := 65535
  for v in bytes do
    for i in [0:8] do
      let mix := ((c >>> 15) ^^^ (v >>> i.toUInt8).toUInt16) &&& 1
      c := c <<< 1
      if mix = 1 then c := c ^^^ 0x8005
  let mut reflected : UInt16 := 0
  for i in [0:16] do reflected := (reflected <<< 1) ||| ((c >>> i.toUInt16) &&& 1)
  return reflected ^^^ 65535
def token (pid : UInt8) (address endpoint : UInt8) : Except String ByteArray := do
  if address > 127 || endpoint > 15 || !(pid = 0xe1 || pid = 0x69 || pid = 0x2d) then throw "token fields"
  let bits := address.toUInt16 ||| (endpoint.toUInt16 <<< 7)
  return ByteArray.mk #[pid,bits.toUInt8,((bits >>> 8).toUInt8 ||| (crc5 bits <<< 3))]
def dataPacket (one : Bool) (bytes : ByteArray) : Except String ByteArray := do
  if bytes.size > 64 then throw "DATA capacity"
  let c := crc16 bytes
  return (ByteArray.mk #[if one then 0x4b else 0xc3] ++ bytes).push c.toUInt8 |>.push (c >>> 8).toUInt8
def dataPayload (packet : ByteArray) : Except String (Bool × ByteArray) := do
  if packet.size < 3 || packet.size > maxPacket then throw "DATA length"
  let pid := packet[0]!
  if !validPID pid || !(pid = 0xc3 || pid = 0x4b) then throw "DATA PID"
  let bytes := packet.extract 1 (packet.size-2)
  let c := crc16 bytes
  if packet[packet.size-2]! != c.toUInt8 || packet[packet.size-1]! != (c >>> 8).toUInt8 then throw "DATA CRC"
  return (pid = 0x4b,bytes)
def handshake (packet : ByteArray) (pid : UInt8) : Bool := packet.size = 1 && packet[0]! = pid
end LemmaSim.USB
