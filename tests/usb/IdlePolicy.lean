import USBHost
open LemmaSim.USB
private def require (p : Bool) (message : String) : IO Unit := if p then pure () else throw (IO.userError message)
private def run (directory : String) : IO Unit := do
  let root := System.FilePath.mk directory
  IO.FS.createDir root
  -- Independent literal USB CRC16 known answer for LMCUSB01. The fixture is a
  -- raw host boundary, not controller or guest execution qualification.
  let lines := String.join (List.replicate 10001 "SENT\nRX 5a\nWAIT_DONE\n") ++ "SENT\nRX c34c4d43555342303140ee\n"
  IO.FS.writeFile (root/"input") lines
  let input ← IO.FS.Handle.mk (root/"input") .read
  let output ← IO.FS.Handle.mk (root/"output") .write
  let h : Host := {input := IO.FS.Stream.ofHandle input,output := IO.FS.Stream.ofHandle output}
  let (one,bytes) ← idleIN h 1
  output.flush
  require (!one && bytes == "LMCUSB01".toUTF8) "actual hosted idle parser returned wrong fragment"
  let commands ← IO.FS.readFile (root/"output")
  let rows := commands.splitOn "\n"
  require (rows.length = 30006) "idle poll issued unexpected command count"
  require ((commands.splitOn "WAIT 100000\n").length = 10002) "idle NAK did not yield through declared clocks"
  require ((commands.splitOn "WAIT 1000\n").length = 1) "idle acquired partial-frame timing"
  IO.println "PASS genuine hosted USB2 idle policy: 10001 actual NAK replies, bounded 1ms waits, independently encoded DATA0 fragment"

#eval (show IO Unit from do
  let some directory ← IO.getEnv "LEMMA_USB_IDLE_WORK" | throw (IO.userError "idle fixture requires unused directory")
  run directory)
