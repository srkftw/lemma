import Lemma.Kernel.Capability

/-! A single bounded service binding. Boot alone publishes it; an ordinary
Directory grant discovers only a receiver-local Endpoint Call16 capability.
Counts are read-only. This module has no Task/Process dependency. -/
namespace Lemma.Kernel.Directory
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done CapabilityABI.fatal 0
def serviceID : UInt64 := 1

def epoch : Action :=
  .bind Objects.serviceBinding fun s base =>
  if failed s = true then fatal else Objects.get (base + Objects.serviceEpochOffset)

def nextEpoch : Action :=
  .bind epoch fun s current =>
  if failed s = true then fatal else
  if current < 0xffffffffffffffff then .done 0 (current + 1)
  else .done CapabilityABI.generationExhausted 0

/-- Trusted preflight accepts a genuinely enrolled constructing descriptor.
It does not change epoch, object references or capability serials. -/
def preflightPublish (server key candidate : UInt64) : Action :=
  .bind Objects.serviceBinding fun s base =>
  if failed s = true then fatal else
  .bind (Objects.get (base + Objects.serviceOffset)) fun s tag =>
  if failed s = true then fatal else
  if tag = Objects.serviceMagic then
  .bind (Objects.get (base + Objects.serviceKeyOffset)) fun s existing =>
  if failed s = true then fatal else
  if existing = 0 then
  .bind nextEpoch fun s expected =>
  if failed s = true then .done s 0 else
  if candidate = expected then
  .bind (Capability.entryCount server) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 40)) fun s owner =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
    if owner = server then .done 0 candidate else .done CapabilityABI.denied 0
  else .done CapabilityABI.wrongType 0
  else .done CapabilityABI.invalidArgument 0
  else .done CapabilityABI.invalidArgument 0
  else .done CapabilityABI.invalidArgument 0

/-- After task activation, contradictions are fatal; there is no ordinary
failure requiring an abort of an already runnable task. Publication is last. -/
def publish (server key candidate : UInt64) : Action :=
  .bind (preflightPublish server key candidate) fun s _ =>
  if failed s = true then fatal else
  .bind (Capability.requireActive server) fun s _ =>
  if failed s = true then fatal else Objects.publishServiceBinding server key candidate

private def current : Action :=
  .bind Objects.serviceBinding fun s base =>
  if failed s = true then fatal else
  .bind (Objects.get (base + Objects.serviceKeyOffset)) fun s key =>
  if failed s = true then fatal else
  if key = 0 then .done IPCABI.peerDied 0 else
  .bind (Objects.get (base + Objects.serviceOwnerOffset)) fun s server =>
  if failed s = true then fatal else
  .bind (Capability.requireActive server) fun s _ =>
  if failed s = true then .done IPCABI.peerDied 0 else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done IPCABI.peerDied 0 else
  .bind (Objects.get (object + 40)) fun s owner =>
  if failed s = true then fatal else
  if owner = server then .done 0 key else fatal

def server : Action :=
  .bind current fun s _ =>
  if failed s = true then .done s 0 else
  .bind Objects.serviceBinding fun s base =>
  if failed s = true then fatal else Objects.get (base + Objects.serviceOwnerOffset)

/-- The dispatcher supplies the verified caller descriptor. Modes0/1 need a
live checked binding; mode2 reports active managed registrations, not raw Task
rows. No User supplied value is a kernel pointer or publication authority. -/
def discover (descriptor handle mode selectedService : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.directoryType
    CapabilityABI.directoryDiscover) fun s _ =>
  if failed s = true then .done s 0 else
  if mode < 2 then
    if selectedService = serviceID then
    .bind current fun s key =>
    if failed s = true then .done s 0 else
    if mode = 0 then Capability.grantDiscovered descriptor key else epoch
    else .done CapabilityABI.invalidArgument 0
  else if selectedService = 0 then
    if mode = 2 then Capability.activeRegisteredCount else
    if mode = 3 then Frames.remaining else .done CapabilityABI.invalidArgument 0
  else .done CapabilityABI.invalidArgument 0

end Lemma.Kernel.Directory
