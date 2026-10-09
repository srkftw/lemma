import Lemma.Core0.Device

/-! Maintained bounded 16550 UART algorithms. Legacy fixtures are clients. -/
namespace Lemma.Platform.LemmaVM.ConsoleDevice
open Lemma.Core0.Device
open Lemma.Core0.Memory
def pollBudget : UInt32 := 1000000

/-- One transmit poll.  Read errors are terminal; a ready transmitter performs
exactly one byte write and asks the enclosing fold to stop. -/
def transmitPollStep (_index _count : UInt32) (accumulator byteWord
    _context1 _context2 _context3 : UInt64) : Action :=
  Action.uartReadStatus fun status value =>
    if status = Status.ok then
      let lsr := value.toUInt8
      if (lsr &&& UART.lsrErrorMask) = 0 then
        if (lsr &&& UART.lsrThrEmpty) = UART.lsrThrEmpty then
          Action.uartWriteByte byteWord.toUInt8 fun writeStatus =>
            if writeStatus = Status.ok then
              Action.done Status.iterationStop accumulator
            else
              Action.done writeStatus accumulator
        else
          Action.done Status.ok accumulator
      else
        Action.done Status.lineError accumulator
    else
      Action.done status accumulator

/-- Send one byte or return the finite transmit timeout.  Internal fold-stop
status is converted back to public success here. -/
def sendByte (byte : UInt8) : Action :=
  Action.boundedFoldU64 1000000 transmitPollStep pollBudget 0 byte.toUInt64 0 0 0
    fun status value =>
      if status = Status.iterationStop then
        Action.done Status.ok value
      else if status = Status.ok then
        Action.done Status.txTimeout 0
      else
        Action.done status value

/-- One receive poll.  Reading RBR occurs only after DR is observed. -/
def receivePollStep (_index _count : UInt32) (accumulator _context0
    _context1 _context2 _context3 : UInt64) : Action :=
  Action.uartReadStatus fun status value =>
    if status = Status.ok then
      let lsr := value.toUInt8
      if (lsr &&& UART.lsrErrorMask) = 0 then
        if (lsr &&& UART.lsrDataReady) = UART.lsrDataReady then
          Action.uartReadByte fun readStatus byte =>
            if readStatus = Status.ok then
              Action.done Status.iterationStop byte
            else
              Action.done readStatus accumulator
        else
          Action.done Status.ok accumulator
      else
        Action.done Status.lineError accumulator
    else
      Action.done status accumulator

/-- Receive one byte or return the finite receive timeout. -/
def receiveByte : Action :=
  Action.boundedFoldU64 1000000 receivePollStep pollBudget 0 0 0 0 0
    fun status value =>
      if status = Status.iterationStop then
        Action.done Status.ok value
      else if status = Status.ok then
        Action.done Status.rxTimeout 0
      else
        Action.done status value

/-- Poll until both THRE and TEMT are observed. -/
def drainPollStep (_index _count : UInt32) (accumulator _context0
    _context1 _context2 _context3 : UInt64) : Action :=
  Action.uartReadStatus fun status value =>
    if status = Status.ok then
      let lsr := value.toUInt8
      if (lsr &&& UART.lsrErrorMask) = 0 then
        if (lsr &&& (UART.lsrThrEmpty ||| UART.lsrTransmitterEmpty)) =
            (UART.lsrThrEmpty ||| UART.lsrTransmitterEmpty) then
          Action.done Status.iterationStop accumulator
        else
          Action.done Status.ok accumulator
      else
        Action.done Status.lineError accumulator
    else
      Action.done status accumulator

def drain : Action :=
  Action.boundedFoldU64 1000000 drainPollStep pollBudget 0 0 0 0 0
    fun status value =>
      if status = Status.iterationStop then
        Action.done Status.ok value
      else if status = Status.ok then
        Action.done Status.txTimeout 0
      else
        Action.done status value

end Lemma.Platform.LemmaVM.ConsoleDevice
