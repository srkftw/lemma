import Lemma.Boot.DevelopmentAuthentication
import Lemma.Boot.RecoveryExecuted

/-! Version2 owner-local DEVELOPMENT-KEY recovery. All image/tag writes and
barriers execute in this immutable Lean ROM; a host only supplies raw frames.
The original version1 integrity-only ROM/transport is unchanged. -/
namespace Lemma.Boot.DevelopmentRecovery
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access
open ProductExecuted
def transportVersion : UInt64 := 2
def capability : UInt64 := ((2 : UInt64) <<< 32) ||| ProductExecuted.mediumSectors
private def writeTag (slot identity : UInt64) : Action :=
  .bind (DevelopmentAuthentication.validateTag RecoveryExecuted.payload slot identity) fun s _ => if s = 0 then
  .bind ProductExecuted.selectedMetadata fun s selected => if s = 0 then
  .bind (if selected < 2 then
    .bind (read64 ((if selected = 0 then metadata0Buffer else metadata1Buffer)+24)) fun s confirmed =>
    if s = 0 then if slot = inactiveSlot confirmed then .done 0 0 else .done wrongReceipt 0 else .done s 0
    else if selected = 2 then .done 0 0 else .done conflict 0) fun s _ => if s = 0 then
  .bind (ProductExecuted.writeSector (2+slot) RecoveryExecuted.payload) fun s _ => if s = 0 then
  ProductExecuted.transaction 3 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def execute (operation slot relative identity checksum : UInt64) : Action :=
  if operation = 0 then .done 0 capability else
  if operation = 1 then
    .bind (RecoveryExecuted.receivePayload checksum) fun s _ => if s = 0 then
    RecoveryExecuted.writeImageSector slot relative else .done s 0
  else if operation = 2 then
    -- Authenticate the actually loaded bytes before metadata publication.
    -- Handoff will independently check the subsequently loaded bytes again.
    .bind (DevelopmentAuthentication.load slot identity) fun s _ => if s = 0 then
    RecoveryExecuted.publishImage slot identity else .done s 0
  else if operation = 3 then DevelopmentAuthentication.boot else
  if operation = 4 then
    -- The old durable receipt includes a fresh real medium barrier. Add MAC
    -- verification; an integrity-only status can never become a v2 receipt.
    .bind (RecoveryExecuted.imageStatus slot identity) fun s receipt => if s = 0 then
    .bind (DevelopmentAuthentication.load slot identity) fun s _ => .done s (if s = 0 then receipt else 0)
    else .done s 0
  else if operation = 5 then
    .bind (RecoveryExecuted.receivePayload checksum) fun s _ => if s = 0 then writeTag slot identity else .done s 0
  else if operation = 6 then .done 0 DevelopmentAuthentication.keyId else .done malformed 0
private def commandStep (_ _ : UInt32) (_ _ _ _ _ : UInt64) : Action :=
  .bind RecoveryExecuted.receiveFrame fun s _ => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+8)) fun s version => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+16)) fun s transaction => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+24)) fun s operation => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+32)) fun s slot => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+40)) fun s relative => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+48)) fun s identity => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+56)) fun s reserved => if s = 0 then
  .bind (read64 (RecoveryExecuted.frame+64)) fun s checksum => if s = 0 then
  if version = transportVersion then if transaction = 0 then .done 0 0 else
  if reserved = 0 then
    .bind (execute operation slot relative identity checksum) fun outcome entry =>
    .bind (RecoveryExecuted.reply transaction outcome entry) fun s _ => if s = 0 then
    if outcome = 0 then if operation = 3 then .done Status.iterationStop entry else .done 0 0
    else .done 0 0 else .done s 0
  else .bind (RecoveryExecuted.reply transaction malformed 0) fun s _ => .done s 0
  else .bind (RecoveryExecuted.reply transaction malformed 0) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else if s = malformed then .done 0 0 else
  if s = Status.rxTimeout then .done 0 0 else .done s 0
private def recovery : Action :=
  .boundedFoldU64 65536 commandStep 65536 0 0 0 0 0 fun s entry =>
  if s = Status.iterationStop then .done 0 entry else
  if s = 0 then .done ProductExecuted.recovery 0 else .done s 0
private def recoveryStart : Action :=
  .bind ProductExecuted.«initialize» fun s _ => if s = 0 then
  .uartEnableAndResetFifo fun s => if s = 0 then
  .bind (RecoveryExecuted.reply 0 0 capability) fun s _ => if s = 0 then recovery else .done s 0
  else .done s 0 else .done s 0
def entry : Action :=
  .uartReadStatus fun s status => if s = 0 then
  if status &&& 1 = 0 then
    .bind DevelopmentAuthentication.boot fun s entry => if s = 0 then .done 0 entry else recoveryStart
  else .uartReadByte fun s byte => if s = 0 then
    if byte = 0x52 then recoveryStart else
    .bind DevelopmentAuthentication.boot fun s entry => if s = 0 then .done 0 entry else recoveryStart
  else .done s 0 else .done s 0
end Lemma.Boot.DevelopmentRecovery
