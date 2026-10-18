import Lemma.Crypto.HMAC256

/-! RFC5869 sections2.2--2.3 HKDF-SHA256 for32byte directional keys. This
bounded single-block Expand is sufficient for one key; caller labels each role
and binds the authenticated session transcript. It never invents live entropy. -/
namespace Lemma.Crypto.HKDF256
private def different (a b : UInt64) : Bool := if a = b then false else true
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access

def workspaceBytes : UInt64 := 4096
private def copy (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (read8 (source+i.toUInt64)) fun s byte => if s = 0 then
  .bind (write8 (target+i.toUInt64) byte) fun s _ => .done s acc else .done s 0
/-- Exactly32 output bytes. For absent salt the caller supplies32zero bytes as
specified by RFC5869. info <=256; IKM <=4096. Internal PRK stays private. -/
def derive (w salt saltBytes ikm ikmBytes info infoBytes output : UInt64) : Action :=
  if different (w%8) (0) = true then .done SHA256.invalid 0 else
  if SHA256.validSpan w workspaceBytes = false then .done SHA256.invalid 0 else
  if SHA256.validSpan salt saltBytes = false then .done SHA256.invalid 0 else
  if SHA256.validSpan ikm ikmBytes = false then .done SHA256.invalid 0 else
  if SHA256.validSpan info infoBytes = false then .done SHA256.invalid 0 else
  if SHA256.validSpan output 32 = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes salt saltBytes = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes ikm ikmBytes = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes info infoBytes = false then .done SHA256.invalid 0 else
  if SHA256.separate w workspaceBytes output 32 = false then .done SHA256.invalid 0 else
  if 256 < infoBytes then .done SHA256.exhausted 0 else
  if 4096 < ikmBytes then .done SHA256.exhausted 0 else
  if 4096 < saltBytes then .done SHA256.exhausted 0 else
  .bind (HMAC256.authenticate w salt saltBytes ikm ikmBytes (w+2048)) fun s _ => if s = 0 then
  .boundedFoldU64 256 copy infoBytes.toUInt32 0 info (w+2080) 0 0 fun s _ => if s = 0 then
  .bind (write8 (w+2080+infoBytes) 1) fun s _ => if s = 0 then
  HMAC256.authenticate w (w+2048) 32 (w+2080) (infoBytes+1) output
  else .done s 0 else .done s 0 else .done s 0
end Lemma.Crypto.HKDF256
