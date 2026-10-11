import Lemma.Kernel.BootServices
import Lemma.Kernel.Scheduler
import Lemma.Kernel.Directory
import Lemma.Kernel.KernelInput

/-! Ordinary volatile-service boot policy. Every task and grant is constructed
before scheduling. This module has no development transport, arbitrary selector,
or restart command. Input has one reader and the CLI receives only Console and
Directory authority. -/
namespace Lemma.Kernel.ServiceEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

def grant (descriptor key kind rights : UInt64) : Action :=
  .bind (Capability.grantBoot descriptor key rights) fun s handle =>
  if s = 255 then fatal else
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0xb1 descriptor handle kind rights) fun s _ =>
  if failed s = true then fatal else .done 0 handle

def createEndpoint (owner : UInt64) : Action :=
  .bind (Objects.createEndpoint owner) fun s key =>
  if s = 255 then fatal else
  if failed s = true then .done s 0 else
  .bind Frames.remaining fun s remaining =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xb4 owner key remaining 0) fun s _ =>
  if failed s = true then fatal else .done 0 key

def abortOne (descriptor : UInt64) (status : UInt8) : Action :=
  if status = 255 then fatal else
  .bind (Task.abort descriptor) fun s _ =>
  if failed s = true then fatal else .done status 0
private def abortTwo (first second : UInt64) (status : UInt8) : Action :=
  .bind (Task.abort second) fun s _ =>
  if failed s = true then fatal else abortOne first status
private def abortThree (first second third : UInt64) (status : UInt8) : Action :=
  .bind (Task.abort third) fun s _ =>
  if failed s = true then fatal else abortTwo first second status
private def abortFour (first second third fourth : UInt64) (status : UInt8) : Action :=
  .bind (Task.abort fourth) fun s _ =>
  if failed s = true then fatal else abortThree first second third status

/-- The validated image's real page count must leave room for all four actual
service backing pages, in addition to the sixteen fixed owned pages. -/
def serverBudget : Action :=
  .bind (Loader.validate 0) fun s image =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (image + 32)) fun s bytes =>
  if failed s = true then fatal else
  let pages := (bytes + 4095) / 4096
  if 16 + pages + 4 ≤ 32 then .done 0 pages else .done 38 0

private def grants (server cli peer endpoint : UInt64) : Action :=
  .bind (grant server Objects.consoleKey CapabilityABI.consoleType 2) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant server endpoint CapabilityABI.endpointType 8) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant cli Objects.consoleKey CapabilityABI.consoleType 3) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant cli Objects.directoryKey CapabilityABI.directoryType 1024) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (grant peer Objects.consoleKey CapabilityABI.consoleType 2) fun s _ =>
  if failed s = true then .done s 0 else
  grant peer Objects.directoryKey CapabilityABI.directoryType 1024

/-- Publication follows all ordinary-failable construction work. No runnable
task is aborted on a contradiction after activation. The Server is last. -/
def activatePublished (server endpoint epoch cli : UInt64) : Action :=
  .bind (Task.activateManaged server) fun s _ =>
  if failed s = true then fatal else
  .bind (Directory.publish server endpoint epoch) fun s actualEpoch =>
  if failed s = true then fatal else
  if actualEpoch = epoch then
  .bind (Lemma.Kernel.Console.record 0x300 server endpoint actualEpoch cli) fun s _ =>
  if failed s = true then fatal else .done 0 actualEpoch
  else fatal

private def configure (server cli peer cpu epoch : UInt64) : Action :=
  .bind (createEndpoint server) fun s endpoint =>
  if failed s = true then abortFour server cli peer cpu s else
  .bind (grants server cli peer endpoint) fun s _ =>
  if failed s = true then abortFour server cli peer cpu s else
  .bind (Directory.preflightPublish server endpoint epoch) fun s _ =>
  if failed s = true then abortFour server cli peer cpu s else
  .bind (KernelInput.bindReader cli) fun s reader =>
  if failed s = true then abortFour server cli peer cpu s else
  if reader = cli then
  .bind (Task.activateManaged cli) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.activateManaged peer) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.activateManaged cpu) fun s _ =>
  if failed s = true then fatal else
  .bind (activatePublished server endpoint epoch cli) fun s _ =>
  if failed s = true then fatal else .done 0 cli
  else fatal

/-- Normal boot starts immediately. Arguments1/2/3 are public instance seeds;
the Server receives the actual next Directory epoch. No launch packet exists. -/
def construct : Action :=
  .bind serverBudget fun s _ =>
  if failed s = true then .done s 0 else
  .bind Directory.nextEpoch fun s epoch =>
  if failed s = true then .done s 0 else
  .bind (Task.prepareManaged 0 epoch) fun s server =>
  if failed s = true then .done s 0 else
  .bind (Task.prepareManaged 1 1) fun s cli =>
  if failed s = true then abortOne server s else
  .bind (Task.prepareManaged 2 2) fun s peer =>
  if failed s = true then abortTwo server cli s else
  .bind (Task.prepareManaged 3 3) fun s cpu =>
  if failed s = true then abortThree server cli peer s else
  configure server cli peer cpu epoch

/-- Mode is trusted entry policy:1 for ordinary boot,2 for the separate
development Entry. It is never selected by an input command or user syscall. -/
def initializeFor (mode expectedInterrupts probeTicks : UInt64) : Action :=
  .bind (BootServices.bootServicesFor expectedInterrupts probeTicks) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 0x80400010) fun s stage =>
  if failed s = true then fatal else
  if stage = 1 then
  .bind Process.init fun s _ =>
  if failed s = true then .done s 0 else
  .bind Task.init fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0xf0 1 Task.capacity Task.stride Scheduler.quantum) fun s _ =>
  if failed s = true then fatal else
  .bind Objects.init fun s _ =>
  if failed s = true then .done s 0 else
  .bind Objects.serviceInitialize fun s _ =>
  if failed s = true then fatal else
  .bind (KernelInput.init mode) fun s _ =>
  if failed s = true then .done s 0 else
  .bind Frames.remaining fun s remaining =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xb0 1 Capability.capacity Objects.capacity remaining) fun s _ =>
  if failed s = true then fatal else .done 0 remaining
  else .done 51 0

def «initialize» (mode : UInt64) : Action :=
  initializeFor mode 0x1446 MachineServices.quantum

def step : Action :=
  .bind KernelInput.poll fun s _ =>
  if failed s = true then fatal else Scheduler.step

def boot : Action :=
  .bind (ServiceEntry.initialize 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind construct fun s _ =>
  if failed s = true then .done s 0 else .loop step

def dispatch (frame cause value : UInt64) : Action :=
  Scheduler.dispatch frame cause value

end Lemma.Kernel.ServiceEntry
