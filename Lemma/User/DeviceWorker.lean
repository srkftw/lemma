import Lemma.User.Syscall

/-! Bounded U-mode consumer for device bring-up. This production-linked probe
exercises actual device interrupts on an owned four-page trap stack. It is not
an ink application, and must not be described as a usable notebook. -/
namespace Lemma.User.DeviceWorker
open Lemma.Core0.Memory

def step : Action := Lemma.User.Syscall.yield
def main (_argument : UInt64) : Action := .loop step

end Lemma.User.DeviceWorker
