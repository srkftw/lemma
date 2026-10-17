/-! Exact standard-request policy for the modeled USB FS device. No hardware
binding is supplied here. Unsupported standard/class/vendor requests STALL.
Unassigned VID/PID0 describe only this development simulation, not registered
physical USB products. Returned plan is untrusted until the caller performs the
actual control transfer; setting address/configuration requires status ACK. -/
namespace Lemma.USB.Control

def invalid : UInt64 := 0

def requestByte (setup index : UInt64) : UInt64 :=
  if index < 8 then (setup >>> (index*8)) &&& 255 else 0

/-- Low8 action, bits8..15 response bytes, bits16..31 request value.
1 device descriptor,2 configuration descriptor,3 address,4 configuration,
5 current configuration,6 device status,7 endpoint status,8 clear endpoint halt,
9 set endpoint halt,10 interface,11 set interface. Zero means STALL. -/
def plan (setup address configuration : UInt64) : UInt64 :=
  let kind := setup &&& 255
  let request := (setup >>> 8) &&& 255
  let value := (setup >>> 16) &&& 65535
  let index := (setup >>> 32) &&& 65535
  let length := setup >>> 48
  if (if 127 < address then true else if 1 < configuration then true else false) then 0 else
  if (if kind = 128 then (if (if request = 6 then (if index = 0 then true else false) else false) then true else false) else false) then
    if value = 256 then (1 : UInt64) ||| ((if length < 18 then length else 18) <<< 8) else
    if value = 512 then (2 : UInt64) ||| ((if length < 32 then length else 32) <<< 8) else 0
  else if (if kind = 0 then (if (if request = 5 then (if (if value ≤ 127 then (if (if index = 0 then (if (if length = 0 then (if configuration = 0 then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then
    (3 : UInt64) ||| (value <<< 16)
  else if (if kind = 0 then (if (if request = 9 then (if (if value ≤ 1 then (if (if index = 0 then (if (if length = 0 then (if (if address = 0 then false else true) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then
    (4 : UInt64) ||| (value <<< 16)
  else if (if kind = 128 then (if (if request = 8 then (if (if value = 0 then (if (if index = 0 then (if (if length = 1 then (if (if address = 0 then false else true) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then
    (5 : UInt64) ||| 256
  else if (if kind = 128 then (if (if request = 0 then (if (if value = 0 then (if (if index = 0 then (if length = 2 then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then
    (6 : UInt64) ||| 512
  else if (if kind = 130 then (if (if request = 0 then (if (if value = 0 then (if length = 2 then true else false) else false) then true else false) else false) then true else false) else false) then
    if index = 0 then (7 : UInt64) ||| 512 else
    if (if configuration = 1 then (if ((if index = 129 then true else if index = 2 then true else false)) then true else false) else false) then (7 : UInt64) ||| (512 : UInt64) ||| (index <<< 16) else 0
  else if (if kind = 2 then (if (if value = 0 then (if (if length = 0 then (if (if configuration = 1 then (if ((if index = 129 then true else if index = 2 then true else false)) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then
    if request = 1 then (8 : UInt64) ||| (index <<< 16) else if request = 3 then (9 : UInt64) ||| (index <<< 16) else 0
  else if (if kind = 129 then (if (if request = 10 then (if (if value = 0 then (if (if index = 0 then (if (if length = 1 then (if configuration = 1 then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then (10 : UInt64) ||| 256
  else if (if kind = 1 then (if (if request = 11 then (if (if value = 0 then (if (if index = 0 then (if (if length = 0 then (if configuration = 1 then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then 11
  else 0

def descriptorWord (which index : UInt64) : UInt64 :=
  if which = 1 then
    if index = 0 then 0x4000000002000112 else
    if index = 1 then 0x0000010000000000 else
    if index = 2 then 0x0100 else 0
  else if which = 2 then
    if index = 0 then 0x8000010100200209 else
    if index = 1 then 0x00ff020000040932 else
    if index = 2 then 0x0040028105070000 else
    if index = 3 then 0x0000400202050700 else 0
  else 0
end Lemma.USB.Control
