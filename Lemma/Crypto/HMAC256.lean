import Lemma.Crypto.SHA256

/-! Streaming HMAC-SHA-256 with a private2048-byte physical RAM workspace.
Keys are supplied by the caller; there is no built-in production identity,
entropy source, authentication success constant or anti-rollback state.
RFC2104's full32-byte tag is used. Input chunks are at most4096 bytes.
Errors require begin again; no constant-time/secure-erasure claim is made. -/
namespace Lemma.Crypto.HMAC256
open Lemma.Core0.Memory
open Lemma.Kernel.Memory.Access
def workspaceBytes : UInt64 := 2048
private def mode : UInt64 := 0x3143414d484d4c
private def validWorkspace (workspace : UInt64) : Bool :=
  if workspace%8 = 0 then SHA256.validSpan workspace workspaceBytes else false
private def clearKeyStep (i _ : UInt32) (acc workspace _ _ _ : UInt64) : Action :=
  .bind (write8 (workspace+1088+i.toUInt64) 0) fun s _ => .done s acc
private def copyKeyStep (i _ : UInt32) (acc key workspace _ _ : UInt64) : Action :=
  .bind (read8 (key+i.toUInt64)) fun s byte => if s = 0 then
  .bind (write8 (workspace+1088+i.toUInt64) byte) fun s _ => .done s acc else .done s 0
private def xorKeyStep (i _ : UInt32) (acc workspace pad _ _ : UInt64) : Action :=
  .bind (read8 (workspace+1088+i.toUInt64)) fun s byte => if s = 0 then
  .bind (write8 (workspace+1088+i.toUInt64) (byte ^^^ pad)) fun s _ => .done s acc else .done s 0
def «begin» (workspace key bytes : UInt64) : Action :=
  if validWorkspace workspace then if SHA256.validSpan key bytes then
  if SHA256.separate workspace workspaceBytes key bytes then
  if SHA256.maximumUpdate < bytes then .done SHA256.exhausted 0 else
  .bind (write64 (workspace+1200) 0) fun s _ => if s = 0 then
  .boundedFoldU64 64 clearKeyStep 64 0 workspace 0 0 0 fun s _ => if s = 0 then
  .bind (if 64 < bytes then SHA256.hash workspace key bytes (workspace+1088) else
    .boundedFoldU64 64 copyKeyStep bytes.toUInt32 0 key workspace 0 0 fun s _ => .done s 0)
    fun s _ => if s = 0 then
  .boundedFoldU64 64 xorKeyStep 64 0 workspace 0x36 0 0 fun s _ => if s = 0 then
  .bind (SHA256.«begin» workspace) fun s _ => if s = 0 then
  .bind (SHA256.update workspace (workspace+1088) 64) fun s _ => if s = 0 then
  write64 (workspace+1200) mode
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done SHA256.invalid 0 else .done SHA256.invalid 0 else .done SHA256.invalid 0
def update (workspace source bytes : UInt64) : Action :=
  if validWorkspace workspace then if SHA256.validSpan source bytes then
  if SHA256.separate workspace workspaceBytes source bytes then
  if SHA256.maximumUpdate < bytes then .done SHA256.exhausted 0 else
  .bind (read64 (workspace+1200)) fun s phase => if s = 0 then
  if phase = mode then SHA256.update workspace source bytes else .done SHA256.wrongState 0
  else .done s 0
  else .done SHA256.invalid 0 else .done SHA256.invalid 0 else .done SHA256.invalid 0
def finish (workspace output : UInt64) : Action :=
  if validWorkspace workspace then if SHA256.validSpan output 32 then
  if SHA256.separate workspace workspaceBytes output 32 then
  .bind (read64 (workspace+1200)) fun s phase => if s = 0 then
  if phase = mode then
  .bind (write64 (workspace+1200) 0) fun s _ => if s = 0 then
  .bind (SHA256.finish workspace (workspace+1024)) fun s _ => if s = 0 then
  -- The retained block currently contains K xor ipad. XOR6a converts it to
  -- K xor opad, including the zero-padded or hashed long-key suffix.
  .boundedFoldU64 64 xorKeyStep 64 0 workspace 0x6a 0 0 fun s _ => if s = 0 then
  .bind (SHA256.«begin» workspace) fun s _ => if s = 0 then
  .bind (SHA256.update workspace (workspace+1088) 64) fun s _ => if s = 0 then
  .bind (SHA256.update workspace (workspace+1024) 32) fun s _ => if s = 0 then
  SHA256.finish workspace output
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done SHA256.wrongState 0 else .done s 0
  else .done SHA256.invalid 0 else .done SHA256.invalid 0 else .done SHA256.invalid 0
def authenticate (workspace key keyBytes source bytes output : UInt64) : Action :=
  -- Admit every public span before changing private state. The inputs may
  -- alias one another, but may never alias this private workspace.
  if validWorkspace workspace then if SHA256.validSpan key keyBytes then
  if SHA256.validSpan source bytes then if SHA256.validSpan output 32 then
  if SHA256.separate workspace workspaceBytes key keyBytes then
  if SHA256.separate workspace workspaceBytes source bytes then
  if SHA256.separate workspace workspaceBytes output 32 then
  if SHA256.maximumUpdate < keyBytes then .done SHA256.exhausted 0 else
  if SHA256.maximumUpdate < bytes then .done SHA256.exhausted 0 else
  .bind («begin» workspace key keyBytes) fun s _ => if s = 0 then
  .bind (update workspace source bytes) fun s _ => if s = 0 then finish workspace output else .done s 0 else .done s 0
  else .done SHA256.invalid 0 else .done SHA256.invalid 0 else .done SHA256.invalid 0
  else .done SHA256.invalid 0 else .done SHA256.invalid 0 else .done SHA256.invalid 0 else .done SHA256.invalid 0
end Lemma.Crypto.HMAC256
