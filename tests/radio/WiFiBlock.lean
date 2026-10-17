import Lemma.Radio.WiFi.Block
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Finite host execution of the genuine owned client Actions. The boundary
model supplies explicit completed TX/immutable RX heads, never CPU execution.
Its independent byte framing/CRC and literal expectations detect premature
publication, resource loss and validation omissions. Target/RTL tests are separate.
-/
namespace WiFiBlockFixture
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.Radio.WiFi
private def base : UInt64 := 0x10013000
private def writer : UInt64 := 0x445566778899aabb
private def require (b : Bool) (message : String) : IO Unit :=
 unless b do throw <| IO.userError message
structure State where
 words : Std.HashMap UInt64 UInt64 := {}
 txActive : Bool := false
 rxActive : Bool := false
 events : UInt64 := 0
 txLength : UInt64 := 0
 rxLength : UInt64 := 0
 staging : Array UInt8 := Array.replicate 16 0
 head : Array UInt8 := #[]
 sent : Array (Array UInt8) := #[]
 acknowledgements : Array UInt64 := #[]
 failRead : Option UInt64 := none
 failWrite : Option UInt64 := none
 deriving Inhabited
private def read (s : State) (address : UInt64) : UInt64 := s.words.getD address 0
private def write (s : State) (address value : UInt64) : State :=
 {s with words := if value = 0 then s.words.erase address else s.words.insert address value}
private def readByte (s : State) (address : UInt64) : UInt64 :=
 (read s (address/8*8) >>> ((address%8)*8)) &&& 255
private def writeByte (s : State) (address value : UInt64) : State :=
 let shift := (address%8)*8
 let aligned := address/8*8
 write s aligned ((read s aligned &&& (0xffffffffffffffff ^^^ ((255 : UInt64) <<< shift))) ||| ((value &&& 255) <<< shift))
private def hardware (s : State) (address : UInt64) : UInt64 :=
 let offset := address-base
 if offset = 0 then 0x31415441444d4657 else if offset = 8 then 1 else
 if offset = 16 then 24+(if s.txActive then 1 else 0)+(if s.rxActive then 2 else 0)+(if s.head.isEmpty then 0 else 4) else
 if offset = 64 then s.events else if offset = 88 then s.head.size.toUInt64 else
 if offset = 136 then 16 else if 512 ≤ offset && offset < 640 then
 (s.head.getD ((offset-512)/8).toNat 0).toUInt64 else 0
private def hardwareWrite (s : State) (address value : UInt64) : IO State := do
 let offset := address-base
 if offset = 24 then return {s with txLength := value}
 if offset = 40 then return {s with rxLength := value}
 if offset = 32 || offset = 48 then return s
 if 256 ≤ offset && offset < 384 then
  require (value ≤ 255) "nonbyte staging"
  return {s with staging := s.staging.set! ((offset-256)/8).toNat value.toUInt8}
 if offset = 64 then return {s with events := s.events &&& (7 ^^^ value), acknowledgements := s.acknowledgements.push value}
 if offset = 56 then
  if value = 1 then
   require (!s.txActive && !s.rxActive && 0 < s.txLength && s.txLength ≤ 16) "invalid TX admission"
   return {s with txActive := true, sent := s.sent.push (s.staging.extract 0 s.txLength.toNat)}
  if value = 2 then
   require (!s.txActive && !s.rxActive && s.head.isEmpty && 0 < s.rxLength && s.rxLength ≤ 16) "invalid RX admission"
   return {s with rxActive := true}
  if value = 3 then return {s with head := #[]}
 throw <| IO.userError "unexpected Common boundary write"
partial def execute (cell : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
 match action with
 | .done s v => pure (s,v)
 | .bind first next =>
   let (s,v) ← execute cell first
   execute cell (next s v)
 | .boundedFoldU64 bound step count acc a b c d next =>
   require (count.toNat ≤ bound) "static fold bound"
   let mut result := (0,acc)
   for i in [:count.toNat] do
    if result.1 = 0 then result ← execute cell (step i.toUInt32 count result.2 a b c d)
   execute cell (next result.1 result.2)
 | .platform op address value _ _ _ _ next =>
   let s ← cell.get
   let isRead := op == .physicalRead64 || op == .physicalRead8 || op == .deviceRead64
   let isWrite := op == .physicalWrite64 || op == .physicalWrite8 || op == .deviceWrite64
   require (isRead || isWrite) "unexpected client effect"
   if (isRead && s.failRead == some address) || (isWrite && s.failWrite == some address) then
    cell.set {s with failRead := none, failWrite := none}
    execute cell (next 7 0)
   else if op = .deviceRead64 then execute cell (next 0 (hardware s address))
   else if op = .deviceWrite64 then
    cell.set (← hardwareWrite s address value)
    execute cell (next 0 0)
   else
    require ((0x80400000 ≤ address && address < 0x80510000) || (0x82000000 ≤ address && address < 0x84000000)) "client RAM authority"
    if op = .physicalRead64 then execute cell (next 0 (read s address))
    else if op = .physicalRead8 then execute cell (next 0 (readByte s address))
    else if op = .physicalWrite64 then
     cell.set (write s address value); execute cell (next 0 0)
    else
     cell.set (writeByte s address value); execute cell (next 0 0)
 | _ => throw <| IO.userError "unexpected client Action"
private def success (cell : IO.Ref State) (action : Action) : IO UInt64 := do
 let (s,v) ← execute cell action
 require (s = 0) s!"unexpected status {s}"
 pure v
private def fresh : IO (IO.Ref State × UInt64 × UInt64) := do
 let cell ← IO.mkRef ({} : State)
 discard <| success cell (Frames.configure 512 32 4)
 discard <| success cell Frames.init
 discard <| success cell Queue.initialize
 let handle ← success cell Block.create
 let frame ← success cell (Frames.resolvePurpose 1 handle 4)
 pure (cell,handle,frame)
private def pins (cell : IO.Ref State) (handle : UInt64) : IO UInt64 := success cell (Frames.mappingCount 1 handle)
private def crc (bytes : Array UInt8) : UInt64 := Id.run do
 let mut c : UInt64 := 0
 for b in bytes do
  c := c ^^^ (b.toUInt64 <<< 56)
  for _ in [:8] do
   let high := c &&& 0x8000000000000000
   c := c <<< 1
   if high != 0 then c := c ^^^ 0x42f0e1eba9ea3693
 return c
private def wordBytes (words : Array UInt64) : Array UInt8 := Id.run do
 let mut bytes := #[]
 for word in words do
  for i in [:8] do bytes := bytes.push ((word >>> (i.toUInt64*8)).toUInt8)
 return bytes
private def payload : Array UInt8 := (Array.range 512).map fun i => ((i*29+7)%256).toUInt8
private def reply (error : UInt64 := 0) : Array UInt8 :=
 let bytes := wordBytes #[0x313030504d434d4c,1,3,writer,0,4096,(if error = 0 then 512 else 0),error] ++ (if error = 0 then payload else #[])
 bytes ++ wordBytes #[crc bytes]
private def begin (cell : IO.Ref State) (handle : UInt64) : IO Unit := do
 let result ← execute cell (Block.beginRead handle writer 4096)
 require (result = (Block.pending,handle)) "READ did not remain pending"
 require ((← pins cell handle) = 1) "pending context is not pinned"
 require ((← execute cell (Frames.release 1 handle)).1 = Frames.mapped) "pending context released"
private def sentRequest (cell : IO.Ref State) (handle : UInt64) : IO Unit := do
 for _ in [:16] do
  let (s,_) ← execute cell (Block.progress base handle)
  require (s = Block.pending) "request delivery published success"
  if (← cell.get).txActive then cell.modify fun s => {s with txActive := false, events := s.events ||| 1}
 let s ← cell.get
 require (s.sent.map (·.size) == #[16,16,16,16,8]) "request fragment boundaries"
 let bytes := s.sent.foldl (· ++ ·) #[]
 let expected := wordBytes #[0x313030504d434d4c,1,0,writer,0,4096,512,0,0xefdb8fa05c40416b]
 require (bytes = expected) "independent literal72-byte request differs"
 require (s.rxActive) "reply RX was not armed"
private def receiveReply (cell : IO.Ref State) (handle : UInt64) (bytes : Array UInt8) : IO (UInt8 × UInt64) := do
 let mut cursor := 0
 let mut outcome := (Block.pending,0)
 for _ in [:100] do
  if outcome.1 = Block.pending then
   let s ← cell.get
   if s.rxActive && cursor < bytes.size then
    let n := min s.rxLength.toNat (bytes.size-cursor)
    cell.set {s with rxActive := false, head := bytes.extract cursor (cursor+n), events := s.events ||| 2}
    cursor := cursor+n
   outcome ← execute cell (Block.progress base handle)
 return outcome
private def retainedFailure (cell : IO.Ref State) (handle frame : UInt64) : IO Unit := do
 require ((← execute cell (Block.result handle)).1 != 0) "invalid reply exposed result"
 require ((← pins cell handle) = 1) "failure lost context pin"
 require (read (← cell.get) (frame+72) = 0) "failure published result flag"
 require ((← success cell (Frames.ownedCount 1)) = 2) "failure lost owned packet/context"

def check : IO Unit := do
 require (crc ("123456789".toUTF8.data) = 0x6c40df5f0b497347) "independent CRC known answer"
 let (cell,h,f) ← fresh
 for (badWriter,badOffset) in #[(0,4096),(writer,1),(writer,268435456),(writer,0xfffffffffffffe00)] do
  require ((← execute cell (Block.beginRead h badWriter badOffset)).1 = Block.invalid) "invalid request admitted"
 require ((← pins cell h) = 0 && (← success cell (Frames.ownedCount 1)) = 1) "invalid request consumed resources"
 begin cell h
 require ((← execute cell (Block.beginRead h writer 4096)).1 = Controller.busy) "pending request overwritten"
 discard <| execute cell (Block.progress base h)
 let before ← cell.get
 for _ in [:5] do require ((← execute cell (Block.progress base h)).1 = Block.pending) "TX without completion advanced"
 require (read (← cell.get) (f+16) = 0 && (← cell.get).sent = before.sent) "TX cursor or packets advanced without completion"
 cell.modify fun s => {s with txActive := false, events := s.events ||| 1}
 -- This state already sent one fragment; drive remaining fragments separately.
 for _ in [:15] do
  require ((← execute cell (Block.progress base h)).1 = Block.pending) "premature completion"
  if (← cell.get).txActive then cell.modify fun s => {s with txActive := false, events := s.events ||| 1}
 let bytes := (← cell.get).sent.foldl (· ++ ·) #[]
 require (bytes = wordBytes #[0x313030504d434d4c,1,0,writer,0,4096,512,0,0xefdb8fa05c40416b]) "literal request"
 for _ in [:10] do require ((← execute cell (Block.progress base h)).1 = Block.pending) "lost reply completed"
 require ((← execute cell (Block.result h)).1 = Block.pending) "absence exposed result"
 let outcome ← receiveReply cell h (reply)
 require (outcome = (0,h)) "valid full reply rejected"
 let address ← success cell (Block.result h)
 require (address = f+1536 && (← pins cell h) = 0) "owned result pin/address"
 require ((← success cell (Frames.ownedCount 1)) = 1) "completed packet retained"
 for i in [:512] do require (readByte (← cell.get) (address+i.toUInt64) = payload[i]!.toUInt64) "full512-byte result"
 discard <| success cell (Frames.release 1 h)
 require ((← success cell (Frames.ownedCount 1)) = 0) "result release leaked frame"
 -- Actual identity, shape and CRC failures, including payload and stored CRC.
 for position in #[0,8,16,24,32,40,48,56,64,311,583] do
  let (cell,h,f) ← fresh; begin cell h; sentRequest cell h
  let bytes := (reply).set! position ((reply)[position]! ^^^ 1)
  require ((← receiveReply cell h bytes).1 = Block.poisoned) s!"corruption at {position} admitted"
  retainedFailure cell h f
 let (cell,h,f) ← fresh; begin cell h; sentRequest cell h
 require ((← receiveReply cell h (reply 5)) = (Block.peerError,5)) "peer error forged success or lost code"
 retainedFailure cell h f
 let (cell,h,f) ← fresh; begin cell h; sentRequest cell h
 cell.modify fun s => {s with rxActive := false, head := (reply).extract 0 8, events := 2}
 require ((← execute cell (Block.progress base h)).1 = Block.poisoned) "short immutable head admitted"
 require (!(← cell.get).head.isEmpty && (← cell.get).events = 2) "bad fragment was ACKed"
 retainedFailure cell h f
 let (cell,h,f) ← fresh; begin cell h; sentRequest cell h
 cell.modify fun s => {s with events := 4}
 require ((← execute cell (Block.progress base h)).1 = Block.poisoned) "hardware fault ignored"
 retainedFailure cell h f
 let (cell,h,f) ← fresh; begin cell h; sentRequest cell h
 cell.modify fun s => {s with failWrite := some (f+1536+37*8)}
 require ((← receiveReply cell h (reply)).1 = Block.poisoned) "late result copy failure ignored"
 retainedFailure cell h f
 let (cell,h,f) ← fresh; begin cell h
 cell.modify fun s => {s with failWrite := some (f+80)}
 require ((← execute cell (Block.progress base h)).1 = Block.poisoned) "post-enqueue metadata failure ignored"
 require (read (← cell.get) (Queue.state+8) = 1 && read (← cell.get) (Queue.state+16) = 0) "uncertain queued packet lost"
 retainedFailure cell h f
 let (cell,h,f) ← fresh
 cell.modify fun s => Id.run do
  let mut value := s
  for i in [1:512] do
   value := write value (Frames.records+i.toUInt64*32) 2
   value := write value (Frames.records+i.toUInt64*32+8) 4
   value := write value (Frames.records+i.toUInt64*32+24) 1
  value := write value Frames.accounting 0
  value := write value Frames.freeCursor 512
  return write value (Frames.ownerCountCell 2) 511
 require ((← execute cell (Block.beginRead h writer 4096)).1 = Frames.exhausted) "packet resource exhaustion ignored"
 require ((← pins cell h) = 0 && read (← cell.get) (f+64) = 0 && (← cell.get).sent.isEmpty) "allocation failure consumed pending ownership"
 let (cell,h,f) ← fresh
 cell.modify fun s => {s with failRead := some (f+128)}
 require ((← execute cell (Block.beginRead h writer 4096)).1 = Block.poisoned) "request checksum read failure ignored"
 retainedFailure cell h f
 let (cell,h,f) ← fresh; begin cell h
 discard <| execute cell (Block.progress base h)
 cell.modify fun s => {s with txActive := false, events := 1, failWrite := some (base+64)}
 require ((← execute cell (Block.progress base h)).1 = Block.poisoned) "completion W1C failure ignored"
 require ((← cell.get).events = 1 && read (← cell.get) (Queue.state+24) = 1) "failed W1C hid actual completion/event"
 retainedFailure cell h f
 -- Failure before context publication returns the distinct newly allocated
 -- packet handle. The caller still holds its original context and can reclaim
 -- both; no queue pin or hardware acceptance occurred.
 let (cell,h,f) ← fresh
 cell.modify fun s => {s with failWrite := some (f+64)}
 let (status,packet) ← execute cell (Block.beginRead h writer 4096)
 require (status = 7 && packet != h && packet != 0) "early packet publication lost its failure handle"
 require ((← pins cell h) = 0 && (← pins cell packet) = 0 && (← success cell (Frames.ownedCount 1)) = 2 && (← cell.get).sent.isEmpty) "early failure made a hidden pending transaction"
 discard <| success cell (Frames.release 1 packet)
 discard <| success cell (Frames.release 1 h)
 require ((← success cell (Frames.ownedCount 1)) = 0) "caller early-allocation cleanup leaked"
 IO.println "WIFI_BLOCK_HOST:PASS fullREAD512,5request/37replyfragments,loss/backpressure,11corruptions,peererror,shorthead,hardwarefault,2latewritefailures; retainedownership; host boundary only"
end WiFiBlockFixture
#eval WiFiBlockFixture.check

open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
 let roots := #[``Lemma.Radio.WiFi.Block.create,``Lemma.Radio.WiFi.Block.beginRead,
  ``Lemma.Radio.WiFi.Block.progress,``Lemma.Radio.WiFi.Block.result]
 let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_8 roots with
  | .ok v => pure v | .error e => throwError e.render
 let lowered ← match lowerActionSuiteExecution .kernel_v0_8 suite {
  preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),symbolPrefix:="wifi_block_"} with
  | .ok v => pure v | .error e => throwError e
 let module : LLVM.Module := {
  sourceName := "genuine owned CommonOFDM companion READ512 client"
  functions := lowered.functions
  declarations := #[{name := "core0_io_fence", returnType := .void, parameters := #[]}] }
 match LLVM.validateModule module with
 | .ok _ => pure () | .error e => throwError e
 let some output ← liftIO <| IO.getEnv "LEMMA_WIFI_BLOCK_OUTPUT" | throwError "new output required"
 let path := System.FilePath.mk output
 if ← liftIO path.pathExists then throwError "refusing retained output"
 liftIO <| IO.FS.createDirAll path
 liftIO <| IO.FS.writeFile (path/"block.ll") module.render
 liftIO <| IO.FS.writeFile (path/"block.symbols") lowered.renderSymbolManifest
 logInfo "WIFI_BLOCK_LOWERING:PASS genuine owned client/Queue/Frames; CPU NOT_RUN"
