import Lemma.Platform.LemmaSim.Entry
import Lemma.Platform.Silicon.Development.DeviceProbe

namespace Lemma.Platform.Silicon.Development.DeviceEntry
open Lemma.Core0.Memory
def boot : Action :=
  .bind (Lemma.Platform.LemmaSim.Entry.initializeBinding 1) fun s _ => if s = 0 then
  .bind DeviceProbe.run fun s _ => if s = 0 then Lemma.Platform.LemmaSim.Entry.start else .done s 0
  else .done s 0
def dispatch (frame cause value : UInt64) : Action :=
  Lemma.Platform.LemmaSim.Entry.dispatch frame cause value
end Lemma.Platform.Silicon.Development.DeviceEntry
