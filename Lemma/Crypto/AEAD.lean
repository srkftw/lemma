import Lemma.Crypto.Poly1305

/-! RFC8439 section2.8 IETF ChaCha20-Poly1305. Bounded one-shot packets with
<=256 AAD and <=4096 payload bytes; 6144-byte private pinned workspace. Tag
verification precedes all plaintext writes. No key/nonce provisioning, timing
security certification, implicit key fallback or physical entropy is provided.
Caller must guarantee unique(key,nonce), immutable input and exclusive buffers. -/
namespace Lemma.Crypto.AEAD
private def different (a b : UInt64) : Bool := if a = b then false else true
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access

def workspaceBytes : UInt64 := 6144
def badTag : UInt8 := 247
private def zero (i _ : UInt32) (acc target _ _ _ : UInt64) : Action :=
  .bind (write8 (target+i.toUInt64) 0) fun s _ => .done s acc
private def copy (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (read8 (source+i.toUInt64)) fun s b => if s = 0 then
  .bind (write8 (target+i.toUInt64) b) fun s _ => .done s acc else .done s 0
private def lengthByte (i _ : UInt32) (acc target a b _ : UInt64) : Action :=
  let n := i.toUInt64
  let word := if n < 8 then a else b
  .bind (write8 (target+n) ((word >>> (n%8*8)) &&& 255)) fun s _ => .done s acc
private def mac (w key nonce aad aadBytes ciphertext bytes : UInt64) : Action :=
  let first := (aadBytes+15)/16*16
  let second := (bytes+15)/16*16
  let length := first+second+16
  .bind (ChaCha20.block w key nonce 0 (w+512)) fun s _ => if s = 0 then
  .boundedFoldU64 4384 zero length.toUInt32 0 (w+1024) 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 256 copy aadBytes.toUInt32 0 aad (w+1024) 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 4096 copy bytes.toUInt32 0 ciphertext (w+1024+first) 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 16 lengthByte 16 0 (w+1024+first+second) aadBytes bytes 0 fun s _ => if s = 0 then
  Poly1305.authenticate (w+256) (w+512) (w+1024) length (w+576)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def xorByte (i _ : UInt32) (acc source target stream _ : UInt64) : Action :=
  .bind (read8 (source+i.toUInt64)) fun s byte => if s = 0 then
  .bind (read8 (stream+i.toUInt64)) fun s pad => if s = 0 then
  .bind (write8 (target+i.toUInt64) (byte ^^^ pad)) fun s _ => .done s acc
  else .done s 0 else .done s 0
private def xorBlock (i _ : UInt32) (acc w key nonce _ : UInt64) : Action :=
  .bind (read64 (w+640)) fun s source => if s = 0 then
  .bind (read64 (w+648)) fun s target => if s = 0 then
  .bind (read64 (w+656)) fun s bytes => if s = 0 then
  .bind (ChaCha20.block w key nonce (i.toUInt64+1) (w+512)) fun s _ => if s = 0 then
  let offset := i.toUInt64*64
  .boundedFoldU64 64 xorByte (if 64 < bytes-offset then 64 else bytes-offset).toUInt32
    acc (source+offset) (target+offset) (w+512) 0 fun s value => .done s value
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def crypt (w key nonce source bytes target : UInt64) : Action :=
  .bind (write64 (w+640) source) fun s _ => if s = 0 then
  .bind (write64 (w+648) target) fun s _ => if s = 0 then
  .bind (write64 (w+656) bytes) fun s _ => if s = 0 then
  .boundedFoldU64 64 xorBlock ((bytes+63)/64).toUInt32 0 w key nonce 0 fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0
/-- Partial overlap is rejected. Exact in-place encryption/decryption is valid;
    caller-owned inputs can overlap each other but not outputs or workspace. -/
def valid (w key nonce aad aadBytes source bytes target tag : UInt64) : Bool :=
  if different (w%8) (0) = true then false else if 256 < aadBytes then false else if 4096 < bytes then false else
  if SHA256.validSpan w workspaceBytes = false then false else
  if SHA256.validSpan key 32 = false then false else if SHA256.validSpan nonce 12 = false then false else
  if SHA256.validSpan aad aadBytes = false then false else if SHA256.validSpan source bytes = false then false else
  if SHA256.validSpan target bytes = false then false else if SHA256.validSpan tag 16 = false then false else
  if SHA256.separate w workspaceBytes key 32 = false then false else
  if SHA256.separate w workspaceBytes nonce 12 = false then false else
  if SHA256.separate w workspaceBytes aad aadBytes = false then false else
  if SHA256.separate w workspaceBytes source bytes = false then false else
  if SHA256.separate w workspaceBytes target bytes = false then false else
  if SHA256.separate w workspaceBytes tag 16 = false then false else
  if SHA256.separate target bytes key 32 = false then false else
  if SHA256.separate target bytes nonce 12 = false then false else
  if SHA256.separate target bytes aad aadBytes = false then false else
  if SHA256.separate target bytes tag 16 = false then false else
  if SHA256.separate tag 16 key 32 = false then false else
  if SHA256.separate tag 16 nonce 12 = false then false else
  if SHA256.separate tag 16 aad aadBytes = false then false else
  if SHA256.separate tag 16 source bytes = false then false else
  if source = target then true else SHA256.separate source bytes target bytes

def «seal» (w key nonce aad aadBytes plaintext bytes ciphertext tag : UInt64) : Action :=
  if valid w key nonce aad aadBytes plaintext bytes ciphertext tag = false then .done SHA256.invalid 0 else
  .bind (crypt w key nonce plaintext bytes ciphertext) fun s _ => if s = 0 then
  .bind (mac w key nonce aad aadBytes ciphertext bytes) fun s _ => if s = 0 then
  .boundedFoldU64 16 copy 16 0 (w+576) tag 0 0 fun s _ => .done s 0
  else .done s 0 else .done s 0
private def compare (i _ : UInt32) (acc a b _ _ : UInt64) : Action :=
  .bind (read8 (a+i.toUInt64)) fun s x => if s = 0 then
  .bind (read8 (b+i.toUInt64)) fun s y => if s = 0 then
  .done 0 (acc ||| (x ^^^ y)) else .done s 0 else .done s 0

def «open» (w key nonce aad aadBytes ciphertext bytes plaintext tag : UInt64) : Action :=
  if valid w key nonce aad aadBytes ciphertext bytes plaintext tag = false then .done SHA256.invalid 0 else
  .bind (mac w key nonce aad aadBytes ciphertext bytes) fun s _ => if s = 0 then
  .boundedFoldU64 16 compare 16 0 (w+576) tag 0 0 fun s difference => if s = 0 then
  if different (difference) (0) = true then .done badTag 0 else crypt w key nonce ciphertext bytes plaintext
  else .done s 0 else .done s 0
end Lemma.Crypto.AEAD
