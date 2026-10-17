import Lemma.Core0.Memory

/-! `lemma-wifi-ofdm-data/1`: reusable genuinely compiled scalar/fold packet
and common coding policy. This is a construction dependency, not HE framing,
a PHY acquisition algorithm, MAC/security, or complete Wi-Fi6 support. -/
namespace Lemma.Radio.WiFi.Codec
open Lemma.Core0.Memory

def invalid : UInt8 := 208
def maximumPayload : UInt64 := 16

def crcBit (state bit : UInt64) : UInt64 :=
  if (state ^^^ bit) &&& (1 : UInt64) = 0 then state >>> 1 else (state >>> 1) ^^^ (0xedb88320 : UInt64)

def crcByte (state byte : UInt64) : UInt64 :=
  let a := crcBit state (byte &&& (1 : UInt64))
  let b := crcBit a ((byte >>> 1) &&& (1 : UInt64))
  let c := crcBit b ((byte >>> 2) &&& (1 : UInt64))
  let d := crcBit c ((byte >>> 3) &&& (1 : UInt64))
  let e := crcBit d ((byte >>> 4) &&& (1 : UInt64))
  let f := crcBit e ((byte >>> 5) &&& (1 : UInt64))
  let g := crcBit f ((byte >>> 6) &&& (1 : UInt64))
  crcBit g ((byte >>> 7) &&& (1 : UInt64))

def octet (index word0 word1 : UInt64) : UInt64 :=
  ((if index < 8 then word0 else word1) >>> ((index%8)*8)) &&& (255 : UInt64)

private def crcStep (index _count : UInt32) (state word0 word1 _ _ : UInt64) : Action :=
  .done 0 (crcByte state (octet index.toUInt64 word0 word1))

/-- Local16-byte resource policy. The CRC32 helper is the reflected IEEE
polynomial; payload octets/FCS enter least-significant bit first. -/
def packetCRC (length word0 word1 : UInt64) : Action :=
  if length = 0 then .done invalid 0 else if maximumPayload < length then .done invalid 0 else
  .boundedFoldU64 16 crcStep length.toUInt32 0xffffffff word0 word1 0 0 fun s v => .done s (v ^^^ (0xffffffff : UInt64))

def scrambleNext (state : UInt64) : UInt64 :=
  ((state <<< 1) ||| (((state >>> 6) ^^^ (state >>> 3)) &&& (1 : UInt64))) &&& (127 : UInt64)

private def scrambleStep (index _count : UInt32) (carry input _ _ _ : UInt64) : Action :=
  let state := carry >>> 32
  let feedback := ((state >>> 6) ^^^ (state >>> 3)) &&& (1 : UInt64)
  .done 0 ((scrambleNext state <<< 32) |||
    ((carry &&& (0xffffffff : UInt64)) ||| ((((input >>> index.toUInt64) &&& (1 : UInt64)) ^^^ feedback) <<< index.toUInt64)))

/-- Low32bits are transformed input, next7-bit state is bits32..38. -/
def scrambleBits (seed count input : UInt64) : Action :=
  if seed = 0 then .done invalid 0 else if 127 < seed then .done invalid 0 else
  if 32 < count then .done invalid 0 else
  .boundedFoldU64 32 scrambleStep count.toUInt32 (seed <<< 32) input 0 0 0 fun s v => .done s v

def parity7 (v : UInt64) : UInt64 :=
  let a := v ^^^ (v >>> 4)
  let b := a ^^^ (a >>> 2)
  (b ^^^ (b >>> 1)) &&& (1 : UInt64)

/-- New input enters position6; A(133octal) precedes B(171octal). Low6bits
are next memory, bits6/7 are the actually computed coded pair. -/
def bccBit (state bit : UInt64) : UInt64 :=
  let reg : UInt64 := ((bit &&& (1 : UInt64)) <<< 6) ||| (state &&& (63 : UInt64))
  ((reg >>> 1) &&& (63 : UInt64)) ||| (parity7 (reg &&& (0x5b : UInt64)) <<< 6) ||| (parity7 (reg &&& (0x79 : UInt64)) <<< 7)

private def encodeStep (index _count : UInt32) (carry input _ _ _ : UInt64) : Action :=
  let step : UInt64 := bccBit (carry &&& (63 : UInt64)) ((input >>> index.toUInt64) &&& (1 : UInt64))
  .done 0 ((step &&& (63 : UInt64)) ||| (((carry >>> 6) ||| ((step >>> 6) <<< (index.toUInt64*2))) <<< 6))

/-- Low48bits are encoded24 input bits; next6-bit state is bits48..53. -/
def encodeSymbol (state input : UInt64) : Action :=
  if 63 < state then .done invalid 0 else if 0xffffff < input then .done invalid 0 else
  .boundedFoldU64 24 encodeStep 24 state input 0 0 0 fun s v => .done s ((v >>> 6) ||| ((v &&& (63 : UInt64)) <<< 48))

def permutation (index : UInt64) : UInt64 := 3*(index%16)+index/16
private def interleaveStep (index _count : UInt32) (carry input _ _ _ : UInt64) : Action :=
  .done 0 (carry ||| (((input >>> index.toUInt64) &&& (1 : UInt64)) <<< permutation index.toUInt64))

def interleaveSymbol (input : UInt64) : Action :=
  if 0xffffffffffff < input then .done invalid 0 else
  .boundedFoldU64 48 interleaveStep 48 0 input 0 0 0 fun s v => .done s v

def symbols (length : UInt64) : UInt64 := (16+(length+4)*8+6+23)/24

def dataBit (index length word0 word1 crc : UInt64) : UInt64 :=
  if index < 16 then 0 else
  let position := index-16
  if position < length*8 then (octet (position/8) word0 word1 >>> (position%8)) &&& (1 : UInt64) else
  if position < (length+4)*8 then (crc >>> (position-length*8)) &&& (1 : UInt64) else 0

private def dataStep (index _count : UInt32) (carry length word0 word1 crc : UInt64) : Action :=
  let position := index.toUInt64
  let seed := (carry >>> 6) &&& (127 : UInt64)
  let mixed := dataBit position length word0 word1 crc ^^^ (((seed >>> 6) ^^^ (seed >>> 3)) &&& (1 : UInt64))
  let tail := 16+(length+4)*8
  let input := if position < tail then mixed else if position < tail+6 then 0 else mixed
  let pair := bccBit (carry &&& (63 : UInt64)) input
  let coded : UInt64 := if position%24 = 0 then 0 else carry >>> 13
  .done 0 ((pair &&& (63 : UInt64)) ||| (scrambleNext seed <<< 6) |||
    ((coded ||| ((pair >>> 6) <<< ((position%24)*2))) <<< 13))

/-- Compute one selected DATA symbol through all preceding coding state.
Low6bits are BCC state, bits6..12 scrambler state, bits13..60 coded48bits.
SERVICE16zero, payload/FCS, six forced-zero tail inputs, scrambled zero padding.
The descriptor's selected length/seed are inputs; acquisition is not implemented. -/
def dataSymbol (symbol length word0 word1 seed : UInt64) : Action :=
  if length = 0 then .done invalid 0 else if maximumPayload < length then .done invalid 0 else
  if seed = 0 then .done invalid 0 else if 127 < seed then .done invalid 0 else
  if symbols length ≤ symbol then .done invalid 0 else
  .bind (packetCRC length word0 word1) fun s crc => if s = 0 then
  .boundedFoldU64 192 dataStep ((symbol+1)*24).toUInt32 (seed <<< 6) length word0 word1 crc fun t v => .done t v
  else .done s 0

end Lemma.Radio.WiFi.Codec
