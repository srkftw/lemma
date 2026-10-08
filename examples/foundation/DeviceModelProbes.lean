import Lemma.Core0.DeviceModel
import examples.foundation.DeviceConformanceSupport

/-! Independent packet-model and source-encoder comparison probes. -/

namespace Lemma.Examples.Foundation.Device

open Lemma.Core0.Device.Model
open Lemma.Core0.Memory
open Lemma.Examples.Foundation.Device.Support

private def expect (label : String) (condition : Bool) : IO Unit := do
  unless condition do
    throw <| IO.userError s!"DEVICE_MODEL:{label}:failed"
  IO.println s!"DEVICE_MODEL:{label}:ok"

private def hasParseError (bytes : Array UInt8) (expected : UInt8) : Bool :=
  match parseRequest bytes with
  | .error status => status == expected
  | .ok _ => false

private def addRequest : Array UInt8 := #[
  0x4c, 0x4d, 0x51, 0x36, 1, 1, 16, 0,
  0x08, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01,
  0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
  0x02, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
]

def deviceModelProbe : IO Unit := do
  let request ← match parseRequest addRequest with
    | .ok request => pure request
    | .error status => throw <| IO.userError s!"DEVICE_MODEL:add-parse:{status.toNat}"
  let added := dispatch request
  expect "add64-wrap"
    (added.actionStatus == Status.ok && added.responseStatus? == some Status.ok &&
      added.value == 1 && request.requestId == 0x0102030405060708)

  let unsupported := dispatch {
    command := 0x7f, requestId := 9, payload := #[0xaa, 0xbb]
  }
  expect "unsupported-recovers"
    (unsupported.actionStatus == Status.ok &&
      unsupported.responseStatus? == some Status.unsupportedCommand &&
      unsupported.value == 0)

  let falseBranch := dispatch { command := 3, requestId := 10, payload := #[0] }
  expect "false-branch-only-ram"
    (falseBranch.actionStatus == Status.ok &&
      falseBranch.scratchMarker? == some 0x5a && falseBranch.uartPrefix.isEmpty)

  let trueBranch := dispatch { command := 3, requestId := 11, payload := #[1] }
  expect "true-branch-only-uart"
    (trueBranch.actionStatus == Status.ok && trueBranch.scratchMarker?.isNone &&
      trueBranch.uartPrefix == #[0xa5])

  let invalidBool := dispatch { command := 3, requestId := 12, payload := #[2] }
  expect "invalid-bool-terminal"
    (invalidBool.actionStatus == Status.malformedFrame && invalidBool.responseStatus?.isNone)

  let stress := dispatch {
    command := 4, requestId := 13, payload := #[3, 0, 0, 0]
  }
  expect "bounded-stress"
    (stress.actionStatus == Status.ok && stress.value == 3 &&
      stress.uartPrefix == #[0x55, 0x55, 0x55])

  expect "empty-timeout" (hasParseError #[] Status.rxTimeout)
  expect "truncated-header"
    (hasParseError #[0x4c, 0x4d, 0x51] Status.truncatedFrame)
  expect "invalid-length"
    (hasParseError #[0x4c, 0x4d, 0x51, 0x36, 1, 1, 17, 0,
      0, 0, 0, 0, 0, 0, 0, 0] Status.invalidLength)
  expect "malformed-magic"
    (hasParseError #[0, 0x4d, 0x51, 0x36, 1, 0x7f, 0, 0,
      0, 0, 0, 0, 0, 0, 0, 0] Status.malformedFrame)

  let ready := (List.range 21).toArray.map fun index => readyByte (UInt32.ofNat index)
  expect "compiled-ready-bytes"
    (ready == #[0x4c, 0x45, 0x4d, 0x4d, 0x41, 0x5f, 0x44, 0x45,
      0x56, 0x49, 0x43, 0x45, 0x2f, 0x31, 0x0a, 0x52, 0x45, 0x41,
      0x44, 0x59, 0x0a])

  let responseStatus : UInt8 := Status.unsupportedCommand
  let requestId : UInt64 := 0x0102030405060708
  let value : UInt64 := 0x8899aabbccddeeff
  let sourceResponse := (List.range 24).toArray.map fun index =>
    responseByte (UInt32.ofNat index) responseStatus requestId value
  expect "source-model-response-encoding"
    (sourceResponse == encodeResponse responseStatus requestId value)
  expect "response-size" (sourceResponse.size == 24)

#eval deviceModelProbe

end Lemma.Examples.Foundation.Device
