import Lemma.Radio.WiFi.Codec

/-! Actual RV64 diagnostic for the pure Wi-Fi common coding dependency.
The guest generates its own two payloads and result records. It does not
claim a connected Wi-Fi driver, PLCP acquisition, HE PPDU or RF execution. -/
namespace Lemma.Platform.RiscV.Development.WiFiCodecPolicy
open Lemma.Core0.Memory Lemma.Radio.WiFi

def recordBase : UInt64 := 0x80100100
def payloadBase : UInt64 := 0x80100400
def emit (index value : UInt64) : Action :=
 .platform .physicalWrite64 (recordBase+index*8) value 0 0 0 0 fun s v => .done s v

def record (index expected : UInt64) (s : UInt8) (v : UInt64) : Action :=
 if s = 0 then
 .bind (emit index v) fun t _ => if t = 0 then
 if v = expected then .done 0 v else .done 209 v
 else .done t 0 else .done s 0

private def payloadStep (index _count : UInt32) (_carry _ _ _ _ : UInt64) : Action :=
 let position := index.toUInt64
 let value := if position < 16 then position*17 else (255 : UInt64) ^^^ ((position-16)*17)
 .platform .physicalWrite8 (payloadBase+position) value 0 0 0 0 fun s v => .done s v

private def symbolStep (index _count : UInt32) (_carry word0 word1 seed _ : UInt64) : Action :=
 .bind (Codec.dataSymbol index.toUInt64 16 word0 word1 seed) fun s v => if s = 0 then
 .bind (emit (8+index.toUInt64) v) fun t _ => .done t v else .done s 0

def main : Action :=
 .bind (emit 5 0) fun s _ => if s = 0 then
 .bind (emit 0 0x57494649504f4c01) fun s _ => if s = 0 then
 .bind (Codec.packetCRC 9 0x3837363534333231 0x39) fun s v =>
 .bind (record 1 0xcbf43926 s v) fun s _ => if s = 0 then
 .bind (Codec.scrambleBits 93 16 0) fun s v =>
 .bind (record 2 0x1900009836 s v) fun s _ => if s = 0 then
 .bind (Codec.encodeSymbol 0 0xd064) fun s v =>
 .bind (record 3 0x0e45889f13b0 s v) fun s _ => if s = 0 then
 .bind (Codec.interleaveSymbol 0x0e45889f13b0) fun s v =>
 .bind (record 4 0x401d2970b596 s v) fun s _ => if s = 0 then
 .boundedFoldU64 32 payloadStep 32 0 0 0 0 0 fun s _ => if s = 0 then
 .boundedFoldU64 8 symbolStep 8 0 0x7766554433221100 0xffeeddccbbaa9988 93 0 fun s _ => if s = 0 then
 .bind (emit 7 32) fun s _ => if s = 0 then
 .bind (emit 5 0x57494649444f4e01) fun s _ => .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0
end Lemma.Platform.RiscV.Development.WiFiCodecPolicy
