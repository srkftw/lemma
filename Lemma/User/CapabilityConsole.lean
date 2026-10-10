import Lemma.User.Console
import Lemma.User.Capability

/-! The same binary serializer uses an explicit caller-local Console grant.
The managed kernel denies the historical ungranted console operation. -/
namespace Lemma.User.CapabilityConsole
open Lemma.Core0.Memory

def record (handle tag a b c d : UInt64) : Action :=
  .bind (Console.prepareRecord tag a b c d) fun s length =>
  if s = 0 then
    .bind (Capability.consoleWrite handle Console.packetAddress length) fun s count =>
    if s = 0 then if count = 88 then .done 0 0 else .done Console.failure count
    else .done s 0
  else .done s 0

end Lemma.User.CapabilityConsole
