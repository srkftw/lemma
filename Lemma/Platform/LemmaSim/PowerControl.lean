import Lemma.Drivers.Power
import Lemma.Drivers.PowerSafety
import Lemma.Drivers.PLIC
import Lemma.Drivers.VirtIOBlock
import Lemma.USB.Block
import Lemma.Kernel.Capability
import Lemma.Kernel.MachineServices

/-! Kernel power policy and named-endpoint authority. A rejected suspend leaves
pending operations alone. Accepted suspend withholds User dispatch; actual WFI
and the machine timer remain the existing structured execution primitives. -/
namespace Lemma.Platform.LemmaSim.PowerControl
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory
open Lemma.User

def stateBase : UInt64 := 0x80400b80
private def get (offset : UInt64) : Action := Access.read64 (stateBase + offset)
private def put (offset value : UInt64) : Action := Access.write64 (stateBase + offset) value
private def fatal : Action := .done 255 0

def configure (enabled key : UInt64) : Action :=
  .bind (put 0 enabled) fun s _ => if s = 0 then
  .bind (put 8 key) fun s _ => if s = 0 then
  if enabled = 0 then .done 0 0 else if enabled = 1 then
  .bind Lemma.Drivers.Power.initialize fun s cause => if s = 0 then
  .bind Lemma.Drivers.Power.epoch fun s epoch => if s = 0 then
  .bind Lemma.Drivers.Power.buttonLevel fun s level => if s = 0 then
  Lemma.Kernel.Console.record 0x442 cause epoch level 0
  else fatal else fatal else .done s 0 else fatal else fatal else fatal

/-- Additive boot entry for the explicitly selected Power-v2 bindings. The
cooperative register policy is retained; validation uses the actual version2
identity and six reset causes. No watchdog is armed implicitly. -/
def configureSafety (enabled key : UInt64) : Action :=
  .bind (put 0 enabled) fun s _ => if s = 0 then
  .bind (put 8 key) fun s _ => if s = 0 then
  if enabled = 0 then .done 0 0 else if enabled = 1 then
  .bind Lemma.Drivers.PowerSafety.initialize fun s cause => if s = 0 then
  .bind Lemma.Drivers.Power.epoch fun s epoch => if s = 0 then
  .bind Lemma.Drivers.Power.buttonLevel fun s level => if s = 0 then
  Lemma.Kernel.Console.record 0x442 cause epoch level 0
  else fatal else fatal else .done s 0 else fatal else fatal else fatal

private def report (source : UInt64) (status : UInt8) : Action :=
  .bind Lemma.Drivers.Power.state fun s state => if s = 0 then
  .bind Lemma.Drivers.Power.epoch fun s epoch => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x440 source status.toUInt64 state epoch) fun s _ =>
  if s = 0 then .done status state else fatal else fatal else fatal

private def requestSuspend (source : UInt64) : Action :=
  -- Hardware cannot inspect driver bookkeeping. A queue which has finished
  -- DMA but whose guest completion has not been consumed is still pending.
  .bind (Access.read64 (Lemma.Drivers.VirtIOBlock.state + 40)) fun s pending => if s = 0 then
  .bind (Access.read64 0x80400c30) fun s completion => if s = 0 then
  if pending ||| completion = 0 then
  .bind Lemma.Drivers.PLIC.disablePen fun s _ => if s = 0 then
  .bind (Lemma.Drivers.Power.command 1) fun status state =>
  -- A raw wake can arrive between accepted COMMAND and the state readback.
  -- Both admitted states are valid; the caller still returns through S policy.
  if status = 0 then if state ≤ 1 then report source 0 else fatal else
  .bind Lemma.Drivers.PLIC.enablePen fun s _ => if s = 0 then
  if status = Lemma.Drivers.Power.busy then report source status else
  if status = Lemma.Drivers.Power.invalid then report source status else fatal
  else fatal else fatal else report source Lemma.Drivers.Power.busy else fatal else fatal

def call (descriptor handle operation r0 r1 r2 : UInt64) : Action :=
  if r0 ||| r1 ||| r2 = 0 then
  .bind (get 0) fun s enabled => if s = 0 then
  if enabled = 1 then
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointCall) fun s key => if s = 0 then
  .bind (get 8) fun s expected => if s = 0 then
  if key = expected then
    if operation = 0 then Lemma.Drivers.Power.state else
    if operation = 1 then requestSuspend 2 else
    if operation = 2 then Lemma.Drivers.Power.command 2 else
    if operation = 3 then Lemma.Drivers.Power.resetCause else .done Lemma.Drivers.Power.invalid 0
  else .done CapabilityABI.denied 0 else fatal else .done s 0
  else .done 17 0 else fatal else .done 16 0

def notification : Action :=
  .bind (get 0) fun s enabled => if s = 0 then
  if enabled = 1 then .done 0 0 else fatal else fatal

private def observeWake (observed : UInt64) : Action :=
  -- Wake takes priority over an older observed request. New physical edges at
  -- or after ACK remain pending according to the controller's W1C boundary.
  .bind (Lemma.Drivers.Power.ack (observed &&& 3)) fun s _ => if s = 0 then
  .bind Lemma.Drivers.PLIC.enablePen fun s _ => if s = 0 then
  .bind Lemma.Drivers.Power.wakeCause fun s cause => if s = 0 then
  .bind Lemma.Drivers.Power.epoch fun s epoch => if s = 0 then
  .bind MachineServices.time fun s now => if s = 0 then
  Lemma.Kernel.Console.record 0x441 cause epoch now 0
  else fatal else fatal else fatal else fatal else fatal

private def waitSuspended : Action :=
  -- Re-arm clears the private M timer notification. Timer/spurious returns
  -- repeat this policy step and never grant permission to dispatch User code.
  .bind (MachineServices.rearmRelative 10000000) fun s _ => if s = 0 then
  .bind MachineServices.wait fun s _ => if s = 0 then .done 0 1 else fatal else fatal

def step : Action :=
  .bind (get 0) fun s enabled => if s = 0 then
  if enabled = 0 then .done 0 0 else if enabled = 1 then
  .bind Lemma.Drivers.Power.events fun s events => if s = 0 then
  .bind (if events &&& 2 = 2 then observeWake events else .done 0 0) fun s _ => if s = 0 then
  .bind (if events &&& 2 = 2 then .done 0 0 else if events &&& 1 = 1 then
    .bind (Lemma.Drivers.Power.ack 1) fun s _ => if s = 0 then
    .bind (requestSuspend 1) fun status state =>
    if status = 0 then .done 0 state else if status = Lemma.Drivers.Power.busy then .done 0 0 else fatal
    else fatal else .done 0 0) fun s _ => if s = 0 then
  .bind Lemma.Drivers.Power.state fun s state => if s = 0 then
  if state = 0 then .done 0 0 else if state = 1 then waitSuspended else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal

private def requestSuspendUSB (source : UInt64) : Action :=
  .bind (Access.read64 (Lemma.USB.Block.state + 40)) fun s request => if s = 0 then
  .bind (Access.read64 (Lemma.USB.Block.state + 80)) fun s phase => if s = 0 then
  .bind (Access.read64 0x80400c30) fun s completion => if s = 0 then
  if request ||| phase ||| completion = 0 then requestSuspend source
  else report source Lemma.Drivers.Power.busy else fatal else fatal else fatal

def callUSB (descriptor handle operation r0 r1 r2 : UInt64) : Action :=
  if r0 ||| r1 ||| r2 = 0 then
  .bind (get 0) fun s enabled => if s = 0 then
  if enabled = 1 then
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointCall) fun s key => if s = 0 then
  .bind (get 8) fun s expected => if s = 0 then
  if key = expected then
    if operation = 0 then Lemma.Drivers.Power.state else
    if operation = 1 then requestSuspendUSB 2 else
    if operation = 2 then Lemma.Drivers.Power.command 2 else
    if operation = 3 then Lemma.Drivers.Power.resetCause else .done Lemma.Drivers.Power.invalid 0
  else .done CapabilityABI.denied 0 else fatal else .done s 0
  else .done 17 0 else fatal else .done 16 0

def stepUSB : Action :=
  .bind (get 0) fun s enabled => if s = 0 then
  if enabled = 0 then .done 0 0 else if enabled = 1 then
  .bind Lemma.Drivers.Power.events fun s events => if s = 0 then
  .bind (if events &&& 2 = 2 then observeWake events else .done 0 0) fun s _ => if s = 0 then
  .bind (if events &&& 2 = 2 then .done 0 0 else if events &&& 1 = 1 then
    .bind (Lemma.Drivers.Power.ack 1) fun s _ => if s = 0 then
    .bind (requestSuspendUSB 1) fun status state =>
    if status = 0 then .done 0 state else if status = Lemma.Drivers.Power.busy then .done 0 0 else fatal
    else fatal else .done 0 0) fun s _ => if s = 0 then
  .bind Lemma.Drivers.Power.state fun s state => if s = 0 then
  if state = 0 then .done 0 0 else if state = 1 then waitSuspended else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal

end Lemma.Platform.LemmaSim.PowerControl
