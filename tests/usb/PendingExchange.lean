import USBPendingPolicy
open LemmaSim.USB LemmaSim.Companion

@[export lemma_usb_pending_fixture_main]
def runFixture (_args : List String) : IO UInt32 := do
  let some socket ← IO.getEnv "LEMMA_POLICY4_SOCKET" | throw (IO.userError "missing socket")
  let some directory ← IO.getEnv "LEMMA_POLICY4_OUTBOX" | throw (IO.userError "missing outbox")
  let some helper ← IO.getEnv "LEMMA_POLICY4_HELPER" | throw (IO.userError "missing helper")
  let some budget ← IO.getEnv "LEMMA_POLICY4_SPENT" | throw (IO.userError "missing budget")
  let some spent := budget.toNat? | throw (IO.userError "invalid budget")
  let client ← loadOutbox {socket := socket,directory := System.FilePath.mk directory,helper := helper,writer := 91}
  let frame : Frame := {kind := 2,writer := 91,sequence := 1,offset := 0,length := 0}
  let host : Host := {input := ← IO.getStdin,output := ← IO.getStdout}
  try
    let (next,bytes,used) ← LemmaSim.USB.Pending4.exchangeOpaque host client (encode frame) spent
    IO.println s!"RESULT ACK NEXT {next.next} ERROR {get64 bytes 56} SPENT {used}"
  catch error =>
    IO.println s!"RESULT REJECT {error}"
  return 0
