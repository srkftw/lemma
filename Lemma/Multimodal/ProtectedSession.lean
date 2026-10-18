import Lemma.Crypto.AEAD
import Lemma.Crypto.HKDF256

/-! Bounded authenticated companion packet admission, lemma-protected/1.
Owner-controlled PSK provisioning/authenticated hello and fresh32byte entropy
on each endpoint precede HKDF directional-key derivation. This module validates
received authenticated AAD only after AEAD; it does not elevate simulator entropy
to qualified physical entropy. No live session may resume snapshot-era keys.
The integration must copy immutable headers to private pinned memory and bind
ciphertext lengths before calling the cryptographic primitive. -/
namespace Lemma.Multimodal.ProtectedSession
private def different (a b : UInt64) : Bool := if a = b then false else true

def version : UInt64 := 1
def maximumPayload : UInt64 := 4096
def maximumSequence : UInt64 := 0xfffffffffffffffe
/-- Channels0control,1document,2interactive audio,3optional archive. These are
priority classes, never a grant. Per-stream and packet sequences are separate.
Strict consecutive frames let bounded queues detect duplicates and known gaps. -/
def receiveReason (boot capture external stream channel sequence streamSequence consent length
    currentBoot currentCapture currentExternal expectedPacket expectedStream currentConsent archiveGranted : UInt64) : UInt64 :=
  if different (boot) (currentBoot) = true then 1 else if different (capture) (currentCapture) = true then 2 else
  if different (external) (currentExternal) = true then 3 else if different (consent) (currentConsent) = true then 4 else
  if 31 < stream then 5 else if 3 < channel then 6 else
  if sequence = 0 then 7 else if maximumSequence < sequence then 8 else
  if streamSequence = 0 then 7 else if maximumSequence < streamSequence then 8 else
  if different (sequence) (expectedPacket) = true then 9 else if different (streamSequence) (expectedStream) = true then 10 else
  if maximumPayload < length then 11 else if channel = 3 then if archiveGranted = 0 then 12 else 0 else 0

/-- Must be checked before creating a live session or enabling raw transmission.
Mode1 is explicit synthetic development. Mode2 needs owner trust and live entropy;
there is no fallback public key, deterministic seed or snapshot credential. -/
def establishReason (mode ownerTrust entropyFresh localRandomBytes peerRandomBytes helloAuthenticated : UInt64) : UInt64 :=
  if mode = 1 then if helloAuthenticated = 1 then 0 else 4 else
  if different (mode) (2) = true then 1 else if different (ownerTrust) (1) = true then 2 else if different (entropyFresh) (1) = true then 3 else
  if different (localRandomBytes) (32) = true then 3 else if different (peerRandomBytes) (32) = true then 3 else
  if different (helloAuthenticated) (1) = true then 4 else 0

/-- An exact sealed continuation is isolated from live sinks. Every live
restore must negotiate new directional keys, interaction epoch, grants and
output leases. Advancing merely a nonce counter inside an old snapshot is
insufficient: its post-snapshot use is unknown. -/
def restoreReason (sealed livePeerConnected newExternal oldExternal keysFresh consentFresh leasesFresh : UInt64) : UInt64 :=
  if sealed = 1 then if livePeerConnected = 0 then 0 else 1 else
  if newExternal ≤ oldExternal then 2 else if maximumSequence < newExternal then 3 else
  if different (keysFresh) (1) = true then 4 else if different (consentFresh) (1) = true then 5 else if different (leasesFresh) (1) = true then 6 else 0

end Lemma.Multimodal.ProtectedSession
