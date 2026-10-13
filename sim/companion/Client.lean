import ClientPolicy

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
