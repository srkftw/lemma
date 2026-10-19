import Lemma.User.Memory

/-! Untrusted companion action admission. Returns a reason, never a mathematical
verdict. Explicit context supplied by the guest owns grants, viewport, revision,
clock and completion frontier; companion fields cannot grant themselves rights.
Keep this small packet in copied IPC; referenced PCM/text use checked bulk pages.
Claim class0 declares no formal claim; class1 requests checking and remains
unverified/pending. Other classes, including a purported checked class2, reject. -/
namespace Lemma.Multimodal.TutorAction
private def different (a b : UInt64) : Bool := if a = b then false else true
open Lemma.Core0.Memory Lemma.User

def version : UInt64 := 2
def proposalBytes : UInt64 := 192
/-- Action packet words: version,session,consent,revision,object,sequence,
cutoff,start,deadline,requiredPermissions,kind,modality,claimKind,textBytes,
pcmFrames,policy,model,source,edition,task,interruption,reserved[3].
Context: session,consent,revision,object,lastCompleted,grants,source,edition,task,
maximumTextBytes,maximumPCMFrames. Reads never acknowledge or mutate events. -/
def reason (session consent revision object sequence cutoff start deadline required kind modality
    currentSession currentConsent currentRevision currentObject lastCompleted grants now : UInt64) : UInt64 :=
  if different (session) (currentSession) = true then 1 else if different (consent) (currentConsent) = true then 2 else
  if different (revision) (currentRevision) = true then 3 else if different (object) (currentObject) = true then 4 else
  if sequence = 0 then 5 else if sequence ≤ lastCompleted then 5 else
  if 0xfffffffffffffffe < sequence then 6 else
  if now < cutoff then 7 else if deadline < start then 8 else if deadline < now then 8 else
  if different ((grants &&& required)) (required) = true then 9 else
  if different ((required &&& modality)) (modality) = true then 9 else
  if 8 < kind then 10 else if 3 < modality then 11 else 0

private def same (proposal context po co : UInt64) : Action :=
  .bind (Memory.read64 (proposal+po)) fun s a => if s = 0 then
  .bind (Memory.read64 (context+co)) fun s b => if s = 0 then
  if a = b then .done 0 0 else .done 0 12 else .done s 0 else .done s 0

def validateVersion (proposal context now expectedVersion : UInt64) : Action :=
  .bind (Memory.read64 proposal) fun s v => if s = 0 then
  if different (v) (expectedVersion) = true then .done 0 13 else
  .bind (Memory.read64 (proposal+8)) fun s session => if s = 0 then
  .bind (Memory.read64 (proposal+16)) fun s consent => if s = 0 then
  .bind (Memory.read64 (proposal+24)) fun s revision => if s = 0 then
  .bind (Memory.read64 (proposal+32)) fun s object => if s = 0 then
  .bind (Memory.read64 (proposal+40)) fun s sequence => if s = 0 then
  .bind (Memory.read64 (proposal+48)) fun s cutoff => if s = 0 then
  .bind (Memory.read64 (proposal+56)) fun s start => if s = 0 then
  .bind (Memory.read64 (proposal+64)) fun s deadline => if s = 0 then
  .bind (Memory.read64 (proposal+72)) fun s required => if s = 0 then
  .bind (Memory.read64 (proposal+80)) fun s kind => if s = 0 then
  .bind (Memory.read64 (proposal+88)) fun s modality => if s = 0 then
  .bind (Memory.read64 context) fun s currentSession => if s = 0 then
  .bind (Memory.read64 (context+8)) fun s currentConsent => if s = 0 then
  .bind (Memory.read64 (context+16)) fun s currentRevision => if s = 0 then
  .bind (Memory.read64 (context+24)) fun s currentObject => if s = 0 then
  .bind (Memory.read64 (context+32)) fun s completed => if s = 0 then
  .bind (Memory.read64 (context+40)) fun s grants => if s = 0 then
  let outcome := reason session consent revision object sequence cutoff start deadline required kind modality
    currentSession currentConsent currentRevision currentObject completed grants now
  if different (outcome) (0) = true then .done 0 outcome else
  .bind (same proposal context 136 48) fun s mismatch => if s = 0 then if mismatch = 0 then
  .bind (same proposal context 144 56) fun s mismatch => if s = 0 then if mismatch = 0 then
  .bind (same proposal context 152 64) fun s mismatch => if s = 0 then if mismatch = 0 then
  .bind (Memory.read64 (proposal+96)) fun s claims => if s = 0 then
  if 1 < claims then .done 0 14 else
  .bind (Memory.read64 (proposal+104)) fun s textBytes => if s = 0 then
  .bind (Memory.read64 (context+72)) fun s maxText => if s = 0 then
  .bind (Memory.read64 (proposal+112)) fun s pcmFrames => if s = 0 then
  .bind (Memory.read64 (context+80)) fun s maxPCM => if s = 0 then
  if maxText < textBytes then .done 0 15 else if maxPCM < pcmFrames then .done 0 15 else
  .bind (Memory.read64 (proposal+160)) fun s interruption => if s = 0 then
  if different (interruption) (1) = true then .done 0 16 else
  .bind (Memory.read64 (proposal+168)) fun s r0 => if s = 0 then
  .bind (Memory.read64 (proposal+176)) fun s r1 => if s = 0 then
  .bind (Memory.read64 (proposal+184)) fun s r2 => if s = 0 then
  if different (r0) (0) = true then .done 0 17 else if different (r1) (0) = true then .done 0 17 else if different (r2) (0) = true then .done 0 17 else
  .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 0 mismatch else .done s 0 else .done 0 mismatch else .done s 0
  else .done 0 mismatch else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

/-- Historical v2 semantics and reserved-zero fields remain unchanged. The
school v3 envelope separately checks its appended binding after these fields. -/
def validate (proposal context now : UInt64) : Action :=
  validateVersion proposal context now version

/-- A receipt reports digital samples, not audibility. Cancel cannot undo an
already consumed prefix. Invalid sink claims are rejected rather than clamped. -/
def delivery (submitted consumed cancelled sinkPending : UInt64) : UInt64 :=
  if submitted < consumed then 5 else if submitted-consumed < sinkPending then 5 else
  if different (cancelled) (0) = true then if consumed = 0 then 3 else 4 else
  if consumed = submitted then 2 else if consumed = 0 then 0 else 1
end Lemma.Multimodal.TutorAction
