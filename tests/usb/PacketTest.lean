import USBPacket
open LemmaSim.USB
private def isError {α : Type} (e : Except String α) : Bool := match e with | .error _ => true | .ok _ => false
private def check (p : Bool) (text : String) : IO Unit := if p then pure () else throw (IO.userError text)
def main : IO UInt32 := do
  check (crc16 "123456789".toUTF8 = 0xb4c8) "independent CRC16 standard check"
  let .ok out := token 0xe1 0 0 | throw (IO.userError "OUT token")
  check (out == ByteArray.mk #[0xe1,0,0x10]) "independent OUT0 token vector"
  let payload := ByteArray.mk #[0,1,2,3,254,255]
  for one in [false,true] do
    let .ok packet := dataPacket one payload | throw (IO.userError "DATA encode")
    let .ok (decoded,bytes) := dataPayload packet | throw (IO.userError "DATA decode")
    check (decoded == one && bytes == payload) "actual DATA roundtrip"
    let bad := packet.set! 2 (packet[2]! ^^^ 1)
    check (isError (dataPayload bad)) "corrupted DATA accepted"
  check (isError (token 0xe1 128 0)) "bad address"
  check (isError (token 0xd2 0 0)) "handshake as token"
  check (isError (dataPacket false (ByteArray.mk (Array.replicate 65 0)))) "packet resource"
  check (isError (dataPayload (ByteArray.mk #[0xc3,0]))) "short DATA"
  check (!validPID 0xc2) "PID complement"
  IO.println "USB_PACKET_POLICY_PASS"
  return 0
