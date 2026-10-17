import USBPendingPolicy
open LemmaSim.USB LemmaSim.Companion
open LemmaSim.USB.Pending4

def require (condition : Bool) (message : String) : IO Unit :=
  if condition then pure () else throw (IO.userError message)

def okClocks (value : Except String Nat) (expected : Nat) : Bool :=
  match value with | .ok actual => actual == expected | .error _ => false

def attempt (pid : String) : String := "SENT\nSENT\nRX " ++ pid ++ "\n"
def nak : String := attempt "5a" ++ "WAIT_DONE\n"
def replyFixture (root : System.FilePath) (name script : String) (spent : Nat)
    (expected : Option String) : IO String := do
  let directory := root / name
  IO.FS.createDir directory
  IO.FS.writeFile (directory / "input") script
  let input ← IO.FS.Handle.mk (directory / "input") .read
  let output ← IO.FS.Handle.mk (directory / "output") .write
  let host : Host := {input := IO.FS.Stream.ofHandle input,output := IO.FS.Stream.ofHandle output}
  let error ← try
    let _ ← replyBudget host (ByteArray.mk (Array.range 80 |>.map UInt8.ofNat)) spent
    pure none
  catch error => pure (some error.toString)
  output.flush
  match expected,error with
  | none,none => pure ()
  | some expected,some actual => require (actual.contains expected) "wrong reply failure"
  | _,_ => throw (IO.userError "reply outcome mismatch")
  IO.FS.readFile (directory / "output")

#eval do
  require (okClocks (chargeWait 99900000 100000) 100000000) "final uncertainty quantum"
  require (okClocks (chargeWait 99999000 1000) 100000000) "final fragment quantum"
  require (!(chargeWait 99900001 100000).isOk) "receipt and reply cannot exceed shared budget"
  require (!(chargeWait 100000000 1000).isOk) "spent shared budget"
  require (!(chargeWait 0 1).isOk) "unadvertised wait quantum"
  let request : Frame := {kind := 1,writer := 91,sequence := 2,offset := 512,length := 512,payload := ByteArray.mk (Array.replicate 512 7)}
  let receipt := response request 0 request.payload
  require ((validateReceipt request receipt).isOk) "exact real receipt admission"
  for wrong in [{receipt with kind := 2}, {receipt with writer := 92},
                {receipt with sequence := 3}, {receipt with offset := 1024},
                {receipt with length := 0,payload := ByteArray.empty},
                {receipt with payload := ByteArray.mk (Array.replicate 512 8)}] do
    require (!(validateReceipt request wrong).isOk) "wrong receipt admitted"
  let prefixReceipt := response request 5 (request.payload.extract 0 128)
  require ((validateReceipt request prefixReceipt).isOk) "actual partial error receipt"
  let some path ← IO.getEnv "LEMMA_USB_POLICY4_WORK" | throw (IO.userError "unused fixture path")
  let root := System.FilePath.mk path
  IO.FS.createDir root
  let shared ← replyFixture root "shared" (nak ++ attempt "d2" ++ attempt "5a") 99900000
    (some "USB opaque operation Pending budget")
  require ((shared.splitOn "WAIT 100000\n").length = 2) "reply reset prior receipt budget"
  require ((shared.splitOn "SEND 4b").length = 2) "shared bound did not reach second fragment"
  let errors ← replyFixture root "errors" (attempt "00" ++ attempt "d2" ++ attempt "00" ++ attempt "00")
    0 (some "USB bulk OUT malformed/error retry bound")
  require ((errors.splitOn "SEND 4b").length = 3) "malformed budget reset between fragments"
  let stalled ← replyFixture root "stall" (attempt "1e") 0 (some "USB endpoint STALL")
  require ((stalled.splitOn "WAIT ").length = 1) "STALL was retried or waited"
  IO.println "PURE_INPUTS_PASS"
