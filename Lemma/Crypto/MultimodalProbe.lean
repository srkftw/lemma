import Lemma.Crypto.AEAD
import Lemma.Boot.RecoveryExecuted

/-! Actual RV64 RFC8439 AEAD known-answer and tamper workload. No expected tag
or ciphertext is supplied to this target. The independent host checks UART. -/
namespace Lemma.Crypto.MultimodalProbe
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access
private def w : UInt64 := 0x81001000
private def key : UInt64 := 0x81003000
private def nonce : UInt64 := 0x81003020
private def aad : UInt64 := 0x81003040
private def source : UInt64 := 0x81004000
private def ciphertext : UInt64 := 0x81005000
private def tag : UInt64 := 0x81005100
private def restored : UInt64 := 0x81006000
private def textWord (i : UInt64) : UInt64 :=
  if i = 0 then 0x612073656964614c else
  if i = 1 then 0x6c746e654720646e else
  if i = 2 then 0x20666f206e656d65 else
  if i = 3 then 0x73616c6320656874 else
  if i = 4 then 0x39392720666f2073 else
  if i = 5 then 0x632049206649203a else
  if i = 6 then 0x66666f20646c756f else
  if i = 7 then 0x6f20756f79207265 else
  if i = 8 then 0x20656e6f20796c6e else
  if i = 9 then 0x20726f6620706974 else
  if i = 10 then 0x7574756620656874 else
  if i = 11 then 0x736e7573202c6572 else
  if i = 12 then 0x6f77206e65657263 else
  if i = 13 then 0x6920656220646c75 else 0x2e74
private def seedText (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (write64 (source+i.toUInt64*8) (textWord i.toUInt64)) fun s _ => .done s acc
private def seedKey (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (write8 (key+i.toUInt64) (128+i.toUInt64)) fun s _ => .done s acc
private def emit (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (read64 (address+i.toUInt64*8)) fun s word => if s = 0 then
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord word) fun s _ => .done s acc else .done s 0
private def report (kind : UInt64) (status : UInt8) : Action :=
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord 0x32444145414d454c) fun s _ => if s = 0 then
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord kind) fun s _ => if s = 0 then
  Lemma.Boot.RecoveryExecuted.transmitWord status.toUInt64 else .done s 0 else .done s 0

def entry : Action :=
  .uartEnableAndResetFifo fun s => if s = 0 then
  .boundedFoldU64 32 seedKey 32 0 0 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 15 seedText 15 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (write64 nonce 0x4342414000000007) fun s _ => if s = 0 then
  .bind (write64 (nonce+8) 0x47464544) fun s _ => if s = 0 then
  .bind (write64 aad 0xc3c2c1c053525150) fun s _ => if s = 0 then
  .bind (write64 (aad+8) 0xc7c6c5c4) fun s _ => if s = 0 then
  .bind (AEAD.«seal» w key nonce aad 12 source 114 ciphertext tag) fun status _ =>
  .bind (report 1 status) fun s _ => if s = 0 then if status = 0 then
  .boundedFoldU64 2 emit 2 0 tag 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 15 emit 15 0 ciphertext 0 0 0 fun s _ => if s = 0 then
  .bind (AEAD.open w key nonce aad 12 ciphertext 114 restored tag) fun status _ =>
  .bind (report 2 status) fun s _ => if s = 0 then if status = 0 then
  .boundedFoldU64 15 emit 15 0 restored 0 0 0 fun s _ => if s = 0 then
  .bind (read8 tag) fun s actual => if s = 0 then
  .bind (write8 tag (actual ^^^ 1)) fun s _ => if s = 0 then
  .bind (AEAD.open w key nonce aad 12 ciphertext 114 restored tag) fun status _ =>
  .bind (report 3 status) fun s _ => if s = 0 then
  Lemma.Boot.RecoveryExecuted.transmitWord 0x32444e45414d454c
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done status 0 else .done s 0
  else .done s 0 else .done s 0 else .done status 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
end Lemma.Crypto.MultimodalProbe
