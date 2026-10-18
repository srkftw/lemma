import Lemma.Multimodal.OpticalDerived
import Lemma.Boot.RecoveryExecuted
namespace Lemma.Multimodal.OpticalDerivedProbe
open Lemma.Core0.Memory Lemma.Kernel.Memory
private def sendByte (i _ : UInt32) (acc word _ _ _ : UInt64) : Action :=
  .bind (Lemma.Boot.RecoveryExecuted.transmitByte ((word >>> (i.toUInt64*8)) &&& 255)) fun s _ => .done s acc
private def sendWord (word : UInt64) : Action :=
  .boundedFoldU64 8 sendByte 8 0 word 0 0 0 fun s v => .done s v
private def transmitStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (0x80412000+i.toUInt64*8)) fun s word => if s = 0 then
  .bind (sendWord word) fun s _ => .done s acc else .done s 0

def entry : Action :=
  .uartEnableAndResetFifo fun s => if s = 0 then
  .bind (OpticalDerived.evaluate 0x80410000 0x80411000 0x80412000) fun s _ => if s = 0 then
  .boundedFoldU64 40 transmitStep 40 0 0 0 0 0 fun s v => .done s v
  else .done s 0 else .done s 0
end Lemma.Multimodal.OpticalDerivedProbe
