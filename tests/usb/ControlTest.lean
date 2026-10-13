import Lemma.USB.Control
open Lemma.USB.Control
private def check (p : Bool) (why : String) : IO Unit := if p then pure () else throw (IO.userError why)
private def setup (kind request value index length : UInt64) : UInt64 := kind ||| (request <<< 8) ||| (value <<< 16) ||| (index <<< 32) ||| (length <<< 48)
def main : IO Unit := do
  check (plan (setup 128 6 256 0 18) 0 0 = 4609) "device descriptor"
  check (plan (setup 128 6 256 0 8) 0 0 = 2049) "descriptor truncation"
  check (plan (setup 128 6 512 0 255) 7 0 = 8194) "configuration bounds"
  check (plan (setup 0 5 7 0 0) 0 0 = 458755) "SET_ADDRESS value binding"
  check (plan (setup 0 5 128 0 0) 0 0 = 0) "bad address"
  check (plan (setup 0 5 7 0 0) 7 1 = 0) "SET_ADDRESS configured rejects"
  check (plan (setup 0 9 1 0 0) 0 0 = 0) "configuration requires address"
  check (plan (setup 0 9 1 0 0) 7 0 = 65540) "SET_CONFIGURATION"
  check (plan (setup 128 8 0 0 1) 7 1 = 261) "GET_CONFIGURATION"
  check (plan (setup 2 1 0 129 0) 7 1 = 8454152) "CLEAR_FEATURE endpoint binding"
  check (plan (setup 2 1 0 130 0) 7 1 = 0) "unknown endpoint"
  check (plan (setup 128 6 768 0 12) 7 1 = 0) "strings explicitly unsupported"
  check (plan (setup 64 6 256 0 18) 7 1 = 0) "vendor cannot imitate standard"
  check (plan (setup 128 6 256 1 18) 7 1 = 0) "wrong descriptor index"
  check (plan (setup 0 9 2 0 0) 7 0 = 0) "unsupported configuration"
  let device : Array UInt8 := #[18,1,0,2,0,0,0,64,0,0,0,0,0,1,0,0,0,1]
  let config : Array UInt8 := #[9,2,32,0,1,1,0,128,50,9,4,0,0,2,255,0,0,0,7,5,129,2,64,0,0,7,5,2,2,64,0,0]
  for i in [0:device.size] do check (((descriptorWord 1 (i/8).toUInt64 >>> (8*(i%8)).toUInt64) &&& 255).toUInt8 = device[i]!) "device independent literal"
  for i in [0:config.size] do check (((descriptorWord 2 (i/8).toUInt64 >>> (8*(i%8)).toUInt64) &&& 255).toUInt8 = config[i]!) "configuration independent literal"
  IO.println "USB_CONTROL_LEAN_PASS exact requests/descriptor bytes and malformed/unadmitted requests"
