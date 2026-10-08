/-!
Closed host/guest protocol constants for the Gate 6 compiled-device session.

The values in this module are shared by the elaborated Lean device program,
the generated machine harness, and host-side evidence tooling.  They describe
the byte protocol only; they do not implement UART access or grant MMIO
authority.
-/

namespace Lemma.Compiler.Test.DeviceABI

def name : String := "lemma-device-session-v1"
def contractVersion : String := "core0-v0.5"

structure Configuration where
  suiteId : Nat
  sourceSeed : Nat
  runtimeSeed : Nat
  deriving Repr, BEq, Inhabited

def Configuration.validate (config : Configuration) : Except String Unit := do
  for (label, value) in #[
      ("suite id", config.suiteId),
      ("source seed", config.sourceSeed),
      ("runtime seed", config.runtimeSeed)] do
    unless value < 2 ^ 64 do
      throw s!"device-suite {label} exceeds UInt64"

def uartBase : Nat := 0x10000000
def uartSpan : Nat := 0x100
def uartClockHz : Nat := 3686400
def uartInterrupt : Nat := 10
def uartRegisterShift : Nat := 0
def uartRegisterWidthBytes : Nat := 1
def uartImplementedBytes : Nat := 8

def uartRbrOffset : Nat := 0
def uartThrOffset : Nat := 0
def uartFcrOffset : Nat := 2
def uartIirOffset : Nat := 2
def uartLsrOffset : Nat := 5

def lsrDataReady : Nat := 0x01
def lsrErrorMask : Nat := 0x1e
def lsrThrEmpty : Nat := 0x20
def lsrTransmitterEmpty : Nat := 0x40
def fcrEnableAndClear : Nat := 0x07

def readyBanner : String := "LEMMA_DEVICE/1\nREADY\n"
def requestsPerSession : Nat := 2
def pollBudget : Nat := 1000000

def requestMagic : Nat := 0x36514d4c
def responseMagic : Nat := 0x36534d4c
def version : Nat := 1
def requestHeaderBytes : Nat := 16
def maximumPayloadBytes : Nat := 16
def maximumRequestBytes : Nat := requestHeaderBytes + maximumPayloadBytes
def responseBytes : Nat := 24
def responsePayloadBytes : Nat := 8

def requestMagicOffset : Nat := 0
def requestVersionOffset : Nat := 4
def requestCommandOffset : Nat := 5
def requestLengthOffset : Nat := 6
def requestFlagsOffset : Nat := 7
def requestIdOffset : Nat := 8

def responseMagicOffset : Nat := 0
def responseVersionOffset : Nat := 4
def responseStatusOffset : Nat := 5
def responseLengthOffset : Nat := 6
def responseFlagsOffset : Nat := 7
def responseIdOffset : Nat := 8
def responseValueOffset : Nat := 16

def commandAdd64 : Nat := 1
def commandXor64 : Nat := 2
def commandBranch : Nat := 3
def commandTxStress : Nat := 4

def add64PayloadBytes : Nat := 16
def xor64PayloadBytes : Nat := 16
def branchPayloadBytes : Nat := 1
def txStressPayloadBytes : Nat := 4
def txStressMaximumBytes : Nat := 65535
def txStressByte : Nat := 0x55

def falseBranchScratchOffset : Nat := 64
def falseBranchMarker : Nat := 0x5a
def trueBranchUartMarker : Nat := 0xa5

def statusOk : Nat := 0
/-- Internal polling result; it must never appear in a public response or as
the final action status returned to the machine harness. -/
def statusPollAgain : Nat := 10
def statusTxTimeout : Nat := 11
def statusRxTimeout : Nat := 12
def statusLineError : Nat := 13
def statusMalformedFrame : Nat := 14
def statusTruncatedFrame : Nat := 15
def statusInvalidLength : Nat := 16
def statusUnsupportedCommand : Nat := 17

def publicStatuses : Array (Nat × String) := #[
  (statusOk, "ok"),
  (statusTxTimeout, "tx-timeout"),
  (statusRxTimeout, "rx-timeout"),
  (statusLineError, "line-error"),
  (statusMalformedFrame, "malformed-frame"),
  (statusTruncatedFrame, "truncated-frame"),
  (statusInvalidLength, "invalid-length"),
  (statusUnsupportedCommand, "unsupported-command")
]

def isPublicStatus (status : Nat) : Bool :=
  publicStatuses.any fun entry => entry.1 == status

end Lemma.Compiler.Test.DeviceABI
