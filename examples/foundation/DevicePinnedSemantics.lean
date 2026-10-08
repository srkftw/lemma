import Lemma.Core0.DeviceModel

/-! Executable probes for ordered UART primitive and polling semantics. -/

namespace Lemma.Examples.Foundation.Device

open Lemma.Core0.Device
open Lemma.Core0.Device.Model
open Lemma.Core0.Memory

private def expect (label : String) (condition : Bool) : IO Unit := do
  unless condition do
    throw <| IO.userError s!"PINNED_DEVICE:{label}:failed"
  IO.println s!"PINNED_DEVICE:{label}:ok"

def devicePinnedSemanticsProbe : IO Unit := do
  expect "catalog" catalogValid

  let initial : State := { rxBytes := #[0xaa, 0xbb] }
  let reset := uartEnableAndResetFifo initial
  expect "fifo-reset-status" (reset.status == Status.ok)
  expect "fifo-reset-discards-rx"
    (reset.state.fifoEnabled && reset.state.rxCursor == 2 &&
      reset.state.fifoResetCount == 1)
  expect "fifo-reset-ordered"
    (reset.state.events ==
      #[.fence, .write UART.fcrOffset UART.fcrEnableAndReset, .fence])

  let received := receiveByte 2 (reset.state.injectRx #[0x34])
  expect "rx-consumes"
    (received.status == Status.ok && received.value == 0x34 &&
      received.state.rxCursor == 1 && received.state.events.size == 9)

  let delayedRx :=
    ((default : State).injectRx #[0x7e]).withLsrScript #[0x00, UART.lsrDataReady]
  let delayed := receiveByte 2 delayedRx
  expect "rx-scripted-delay"
    (delayed.status == Status.ok && delayed.value == 0x7e &&
      delayed.state.lsrCursor == 2 && delayed.state.events.size == 9)

  let timeoutState := (default : State).withLsrScript #[0x00, 0x00]
  let timedOut := receiveByte 2 timeoutState
  expect "rx-timeout"
    (timedOut.status == Status.rxTimeout && timedOut.state.events.size == 6)

  let errorState := (default : State).withLineErrors 0x02
  let lineError := receiveByte 1 errorState
  expect "line-error-cleared-by-lsr"
    (lineError.status == Status.lineError &&
      lineError.state.latchedLineErrors == 0 && lineError.state.events.size == 3)

  let allErrors := uartReadStatus ((default : State).withLineErrors 0x1e)
  let remainingErrors := uartReadStatus allErrors.state
  expect "lsr-clears-only-break-overrun"
    (allErrors.value.toUInt8 &&& 0x1e == 0x1e &&
      allErrors.state.latchedLineErrors == 0x0c &&
      remainingErrors.value.toUInt8 &&& 0x1e == 0x0c)

  let txState := (default : State).withLsrScript #[0x00, UART.lsrThrEmpty]
  let transmitted := sendByte 2 txState 0xa5
  expect "tx-scripted-ready"
    (transmitted.status == Status.ok && transmitted.state.txBytes == #[0xa5] &&
      transmitted.state.events.size == 9)

  let txTimeout := sendByte 2 timeoutState 0x55
  expect "tx-timeout"
    (txTimeout.status == Status.txTimeout && txTimeout.state.txBytes.isEmpty &&
      txTimeout.state.events.size == 6)

  let drainState := (default : State).withLsrScript #[0x20, 0x60]
  let drained := drain 2 drainState
  expect "drain-requires-temt"
    (drained.status == Status.ok && drained.state.events.size == 6)

#eval devicePinnedSemanticsProbe

end Lemma.Examples.Foundation.Device
