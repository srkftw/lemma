import USBHost

/-! Additive hosted-Lean policy4. USB packet/control routines remain the
versioned policy3 implementation; uncertainty has an explicit wait budget.
This module and its normal host runtime never enter an RV64 target image. -/
namespace LemmaSim.USB.Pending4
open LemmaSim.USB LemmaSim.Companion

def chargeWait (spent clocks : Nat) : Except String Nat :=
  if clocks = 1000 || clocks = 100000 then
    if spent ≤ maximumPendingClocks - clocks then .ok (spent + clocks)
    else .error "USB opaque operation Pending budget"
  else .error "USB Pending wait quantum"

def waitClocks (h : Host) (spent clocks : Nat) : IO Nat := do
  let next ← match chargeWait spent clocks with
    | .ok next => pure next
    | .error error => throw (IO.userError error)
  if (← line h s!"WAIT {clocks}") != "WAIT_DONE" then
    throw (IO.userError "USB Pending wait boundary")
  return next

def pollBudget (h : Host) (endpoint : UInt8) (spent0 : Nat) : IO (Bool × ByteArray × Nat) := do
  let mut spent := spent0
  for _ in [0:10000] do
    send h (← checked (token 0x69 h.address endpoint))
    let packet ← receive h
    if handshake packet 0x5a then
      spent ← waitClocks h spent 1000
    else if handshake packet 0x1e then
      throw (IO.userError "USB endpoint STALL")
    else
      match dataPayload packet with
      | .ok (one,bytes) => return (one,bytes,spent)
      | .error error => throw (IO.userError error)
  throw (IO.userError "USB IN deadline")

def requestBudget (h : Host) : IO (Host × ByteArray × Nat) := do
  let mut h := h
  let mut bytes := ByteArray.emptyWithCapacity 584
  let mut spent := 0
  let mut duplicates := 0
  for _ in [0:16] do
    let (one,part,next) ← if bytes.isEmpty then do
      let (one,part) ← idleIN h 1
      pure (one,part,spent)
    else pollBudget h 1 spent
    spent := next
    send h (ByteArray.mk #[0xd2])
    if one != h.inOne then
      duplicates := duplicates + 1
      if duplicates > 3 then throw (IO.userError "USB duplicate retry bound")
    else
      if bytes.size + part.size > 584 then throw (IO.userError "USB opaque request bound")
      bytes := bytes ++ part
      h := {h with inOne := !h.inOne}
      if part.size < 64 then return (h,bytes,spent)
  throw (IO.userError "USB fragment bound")

def validateReceipt (request reply : Frame) : Except String Frame := do
  if reply.kind != 3 || reply.writer != request.writer ||
     reply.sequence != request.sequence || reply.offset != request.offset ||
     reply.length > request.length then throw "reply identity/bounds"
  if reply.error = 0 && reply.length != request.length then throw "short successful reply"
  if request.kind = 1 && reply.payload != request.payload.extract 0 reply.length.toNat then
    throw "write receipt payload"
  return reply

/-- Raw I/O failure is uncertainty. A decoded wrong receipt is a protocol error.
Neither produces a response or changes durable outbox ownership. -/
def wireReceipt (c : Client) (f : Frame) : IO (Except String (Option Frame)) := do
  let text? ← try
    pure (some (← primitive c.helper #["wire",c.socket,hex (encode f)]))
  catch _ => pure none
  let some text := text? | return .ok none
  return do
    let reply ← unhex text >>= decode
    return some (← validateReceipt f reply)

def pendingReceipt (h : Host) (c : Client) (f : Frame) (spent0 : Nat) : IO (Frame × Nat) := do
  let mut spent := spent0
  let mut errors := 0
  for _ in [0:1004] do
    match ← wireReceipt c f with
    | .ok (some receipt) => return (receipt,spent)
    | .ok none => pure ()
    | .error error =>
      errors := errors + 1
      if errors ≥ 3 then
        throw (IO.userError ("USB malformed durable receipt retry bound: " ++ error))
    spent ← waitClocks h spent 100000
  throw (IO.userError "USB durable receipt finite attempt bound")

def exchangeOpaque (h : Host) (c : Client) (bytes : ByteArray) (spent0 : Nat) :
    IO (Client × ByteArray × Nat) := do
  if bytes.size = 8 && get64 bytes 0 = helloMagic then
    return (c,put64 (put64 (put64 (put64 ByteArray.empty helloMagic) c.writer) c.next) mediumBytes,spent0)
  let frame ← match decode bytes with
    | .ok frame => pure frame
    | .error error => throw (IO.userError error)
  if frame.kind = 3 || frame.writer != c.writer || frame.length > 512 then
    throw (IO.userError "USB request identity/capacity")
  -- Reads do not reconcile another transaction. An old sequence requests the
  -- peer's actual retained receipt; it never allocates a new sequence.
  if frame.kind = 0 || frame.sequence < c.next then
    let (receipt,spent) ← pendingReceipt h c frame spent0
    return (c,encode receipt,spent)
  if frame.sequence != c.next then throw (IO.userError "USB request sequence")
  let c ← if let some pending := c.pending then do
    if !sameRequest pending frame then throw (IO.userError "USB older outbox unresolved")
    pure c
  else do
    let next := {c with pending := some frame}
    storeOutbox next
    pure next
  let (receipt,spent) ← pendingReceipt h c frame spent0
  return (← acceptReceipt c frame receipt,encode receipt,spent)

def replyBudget (h : Host) (bytes : ByteArray) (spent0 : Nat) : IO Host := do
  if bytes.isEmpty || bytes.size > 584 then throw (IO.userError "USB opaque reply bound")
  let mut h := h
  let mut spent := spent0
  let mut errors := 0
  for i in [0:(bytes.size+63)/64] do
    let part := bytes.extract (64*i) (min bytes.size (64*(i+1)))
    let packet ← checked (dataPacket h.outOne part)
    let mut accepted := false
    for _ in [0:1004] do
      if !accepted then
        send h (← checked (token 0xe1 h.address 2)); send h packet
        let ack ← receive h
        if handshake ack 0xd2 then accepted := true
        else if handshake ack 0x5a then spent ← waitClocks h spent 100000
        else if handshake ack 0x1e then throw (IO.userError "USB endpoint STALL")
        else
          errors := errors + 1
          if errors ≥ 3 then throw (IO.userError "USB bulk OUT malformed/error retry bound")
    if !accepted then throw (IO.userError "USB bulk OUT finite attempt bound")
    h := {h with outOne := !h.outOne}
  return h

@[export lemma_usb_pending_main]
def run (args : List String) : IO UInt32 := do
  let [socket,directory,writerText,helper] := args |
    throw (IO.userError "USBPendingPolicy SOCKET OUTBOX WRITER OS_HELPER")
  let some writer := writerText.toNat? | throw (IO.userError "USB writer integer")
  if writer = 0 || writer > 18446744073709551615 then throw (IO.userError "USB writer bound")
  let directory := System.FilePath.mk directory
  IO.FS.createDirAll directory
  let lock ← IO.FS.Handle.mk (directory / "lock") .append
  if !(← lock.tryLock) then throw (IO.userError "USB outbox already owned")
  let mut client ← loadOutbox {socket := socket,directory := directory,helper := helper,writer := writer.toUInt64}
  let host : Host := {input := ← IO.getStdin,output := ← IO.getStdout}
  if (← line host "USBHOST/2 PACKET_BYTES_DEV") != "OPEN" then
    throw (IO.userError "USB raw adapter version")
  if let some pending := client.pending then
    let (receipt,_) ← pendingReceipt host client pending 0
    if receipt.error != 0 then throw (IO.userError "USB startup outbox error receipt")
    client ← acceptReceipt client pending receipt
  let mut host ← enumerate host
  for _ in [0:100000] do
    let (next,bytes,spent) ← requestBudget host
    let (clientNext,response,spent) ← exchangeOpaque next client bytes spent
    client := clientNext
    host ← replyBudget next response spent
  throw (IO.userError "USB session resource bound")
end LemmaSim.USB.Pending4
