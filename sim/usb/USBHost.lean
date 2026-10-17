import USBPacket
import ClientPolicy

/-! Hosted Lean development USB host and opaque backing adapter. USB packets
and their CRC/toggle policy are generated/checked here; the native boundary
only transfers packet bytes and digital reset/attach inputs. Durability remains
the existing separately running opaque peer's actual barrier/receipt policy.
No document, notebook journal, ink or mathematical object is interpreted. -/
namespace LemmaSim.USB
open LemmaSim.Companion
def helloMagic : UInt64 := 0x3130425355434d4c
structure Host where
  input : IO.FS.Stream
  output : IO.FS.Stream
  address : UInt8 := 7
  inOne : Bool := false
  outOne : Bool := false
  deriving Inhabited
def line (h : Host) (command : String) : IO String := do
  if command.toUTF8.size > 160 then throw (IO.userError "USB command bound")
  h.output.putStrLn command;h.output.flush
  let reply ← h.input.getLine
  if reply.toUTF8.size > 160 || !reply.endsWith "\n" then throw (IO.userError "USB raw reply boundary")
  return reply.trimAscii.toString
def send (h : Host) (packet : ByteArray) : IO Unit := do
  if packet.isEmpty || packet.size > maxPacket then throw (IO.userError "USB packet resource")
  if (← line h ("SEND "++hex packet)) != "SENT" then throw (IO.userError "USB packet transfer failed")
def receive (h : Host) : IO ByteArray := do
  let reply ← line h "RECV"
  let ["RX",bytes] := reply.splitOn " " | throw (IO.userError "USB raw RX framing")
  let packet ← match unhex bytes with
    | .ok p => pure p
    | .error e => throw (IO.userError e)
  if packet.isEmpty || packet.size > maxPacket then throw (IO.userError "USB RX packet bound")
  return packet
def checked (packet : Except String ByteArray) : IO ByteArray :=
  match packet with | .ok bytes => pure bytes | .error e => throw (IO.userError e)
def wait (h : Host) : IO Unit := do
  if (← line h "WAIT 1000") != "WAIT_DONE" then throw (IO.userError "USB wait boundary")
def setup (h : Host) (word : UInt64) : IO Unit := do
  send h (← checked (token 0x2d h.address 0))
  send h (← checked (dataPacket false (put64 ByteArray.empty word)))
  if !handshake (← receive h) 0xd2 then throw (IO.userError "USB SETUP not ACKed")
def pollIN (h : Host) (endpoint : UInt8) : IO (Bool × ByteArray) := do
  -- At most10,000 attempts and ten million explicitly scheduled wait clocks.
  -- Packet transfer and raw-adapter scheduling add virtual clocks. This is a
  -- bounded development host, not full USB timing qualification.
  for _ in [0:10000] do
    send h (← checked (token 0x69 h.address endpoint))
    let p ← receive h
    if handshake p 0x5a then wait h else
    if handshake p 0x1e then throw (IO.userError "USB endpoint STALL") else
    match dataPayload p with
      | .ok decoded => return decoded
      | .error e => throw (IO.userError e)
  throw (IO.userError "USB IN deadline")
/-- Before a first opaque fragment exists there is no transaction to expire.
The idle loop retains bounded buffers and yields through an explicit 1ms
virtual wait after each real NAK. Control and partial frames keep pollIN's
separate bounded retry deadline. No receipt or configured state is invented. -/
partial def idleIN (h : Host) (endpoint : UInt8) : IO (Bool × ByteArray) := do
  send h (← checked (token 0x69 h.address endpoint))
  let p ← receive h
  if handshake p 0x5a then
    if (← line h "WAIT 100000") != "WAIT_DONE" then throw (IO.userError "USB idle wait boundary")
    idleIN h endpoint
  else if handshake p 0x1e then throw (IO.userError "USB endpoint STALL") else
    match dataPayload p with
      | .ok decoded => return decoded
      | .error e => throw (IO.userError e)
def control (h : Host) (word : UInt64) (hasData : Bool) : IO ByteArray := do
  setup h word
  let (one,bytes) ← pollIN h 0
  if !one then throw (IO.userError "USB control must start DATA1")
  send h (ByteArray.mk #[0xd2])
  if hasData then
    send h (← checked (token 0xe1 h.address 0))
    send h (← checked (dataPacket true ByteArray.empty))
    if !handshake (← receive h) 0xd2 then throw (IO.userError "USB control OUT status")
  else if !bytes.isEmpty then throw (IO.userError "USB status stage must be empty")
  return bytes
def enumerate (h : Host) : IO Host := do
  if (← line h "RESET 5000000") != "RESET_DONE" then throw (IO.userError "USB reset boundary")
  let h := {h with address := 0}
  let device ← control h 0x0012000001000680 true
  let expected := ByteArray.mk #[18,1,0,2,0,0,0,64,0,0,0,0,0,1,0,0,0,1]
  if device != expected then throw (IO.userError "USB development device descriptor mismatch")
  let _ ← control h 0x0000000000070500 false
  let h := {h with address := 7}
  let config ← control h 0x0020000002000680 true
  let expected := ByteArray.mk #[9,2,32,0,1,1,0,128,50,9,4,0,0,2,255,0,0,0,7,5,129,2,64,0,0,7,5,2,2,64,0,0]
  if config != expected then throw (IO.userError "USB development configuration descriptor mismatch")
  let _ ← control h 0x0000000000010900 false
  let current ← control h 0x0001000000000880 true
  if current != ByteArray.mk #[1] then throw (IO.userError "USB guest did not reach configured state")
  return {h with inOne := false,outOne := false}
def request (h : Host) : IO (Host × ByteArray) := do
  let mut h := h
  let mut bytes := ByteArray.emptyWithCapacity 584
  let mut duplicates := 0
  for _ in [0:16] do
    let (one,part) ← if bytes.isEmpty then idleIN h 1 else pollIN h 1
    send h (ByteArray.mk #[0xd2])
    if one != h.inOne then
      duplicates := duplicates+1
      if duplicates > 3 then throw (IO.userError "USB duplicate retry bound")
    else
      if bytes.size+part.size > 584 then throw (IO.userError "USB opaque request bound")
      bytes := bytes ++ part
      h := {h with inOne := !h.inOne}
      if part.size < 64 then return (h,bytes)
  throw (IO.userError "USB fragment bound")
/-- Policy3: NAK is occupied-slot Pending, not a transfer error. The
100M explicitly scheduled wait-clock budget covers the entire opaque reply,
not each fragment. Packet/admission clocks add actual virtual time, which the
caller separately bounds. This is not a claimed USB timing qualification. -/
def pendingQuantum : Nat := 100000
def maximumPendingClocks : Nat := 100000000
def chargePending (spent : Nat) : Except String Nat :=
  if spent ≤ maximumPendingClocks - pendingQuantum then .ok (spent + pendingQuantum)
  else .error "USB bulk OUT Pending budget"
def reply (h : Host) (bytes : ByteArray) : IO Host := do
  if bytes.isEmpty || bytes.size > 584 then throw (IO.userError "USB opaque reply bound")
  let mut h := h
  let mut spent := 0
  for i in [0:(bytes.size+63)/64] do
    let part := bytes.extract (64*i) (min bytes.size (64*(i+1)))
    let packet ← checked (dataPacket h.outOne part)
    let mut accepted := false
    let mut errors := 0
    for _ in [0:1004] do
      if !accepted then
        send h (← checked (token 0xe1 h.address 2));send h packet
        let ack ← receive h
        if handshake ack 0xd2 then accepted := true else
        if handshake ack 0x5a then
          spent ← match chargePending spent with
            | .ok next => pure next
            | .error e => throw (IO.userError e)
          if (← line h "WAIT 100000") != "WAIT_DONE" then throw (IO.userError "USB backpressure wait")
        else if handshake ack 0x1e then throw (IO.userError "USB endpoint STALL") else
          errors := errors+1
          if errors ≥ 3 then throw (IO.userError "USB bulk OUT malformed/error retry bound")
    if !accepted then throw (IO.userError "USB bulk OUT finite attempt bound")
    h := {h with outOne := !h.outOne}
  return h
def exchangeOpaque (c : Client) (bytes : ByteArray) : IO (Client × ByteArray) := do
  if bytes.size = 8 && get64 bytes 0 = helloMagic then
    return (c,put64 (put64 (put64 (put64 ByteArray.empty helloMagic) c.writer) c.next) mediumBytes)
  let frame ← match decode bytes with
    | .ok f => pure f
    | .error e => throw (IO.userError e)
  if frame.kind = 3 || frame.writer != c.writer || frame.length > 512 then throw (IO.userError "USB request identity/capacity")
  -- Retrying an already committed older transaction reaches the independent
  -- peer's exact retained receipt, including a fresh barrier. No new sequence
  -- is assigned and no success is generated from USB delivery alone.
  if frame.kind != 0 && frame.sequence < c.next then
    let some receipt ← sendFrame c frame | throw (IO.userError "USB old receipt uncertain")
    return (c,encode receipt)
  if frame.kind != 0 && frame.sequence != c.next then throw (IO.userError "USB request sequence")
  let (next,receipt,actual) ← clientExchange c frame
  if let some receipt := receipt then return (next,encode receipt)
  let some actual := actual | throw (IO.userError "USB older outbox unresolved")
  -- Keep the original exact durable outbox/sequence through uncertainty. A
  -- disconnected reply never becomes a fabricated guest completion.
  let mut c := next
  for _ in [0:3] do
    if let some receipt ← sendFrame c actual then
      c ← acceptReceipt c actual receipt
      return (c,encode receipt)
  throw (IO.userError "USB durable receipt unresolved")
end LemmaSim.USB
open LemmaSim.USB LemmaSim.Companion
def main (args : List String) : IO UInt32 := do
  let [socket,directory,writerText,helper] := args | throw (IO.userError "USBHost SOCKET OUTBOX WRITER OS_HELPER")
  let some writer := writerText.toNat? | throw (IO.userError "USB writer integer")
  if writer = 0 || writer > 18446744073709551615 then throw (IO.userError "USB writer bound")
  let directory := System.FilePath.mk directory
  IO.FS.createDirAll directory
  let lock ← IO.FS.Handle.mk (directory/"lock") .append
  if !(← lock.tryLock) then throw (IO.userError "USB outbox already owned")
  let mut c ← loadOutbox {socket := socket,directory := directory,helper := helper,writer := writer.toUInt64}
  let (next,ready) ← reconcile c
  if !ready then throw (IO.userError "USB pending outbox uncertain")
  c := next
  let host : Host := {input := ← IO.getStdin,output := ← IO.getStdout}
  if (← line host "USBHOST/2 PACKET_BYTES_DEV") != "OPEN" then throw (IO.userError "USB raw adapter version")
  let mut host ← enumerate host
  for _ in [0:100000] do
    let (next,bytes) ← request host
    let (client,response) ← exchangeOpaque c bytes
    c := client;host ← reply next response
  throw (IO.userError "USB session resource bound")
