import Lemma.Core0.DeviceModel

/-! Small kernel-checked facts used by the finite UART contract. -/

namespace Lemma.Core0.Device

namespace Model

theorem empty_write_has_ordered_events (byte : UInt8) :
    (uartWriteByte (default : State) byte).state.events =
      #[.fence, .write UART.rbrThrOffset byte, .fence] := by
  rfl

theorem fifo_reset_discards_pending_rx (state : State) :
    (uartEnableAndResetFifo state).state.rxCursor = state.rxBytes.size := by
  rfl

theorem fifo_reset_is_ordered (state : State) :
    (uartEnableAndResetFifo state).state.events =
      ((state.events.push .fence).push
        (.write UART.fcrOffset UART.fcrEnableAndReset)).push .fence := by
  rfl

theorem response_size (status : UInt8) (requestId value : UInt64) :
    (encodeResponse status requestId value).size = 24 := by
  simp [encodeResponse, encodeLittleEndian]

end Model
end Lemma.Core0.Device
