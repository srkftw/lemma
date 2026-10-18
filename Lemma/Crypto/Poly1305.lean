import Lemma.Crypto.ChaCha20

/-! RFC8439 section2.5 Poly1305 with26bit limbs. Every multiplication sum is
below2^61 for admitted state; no big integer or hosted runtime is used. This
one-shot bounded primitive requires a unique one-time key supplied by AEAD. -/
namespace Lemma.Crypto.Poly1305
private def different (a b : UInt64) : Bool := if a = b then false else true
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access
private def mask : UInt64 := 0x3ffffff
def workspaceBytes : UInt64 := 256
private def clear (i _ : UInt32) (acc w _ _ _ : UInt64) : Action :=
  .bind (write64 (w+i.toUInt64*8) 0) fun s _ => .done s acc
private def keyStep (i _ : UInt32) (acc w key _ _ : UInt64) : Action :=
  let n := i.toUInt64
  let offset : UInt64 := if n = 0 then 0 else if n = 1 then 3 else if n = 2 then 6 else if n = 3 then 9 else 12
  let bits : UInt64 := if n = 0 then 0 else if n = 1 then 2 else if n = 2 then 4 else if n = 3 then 6 else 8
  let clamp : UInt64 := if n = 0 then 0x3ffffff else if n = 1 then 0x3ffff03 else if n = 2 then 0x3ffc0ff else if n = 3 then 0x3f03fff else 0x00fffff
  .bind (ChaCha20.readLE32 (key+offset)) fun s word => if s = 0 then
  .bind (write64 (w+n*8) ((word >>> bits) &&& clamp)) fun s _ => .done s acc else .done s 0
private def copy (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (read8 (source+i.toUInt64)) fun s b => if s = 0 then
  .bind (write8 (target+i.toUInt64) b) fun s _ => .done s acc else .done s 0
private def process (w source count : UInt64) : Action :=
  .bind (write64 (w+128) 0) fun s _ => if s = 0 then
  .bind (write64 (w+136) 0) fun s _ => if s = 0 then
  .boundedFoldU64 16 copy count.toUInt32 0 source (w+128) 0 0 fun s _ => if s = 0 then
  .bind (if count < 16 then write8 (w+128+count) 1 else .done 0 0) fun s _ => if s = 0 then
  .bind (ChaCha20.readLE32 (w+128)) fun s t0 => if s = 0 then
  .bind (ChaCha20.readLE32 (w+131)) fun s t1 => if s = 0 then
  .bind (ChaCha20.readLE32 (w+134)) fun s t2 => if s = 0 then
  .bind (ChaCha20.readLE32 (w+137)) fun s t3 => if s = 0 then
  .bind (ChaCha20.readLE32 (w+140)) fun s t4 => if s = 0 then
  .bind (read64 (w+72)) fun s old0 => if s = 0 then
  .bind (read64 (w+80)) fun s old1 => if s = 0 then
  .bind (read64 (w+88)) fun s old2 => if s = 0 then
  .bind (read64 (w+96)) fun s old3 => if s = 0 then
  .bind (read64 (w+104)) fun s old4 => if s = 0 then
  .bind (read64 w) fun s r0 => if s = 0 then
  .bind (read64 (w+8)) fun s r1 => if s = 0 then
  .bind (read64 (w+16)) fun s r2 => if s = 0 then
  .bind (read64 (w+24)) fun s r3 => if s = 0 then
  .bind (read64 (w+32)) fun s r4 => if s = 0 then
  let h0 : UInt64 := old0+(t0 &&& mask)
  let h1 : UInt64 := old1+((t1 >>> 2) &&& mask)
  let h2 : UInt64 := old2+((t2 >>> 4) &&& mask)
  let h3 : UInt64 := old3+((t3 >>> 6) &&& mask)
  let h4 : UInt64 := old4+(t4 >>> 8)+(if count = 16 then 0x1000000 else 0)
  let d0 : UInt64 := h0*r0+h1*r4*(5 : UInt64)+h2*r3*(5 : UInt64)+h3*r2*(5 : UInt64)+h4*r1*(5 : UInt64)
  let d1 : UInt64 := h0*r1+h1*r0+h2*r4*(5 : UInt64)+h3*r3*(5 : UInt64)+h4*r2*(5 : UInt64)+(d0 >>> 26)
  let d2 : UInt64 := h0*r2+h1*r1+h2*r0+h3*r4*(5 : UInt64)+h4*r3*(5 : UInt64)+(d1 >>> 26)
  let d3 : UInt64 := h0*r3+h1*r2+h2*r1+h3*r0+h4*r4*(5 : UInt64)+(d2 >>> 26)
  let d4 : UInt64 := h0*r4+h1*r3+h2*r2+h3*r1+h4*r0+(d3 >>> 26)
  let f0 : UInt64 := (d0 &&& mask)+(d4 >>> 26)*(5 : UInt64)
  .bind (write64 (w+72) (f0 &&& mask)) fun s _ => if s = 0 then
  .bind (write64 (w+80) ((d1 &&& mask)+(f0 >>> 26))) fun s _ => if s = 0 then
  .bind (write64 (w+88) (d2 &&& mask)) fun s _ => if s = 0 then
  .bind (write64 (w+96) (d3 &&& mask)) fun s _ => if s = 0 then
  write64 (w+104) (d4 &&& mask)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def blockStep (i _ : UInt32) (acc w source bytes _ : UInt64) : Action :=
  let offset : UInt64 := i.toUInt64*16
  .bind (process w (source+offset) (if 16 < bytes-offset then 16 else bytes-offset)) fun s _ => .done s acc
private def emitStep (i _ : UInt32) (acc w output _ _ : UInt64) : Action :=
  .bind (read64 (w+160+i.toUInt64/4*8)) fun s word => if s = 0 then
  .bind (write8 (output+i.toUInt64) ((word >>> (i.toUInt64%4*8)) &&& 255)) fun s _ => .done s acc else .done s 0
private def finish (w key output : UInt64) : Action :=
  .bind (read64 (w+72)) fun s old0 => if s = 0 then
  .bind (read64 (w+80)) fun s old1 => if s = 0 then
  .bind (read64 (w+88)) fun s old2 => if s = 0 then
  .bind (read64 (w+96)) fun s old3 => if s = 0 then
  .bind (read64 (w+104)) fun s old4 => if s = 0 then
  let t2 : UInt64 := old2+(old1 >>> 26)
  let t3 : UInt64 := old3+(t2 >>> 26)
  let t4 : UInt64 := old4+(t3 >>> 26)
  let t0 : UInt64 := old0+(t4 >>> 26)*(5 : UInt64)
  let h0 : UInt64 := t0 &&& mask
  let h1 : UInt64 := (old1 &&& mask)+(t0 >>> 26)
  let h2 : UInt64 := t2 &&& mask
  let h3 : UInt64 := t3 &&& mask
  let h4 : UInt64 := t4 &&& mask
  let g0 : UInt64 := h0+5
  let g1 : UInt64 := h1+(g0 >>> 26)
  let g2 : UInt64 := h2+(g1 >>> 26)
  let g3 : UInt64 := h3+(g2 >>> 26)
  let g4 : UInt64 := h4+(g3 >>> 26)
  let reduce : Bool := if 0x4000000 ≤ g4 then true else false
  let f0 : UInt64 := if reduce = true then g0 &&& mask else h0
  let f1 : UInt64 := if reduce = true then g1 &&& mask else h1
  let f2 : UInt64 := if reduce = true then g2 &&& mask else h2
  let f3 : UInt64 := if reduce = true then g3 &&& mask else h3
  let f4 : UInt64 := if reduce = true then g4 &&& mask else h4
  .bind (ChaCha20.readLE32 (key+16)) fun s s0 => if s = 0 then
  .bind (ChaCha20.readLE32 (key+20)) fun s s1 => if s = 0 then
  .bind (ChaCha20.readLE32 (key+24)) fun s s2 => if s = 0 then
  .bind (ChaCha20.readLE32 (key+28)) fun s s3 => if s = 0 then
  let x0 : UInt64 := ((f0 ||| (f1 <<< 26)) &&& (0xffffffff : UInt64))+s0
  let x1 : UInt64 := (((f1 >>> 6) ||| (f2 <<< 20)) &&& (0xffffffff : UInt64))+s1+(x0 >>> 32)
  let x2 : UInt64 := (((f2 >>> 12) ||| (f3 <<< 14)) &&& (0xffffffff : UInt64))+s2+(x1 >>> 32)
  let x3 : UInt64 := (((f3 >>> 18) ||| (f4 <<< 8)) &&& (0xffffffff : UInt64))+s3+(x2 >>> 32)
  .bind (write64 (w+160) x0) fun s _ => if s = 0 then
  .bind (write64 (w+168) x1) fun s _ => if s = 0 then
  .bind (write64 (w+176) x2) fun s _ => if s = 0 then
  .bind (write64 (w+184) x3) fun s _ => if s = 0 then
  .boundedFoldU64 16 emitStep 16 0 w output 0 0 fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def authenticate (w key source bytes output : UInt64) : Action :=
  if different (w%8) (0) = true then .done SHA256.invalid 0 else
  if SHA256.validSpan w workspaceBytes = false then .done SHA256.invalid 0 else
  if SHA256.validSpan key 32 = false then .done SHA256.invalid 0 else
  if SHA256.validSpan source bytes = false then .done SHA256.invalid 0 else
  if SHA256.validSpan output 16 = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes key 32 = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes source bytes = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes output 16 = false then .done SHA256.invalid 0 else
  if SHA256.separate output 16 key 32 = false then .done SHA256.invalid 0 else
  if 8192 < bytes then .done SHA256.exhausted 0 else
  .boundedFoldU64 32 clear 32 0 w 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 5 keyStep 5 0 w key 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 512 blockStep ((bytes+15)/16).toUInt32 0 w source bytes 0 fun s _ => if s = 0 then
  finish w key output else .done s 0 else .done s 0 else .done s 0
end Lemma.Crypto.Poly1305
