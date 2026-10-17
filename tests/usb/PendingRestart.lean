import USBPendingPolicy
open LemmaSim.USB LemmaSim.Companion

@[export lemma_usb_pending_restart_main]
def runFixture (_args : List String) : IO UInt32 := do
  let some socket ← IO.getEnv "LEMMA_POLICY4_SOCKET" | throw (IO.userError "missing socket")
  let some directory ← IO.getEnv "LEMMA_POLICY4_OUTBOX" | throw (IO.userError "missing outbox")
  let some helper ← IO.getEnv "LEMMA_POLICY4_HELPER" | throw (IO.userError "missing helper")
  let client ← loadOutbox {socket := socket,directory := System.FilePath.mk directory,helper := helper,writer := 91}
  let payload := ByteArray.mk ((Array.range 512).map UInt8.ofNat)
  let frame : Frame := {kind := 1,writer := 91,sequence := 1,offset := 8192,length := 512,payload := payload}
  let host : Host := {input := ← IO.getStdin,output := ← IO.getStdout}
  let (next,bytes,spent) ← LemmaSim.USB.Pending4.exchangeOpaque host client (encode frame) 0
  IO.println s!"RESULT ACK NEXT {next.next} ERROR {get64 bytes 56} SPENT {spent}"
  return 0
