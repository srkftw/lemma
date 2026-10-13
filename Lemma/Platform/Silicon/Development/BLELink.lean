import Lemma.Radio.BLE.Controller
import Lemma.Radio.BLE.Link
import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaSim.MachineServices
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Kernel.Console

/-! Explicit future0.5 development probe: actual privileged PIO and source15
claim/completion, finite one-context retries, opaque companion-prefix bytes.
No connection establishment, authentication, notebook mutation or durable receipt.
Binding5 deliberately fails discovery until the exact0.5 descriptor is supplied. -/
namespace Lemma.Platform.Silicon.Development.BLELink
open Lemma.Core0.Memory
open Lemma.Radio.BLE
def base : UInt64 := 0x10010600
def timeout : UInt8 := 201
private def fatal : Action := .done 255 0

private def configureIRQ : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c00003c 1) fun s _ => if s = 0 then
  .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c002080 0x8000) fun s _ => if s = 0 then
  Lemma.Platform.LemmaSim.IO.write32 0x0c201000 0 else .done s 0 else .done s 0

private def waitStep : Action :=
  .bind (Lemma.Kernel.MachineServices.rearmRelative 1000) fun s _ => if s = 0 then
  Lemma.Kernel.MachineServices.wait else .done s 0

/-- A PLIC claim is completed only after its immutable head/events have been
consumed. Invalid or unexpected source numbers are terminal, never completed
as15. This preserves the actual controller's interrupt admission. -/
private def pollIRQ (state : UInt64) : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c201004) fun s source => if s = 0 then
  if source = 0 then .done 0 state else if source = 15 then
  .bind (Controller.events base) fun s events => if s = 0 then
  if events &&& (2 : UInt64) = 2 then
    .bind (Controller.receivedHeader base) fun s header => if s = 0 then
    -- The scripted external peer acknowledges with a real CRC-valid empty
    -- LLID1 packet. Arbitrary unsolicited payload cannot satisfy this probe.
    if header >>> 8 = 0 then
    .bind (Link.receive state (header &&& 255) 0 1) fun s next => if s = 0 then
    .bind (Controller.releaseReceived base) fun s _ => if s = 0 then
    .bind (Controller.acknowledge base events) fun s _ => if s = 0 then
    .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c201004 source) fun s _ => if s = 0 then
    .bind (Lemma.Kernel.Console.record 0x451 source header next events) fun s _ =>
      .done s next
    else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done 197 0 else .done s 0
  else
    .bind (Controller.acknowledge base events) fun s _ => if s = 0 then
    .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c201004 source) fun s _ =>
      .done s state
    else .done s 0
  else .done s 0 else .done 197 0 else .done s 0

private def awaitStep (_i _count : UInt32) (state deadline _ _ _ : UInt64) : Action :=
  .bind (pollIRQ (state &&& Link.stateMask)) fun s next => if s = 0 then
  if next &&& Link.acknowledged = Link.acknowledged then .done Status.iterationStop next else
  .bind Lemma.Kernel.MachineServices.time fun s now => if s = 0 then
  if deadline ≤ now then .done timeout (next &&& Link.stateMask) else
  .bind waitStep fun s _ => .done s (next &&& Link.stateMask)
  else .done s 0 else .done s 0

private def awaitACK (state : UInt64) : Action :=
  .bind Lemma.Kernel.MachineServices.time fun s now => if s = 0 then
  if now ≤ 0xffffffffffffffff-100000 then
  .boundedFoldU64 128 awaitStep 128 state (now+100000) 0 0 0 fun s next =>
    if s = Status.iterationStop then .done 0 next else
    if s = 0 then .done timeout next else .done s next
  else .done 202 0 else .done s 0

private def attemptStep (i _count : UInt32) (state _ _ _ _ : UInt64) : Action :=
  .bind (if i = 0 then Link.begin state else Link.retry state) fun s next => if s = 0 then
  .bind (Link.packetHeader next 2 12) fun s header => if s = 0 then
  .bind (Controller.submit base header 12 0x313030504d434d4c 0x00020001 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x450 i.toUInt64 next header 12) fun s _ => if s = 0 then
  .bind (awaitACK next) fun s final => if s = 0 then
    .done Status.iterationStop (final &&& Link.stateMask)
  else if s = timeout then .done 0 final else .done s final
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def transaction : Action :=
  .boundedFoldU64 3 attemptStep 3 Link.initial 0 0 0 0 fun s state =>
  if s = Status.iterationStop then
    .bind (Lemma.Kernel.Console.record 0x452 state 12 3 0) fun s _ => .done s state
  else if s = 0 then
    .bind (Link.retry state) fun exhausted frozen =>
    .bind (Controller.cancel base) fun s _ => if s = 0 then
    .bind (Lemma.Kernel.Console.record 0x453 exhausted.toUInt64 frozen 3 0) fun s _ =>
      .done s frozen
    else .done s 0
  else .done s 0

def boot : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind Lemma.Kernel.BootInfo.validate fun s _ => if s = 0 then
  .bind (Lemma.Platform.LemmaSim.Descriptor.validateBinding 5) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun s _ => if s = 0 then
  .bind (Controller.initialize base) fun s _ => if s = 0 then
  .bind (Controller.configure base 0xaa08192b 0xc4c181 16) fun s _ => if s = 0 then
  .bind configureIRQ fun s _ => if s = 0 then
  .bind transaction fun s _ => if s = 0 then .loop waitStep else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

def dispatch (_frame _cause _value : UInt64) : Action := fatal
end Lemma.Platform.Silicon.Development.BLELink
