import Lemma.Boot.ProductExecuted
import Lemma.Crypto.HMAC256

/-! Product10-compatible, explicitly DEVELOPMENT-KEY image authentication.
The key below is public deterministic test material. It establishes executable
MAC enforcement, not production owner identity or anti-rollback security.
The MAC names the slot, exact validated header, loaded discovery bytes and
loaded file bytes in descriptor order. It therefore checks the bytes that
will execute, without a second-medium-read TOCTOU at handoff.
Tag sectors2/3 are separate from transactional metadata0/1 and payload8+.
No user document medium is accessible through this policy. -/
namespace Lemma.Boot.DevelopmentAuthentication
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access
open Lemma.Crypto
open ProductExecuted
def denied : UInt8 := 240
def tagMagic : UInt64 := 0x31474154414d454c
def tagVersion : UInt64 := 1
def keyId : UInt64 := 0x4445560000000001
def domainMagic : UInt64 := 0x31544855414d454c
def workspace : UInt64 := ProductExecuted.scratch+0x1800
def domain : UInt64 := ProductExecuted.scratch+0x1400
def keyBuffer : UInt64 := ProductExecuted.scratch+0x1500
def digest : UInt64 := ProductExecuted.scratch+0x1600
-- The PIO sector helper admits only the original16KiB ROM scratch span.
-- This512B slot is disjoint from payload+0x400, command+0x800,
-- header+0x1000 and both metadata pages; crypto occupies the unused+0x1800..+0x2000 span.
def tagBuffer : UInt64 := ProductExecuted.scratch+0xc00
private def zeroReserved (i _ : UInt32) (valid tag _ _ _ : UInt64) : Action :=
  .bind (read64 (tag+80+i.toUInt64*8)) fun s word => if s = 0 then
  .done 0 (if word = 0 then valid else 0) else .done s 0
/-- Structural validation only. This never returns authenticated authority. -/
def validateTag (tag slot identity : UInt64) : Action :=
  if slot < 2 then if identity = 0 then .done denied 0 else
  .bind (ProductExecuted.verifySector tag) fun s _ => if s = 0 then
  .bind (read64 tag) fun s magic => if s = 0 then
  .bind (read64 (tag+8)) fun s version => if s = 0 then
  .bind (read64 (tag+16)) fun s target => if s = 0 then
  .bind (read64 (tag+24)) fun s id => if s = 0 then
  .bind (read64 (tag+32)) fun s binding => if s = 0 then
  .bind (read64 (tag+40)) fun s key => if s = 0 then
  if magic = tagMagic then if version = tagVersion then if target = slot then
  if id = identity then if binding = ProductExecuted.compatibility then if key = keyId then
  .boundedFoldU64 53 zeroReserved 53 1 tag 0 0 0 fun s valid => if s = 0 then
  if valid = 1 then .done 0 0 else .done denied 0 else .done s 0
  else .done denied 0 else .done denied 0 else .done denied 0 else .done denied 0 else .done denied 0 else .done denied 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done denied 0
private def developmentKey : Action :=
  -- Public bytes00..1f. Production key provisioning is deliberately absent.
  .bind (write64 keyBuffer 0x0706050403020100) fun s _ => if s = 0 then
  .bind (write64 (keyBuffer+8) 0x0f0e0d0c0b0a0908) fun s _ => if s = 0 then
  .bind (write64 (keyBuffer+16) 0x1716151413121110) fun s _ => if s = 0 then
  write64 (keyBuffer+24) 0x1f1e1d1c1b1a1918 else .done s 0 else .done s 0 else .done s 0
private def hashRangeStep (i _ : UInt32) (acc base bytes _ _ : UInt64) : Action :=
  let offset := i.toUInt64*4096
  let count := if 4096 < bytes-offset then 4096 else bytes-offset
  .bind (HMAC256.update workspace (base+offset) count) fun s _ => .done s acc
private def hashRange (base bytes : UInt64) : Action :=
  -- Validated image spans are at most31MiB; this explicit guard also makes
  -- the addition and UInt32 loop-count conversion independently bounded.
  if bytes ≤ 0x1f00000 then
  .boundedFoldU64 8192 hashRangeStep ((bytes+4095)/4096).toUInt32 0 base bytes 0 0 fun s _ => .done s 0
  else .done denied 0
private def hashSegment (i _ : UInt32) (acc count _ _ _ : UInt64) : Action :=
  if i.toUInt64 < count then
  let descriptor := ProductExecuted.headerBuffer+64+i.toUInt64*40
  .bind (read64 (descriptor+8)) fun s bytes => if s = 0 then
  .bind (read64 (descriptor+24)) fun s destination => if s = 0 then
  .bind (hashRange destination bytes) fun s _ => .done s acc else .done s 0 else .done s 0
  else .done 0 acc
private def compareDigest (i _ : UInt32) (different _ _ _ _ : UInt64) : Action :=
  .bind (read64 (digest+i.toUInt64*8)) fun s actual => if s = 0 then
  .bind (read64 (tagBuffer+48+i.toUInt64*8)) fun s expected => if s = 0 then
  .done 0 (different ||| (actual ^^^ expected)) else .done s 0 else .done s 0
/-- Called only immediately after this ROM loaded the candidate. Header and
payload RAM are private, validated and outside the ROM scratch/stack spans.
No target instruction from the image executes before this function succeeds. -/
def verifyLoaded (slot identity : UInt64) : Action :=
  .bind (ProductExecuted.validateImageHeader ProductExecuted.headerBuffer identity) fun s entry => if s = 0 then
  .bind (ProductExecuted.readSector (2+slot) tagBuffer) fun s _ => if s = 0 then
  .bind (validateTag tagBuffer slot identity) fun s _ => if s = 0 then
  .bind developmentKey fun s _ => if s = 0 then
  .bind (write64 domain domainMagic) fun s _ => if s = 0 then
  .bind (write64 (domain+8) tagVersion) fun s _ => if s = 0 then
  .bind (write64 (domain+16) keyId) fun s _ => if s = 0 then
  .bind (write64 (domain+24) slot) fun s _ => if s = 0 then
  .bind (HMAC256.«begin» workspace keyBuffer 32) fun s _ => if s = 0 then
  .bind (HMAC256.update workspace domain 32) fun s _ => if s = 0 then
  .bind (HMAC256.update workspace ProductExecuted.headerBuffer 512) fun s _ => if s = 0 then
  .bind (read64 (ProductExecuted.headerBuffer+48)) fun s discoveryBytes => if s = 0 then
  .bind (hashRange ProductExecuted.discoveryBase discoveryBytes) fun s _ => if s = 0 then
  .bind (read64 (ProductExecuted.headerBuffer+32)) fun s segments => if s = 0 then
  .boundedFoldU64 8 hashSegment 8 0 segments 0 0 0 fun s _ => if s = 0 then
  .bind (HMAC256.finish workspace digest) fun s _ => if s = 0 then
  .boundedFoldU64 4 compareDigest 4 0 0 0 0 0 fun s different => if s = 0 then
  if different = 0 then .done 0 entry else .done denied 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
def load (slot identity : UInt64) : Action :=
  .bind (ProductExecuted.loadImage slot identity) fun s expectedEntry => if s = 0 then
  .bind (verifyLoaded slot identity) fun s entry => if s = 0 then
  if entry = expectedEntry then .done 0 entry else .done denied 0 else .done s 0 else .done s 0
private def publishContext (slot identity generation entry : UInt64) : Action :=
  .bind (write64 ProductExecuted.scratch ProductExecuted.contextMagic) fun s _ => if s = 0 then
  .bind (write64 (ProductExecuted.scratch+8) 1) fun s _ => if s = 0 then
  .bind (write64 (ProductExecuted.scratch+16) slot) fun s _ => if s = 0 then
  .bind (write64 (ProductExecuted.scratch+24) identity) fun s _ => if s = 0 then
  .bind (write64 (ProductExecuted.scratch+32) generation) fun s _ => if s = 0 then
  .bind (write64 (ProductExecuted.scratch+40) 0) fun s _ => .done s entry
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def confirmed (metadata : UInt64) : Action :=
  .bind (ProductExecuted.validateMetadata metadata) fun s _ => if s = 0 then
  .bind (read64 (metadata+16)) fun s generation => if s = 0 then
  .bind (read64 (metadata+24)) fun s slot => if s = 0 then
  .bind (read64 (metadata+32)) fun s identity => if s = 0 then
  .bind (load slot identity) fun s entry => if s = 0 then
  publishContext slot identity generation entry else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def fallback : Action :=
  .bind ProductExecuted.selectedMetadata fun s selected => if s = 0 then
  if selected < 2 then
  .bind (confirmed (if selected = 0 then ProductExecuted.metadata0Buffer else ProductExecuted.metadata1Buffer)) fun s entry =>
  if s = 0 then .done 0 entry else
  confirmed (if selected = 0 then ProductExecuted.metadata1Buffer else ProductExecuted.metadata0Buffer)
  else .done denied 0 else .done s 0
def boot : Action :=
  -- The old transactional selection/attempt policy may load a candidate but
  -- cannot hand off here. Both the chosen image and any fallback require MAC.
  .bind ProductExecuted.boot fun s expectedEntry => if s = 0 then
  .bind (read64 (ProductExecuted.scratch+16)) fun s slot => if s = 0 then
  .bind (read64 (ProductExecuted.scratch+24)) fun s identity => if s = 0 then
  .bind (verifyLoaded slot identity) fun s entry => if s = 0 then
  if entry = expectedEntry then .done 0 entry else fallback else fallback
  else .done s 0 else .done s 0 else .done s 0
end Lemma.Boot.DevelopmentAuthentication
