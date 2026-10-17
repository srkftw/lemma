import Lemma.Boot.Product

/-!
Immutable integrity-only local recovery transport, version1. This raw UART
transport conveys opaque image sectors; Product performs every media operation,
validation and selection. It provides no cryptographic authentication claim.
-/
namespace Lemma.Boot.Recovery
open Lemma.Core0.Memory Lemma.Boot.Product

def requestMagic : UInt64 := 0x31564f4345524d4c -- LMRECOV1
def responseMagic : UInt64 := 0x3154504345524d4c -- LMRECPT1
def frame : UInt64 := scratch + 0x800
def payload : UInt64 := scratch + 0x400
def commandBudget : Nat := 65536
def bytePollBudget : Nat := 100000

private def receiveStep (_ _ : UInt32) (_ _ _ _ _ : UInt64) : Action :=
  .uartReadStatus fun s status => if s = 0 then
  if status &&& 0x1e = 0 then
  if status &&& 1 = 0 then .done 0 0 else
    .uartReadByte fun s byte => if s = 0 then .done Status.iterationStop (byte+1) else .done s 0
  else .done Status.lineError 0 else .done s 0
def receiveByte : Action :=
  .boundedFoldU64 100000 receiveStep 100000 0 0 0 0 0 fun s byte =>
  if s = Status.iterationStop then .done 0 (byte-1) else
  if s = 0 then .done Status.rxTimeout 0 else .done s 0
private def wordByteStep (index count : UInt32) (word _ _ _ _ : UInt64) : Action :=
  if index < count then
  .bind receiveByte fun s byte => if s = 0 then
    .done 0 (word ||| (byte <<< (index.toUInt64*8))) else .done s 0
  else .done 0 word
def receiveWord : Action :=
  .boundedFoldU64 8 wordByteStep 8 0 0 0 0 0 fun s word => .done s word
private def transmitStep (_ _ : UInt32) (_ byte _ _ _ : UInt64) : Action :=
  .uartReadStatus fun s status => if s = 0 then
  if status &&& 0x20 = 0 then .done 0 0 else
  .uartWriteByte byte.toUInt8 fun s => if s = 0 then .done Status.iterationStop 0 else .done s 0
  else .done s 0
def transmitByte (byte : UInt64) : Action :=
  .boundedFoldU64 100000 transmitStep 100000 0 byte 0 0 0 fun s _ =>
  if s = Status.iterationStop then .done 0 0 else
  if s = 0 then .done Status.txTimeout 0 else .done s 0
private def transmitWordStep (index count : UInt32) (_ word _ _ _ : UInt64) : Action :=
  if index < count then transmitByte ((word >>> (index.toUInt64*8)) &&& 255) else .done 0 0
def transmitWord (word : UInt64) : Action :=
  .boundedFoldU64 8 transmitWordStep 8 0 word 0 0 0 fun s _ => .done s 0

private def synchronizeStep (_ _ : UInt32) (window _ _ _ _ : UInt64) : Action :=
  .bind receiveByte fun s byte => if s = 0 then
  let window := (window >>> 8) ||| (byte <<< 56)
  if window = requestMagic then .done Status.iterationStop window else .done 0 window
  else .done s 0
private def receiveFrameWordStep (index count : UInt32) (crc _ _ _ _ : UInt64) : Action :=
  if index < count then
  .bind receiveWord fun s word => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.write64 (frame+(index.toUInt64+1)*8) word) fun s _ =>
  if s = 0 then .done 0 (if index < 8 then crcWord crc word else crc) else .done s 0
  else .done s 0 else .done 0 crc
def receiveFrame : Action :=
  .boundedFoldU64 65536 synchronizeStep 65536 0 0 0 0 0 fun s _ =>
  if s = Status.iterationStop then
  .bind (Lemma.Kernel.Memory.Access.write64 frame requestMagic) fun s _ => if s = 0 then
  .boundedFoldU64 9 receiveFrameWordStep 9 (crcWord crcInitial requestMagic) 0 0 0 0 fun s crc =>
  if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+72)) fun s checksum => if s = 0 then
  if crcFinish crc = checksum then .done 0 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0
  else if s = 0 then .done Status.rxTimeout 0 else .done s 0

private def receivePayloadStep (index count : UInt32) (crc _ _ _ _ : UInt64) : Action :=
  if index < count then
  .bind receiveWord fun s word => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.write64 (payload+index.toUInt64*8) word) fun s _ =>
  if s = 0 then .done 0 (crcWord crc word) else .done s 0
  else .done s 0 else .done 0 crc
def receivePayload (expected : UInt64) : Action :=
  .boundedFoldU64 64 receivePayloadStep 64 crcInitial 0 0 0 0 fun s crc =>
  if s = 0 then if crcFinish crc = expected then .done 0 0 else .done malformed 0
  else .done s 0
def reply (transaction : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (transmitWord responseMagic) fun s _ => if s = 0 then
  .bind (transmitWord transaction) fun s _ => if s = 0 then
  .bind (transmitWord status.toUInt64) fun s _ => if s = 0 then
  .bind (transmitWord value) fun s _ => if s = 0 then
  transmitWord (crcFinish (crcWord (crcWord (crcWord (crcWord crcInitial responseMagic) transaction) status.toUInt64) value))
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

def writeImageSector (slot relative : UInt64) : Action :=
  if slot < 2 then if relative < slotSectors then
  .bind selectedMetadata fun s selected => if s = 0 then
  if selected < 2 then
    .bind (Lemma.Kernel.Memory.Access.read64 ((if selected = 0 then metadata0Buffer else metadata1Buffer)+24)) fun s confirmed =>
    if s = 0 then installSector confirmed slot relative payload else .done s 0
  else if selected = 2 then writeSector (slotFirst slot+relative) payload
  else .done conflict 0
  else .done s 0 else .done malformed 0 else .done malformed 0
def publishImage (slot identity : UInt64) : Action :=
  if slot < 2 then
  .bind selectedMetadata fun s selected => if s = 0 then
  if selected < 2 then
    let metadata := if selected = 0 then metadata0Buffer else metadata1Buffer
    .bind (Lemma.Kernel.Memory.Access.read64 (metadata+24)) fun s confirmed => if s = 0 then
    if slot = inactiveSlot confirmed then finishInstall selected metadata identity else .done wrongReceipt 0
    else .done s 0
  else if selected = 2 then establishRecoveryImage slot identity else .done conflict 0
  else .done s 0 else .done malformed 0

-- A receipt can be lost after a first-image barrier. Reconcile against fresh
-- durable metadata instead of treating a duplicate establishment as failure.
-- Reconciliation establishes a fresh barrier and revalidates the complete
-- image. Observed metadata after a failed older barrier is not an acknowledgment.
def imageStatus (slot identity : UInt64) : Action :=
  if slot < 2 then
  .bind (transaction 3 0) fun s _ => if s = 0 then
  .bind selectedMetadata fun s selected => if s = 0 then
  if selected < 2 then
    let metadata := if selected = 0 then metadata0Buffer else metadata1Buffer
    .bind (Lemma.Kernel.Memory.Access.read64 (metadata+24)) fun s confirmed => if s = 0 then
    .bind (Lemma.Kernel.Memory.Access.read64 (metadata+32)) fun s confirmedIdentity => if s = 0 then
    if canConfirm slot identity confirmed confirmedIdentity then
      .bind (verifyImage slot identity) fun s _ => .done s (if s = 0 then 1 else 0)
    else
    .bind (Lemma.Kernel.Memory.Access.read64 (metadata+40)) fun s trial => if s = 0 then
    .bind (Lemma.Kernel.Memory.Access.read64 (metadata+48)) fun s trialIdentity => if s = 0 then
    if canConfirm slot identity trial trialIdentity then
      .bind (verifyImage slot identity) fun s _ => .done s (if s = 0 then 2 else 0)
    else .done wrongReceipt 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else if selected = 2 then .done Product.recovery 0 else .done conflict 0
  else .done s 0 else .done s 0 else .done malformed 0

private def execute (operation slot relative identity checksum : UInt64) : Action :=
  if operation = 0 then .done 0 mediumSectors else
  if operation = 1 then
    .bind (receivePayload checksum) fun s _ => if s = 0 then writeImageSector slot relative else .done s 0
  else if operation = 2 then publishImage slot identity else
  if operation = 3 then boot else
  if operation = 4 then imageStatus slot identity else .done malformed 0
private def commandStep (_ _ : UInt32) (_ _ _ _ _ : UInt64) : Action :=
  .bind receiveFrame fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+8)) fun s version => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+16)) fun s transaction => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+24)) fun s operation => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+32)) fun s slot => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+40)) fun s relative => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+48)) fun s identity => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+56)) fun s reserved => if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.read64 (frame+64)) fun s checksum => if s = 0 then
  if version = 1 then if transaction = 0 then .done 0 0 else
  if reserved = 0 then
    .bind (execute operation slot relative identity checksum) fun outcome value =>
    .bind (reply transaction outcome value) fun s _ => if s = 0 then
    if outcome = 0 then if operation = 3 then .done Status.iterationStop value else .done 0 0
    else .done 0 0 else .done s 0
  else .bind (reply transaction malformed 0) fun s _ => .done s 0
  else .bind (reply transaction malformed 0) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  -- A malformed/timed-out request has no storage effects. Scan for the next
  -- request magic; no partial frame is reused as an installation request.
  else if s = malformed then .done 0 0 else
  if s = Status.rxTimeout then .done 0 0 else .done s 0

def recovery : Action :=
  .boundedFoldU64 65536 commandStep 65536 0 0 0 0 0 fun s entry =>
  if s = Status.iterationStop then .done 0 entry else
  if s = 0 then .done Product.recovery 0 else .done s 0
private def recoveryStart : Action :=
  .bind Product.«initialize» fun s _ => if s = 0 then
  .uartEnableAndResetFifo fun s => if s = 0 then
  .bind (reply 0 0 mediumSectors) fun s _ => if s = 0 then recovery else .done s 0
  else .done s 0 else .done s 0
def entry : Action :=
  -- Owner-local reset request is a single byte sent before normal boot. Only
  -- after the ROM beacon may the host send framed image transactions; FIFO
  -- initialization never discards a partly submitted request.
  .uartReadStatus fun s status => if s = 0 then
  if status &&& 1 = 0 then
    .bind boot fun s entry => if s = 0 then .done 0 entry else recoveryStart
  else
    .uartReadByte fun s byte => if s = 0 then
    if byte = 0x52 then recoveryStart else
      .bind boot fun s entry => if s = 0 then .done 0 entry else recoveryStart
    else .done s 0
  else .done s 0
end Lemma.Boot.Recovery
