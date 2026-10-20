import Lemma.User.Capability
import Lemma.User.Memory
import Lemma.User.CapabilityConsole

/-! Transient converter diagnostic window for Notebook21. No upload, retention,
research or training bit is requested. A deliberate local tap grants at most
five seconds. The normal workbook starts with every modality refused. -/
namespace Lemma.User.Multimodal

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true
open Lemma.Core0.Memory
open Lemma.User

def records : UInt64 := 0x340000
/-- One explicitly allocated page: samples[0,512), tutor context[1024,1112),
tutor proposal[1536,1792), school context[1152,1256), JOIN packet[1792,1896),
state[2048,2304), config packet[2304,2368).
State+40 selects the next acquisition endpoint fairly; +48/+56 retain one
logical pending record-DMA stream/epoch. Kernel-owned DMA memory is never mapped
into this page. The pending operation is cleaned even after collection stops.
The Notebook uses state+160 for one transient ASK/LOAD/JOIN/chooser-LOAD intent,
+168 for an explicit pending JOIN read and+176/+184/+192 for the queued chooser
page/request identity/edition. Legacy tutor action v2 remains192bytes.
The original BSS20d00..20f20 remains owned by ControlBacklog. -/
def state : UInt64 := records + 2048
def packet : UInt64 := records + 2304
private def get (offset : UInt64) : Action := Memory.read64 (state + offset)
private def put (offset value : UInt64) : Action := Memory.write64 (state + offset) value
private def field (offset value : UInt64) : Action := Memory.write64 (packet + offset) value
private def invoke (operation stream pointer epoch : UInt64) : Action :=
  .bind (get 0) fun s cap => if mmFailed s = true then .done s 0 else Syscall.call 69 cap operation stream pointer epoch
private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

def «initialize» (console : UInt64) : Action :=
  .bind (Syscall.allocatePage records) fun s address => if mmFailed s = true then .done s 0 else
  if mmDifferent address records = true then .done 95 0 else
  .boundedFoldU64 32 clearStep 32 0 0 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Memory.write64 (records + 1152) 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 4) fun s cap => if mmFailed s = true then .done s 0 else
  .bind (put 0 cap) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 8 console) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 0 0 0 0) fun s features => if mmFailed s = true then .done s 0 else
  .bind (invoke 18 0 0 0) fun s version => if mmFailed s = true then .done s 0 else
  if (if version = 2 then true else if version = 3 then true else false) = false then .done 15 0 else
  .bind (put 136 version) fun s _ => if mmFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x710 features version 0 0

private def startStep (i _ : UInt32) (acc expiry _ _ _ : UInt64) : Action :=
  let stream := i.toUInt64
  .bind (invoke 11 stream 0 0) fun s previous => if mmFailed s = true then .done s 0 else
  .bind (field 0 0x31474d4d) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 8 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 16 3) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 24 100) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 32 32768) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 40 expiry) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 48 previous) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 56 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 2 stream packet 0) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (put (64 + stream * 8) epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 0 2) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 8 1000000) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 16 4) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 24 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 3 stream packet epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 4 stream 0 epoch) fun s _ => .done s (acc + 1)

private def revokeStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (invoke 6 i.toUInt64 0 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put (64 + i.toUInt64 * 8) 0) fun s _ => .done s (acc + 1)

private def wipeStep (i _ : UInt32) (acc stream _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (records + stream * 64 + i.toUInt64 * 8) 0) fun s _ => .done s acc
private def wipe (stream : UInt64) : Action :=
  .boundedFoldU64 8 wipeStep 8 0 stream 0 0 0 fun s _ => .done s 0
private def wipeAllStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (wipe i.toUInt64) fun s _ => .done s acc

/-- Lazily allocated only after the explicit local AUDIO TEST control. It is
not a retained document or transmission buffer. A test has one bounded packet;
accepted samples and the independently observed consumed prefix remain distinct. -/
private def audioPage : UInt64 := 0x360000
private def audioGet (offset : UInt64) : Action := Memory.read64 (audioPage + offset)
private def audioPut (offset value : UInt64) : Action := Memory.write64 (audioPage + offset) value

private def audioReceipt (reason : UInt64) : Action :=
  .bind (audioGet 56) fun s sequence => if mmFailed s = true then .done s 0 else
  .bind (audioGet 16) fun s submitted => if mmFailed s = true then .done s 0 else
  .bind (audioGet 32) fun s consumed => if mmFailed s = true then .done s 0 else
  .bind (audioPut 0 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x716 sequence submitted consumed reason

/-- Ring packets occupy audioPage+128..1184. Separate metadata at+3584 keeps
both the legacy packet and all accepted/fetched/submitted/consumed frontiers. -/
private def ringGet (offset : UInt64) : Action := Memory.read64 (audioPage + 3584 + offset)
private def ringPut (offset value : UInt64) : Action := Memory.write64 (audioPage + 3584 + offset) value
private def ringField (offset value : UInt64) : Action := Memory.write64 (audioPage + 128 + offset) value

def beginOwnedPCM (pointer epoch : UInt64) : Action := invoke 19 8 pointer epoch
def enqueueOwnedPCM (pointer epoch : UInt64) : Action := invoke 20 8 pointer epoch
def finishOwnedPCM (producer epoch : UInt64) : Action := invoke 21 8 producer epoch
/-- Raw owned controller observations, including after revocation. None grants
playback or turns accepted bytes into a presentation acknowledgement. -/
def statusOwnedPCM (selector epoch : UInt64) : Action := invoke 22 8 selector epoch

private def observeRing : Action :=
  .bind (audioGet 8) fun s epoch => if mmFailed s = true then .done s 0 else
  -- These are separate advancing controller observations. Read the downstream
  -- frontier first: earlier consumed <= later submitted <= later fetched <=
  -- later accepted. The opposite read order falsely rejects valid playback.
  .bind (statusOwnedPCM 4 epoch) fun s consumed => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 3 epoch) fun s submitted => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 2 epoch) fun s fetched => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 1 epoch) fun s accepted => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 5 epoch) fun s gaps => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 6 epoch) fun s held => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 0 epoch) fun s mode => if mmFailed s = true then .done s 0 else
  .bind (ringGet 16) fun s submittedBase => if mmFailed s = true then .done s 0 else
  .bind (ringGet 24) fun s consumedBase => if mmFailed s = true then .done s 0 else
  if submitted < submittedBase then .done 4 0 else if consumed < consumedBase then .done 4 0 else
  if accepted < fetched then .done 4 0 else if fetched < submitted - submittedBase then .done 4 0 else
  if submitted - submittedBase < consumed - consumedBase then .done 4 0 else
  .bind (ringPut 0 accepted) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 8 fetched) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 16 (submitted - submittedBase)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 32 (consumed - consumedBase)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 48 gaps) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 56 held) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 72 mode) fun s _ => .done s (consumed - consumedBase)

private def ringReceipt (reason : UInt64) : Action :=
  .bind (audioGet 56) fun s sequence => if mmFailed s = true then .done s 0 else
  .bind (audioGet 32) fun s consumed => if mmFailed s = true then .done s 0 else
  .bind (ringGet 48) fun s gaps => if mmFailed s = true then .done s 0 else
  .bind (ringGet 56) fun s held => if mmFailed s = true then .done s 0 else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x718 sequence consumed gaps held) fun s _ =>
  if mmFailed s = true then .done s 0 else audioReceipt reason

private def stopRing (reason force : UInt64) : Action :=
  .bind (audioGet 8) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (invoke 11 8 0 0) fun status current =>
  if mmFailed status = true then .done status 0 else
  if mmDifferent current epoch = true then
    if force = 1 then .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else ringReceipt reason
    else ringReceipt 4
  else
  .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind observeRing fun _ _ => ringReceipt reason

/-- A background completion may stop only its own epoch. Explicit MUTE may
revoke any current local output grant. A superseded test retains its last known
prefix; it never attributes the successor grant's samples to the old packet. -/
private def stopAudio (reason force : UInt64) : Action :=
  .bind (get 128) fun s allocated => if mmFailed s = true then .done s 0 else
  if allocated = 0 then if force = 1 then invoke 6 8 0 0 else .done 0 0 else
  .bind (audioGet 0) fun s running => if mmFailed s = true then .done s 0 else
  if running = 0 then if force = 1 then invoke 6 8 0 0 else .done 0 0 else
  if running = 2 then stopRing reason force else
  .bind (audioGet 8) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (invoke 11 8 0 0) fun status current =>
  if mmFailed status = true then
    if force = 1 then .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else audioReceipt reason
    else .done status 0
  else if mmDifferent (current) (epoch) = true then
    if force = 1 then .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else audioReceipt reason
    else audioReceipt 4
  else
  .bind (invoke 15 8 0 0) fun status counter =>
  .bind (if mmFailed status = true then .done 0 0 else
    .bind (audioGet 24) fun s baseline => if mmFailed s = true then .done s 0 else
    if counter < baseline then .done 0 0 else
    let observed := counter - baseline
    audioPut 32 (if 16 < observed then 16 else observed)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else audioReceipt reason

def revokeAll : Action :=
  .bind (stopAudio 1 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 16 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 32 1) fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 9 revokeStep 9 0 0 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 8 wipeAllStep 8 0 0 0 0 0 fun s _ => .done s 0

def control (operation : UInt64) : Action :=
  if operation = 1 then
    .bind (stopAudio 1 1) fun s _ => if mmFailed s = true then .done s 0 else put 32 1
  else
  if operation = 2 then
    .bind (invoke 6 0 0 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (put 64 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (put 32 1) fun s _ => if mmFailed s = true then .done s 0 else wipe 0
  else
  .bind (get 16) fun s enabled => if mmFailed s = true then .done s 0 else
  if enabled = 1 then revokeAll else
  .bind (invoke 10 0 0 0) fun s ticks => if mmFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe - 500000000 < ticks then .done 14 0 else
  .bind (put 24 (ticks + 500000000)) fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 8 startStep 8 0 (ticks + 500000000) 0 0 0 fun s _ =>
  if mmFailed s = true then .bind revokeAll fun _ _ => .done s 0 else
  .bind (put 16 1) fun s _ => if mmFailed s = true then .done s 0 else put 32 1

private def sampleFailure (stream status epoch : UInt64) : Action :=
  .bind (invoke 6 stream 0 0) fun _ _ =>
  .bind (put (64 + stream * 8) 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (wipe stream) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x713 stream status epoch 0

private def finishSample : Action :=
  .bind (get 48) fun s pending => if mmFailed s = true then .done s 0 else
  if pending = 0 then .done 0 0 else
  if 8 < pending then .done 2 0 else
  let stream := pending - 1
  .bind (get 56) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (invoke 13 stream (records + stream * 64) epoch) fun status sequence =>
  if status = 6 then .done 0 0 else
  .bind (put 48 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 56 0) fun s _ => if mmFailed s = true then .done s 0 else
  if mmFailed status = true then sampleFailure stream status.toUInt64 epoch else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  .bind (Memory.read64 (records + stream * 64 + 8)) fun s capture => if mmFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x711 stream sequence 1 capture) fun s _ => .done s 1

private def sampleStep (i _ : UInt32) (acc cursor _ _ _ : UInt64) : Action :=
  .bind (get 48) fun s pending => if mmFailed s = true then .done s 0 else
  if mmDifferent (pending) (0) = true then .done 0 acc else
  let stream := (cursor + i.toUInt64) % 8
  .bind (get (64 + stream * 8)) fun s epoch => if mmFailed s = true then .done s 0 else
  if epoch = 0 then .done 0 acc else
  .bind (invoke 12 stream (records + stream * 64) epoch) fun status _ =>
  if status = 6 then .done 0 acc else
  if mmFailed status = true then .bind (sampleFailure stream status.toUInt64 epoch) fun s _ => .done s acc else
  .bind (put 48 (stream + 1)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 56 epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 40 ((stream + 1) % 8)) fun s _ => .done s acc

/-- Poll one completed owned record per turn and fairly begin at most one
successor. There is no busy wait. Revocation keeps polling only to reclaim the
private transfer; a revoked completion cannot be copied into application RAM. -/
private def pumpAcquisition : Action :=
  .bind finishSample fun s completed => if mmFailed s = true then .done s 0 else
  .bind (get 16) fun s enabled => if mmFailed s = true then .done s 0 else
  if enabled = 0 then .done 0 completed else
  .bind (invoke 10 0 0 0) fun s ticks => if mmFailed s = true then .done s 0 else
  .bind (get 24) fun s expiry => if mmFailed s = true then .done s 0 else
  if expiry ≤ ticks then revokeAll else
  .bind (get 40) fun s cursor => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 8 sampleStep 8 completed cursor 0 0 0 fun s count => .done s count

/-- Explicit local output permission. Arm first so an extension can prefill
its bounded samples before the first playback deadline. The existing MUTE
control revokes this grant; acquisition permissions are unaffected. -/
def armPCM (session rate extent expiry gain period : UInt64) : Action :=
  .bind (invoke 11 8 0 0) fun s previous => if mmFailed s = true then .done s 0 else
  .bind (field 0 0x31474d4d) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 8 session) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 16 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 24 rate) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 32 extent) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 40 expiry) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 48 previous) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 56 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 2 8 packet 0) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (field 0 gain) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 8 period) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 16 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 24 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 3 8 packet epoch) fun status _ =>
  if mmFailed status = true then .bind (invoke 6 8 0 0) fun _ _ => .done status 0 else
  .bind (invoke 16 8 0 epoch) fun status _ =>
  if mmFailed status = true then .bind (invoke 6 8 0 0) fun _ _ => .done status 0 else .done 0 epoch

def startPCM (epoch : UInt64) : Action := invoke 17 8 0 epoch

/-- An extension passes a version1 S16_LE packet from its own mapped memory.
The returned accepted count is separate from consumed PCM and never a claim of
physical audibility. Local control1 revokes output immediately. -/
def submitPCM (pointer epoch : UInt64) : Action := invoke 14 8 pointer epoch
/-- Raw machine counter only: callers must retain their own grant/packet
baselines and actual completion before deriving any presentation receipt. -/
def consumedPCM : Action := invoke 15 8 0 0

/-- An explicit digital-controller self-test, not a continuous-audio or
physical-audibility claim: sixteen arbitrary signed16 samples at16kHz. The
controller budget is128 bytes (16×8); the packet carries32 payload bytes. -/
private def testLegacyAudio : Action :=
  .bind (get 128) fun s allocated => if mmFailed s = true then .done s 0 else
  .bind (if allocated = 0 then
    .bind (Syscall.allocatePage audioPage) fun s address => if mmFailed s = true then .done s 0 else
    if mmDifferent (address) (audioPage) = true then .done 95 0 else
    .bind (audioPut 0 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 56 0) fun s _ => if mmFailed s = true then .done s 0 else put 128 1
    else .done 0 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioGet 0) fun s running => if mmFailed s = true then .done s 0 else
  if mmDifferent (running) (0) = true then .done 6 0 else
  .bind (audioGet 56) fun s previous => if mmFailed s = true then .done s 0 else
  if previous = 0xffffffffffffffff then .done 14 0 else
  .bind (invoke 10 0 0 0) fun s ticks => if mmFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe - 100000000 < ticks then .done 14 0 else
  .bind (armPCM 1 16000 128 (ticks + 100000000) 1 6250) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (invoke 15 8 0 0) fun status baseline =>
  if mmFailed status = true then .bind (invoke 6 8 0 0) fun _ _ => .done status 0 else
  if 0xffffffffffffffff - 16 < baseline then .bind (invoke 6 8 0 0) fun _ _ => .done 14 0 else
  .bind (audioPut 8 epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 16 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 24 baseline) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 32 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 40 (ticks + 100000000)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 56 (previous+1)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 0 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind audioPacket fun status _ =>
  if mmFailed status = true then .bind (stopAudio 3 0) fun _ _ => .done status 0 else
  .bind (submitPCM (audioPage+64) epoch) fun status accepted =>
  .bind (audioPut 16 accepted) fun s _ => if mmFailed s = true then .done s 0 else
  if mmFailed status = true then .bind (stopAudio 3 0) fun _ _ => .done status 0 else
  if mmDifferent (accepted) (16) = true then .bind (stopAudio 3 0) fun _ _ => .done 6 accepted else
  .bind (startPCM epoch) fun status _ =>
  if mmFailed status = true then .bind (stopAudio 3 0) fun _ _ => .done status 0 else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x715 (previous+1) epoch 16 6250
where
  audioPacket : Action :=
    .bind (audioPut 64 0x31424350) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 72 1) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 80 16) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 88 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 96 0x26a01d9010000000) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 104 0x10001d9026a02a00) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 112 0xd960e270f0000000) fun s _ => if mmFailed s = true then .done s 0 else
    audioPut 120 0xf000e270d960d600

private def pumpLegacyAudio : Action :=
  .bind (get 128) fun s allocated => if mmFailed s = true then .done s 0 else
  if allocated = 0 then .done 0 0 else
  .bind (audioGet 0) fun s running => if mmFailed s = true then .done s 0 else
  if running = 0 then .done 0 0 else
  .bind (audioGet 8) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (invoke 11 8 0 0) fun status current =>
  if mmFailed status = true then stopAudio 3 0 else
  if mmDifferent (current) (epoch) = true then audioReceipt 4 else
  .bind (invoke 15 8 0 0) fun status counter =>
  if mmFailed status = true then stopAudio 3 0 else
  .bind (audioGet 24) fun s baseline => if mmFailed s = true then .done s 0 else
  if counter < baseline then stopAudio 3 0 else
  let observed := counter - baseline
  .bind (audioPut 32 (if 16 < observed then 16 else observed)) fun s _ => if mmFailed s = true then .done s 0 else
  if 16 ≤ observed then stopAudio 0 0 else
  .bind (invoke 10 0 0 0) fun status ticks =>
  if mmFailed status = true then stopAudio 3 0 else
  .bind (audioGet 40) fun s expiry => if mmFailed s = true then .done s 0 else
  if expiry ≤ ticks then stopAudio 2 0 else .done 0 observed

private def ringWave (index : UInt64) : UInt64 := (index * 7919 + 311) &&& 65535
private def ringWaveStep (i _ : UInt32) (acc producer _ _ _ : UInt64) : Action :=
  let n := producer + i.toUInt64 * 4
  let packed := ringWave n ||| (ringWave (n + 1) <<< 16) |||
    (ringWave (n + 2) <<< 32) ||| (ringWave (n + 3) <<< 48)
  .bind (ringField (32 + i.toUInt64 * 8) packed) fun s _ => .done s acc

/-- Refill one bounded packet per turn. Backpressure preserves the next sample
index; it never substitutes silence, drops a sample, or busy-waits. -/
private def refillRing : Action :=
  .bind (audioGet 8) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (ringGet 0) fun s producer => if mmFailed s = true then .done s 0 else
  .bind (ringGet 32) fun s total => if mmFailed s = true then .done s 0 else
  if total ≤ producer then .done 0 producer else
  .bind (statusOwnedPCM 2 epoch) fun s fetched => if mmFailed s = true then .done s 0 else
  if producer < fetched then .done 4 0 else if 2048 < producer - fetched then .done 4 0 else
  let count := if 512 < total - producer then 512 else total - producer
  if 2048 - (producer - fetched) < count then .done 0 producer else
  .bind (ringField 0 0x32424350) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringField 8 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringField 16 count) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringField 24 producer) fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 128 ringWaveStep ((count + 3) / 4).toUInt32 0 producer 0 0 0 fun s _ =>
  if mmFailed s = true then .done s 0 else
  .bind (enqueueOwnedPCM (audioPage + 128) epoch) fun status next =>
  if status = 6 then .done 0 producer else if mmFailed status = true then .done status 0 else
  if mmDifferent next (producer + count) = true then .done 4 0 else
  .bind (ringPut 0 next) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 2 epoch) fun s fetched => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 3 epoch) fun s submitted => if mmFailed s = true then .done s 0 else
  .bind (ringGet 16) fun s baseline => if mmFailed s = true then .done s 0 else
  if submitted < baseline then .done 4 0 else
  .bind (audioGet 56) fun s sequence => if mmFailed s = true then .done s 0 else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x717 sequence next fetched (submitted - baseline)) fun s _ => .done s next

private def prefillRingStep (_ _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind refillRing fun s _ => .done s acc

private def testRingAudio : Action :=
  .bind (get 128) fun s allocated => if mmFailed s = true then .done s 0 else
  .bind (if allocated = 0 then
    .bind (Syscall.allocatePage audioPage) fun s address => if mmFailed s = true then .done s 0 else
    if mmDifferent address audioPage = true then .done 95 0 else
    .bind (audioPut 0 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (audioPut 56 0) fun s _ => if mmFailed s = true then .done s 0 else put 128 1
    else .done 0 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioGet 0) fun s running => if mmFailed s = true then .done s 0 else
  if mmDifferent running 0 = true then .done 6 0 else
  .bind (audioGet 56) fun s previous => if mmFailed s = true then .done s 0 else
  if previous = 0xffffffffffffffff then .done 14 0 else
  .bind (invoke 10 0 0 0) fun s ticks => if mmFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe - 500000000 < ticks then .done 14 0 else
  .bind (armPCM 1 16000 (4099 * 8) (ticks + 500000000) 1 6250) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (invoke 15 8 0 0) fun status consumedBase =>
  if mmFailed status = true then .bind (invoke 6 8 0 0) fun _ _ => .done status 0 else
  if 0xffffffffffffffff - 4099 < consumedBase then .bind (invoke 6 8 0 0) fun _ _ => .done 14 0 else
  .bind (ringField 0 0x32474e52) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringField 8 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringField 16 2048) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringField 24 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (beginOwnedPCM (audioPage + 128) epoch) fun status _ =>
  if mmFailed status = true then .bind (invoke 6 8 0 0) fun _ _ => .done status 0 else
  .bind (statusOwnedPCM 3 epoch) fun s submittedBase => if mmFailed s = true then .done s 0 else
  .bind (audioPut 8 epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 16 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 24 consumedBase) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 32 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 40 (ticks + 500000000)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 56 (previous + 1)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 0 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 8 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 16 submittedBase) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 24 consumedBase) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 32 4099) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 40 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 48 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringPut 56 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (audioPut 0 2) fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 4 prefillRingStep 4 0 0 0 0 0 fun status _ =>
  if mmFailed status = true then .bind (stopRing 3 0) fun _ _ => .done status 0 else
  .bind (startPCM epoch) fun status _ =>
  if mmFailed status = true then .bind (stopRing 3 0) fun _ _ => .done status 0 else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x715 (previous + 1) epoch 4099 6250

private def pumpRingAudio : Action :=
  .bind (audioGet 8) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (invoke 11 8 0 0) fun status current =>
  if mmFailed status = true then .done status 0 else
  if mmDifferent current epoch = true then ringReceipt 4 else
  .bind observeRing fun status consumed =>
  if mmFailed status = true then stopRing 3 0 else
  .bind (ringGet 32) fun s total => if mmFailed s = true then .done s 0 else
  .bind (ringGet 72) fun s mode => if mmFailed s = true then .done s 0 else
  .bind (ringGet 48) fun s gaps => if mmFailed s = true then .done s 0 else
  .bind (statusOwnedPCM 7 epoch) fun s fault => if mmFailed s = true then .done s 0 else
  if mmDifferent fault 0 = true then stopRing 3 0 else
  if mmDifferent gaps 0 = true then stopRing 3 0 else
  -- These are separate service calls: DONE may become visible after the
  -- earlier consumed observation. Require a fresh exact raw consumed count;
  -- neither accepted/fetched nor DONE alone invents a consumed prefix.
  if mode = 2 then
    if total = consumed then stopRing 0 0 else
    .bind (statusOwnedPCM 4 epoch) fun s actual => if mmFailed s = true then stopRing 3 0 else
    .bind (ringGet 24) fun s base => if mmFailed s = true then .done s 0 else
    if actual < base then stopRing 3 0 else
    if actual-base = total then stopRing 0 0 else stopRing 3 0
  else if total = consumed then .done 0 consumed else
  .bind (invoke 10 0 0 0) fun status ticks =>
  if mmFailed status = true then stopRing 3 0 else
  .bind (audioGet 40) fun s expiry => if mmFailed s = true then .done s 0 else
  if expiry ≤ ticks then stopRing 2 0 else
  if mmDifferent mode 1 = true then stopRing 3 0 else
  .bind refillRing fun status _ => if mmFailed status = true then stopRing 3 0 else
  .bind (ringGet 0) fun s accepted => if mmFailed s = true then .done s 0 else
  .bind (ringGet 40) fun s eof => if mmFailed s = true then .done s 0 else
  if accepted = total then if eof = 0 then
    .bind (finishOwnedPCM accepted epoch) fun status _ => if mmFailed status = true then stopRing 3 0 else
    .bind (ringPut 40 1) fun s _ => .done s consumed
    else .done 0 consumed
  else .done 0 consumed

/-- Version3 negotiates an actual wrap/refill4099-sample owned-ring test. The
version2 path retains the original sixteen-sample packet and controller meaning. -/
def testAudio : Action :=
  .bind (get 136) fun s service => if mmFailed s = true then .done s 0 else
  if service = 3 then testRingAudio else testLegacyAudio

private def pumpAudio : Action :=
  .bind (get 128) fun s allocated => if mmFailed s = true then .done s 0 else
  if allocated = 0 then .done 0 0 else
  .bind (audioGet 0) fun s running => if mmFailed s = true then .done s 0 else
  if running = 2 then pumpRingAudio else pumpLegacyAudio

/-- Acquisition and local output have separate grants. Poll without a busy
wait; acquisition errors never prevent an explicit MUTE from revoking output. -/
def pump : Action :=
  .bind pumpAcquisition fun status count =>
  .bind pumpAudio fun audioStatus _ =>
  if mmFailed status = true then .done status count else .done audioStatus count

def active : Action := get 16

end Lemma.User.Multimodal
