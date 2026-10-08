import Lemma.Core0.Device

/-!
A finite host-side model of the four `core0-v0.5` UART operations and the
bounded packet contract.  This model is executable Lean, but it is not used to
generate target LLVM and is not a proof that lowering preserves the model.
-/

namespace Lemma.Core0.Device.Model

open Lemma.Core0.Device
open Lemma.Core0.Memory

/-- Physical observations are deliberately lower level than source operations:
each access is bracketed by two distinct ordering events. -/
inductive Event where
  | fence
  | read (offset : UInt64) (value : UInt8)
  | write (offset : UInt64) (value : UInt8)
  deriving BEq, Inhabited, Repr

structure State where
  lsrScript : Array UInt8 := #[]
  lsrCursor : Nat := 0
  rxBytes : Array UInt8 := #[]
  rxCursor : Nat := 0
  txBytes : Array UInt8 := #[]
  fifoEnabled : Bool := false
  fifoResetCount : Nat := 0
  latchedLineErrors : UInt8 := 0
  events : Array Event := #[]
  deriving BEq, Inhabited, Repr

structure Result where
  status : UInt8
  value : UInt64
  state : State
  deriving BEq, Inhabited, Repr

namespace State

def append (state : State) (event : Event) : State :=
  { state with events := state.events.push event }

/-- Host-side arrival after FIFO initialization. -/
def injectRx (state : State) (bytes : Array UInt8) : State :=
  { state with rxBytes := bytes, rxCursor := 0 }

def withLsrScript (state : State) (script : Array UInt8) : State :=
  { state with lsrScript := script, lsrCursor := 0 }

def withLineErrors (state : State) (errors : UInt8) : State :=
  { state with latchedLineErrors := errors &&& UART.lsrErrorMask }

def unreadRx (state : State) : Nat := state.rxBytes.size - state.rxCursor

end State

def orderedRead (state : State) (offset : UInt64) (value : UInt8) : State :=
  ((state.append .fence).append (.read offset value)).append .fence

def orderedWrite (state : State) (offset : UInt64) (value : UInt8) : State :=
  ((state.append .fence).append (.write offset value)).append .fence

private def defaultLsr (state : State) : UInt8 :=
  let ready := if state.rxCursor < state.rxBytes.size then UART.lsrDataReady else 0
  ready ||| UART.lsrThrEmpty ||| UART.lsrTransmitterEmpty

/-- Model one ordered volatile LSR byte read.  A scripted sample is consumed
when present; otherwise THRE/TEMT and RX occupancy determine the value.  As in
the pinned QEMU UART, an LSR observation clears only the BI/OE latches;
parity/frame-error bits remain set. The scripted observations abstract backend
timing rather than model the asynchronous transmitter or FIFO occupancy. -/
def uartReadStatus (state : State) : Result :=
  let scripted := state.lsrScript.getD state.lsrCursor (defaultLsr state)
  let value := scripted ||| state.latchedLineErrors
  let nextCursor :=
    if state.lsrCursor < state.lsrScript.size then state.lsrCursor + 1
    else state.lsrCursor
  let state := {
    state with
    lsrCursor := nextCursor
    latchedLineErrors := state.latchedLineErrors &&& 0xed
  }
  { status := Status.ok, value := value.toUInt64,
    state := orderedRead state UART.lsrOffset value }

/-- Model one ordered RBR read.  It consumes at most one pending byte. -/
def uartReadByte (state : State) : Result :=
  let hasByte := state.rxCursor < state.rxBytes.size
  let value := if hasByte then state.rxBytes.getD state.rxCursor 0 else 0
  let state := if hasByte then { state with rxCursor := state.rxCursor + 1 } else state
  { status := Status.ok, value := value.toUInt64,
    state := orderedRead state UART.rbrThrOffset value }

/-- Model one ordered THR write.  `txBytes` is the externally visible byte
stream; later FIFO resets cannot retroactively erase transmitted bytes. -/
def uartWriteByte (state : State) (value : UInt8) : Result :=
  let state := { state with txBytes := state.txBytes.push value }
  { status := Status.ok, value := 0,
    state := orderedWrite state UART.rbrThrOffset value }

/-- Enable FIFO mode and apply both receive/transmit reset bits.  Pending input
that arrived before initialization is discarded. -/
def uartEnableAndResetFifo (state : State) : Result :=
  let state := {
    state with
    fifoEnabled := true
    fifoResetCount := state.fifoResetCount + 1
    rxCursor := state.rxBytes.size
  }
  { status := Status.ok, value := 0,
    state := orderedWrite state UART.fcrOffset UART.fcrEnableAndReset }

/-! The finite UART model can step only the four closed v0.5 device primitives.
It deliberately does not pretend to simulate the Gate 7 machine trap substrate. -/

inductive ActionStepDiagnosticCode where
  | nonDeviceActionUnsupported
  | trapActionUnsupported
  | timerActionUnsupported
  deriving BEq, DecidableEq, Inhabited, Repr

structure ActionStepDiagnostic where
  code : ActionStepDiagnosticCode
  message : String
  deriving Inhabited, Repr

/-- Execute exactly one top-level UART Action and expose its instantiated
continuation.  RAM, control-flow, call, fold, and trap Actions belong to their
own models; traps fail explicitly instead of receiving fabricated hardware state. -/
def stepDeviceAction (state : State) (action : Action) :
    Except ActionStepDiagnostic (Result × Action) :=
  match action with
  | .uartReadStatus next =>
      let result := uartReadStatus state
      .ok (result, next result.status result.value)
  | .uartReadByte next =>
      let result := uartReadByte state
      .ok (result, next result.status result.value)
  | .uartWriteByte value next =>
      let result := uartWriteByte state value
      .ok (result, next result.status)
  | .uartEnableAndResetFifo next =>
      let result := uartEnableAndResetFifo state
      .ok (result, next result.status)
  | .trapEcall _ | .trapBreakpoint _ | .trapUnexpectedEcall _ |
      .trapIllegalInstruction _ =>
      .error {
        code := .trapActionUnsupported
        message := "the finite UART model does not simulate synchronous trap actions"
      }
  | .timerReadTime _ | .timerSetCompare _ _ | .timerReadPending _ |
      .irqSaveDisable _ | .irqRestore _ _ | .timerSetInterrupt _ _ |
      .timerProbe _ =>
      .error {
        code := .timerActionUnsupported
        message := "the finite UART model does not simulate timer/interrupt actions"
      }
  | _ =>
      .error {
        code := .nonDeviceActionUnsupported
        message := "the finite UART primitive model received a non-device Action"
      }

/-- Finite source-level receive polling over the primitive model. -/
def receiveByte : Nat → State → Result
  | 0, state => { status := Status.rxTimeout, value := 0, state }
  | remaining + 1, state =>
      let statusResult := uartReadStatus state
      let lsr := statusResult.value.toUInt8
      if statusResult.status != Status.ok then statusResult
      else if (lsr &&& UART.lsrErrorMask) != 0 then
        { status := Status.lineError, value := 0, state := statusResult.state }
      else if (lsr &&& UART.lsrDataReady) = UART.lsrDataReady then
        uartReadByte statusResult.state
      else
        receiveByte remaining statusResult.state

/-- Finite source-level transmit polling over the primitive model. -/
def sendByte : Nat → State → UInt8 → Result
  | 0, state, _ => { status := Status.txTimeout, value := 0, state }
  | remaining + 1, state, value =>
      let statusResult := uartReadStatus state
      let lsr := statusResult.value.toUInt8
      if statusResult.status != Status.ok then statusResult
      else if (lsr &&& UART.lsrErrorMask) != 0 then
        { status := Status.lineError, value := 0, state := statusResult.state }
      else if (lsr &&& UART.lsrThrEmpty) = UART.lsrThrEmpty then
        uartWriteByte statusResult.state value
      else
        sendByte remaining statusResult.state value

/-- Finite final-drain polling. -/
def drain : Nat → State → Result
  | 0, state => { status := Status.txTimeout, value := 0, state }
  | remaining + 1, state =>
      let statusResult := uartReadStatus state
      let lsr := statusResult.value.toUInt8
      if statusResult.status != Status.ok then statusResult
      else if (lsr &&& UART.lsrErrorMask) != 0 then
        { status := Status.lineError, value := 0, state := statusResult.state }
      else if (lsr &&& (UART.lsrThrEmpty ||| UART.lsrTransmitterEmpty)) =
          (UART.lsrThrEmpty ||| UART.lsrTransmitterEmpty) then
        { status := Status.ok, value := 0, state := statusResult.state }
      else
        drain remaining statusResult.state

/-! ## Independent bounded packet model -/

private def readLittleEndian (bytes : Array UInt8) (offset count : Nat) : UInt64 :=
  UInt64.ofNat <| (List.range count).foldl (init := 0) fun value index =>
    value + (bytes.getD (offset + index) 0).toNat * 2 ^ (8 * index)

def encodeLittleEndian (value : UInt64) (count : Nat) : Array UInt8 :=
  (List.range count).foldl (init := #[]) fun bytes index =>
    bytes.push <| UInt8.ofNat ((value.toNat / 2 ^ (8 * index)) % 256)

structure Request where
  command : UInt8
  requestId : UInt64
  payload : Array UInt8
  deriving BEq, Inhabited, Repr

/-- Model the exact receive boundary for one frame. -/
def parseRequest (bytes : Array UInt8) : Except UInt8 Request := do
  if bytes.isEmpty then throw Status.rxTimeout
  if bytes.size < 16 then throw Status.truncatedFrame
  let length := (bytes.getD 6 0).toNat
  if length > 16 then throw Status.invalidLength
  if bytes.size < 16 + length then throw Status.truncatedFrame
  if readLittleEndian bytes 0 4 != 0x36514d4c then throw Status.malformedFrame
  if bytes.getD 4 0 != 1 then throw Status.malformedFrame
  if bytes.getD 7 0 != 0 then throw Status.malformedFrame
  pure {
    command := bytes.getD 5 0
    requestId := readLittleEndian bytes 8 8
    payload := bytes.extract 16 (16 + length)
  }

structure Dispatch where
  /-- Final Action status: zero means the session may continue. -/
  actionStatus : UInt8
  /-- `some` means a common response frame is emitted. -/
  responseStatus? : Option UInt8
  value : UInt64
  uartPrefix : Array UInt8 := #[]
  /-- Final scratch+64 byte read back by command 3. -/
  scratchMarker? : Option UInt8 := none
  deriving BEq, Inhabited, Repr

def dispatch (request : Request) : Dispatch :=
  if request.command = 1 then
    if request.payload.size = 16 then {
      actionStatus := Status.ok
      responseStatus? := some Status.ok
      value := readLittleEndian request.payload 0 8 + readLittleEndian request.payload 8 8
    } else { actionStatus := Status.invalidLength, responseStatus? := none, value := 0 }
  else if request.command = 2 then
    if request.payload.size = 16 then {
      actionStatus := Status.ok
      responseStatus? := some Status.ok
      value := readLittleEndian request.payload 0 8 ^^^ readLittleEndian request.payload 8 8
    } else { actionStatus := Status.invalidLength, responseStatus? := none, value := 0 }
  else if request.command = 3 then
    if request.payload.size != 1 then
      { actionStatus := Status.invalidLength, responseStatus? := none, value := 0 }
    else if request.payload.getD 0 0 = 0 then {
      actionStatus := Status.ok
      responseStatus? := some Status.ok
      value := 0x5a00
      scratchMarker? := some 0x5a
    } else if request.payload.getD 0 0 = 1 then {
      actionStatus := Status.ok
      responseStatus? := some Status.ok
      value := 0x3c01
      uartPrefix := #[0xa5]
      scratchMarker? := some 0x3c
    } else
      { actionStatus := Status.malformedFrame, responseStatus? := none, value := 0,
        scratchMarker? := some 0x3c }
  else if request.command = 4 then
    if request.payload.size != 4 then
      { actionStatus := Status.invalidLength, responseStatus? := none, value := 0 }
    else
      let count := readLittleEndian request.payload 0 4
      if count ≤ 65535 then {
        actionStatus := Status.ok
        responseStatus? := some Status.ok
        value := count
        uartPrefix := Array.replicate count.toNat 0x55
      } else
        { actionStatus := Status.invalidLength, responseStatus? := none, value := 0 }
  else {
    actionStatus := Status.ok
    responseStatus? := some Status.unsupportedCommand
    value := 0
  }

def encodeResponse (status : UInt8) (requestId value : UInt64) : Array UInt8 :=
  #[0x4c, 0x4d, 0x53, 0x36, 1, status, 8, 0] ++
    encodeLittleEndian requestId 8 ++ encodeLittleEndian value 8

end Lemma.Core0.Device.Model
