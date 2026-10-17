import Lemma.Platform.LemmaSim.NotebookKernel
import Lemma.Boot.TrialWatchdog

/-! ProductReader trial supervision successor. Historical startup/dispatch and
health-confirmation policy remain unchanged. A watchdog is disarmed only after
their successful durable confirmation, once per launch. No user request can
write the private marker or health phase. -/
namespace Lemma.Platform.LemmaSim.TrialWatchdogKernel
open Lemma.Core0.Memory
open Lemma.Kernel.Memory.Access

def completed : UInt64 := BootHealthExecuted.state + 40

private def finish : Action :=
  .bind (Lemma.Drivers.PowerSafety.disarm) fun s _ => if s = 0 then
  .bind (Lemma.Drivers.Power.read 120) fun s armed => if s = 0 then
  if armed = 0 then
  .bind (write64 completed 1) fun s _ => if s = 0 then
  Lemma.Kernel.Console.record 0x47b 1 Lemma.Boot.TrialWatchdog.timeoutClocks 0 0
  else .done s 0 else .done Lemma.Boot.TrialWatchdog.invalidContext 0
  else .done s 0 else .done s 0

private def disarmIfHealthy : Action :=
  .bind (read64 completed) fun s done => if s = 0 then
  if done = 1 then .done 0 0 else
  .bind (read64 Lemma.Boot.TrialWatchdog.contextPolicy) fun s policy => if s = 0 then
  if policy = Lemma.Boot.TrialWatchdog.policyMagic then
  .bind (read64 Lemma.Boot.TrialWatchdog.contextTimeout) fun s timeout => if s = 0 then
  if timeout = Lemma.Boot.TrialWatchdog.timeoutClocks then
  .bind (read64 BootHealthExecuted.state) fun s phase => if s = 0 then
  if phase = 3 then
  .bind (read64 (BootHealthExecuted.state + 24)) fun s status => if s = 0 then
  if status = 0 then finish else .done Lemma.Boot.TrialWatchdog.invalidContext 0
  else .done s 0 else .done 0 0 else .done s 0
  else .done Lemma.Boot.TrialWatchdog.invalidContext 0 else .done s 0
  else .done 0 0 else .done s 0 else .done s 0

def boot : Action :=
  .bind (write64 completed 0) fun s _ => if s = 0 then
  NotebookKernel.siliconProductCourseReaderBoot else .done s 0

def dispatch (frame cause value : UInt64) : Action :=
  .bind (NotebookKernel.dispatchProductExecutedBulk frame cause value) fun s result =>
  if s = 0 then
  .bind disarmIfHealthy fun status _ => .done status result
  else .done s result

end Lemma.Platform.LemmaSim.TrialWatchdogKernel
