import Lemma.Crypto.HMAC256
import Lemma.Boot.RecoveryExecuted

/-! RV64 cryptographic known-answer workload. UART carries actual computed
digest bytes; the independent host oracle supplies no digest to this program.
This is a component test, not the authenticated boot policy. -/
namespace Lemma.Crypto.Probe
open Lemma.Core0.Memory Lemma.Kernel.Memory.Access
def context : UInt64 := 0x81001000
def key : UInt64 := 0x81002000
def output : UInt64 := 0x81003000
def source : UInt64 := 0x81004000
private def seedStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (write8 (source+i.toUInt64) ((i.toUInt64*37+11)%256)) fun s _ => .done s acc
private def keyStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (write8 (key+i.toUInt64) 11) fun s _ => .done s acc
private def digestStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (read64 (output+i.toUInt64*8)) fun s word => if s = 0 then
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord word) fun s _ => .done s acc else .done s 0
private def report (caseId : UInt64) (status : UInt8) (bytes : UInt64) : Action :=
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord 0x31414853414d454c) fun s _ => if s = 0 then
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord caseId) fun s _ => if s = 0 then
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord status.toUInt64) fun s _ => if s = 0 then
  .bind (Lemma.Boot.RecoveryExecuted.transmitWord bytes) fun s _ => if s = 0 then
  .boundedFoldU64 4 digestStep 4 0 0 0 0 0 fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def length (index : UInt64) : UInt64 :=
  if index = 0 then 0 else if index = 1 then 1 else if index = 2 then 55 else
  if index = 3 then 56 else if index = 4 then 57 else if index = 5 then 63 else
  if index = 6 then 64 else if index = 7 then 65 else if index = 8 then 129 else 4096
private def caseStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (SHA256.hash context source (length i.toUInt64) output) fun s _ =>
  .bind (report i.toUInt64 s (length i.toUInt64)) fun s _ => .done s acc
def entry : Action :=
  .uartEnableAndResetFifo fun s => if s = 0 then
  .boundedFoldU64 4096 seedStep 4096 0 0 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 10 caseStep 10 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (write64 source 0x636261) fun s _ => if s = 0 then
  .bind (SHA256.hash context source 3 output) fun s _ =>
  .bind (report 100 s 3) fun s _ => if s = 0 then
  .boundedFoldU64 20 keyStep 20 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (write64 source 0x6572656854206948) fun s _ => if s = 0 then
  .bind (HMAC256.authenticate context key 20 source 8 output) fun s _ =>
  .bind (report 101 s 8) fun s _ => if s = 0 then
  Lemma.Boot.RecoveryExecuted.transmitWord 0x31444e45414d454c
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
end Lemma.Crypto.Probe
