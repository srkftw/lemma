import USBHost
open LemmaSim.USB

private def require (p : Bool) (message : String) : IO Unit :=
  if p then pure () else throw (IO.userError message)
private def attempt (pid : String) : String := "SENT\nSENT\nRX " ++ pid ++ "\n"
private def nak : String := attempt "5a" ++ "WAIT_DONE\n"
private def fixture (root : System.FilePath) (name script : String) (bytes : ByteArray)
    (failure : Option String) : IO String := do
  let dir := root/name
  IO.FS.createDir dir
  IO.FS.writeFile (dir/"input") script
  let input ← IO.FS.Handle.mk (dir/"input") .read
  let output ← IO.FS.Handle.mk (dir/"output") .write
  let h : Host := {input := IO.FS.Stream.ofHandle input,output := IO.FS.Stream.ofHandle output}
  let result ← try
    let next ← reply h bytes
    require (next.outOne = ((bytes.size+63)/64 % 2 = 1)) "toggle did not follow accepted fragments"
    pure none
  catch e => pure (some e.toString)
  output.flush
  match failure,result with
  | none,none => pure ()
  | some expected,some actual => require (actual.contains expected) ("wrong failure: " ++ actual)
  | _,_ => throw (IO.userError "reply outcome mismatch")
  IO.FS.readFile (dir/"output")

#eval (show IO Unit from do
  let some directory ← IO.getEnv "LEMMA_USB_PENDING_WORK" | throw (IO.userError "pending fixture requires unused output")
  let root := System.FilePath.mk directory
  IO.FS.createDir root
  let bytes := ByteArray.mk (Array.range 80 |>.map UInt8.ofNat)
  let ok ← fixture root "pending" (String.join (List.replicate 5 nak) ++
    attempt "00" ++ attempt "00" ++ attempt "d2" ++
    String.join (List.replicate 4 nak) ++ attempt "d2") bytes none
  require ((ok.splitOn "WAIT 100000\n").length = 10) "NAK failed to schedule exact bounded waits"
  let sends := (ok.splitOn "\n").filter (·.startsWith "SEND c3")
  require (sends.length = 8 && sends.all (· = sends.head!)) "Pending/error retry changed DATA0 bytes or toggle"
  let sends := (ok.splitOn "\n").filter (·.startsWith "SEND 4b")
  require (sends.length = 5 && sends.all (· = sends.head!)) "second fragment retry changed DATA1 bytes"
  let shared ← fixture root "shared-budget" (String.join (List.replicate 1000 nak) ++
    attempt "d2" ++ attempt "5a") bytes (some "USB bulk OUT Pending budget")
  require ((shared.splitOn "WAIT 100000\n").length = 1001) "Pending budget was enlarged or restarted per fragment"
  require ((shared.splitOn "SEND 4b").length = 2) "shared budget did not reach real second fragment"
  let errors ← fixture root "errors" (attempt "00" ++ nak ++ attempt "00" ++ nak ++ attempt "00")
    "LMCUSB01".toUTF8 (some "USB bulk OUT malformed/error retry bound")
  require ((errors.splitOn "WAIT 100000\n").length = 3) "NAK consumed the malformed/error retry budget"
  let stalled ← fixture root "stall" (attempt "1e") "LMCUSB01".toUTF8 (some "USB endpoint STALL")
  require ((stalled.splitOn "SEND c3").length = 2) "STALL was retried or acknowledged"
  require (match chargePending 99900000 with | .ok n => n == 100000000 | _ => false) "last allowed Pending wait rejected"
  require (match chargePending 100000000 with | .error e => e == "USB bulk OUT Pending budget" | _ => false) "Pending bound changed"
  IO.println "PASS genuine hosted Lean USB policy3: retained NAK bytes/toggle, whole-reply100M waitclock limit, three errors, terminal STALL")
