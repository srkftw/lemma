/-! Scalar codec primitives for the existing opaque companion-v1 frame and
an8-byte development USB session inquiry. All guest bytes are constructed in
owned memory by checked Lean actions; hosts never construct guest journals. -/
namespace Lemma.USB.BlockProtocol

def magic : UInt64 := 0x313030504d434d4c
def helloMagic : UInt64 := 0x3130425355434d4c
def capacity : UInt64 := 268435456
def sectorBytes : UInt64 := 512
def requestBytes (kind : UInt64) : UInt64 := if kind = 1 then 584 else 72
def payloadBytes (kind : UInt64) : UInt64 := if kind = 2 then 0 else 512
def validRequest (kind writer sequence offset : UInt64) : Bool :=
  if (if writer = 0 then false else true) then
  if kind = 0 then if offset % 512 = 0 then offset ≤ capacity-512 else false else
  if kind = 1 then if (if sequence = 0 then false else true) then
    if offset % 512 = 0 then offset ≤ capacity-512 else false else false else
  if kind = 2 then if (if sequence = 0 then false else true) then offset = 0 else false else false
  else false

def headerWord (index kind writer sequence offset : UInt64) : UInt64 :=
  if index = 0 then magic else if index = 1 then 1 else
  if index = 2 then kind else if index = 3 then writer else
  if index = 4 then if kind = 0 then 0 else sequence else
  if index = 5 then offset else if index = 6 then payloadBytes kind else 0
private def crcStep (c : UInt64) : UInt64 := (c <<< 1) ^^^ (if c >>> 63 = 0 then 0 else 0x42f0e1eba9ea3693)
def crcByte (state value : UInt64) : UInt64 :=
  let c := state ^^^ ((value &&& 255) <<< 56)
  crcStep (crcStep (crcStep (crcStep (crcStep (crcStep (crcStep (crcStep c)))))))
def crcWord (state word : UInt64) : UInt64 :=
  let c := crcByte state word
  let c := crcByte c (word >>> 8)
  let c := crcByte c (word >>> 16)
  let c := crcByte c (word >>> 24)
  let c := crcByte c (word >>> 32)
  let c := crcByte c (word >>> 40)
  let c := crcByte c (word >>> 48)
  crcByte c (word >>> 56)
end Lemma.USB.BlockProtocol
