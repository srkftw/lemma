import Lemma.Core0.Device

/-!
Closed helper declarations for the `core0-v0.5` compiled-device session.

Every UART operation below is one of the four exact source constructors in
`Lemma.Core0.Memory.Action`.  Polling is finite, and status 10 is used only as
an internal early-stop signal which the enclosing helper consumes.
-/

namespace Lemma.Examples.Foundation.Device.Support

open Lemma.Core0.Device
open Lemma.Core0.Memory

def pollBudget : UInt32 := 1000000

def readyLength : UInt32 := 21

def readyByte (index : UInt32) : UInt8 :=
  if index = 0 then 0x4c       -- L
  else if index = 1 then 0x45  -- E
  else if index = 2 then 0x4d  -- M
  else if index = 3 then 0x4d  -- M
  else if index = 4 then 0x41  -- A
  else if index = 5 then 0x5f  -- _
  else if index = 6 then 0x44  -- D
  else if index = 7 then 0x45  -- E
  else if index = 8 then 0x56  -- V
  else if index = 9 then 0x49  -- I
  else if index = 10 then 0x43 -- C
  else if index = 11 then 0x45 -- E
  else if index = 12 then 0x2f -- /
  else if index = 13 then 0x31 -- 1
  else if index = 14 then 0x0a
  else if index = 15 then 0x52 -- R
  else if index = 16 then 0x45 -- E
  else if index = 17 then 0x41 -- A
  else if index = 18 then 0x44 -- D
  else if index = 19 then 0x59 -- Y
  else 0x0a

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

/-- Header and payload receiver callback.  `timeoutMode = 0` distinguishes an
empty initial receive (status 12) from a partial header; payload mode converts
every receive timeout to the terminal truncated-frame status. -/
def receiveIntoStep (index _count : UInt32) (accumulator regionWord baseOffset
    timeoutMode _unused : UInt64) : Action :=
  Action.bind receiveByte fun status byte =>
    if status = Status.ok then
      Action.store8 regionWord.toUInt8 (baseOffset + index.toUInt64) byte.toUInt8
        fun writeStatus =>
          if writeStatus = Status.ok then
            Action.done Status.ok (accumulator + 1)
          else
            Action.done writeStatus accumulator
    else if status = Status.rxTimeout then
      if timeoutMode = 0 then
        if index = 0 then
          Action.done Status.rxTimeout accumulator
        else
          Action.done Status.truncatedFrame accumulator
      else
        Action.done Status.truncatedFrame accumulator
    else
      Action.done status accumulator

def receiveHeader : Action :=
  Action.boundedFoldU64 16 receiveIntoStep 16 0 RegionId.scratch.toUInt64 0 0 0
    fun status count => Action.done status count

def receivePayload (count : UInt32) : Action :=
  Action.boundedFoldU64 16 receiveIntoStep count 0 RegionId.scratch.toUInt64 16 1 0
    fun status received => Action.done status received

/-- Exact byte encoding of the fixed 24-byte response frame. -/
def responseByte (index : UInt32) (responseStatus : UInt8)
    (requestId value : UInt64) : UInt8 :=
  if index = 0 then 0x4c       -- L
  else if index = 1 then 0x4d  -- M
  else if index = 2 then 0x53  -- S
  else if index = 3 then 0x36  -- 6
  else if index = 4 then 1
  else if index = 5 then responseStatus
  else if index = 6 then 8
  else if index = 7 then 0
  else if index = 8 then requestId.toUInt8
  else if index = 9 then (requestId >>> 8).toUInt8
  else if index = 10 then (requestId >>> 16).toUInt8
  else if index = 11 then (requestId >>> 24).toUInt8
  else if index = 12 then (requestId >>> 32).toUInt8
  else if index = 13 then (requestId >>> 40).toUInt8
  else if index = 14 then (requestId >>> 48).toUInt8
  else if index = 15 then (requestId >>> 56).toUInt8
  else if index = 16 then value.toUInt8
  else if index = 17 then (value >>> 8).toUInt8
  else if index = 18 then (value >>> 16).toUInt8
  else if index = 19 then (value >>> 24).toUInt8
  else if index = 20 then (value >>> 32).toUInt8
  else if index = 21 then (value >>> 40).toUInt8
  else if index = 22 then (value >>> 48).toUInt8
  else (value >>> 56).toUInt8

/-- Encode each response byte into checked output RAM before transmitting it.
This keeps the source-visible RAM effect and the UART byte stream tied to the
same compiled scalar encoder. -/
def responseStep (index _count : UInt32) (accumulator responseStatus requestId
    value _unused : UInt64) : Action :=
  let byte := responseByte index responseStatus.toUInt8 requestId value
  Action.store8 RegionId.output index.toUInt64 byte fun memoryStatus =>
    if memoryStatus = Status.ok then
      Action.bind (sendByte byte) fun sendStatus _sent =>
        if sendStatus = Status.ok then
          Action.done Status.ok (accumulator + 1)
        else
          Action.done sendStatus accumulator
    else
      Action.done memoryStatus accumulator

def sendResponse (responseStatus : UInt8) (requestId value : UInt64) : Action :=
  Action.boundedFoldU64 24 responseStep 24 0 responseStatus.toUInt64 requestId value 0
    fun status sent => Action.done status sent

def readyStep (index _count : UInt32) (accumulator _context0 _context1
    _context2 _context3 : UInt64) : Action :=
  Action.bind (sendByte (readyByte index)) fun status _value =>
    if status = Status.ok then
      Action.done Status.ok (accumulator + 1)
    else
      Action.done status accumulator

def sendReady : Action :=
  Action.boundedFoldU64 21 readyStep readyLength 0 0 0 0 0
    fun status sent => Action.done status sent

def repeatedByteStep (_index _count : UInt32) (accumulator byteWord
    _context1 _context2 _context3 : UInt64) : Action :=
  Action.bind (sendByte byteWord.toUInt8) fun status _value =>
    if status = Status.ok then
      Action.done Status.ok (accumulator + 1)
    else
      Action.done status accumulator

def sendRepeatedByte (count : UInt32) (byte : UInt8) : Action :=
  Action.boundedFoldU64 65535 repeatedByteStep count 0 byte.toUInt64 0 0 0
    fun status sent => Action.done status sent

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

end Lemma.Examples.Foundation.Device.Support
