import Lemma.Crypto.SHA256

/-! RFC8439 sections2.1--2.4 IETF ChaCha20, with explicit bounded private RAM.
All target operations are ordinary Lean scalar/Action declarations. This is a
primitive, not identity provisioning or a claim of physical side-channel safety.
Counter0 is reserved by AEAD; standalone xor admits caller-selected counters. -/
namespace Lemma.Crypto.ChaCha20
private def different (a b : UInt64) : Bool := if a = b then false else true
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access

def workspaceBytes : UInt64 := 256
private def mask : UInt64 := 0xffffffff
private def rotate (v n : UInt64) : UInt64 := ((v <<< n) ||| (v >>> (32-n))) &&& mask

def readLE32 (a : UInt64) : Action :=
  .bind (read8 a) fun s a0 => if s = 0 then
  .bind (read8 (a+1)) fun s a1 => if s = 0 then
  .bind (read8 (a+2)) fun s a2 => if s = 0 then
  .bind (read8 (a+3)) fun s a3 => if s = 0 then
  .done 0 (a0 ||| (a1 <<< 8) ||| (a2 <<< 16) ||| (a3 <<< 24))
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def quarter (w ai bi ci di : UInt64) : Action :=
  .bind (read64 (w+ai*8)) fun s a => if s = 0 then
  .bind (read64 (w+bi*8)) fun s b => if s = 0 then
  .bind (read64 (w+ci*8)) fun s c => if s = 0 then
  .bind (read64 (w+di*8)) fun s d => if s = 0 then
  let a1 := (a+b) &&& mask
  let d1 := rotate (d ^^^ a1) 16
  let c1 := (c+d1) &&& mask
  let b1 := rotate (b ^^^ c1) 12
  let a2 := (a1+b1) &&& mask
  let d2 := rotate (d1 ^^^ a2) 8
  let c2 := (c1+d2) &&& mask
  let b2 := rotate (b1 ^^^ c2) 7
  .bind (write64 (w+ai*8) a2) fun s _ => if s = 0 then
  .bind (write64 (w+bi*8) b2) fun s _ => if s = 0 then
  .bind (write64 (w+ci*8) c2) fun s _ => if s = 0 then
  write64 (w+di*8) d2
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def rounds (_ _ : UInt32) (acc w _ _ _ : UInt64) : Action :=
  .bind (quarter w 0 4 8 12) fun s _ => if s = 0 then
  .bind (quarter w 1 5 9 13) fun s _ => if s = 0 then
  .bind (quarter w 2 6 10 14) fun s _ => if s = 0 then
  .bind (quarter w 3 7 11 15) fun s _ => if s = 0 then
  .bind (quarter w 0 5 10 15) fun s _ => if s = 0 then
  .bind (quarter w 1 6 11 12) fun s _ => if s = 0 then
  .bind (quarter w 2 7 8 13) fun s _ => if s = 0 then
  .bind (quarter w 3 4 9 14) fun s _ => .done s acc
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
private def seedState (i _ : UInt32) (acc w key nonce counter : UInt64) : Action :=
  let n := i.toUInt64
  .bind (if n < 4 then .done 0 (if n = 0 then 0x61707865 else if n = 1 then 0x3320646e else if n = 2 then 0x79622d32 else 0x6b206574)
    else if n < 12 then readLE32 (key+(n-4)*4) else
    if n = 12 then .done 0 counter else readLE32 (nonce+(n-13)*4)) fun s word => if s = 0 then
  .bind (write64 (w+n*8) word) fun s _ => if s = 0 then
  .bind (write64 (w+128+n*8) word) fun s _ => .done s acc else .done s 0 else .done s 0
private def emit (i _ : UInt32) (acc w output _ _ : UInt64) : Action :=
  let n := i.toUInt64
  .bind (read64 (w+(n/4)*8)) fun s original => if s = 0 then
  .bind (read64 (w+128+(n/4)*8)) fun s mixed => if s = 0 then
  .bind (write8 (output+n) (((original+mixed) >>> (n%4*8)) &&& 255)) fun s _ => .done s acc
  else .done s 0 else .done s 0
/-- All extents are checked before any mutation; output cannot alias key,
nonce or workspace. Each output block is64bytes and counter is exactly32bits. -/
def block (w key nonce counter output : UInt64) : Action :=
  if different (w%8) (0) = true then .done SHA256.invalid 0 else
  if SHA256.validSpan w workspaceBytes = false then .done SHA256.invalid 0 else
  if SHA256.validSpan key 32 = false then .done SHA256.invalid 0 else
  if SHA256.validSpan nonce 12 = false then .done SHA256.invalid 0 else
  if SHA256.validSpan output 64 = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes key 32 = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes nonce 12 = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes output 64 = false then .done SHA256.invalid 0 else
  if SHA256.separate output 64 key 32 = false then .done SHA256.invalid 0 else
  if SHA256.separate output 64 nonce 12 = false then .done SHA256.invalid 0 else
  if mask < counter then .done SHA256.exhausted 0 else
  .boundedFoldU64 16 seedState 16 0 w key nonce counter fun s _ => if s = 0 then
  .boundedFoldU64 10 rounds 10 0 (w+128) 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 64 emit 64 0 w output 0 0 fun s _ => .done s 0
  else .done s 0 else .done s 0
end Lemma.Crypto.ChaCha20
