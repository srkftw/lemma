import HostIO

/-! Hosted-Lean development backing client. A durable outbox preserves the exact
writer/transaction before any send. Transport uncertainty leaves it pending;
restart reconciles the same bytes and sequence before new work. -/
namespace LemmaSim.Companion

def outboxMagic : UInt64 := 0x313054554f434d4c

structure Client where
  socket : String
  directory : System.FilePath
  helper : String
  writer : UInt64
  next : UInt64 := 1
  pending : Option Frame := none

def outboxBytes (c : Client) : ByteArray := Id.run do
  let mut b := put64 (put64 (put64 ByteArray.empty outboxMagic) c.writer) c.next
  let frame := c.pending.map encode |>.getD ByteArray.empty
  b := put64 b frame.size.toUInt64 ++ frame
  return put64 b (crc64 b)

def storeOutbox (c : Client) : IO Unit := do
  let temp := c.directory / "outbox.pending"
  IO.FS.writeBinFile temp (outboxBytes c)
  let _ ← primitive c.helper #["replace",temp.toString,(c.directory / "outbox").toString]

def loadOutbox (c : Client) : IO Client := do
  let path := c.directory / "outbox"
  if !(← path.pathExists) then
    storeOutbox c
    return c
  let b ← IO.FS.readBinFile path
  if b.size < 40 || b.size > 624 || get64 b 0 != outboxMagic || get64 b 8 != c.writer || get64 b (b.size-8) != crc64 (b.extract 0 (b.size-8)) then
    throw (IO.userError "outbox identity/CRC/resource")
  let next := get64 b 16
  let n := get64 b 24
  if next = 0 || n.toNat != b.size-40 then throw (IO.userError "outbox bounds")
  let pending ← if n = 0 then pure none else do
    let f ← match decode (b.extract 32 (b.size-8)) with
      | .ok f => pure f
      | .error e => throw (IO.userError e)
    if f.writer != c.writer || f.sequence != next || (f.kind != 1 && f.kind != 2) then
      throw (IO.userError "outbox transaction")
    pure (some f)
  return {c with next := next, pending := pending}

def sendFrame (c : Client) (f : Frame) : IO (Option Frame) := do
  -- Two bounded sends of exactly the same transaction. The raw helper owns no
  -- retry, receipt or protocol policy. No response is synthesized on disconnect.
  for _ in [0:2] do
    try
      let text ← primitive c.helper #["wire",c.socket,hex (encode f)]
      let reply ← match unhex text >>= decode with
        | .ok reply => pure reply
        | .error e => throw (IO.userError e)
      if reply.kind != 3 || reply.writer != f.writer || reply.sequence != f.sequence || reply.offset != f.offset || reply.length > f.length then
        throw (IO.userError "reply identity/bounds")
      if reply.error = 0 && reply.length != f.length then throw (IO.userError "short successful reply")
      if f.kind = 1 && reply.payload != f.payload.extract 0 reply.length.toNat then throw (IO.userError "write receipt payload")
      return some reply
    catch _ => pure ()
  return none

def reconcile (c : Client) : IO (Client × Bool) := do
  if let some pending := c.pending then
    let reply ← sendFrame c pending
    if let some reply := reply then
      if reply.error = 0 then
        if c.next = 0xffffffffffffffff then throw (IO.userError "writer sequence exhausted")
        let c := {c with next := c.next+1, pending := none}
        storeOutbox c
        return (c,true)
    return (c,false)
  return (c,true)

def rawRequest (c : Client) (line : String) : Except String Frame := do
  let [kind,id,boundary,offset,length,data] := line.splitOn " " | throw "request fields"
  let number (text : String) : Except String UInt64 := do
    let some n := text.toNat? | throw "request number"
    if n > 18446744073709551615 then throw "request integer bound"
    return n.toUInt64
  let _ ← number id
  let _ ← number boundary
  let kind ← number kind
  let payload ← if data = "-" then pure ByteArray.empty else unhex data
  let f : Frame := {
    kind := kind,writer := c.writer,sequence := if kind = 0 then 0 else c.next,
    offset := ← number offset,length := ← number length,payload := payload}
  if kind > 2 then throw "request kind"
  decode (encode f)

def acceptReceipt (c : Client) (request reply : Frame) : IO Client := do
  if request.kind != 0 && reply.error = 0 then
    if c.next = 0xffffffffffffffff then throw (IO.userError "writer sequence exhausted")
    let c := {c with next := c.next+1,pending := none}
    storeOutbox c
    return c
  return c

/-- The third result records the exact frame actually submitted. `none` means
the request is still blocked on an older outbox, so its reply cannot be reused
as the new request's completion. -/
def clientExchange (c : Client) (f : Frame) : IO (Client × Option Frame × Option Frame) := do
  -- Reads, including snapshot/export passive reads, never reconcile an outbox
  -- or execute a hidden durability barrier. Only explicit mutating requests and
  -- an explicit restarted client may advance a pending transaction.
  if f.kind = 0 then return (c,← sendFrame c f,some f)
  let (c,ready) ← reconcile c
  if !ready then return (c,none,none)
  let f := {f with sequence := c.next}
  let c := {c with pending := some f}
  storeOutbox c
  let reply ← sendFrame c f
  if let some reply := reply then
    if reply.error = 0 then
      return (← acceptReceipt c f reply,some reply,some f)
    -- Error receipts preserve observed byte prefixes. Retaining the outbox
    -- allows a later same-ID retry to establish durability without duplication.
    return (c,some reply,some f)
  return (c,none,some f)

end LemmaSim.Companion
open LemmaSim.Companion

def main (args : List String) : IO UInt32 := do
  let asynchronous := args.length = 5 && args[4]? = some "--pending"
  let [socket,directory,writerText,helper] := if asynchronous then args.take 4 else args | throw (IO.userError "Client SOCKET DIR WRITER OS_HELPER [--pending]")
  let some writer := writerText.toNat? | throw (IO.userError "invalid writer")
  if writer = 0 || writer > 18446744073709551615 then throw (IO.userError "writer bound")
  let directory := System.FilePath.mk directory
  IO.FS.createDirAll directory
  let lock ← IO.FS.Handle.mk (directory / "lock") .append
  if !(← lock.tryLock) then throw (IO.userError "outbox already owned")
  let mut client ← loadOutbox {socket := socket,directory := directory,helper := helper,writer := writer.toUInt64}
  let (next,ready) ← reconcile client
  client := next
  if !ready then throw (IO.userError "pending transaction unresolved")
  let probe : Frame := {kind := 0,writer := client.writer,sequence := 0,offset := 0,length := 512}
  let some reply ← sendFrame client probe | throw (IO.userError "peer unavailable")
  if reply.error != 0 then throw (IO.userError "peer medium unavailable")
  let input ← IO.getStdin
  let output ← IO.getStdout
  output.putStrLn s!"READY {mediumBytes} {client.writer} {client.next}"
  output.flush
  while true do
    let line ← input.getLine
    if line.isEmpty then break
    let frame ← match rawRequest client line.trimAscii.toString with
      | .ok f => pure f
      | .error e => throw (IO.userError e)
    let (next,reply,submitted) ← clientExchange client frame
    client := next
    let mut reply := reply
    let mut submitted := submitted
    let mut retries := 0
    while reply.isNone do
      output.putStrLn "PENDING"
      output.flush
      -- The historical synchronous adapter exits; the optional pending adapter
      -- waits for an explicit bounded same-frame retry, never a fabricated ACK.
      if !asynchronous then return 2
      let command ← input.getLine
      if command.trimAscii.toString != "RETRY" || retries >= 16 then return 2
      retries := retries+1
      if let some actual := submitted then
        reply ← sendFrame client actual
        if let some receipt := reply then client ← acceptReceipt client actual receipt
      else
        let (next,received,actual) ← clientExchange client frame
        client := next;reply := received;submitted := actual
    if let some receipt := reply then
      output.putStrLn s!"{receipt.length} {receipt.error} {if receipt.payload.isEmpty then "-" else hex receipt.payload}"
      output.flush
  return 0
