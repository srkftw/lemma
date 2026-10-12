import Std

/-! Hosted Lean reference protocol for the development opaque block peer.
No guest document, ink, journal, mathematics or recovery codec is interpreted.
This ordinary Lean module is not yet an admitted freestanding target subset. -/
namespace LemmaSim.Companion

def magic : UInt64 := 0x313030504d434d4c

def maxPayload : Nat := 1048576

def mediumBytes : UInt64 := 268435456

structure Frame where
  kind : UInt64
  writer : UInt64
  sequence : UInt64
  offset : UInt64
  length : UInt64
  error : UInt64 := 0
  payload : ByteArray := ByteArray.empty
  deriving Inhabited

def put64 (b : ByteArray) (v : UInt64) : ByteArray := Id.run do
  let mut out := b
  for i in [0:8] do out := out.push ((v >>> (8 * i).toUInt64).toUInt8)
  return out

def get64 (b : ByteArray) (offset : Nat) : UInt64 := Id.run do
  let mut v : UInt64 := 0
  for i in [0:8] do v := v ||| (b[offset+i]!.toUInt64 <<< (8*i).toUInt64)
  return v

def crc64 (b : ByteArray) : UInt64 := Id.run do
  let mut c : UInt64 := 0
  for v in b do
    c := c ^^^ (v.toUInt64 <<< 56)
    for _ in [0:8] do
      c := (c <<< 1) ^^^ (if c >>> 63 = 0 then 0 else 0x42f0e1eba9ea3693)
  return c

def encode (f : Frame) : ByteArray := Id.run do
  let mut b := ByteArray.empty
  for v in [magic,1,f.kind,f.writer,f.sequence,f.offset,f.length,f.error] do b := put64 b v
  b := b ++ f.payload
  return put64 b (crc64 b)

def decode (b : ByteArray) : Except String Frame := do
  if b.size < 72 || b.size > maxPayload + 72 then throw "frame length"
  if get64 b 0 != magic || get64 b 8 != 1 then throw "frame identity"
  if get64 b (b.size-8) != crc64 (b.extract 0 (b.size-8)) then throw "frame CRC"
  let f : Frame := {
    kind := get64 b 16, writer := get64 b 24, sequence := get64 b 32,
    offset := get64 b 40, length := get64 b 48, error := get64 b 56,
    payload := b.extract 64 (b.size-8) }
  if f.kind > 3 || f.writer = 0 || f.error > 4095 then throw "frame fields"
  if f.kind = 0 then
    if f.length = 0 || f.length > maxPayload.toUInt64 || f.offset > mediumBytes - f.length || f.offset % 512 != 0 || f.length % 512 != 0 || !f.payload.isEmpty || f.error != 0 then throw "read fields"
  else if f.kind = 1 then
    if f.sequence = 0 || f.length != 512 || f.offset > mediumBytes - 512 || f.offset % 512 != 0 || f.payload.size != 512 || f.error != 0 then throw "write fields"
  else if f.kind = 2 then
    if f.sequence = 0 || f.length != 0 || f.offset != 0 || !f.payload.isEmpty || f.error != 0 then throw "barrier fields"
  else if f.length > maxPayload.toUInt64 || f.payload.size != f.length.toNat then throw "response fields"
  return f

def sameRequest (a b : Frame) : Bool := encode a == encode b

def response (request : Frame) (error : UInt64) (bytes : ByteArray := ByteArray.empty) : Frame :=
  { kind := 3, writer := request.writer, sequence := request.sequence, offset := request.offset,
    length := bytes.size.toUInt64, error := error, payload := bytes }

def hex (b : ByteArray) : String := Id.run do
  let digits := "0123456789abcdef".toList.toArray
  let mut chars : Array Char := #[]
  for v in b do
    chars := chars.push digits[(v >>> 4).toNat]!
    chars := chars.push digits[(v &&& 15).toNat]!
  return String.ofList chars.toList

def unhex (s : String) : Except String ByteArray := do
  let a := s.toList.toArray
  if a.size % 2 != 0 || a.size > 2*(maxPayload+72) then throw "hex length"
  let digit (c : Char) : Except String UInt8 :=
    if c >= '0' && c <= '9' then .ok (c.toNat-'0'.toNat).toUInt8
    else if c >= 'a' && c <= 'f' then .ok (c.toNat-'a'.toNat+10).toUInt8
    else throw "hex digit"
  let mut b := ByteArray.empty
  for i in [0:a.size/2] do b := b.push (((← digit a[2*i]!) <<< 4) ||| (← digit a[2*i+1]!))
  return b
end LemmaSim.Companion
