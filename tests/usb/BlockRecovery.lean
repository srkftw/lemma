import Lemma.USB.Block
import Lemma.Platform.LemmaSim.DeviceService
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Execute the actual new driver Actions. This boundary model supplies explicit
controller acknowledgements/immutable heads and independently encoded peer
receipts. It never supplies target instructions, journals or a Saved record.
Actual circuitry/guest reconnect remains a separate required qualification. -/
namespace USBRecoveryTests
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.USB

structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  connected : Bool := true
  configured : Bool := true
  events : UInt64 := 0
  now : UInt64 := 100
  txQueued : Bool := false
  txLength : UInt64 := 0
  txStage : Array UInt8 := Array.replicate 64 0
  sent : Array (Array UInt8) := #[]
  head : Array UInt8 := #[]
  mmioWrites : Array (UInt64 × UInt64) := #[]
  failRead : UInt64 := 0
  failWrite : UInt64 := 0

private def require (ok : Bool) (message : String) : IO Unit :=
  unless ok do throw <| IO.userError message
private def read (m : Model) (a : UInt64) : UInt64 := m.words.getD a 0
private def write (m : Model) (a v : UInt64) : Model := {m with words := m.words.insert a v}
private def bytes (words : Array UInt64) : Array UInt8 := Id.run do
  let mut b := #[]
  for word in words do for i in [:8] do b := b.push ((word >>> (i.toUInt64*8)).toUInt8)
  return b
private def pack (b : Array UInt8) (offset : Nat) : UInt64 :=
  (List.range 8).foldl (fun v i => v ||| ((b.getD (offset+i) 0).toUInt64 <<< (i.toUInt64*8))) 0
private def crc (b : Array UInt8) : UInt64 := Id.run do
  let mut v : UInt64 := 0
  for byte in b do
    v := v ^^^ (byte.toUInt64 <<< 56)
    for _ in [:8] do
      let high := v >>> 63
      v := v <<< 1
      if high != 0 then v := v ^^^ 0x42f0e1eba9ea3693
  return v
private def payload : Array UInt8 := (Array.range 512).map fun i => ((i*29+7)%256).toUInt8
private def receipt (writer sequence error : UInt64) (p : Array UInt8) : Array UInt8 :=
  let b := bytes #[0x313030504d434d4c,1,3,writer,sequence,4096,p.size.toUInt64,error] ++ p
  b ++ bytes #[crc b]
private def hardware (m : Model) (offset : UInt64) : UInt64 :=
  if offset = 0 then 0x315645444253554c else if offset = 8 then 1 else
  if offset = 16 then 1+(if m.connected then 2 else 0)+(if m.configured then 8 else 0)+
    (if m.txQueued then 128 else 0)+(if m.head.isEmpty then 0 else 32) else
  if offset = 40 then m.events else if offset = 88 then m.head.size.toUInt64 else
  if 576 ≤ offset && offset < 640 then pack m.head (offset-576).toNat else 0

private def hardwareWrite (m : Model) (offset value : UInt64) : IO Model := do
  let m := {m with mmioWrites := m.mmioWrites.push (offset,value)}
  if offset = 40 then return {m with events := m.events &&& ~~~value}
  if offset = 48 then return m
  if offset = 72 then return {m with txLength := value}
  if 320 ≤ offset && offset < 384 then
    let mut stage := m.txStage
    for i in [:8] do stage := stage.set! ((offset-320).toNat+i) (value >>> (i.toUInt64*8)).toUInt8
    return {m with txStage := stage}
  if offset = 56 then
    if value = 257 then
      require (!m.txQueued && m.configured && m.txLength ≤ 64) "TX admitted without an available configured slot"
      return {m with txQueued := true, sent := m.sent.push (m.txStage.extract 0 m.txLength.toNat)}
    if value = 514 then
      require (!m.head.isEmpty) "POP without a retained actual endpoint2 head"
      return {m with head := #[]}
  throw <| IO.userError s!"recovery used undeclared MMIO write{offset}/{value}"

partial def run (cell : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
      let (s,v) ← run cell first
      run cell (next s v)
  | .boundedFoldU64 bound step count initial a b c d next => do
      require (count.toNat ≤ bound) "recovery exceeded static Action bound"
      let mut result := (0,initial)
      for i in [:count.toNat] do
        if result.1 = 0 then result ← run cell (step i.toUInt32 count result.2 a b c d)
      run cell (next result.1 result.2)
  | .platform op a b _ _ _ _ next => do
      let m ← cell.get
      if op = .firmwareCall then
        require (a = 2 && b = 0) "recovery issued an undeclared firmware effect"
        run cell (next 0 m.now)
      else if op = .deviceRead64 then run cell (next 0 (hardware m (a-Block.mmio)))
      else if op = .deviceWrite64 then
        cell.set (← hardwareWrite m (a-Block.mmio) b)
        run cell (next 0 0)
      else if op = .physicalRead64 then
        if a = m.failRead then run cell (next 7 0) else run cell (next 0 (read m a))
      else if op = .physicalWrite64 then
        if a = m.failWrite then run cell (next 7 0) else
        cell.set (write m a b)
        run cell (next 0 0)
      else throw <| IO.userError "recovery acquired an undeclared target effect"
  | _ => throw <| IO.userError "recovery acquired an unbounded Action"

private def ok (cell : IO.Ref Model) (action : Action) : IO UInt64 := do
  let (s,v) ← run cell action
  require (s = 0) s!"unexpected recovery fixture status{s}"
  return v
private def span (m : Model) (base : UInt64) (length : Nat) : Array UInt8 :=
  (Array.range length).map fun i => ((read m (base+i.toUInt64-i.toUInt64%8)) >>> (i.toUInt64%8*8)).toUInt8

private def sameMemory (before after : Model) : IO Unit := do
  require (before.words.size == after.words.size) "rejected recovery changed memory cardinality"
  for (address,value) in before.words do
    require (read after address == value) "rejected recovery changed an owned word"

private def fresh : IO (IO.Ref Model × UInt64 × Array UInt8) := do
  let cell ← IO.mkRef ({} : Model)
  discard <| ok cell (Frames.configure 512 32 4)
  let mut m ← cell.get
  m := write m (Frames.record 0) 1
  m := write m (Frames.record 0+8) 1
  m := write m (Frames.record 0+24) 1
  for (o,v) in #[(0,512),(8,Frames.pool),(16,524288),(64,12),(72,83)] do
    m := write m (Block.state+o) v
  for i in [:64] do m := write m (Frames.pool+1536+i.toUInt64*8) (pack payload (i*8))
  cell.set m
  require ((← run cell (Block.submit 1 8)) = (0,12)) "real Block.submit did not construct the owned WRITE"
  let original := span (← cell.get) (Frames.pool+128) 584
  require (original = bytes #[0x313030504d434d4c,1,1,83,12,4096,512,0] ++ payload ++
    bytes #[crc (bytes #[0x313030504d434d4c,1,1,83,12,4096,512,0] ++ payload)]) "independent original frame/CRC differs"
  cell.modify fun m => {m with connected := false, configured := false, events := 16}
  require ((← run cell Block.finishRecovery).1 = Block.poisoned) "actual disconnect did not quarantine in-flight frame"
  require (read (← cell.get) (Block.state+200) = 1 && read (← cell.get) (Block.state+56) = 1)
    "new driver did not retain real disconnect witness/poison"
  return (cell,Frames.pool,original)

private def start (cell : IO.Ref Model) : IO Unit := do
  let sent := (← cell.get).sent
  require ((← run cell (Block.beginRecovery 91 1)) = (Block.pending,1)) "recovery was not Pending"
  require ((← cell.get).sent = sent && read (← cell.get) (Block.state+56) = 1) "begin recovery supplied a packet/success"
  -- An independent boundary reset event and completed configuration are posed;
  -- this is a driver Action fixture, not actual RTL enumeration qualification.
  cell.modify fun m => {m with connected := true, configured := true, events := 1}
  require ((← run cell Block.finishRecovery).1 = Block.pending) "qualified reset/config did not begin HELLO"
  require ((← run cell Block.finishRecovery).1 = Block.pending) "HELLO delivery fabricated receipt"
  cell.modify fun m => {m with txQueued := false}
  require ((← run cell Block.finishRecovery).1 = Block.pending) "HELLO transition was not pending"
  require ((← cell.get).sent = #[bytes #[0x3130425355434d4c]]) "actual HELLO bytes changed"

private def hello (cell : IO.Ref Model) (writer next : UInt64) : IO (UInt8 × UInt64) := do
  cell.modify fun m => {m with head := bytes #[0x3130425355434d4c,writer,next,268435456]}
  run cell Block.finishRecovery

private def transmitOriginal (cell : IO.Ref Model) (original : Array UInt8) : IO Unit := do
  for _ in [:11] do
    require ((← run cell Block.finishRecovery).1 = Block.pending) "delivery alone released poison"
    cell.modify fun m => {m with txQueued := false}
  require (((← cell.get).sent.extract 1 11 |>.foldl (· ++ ·) #[]) == original)
    "recovery did not transmit the exact retained request/old writer/old sequence"

private def receive (cell : IO.Ref Model) (b : Array UInt8) : IO (UInt8 × UInt64) := do
  let mut result := (Block.pending,0)
  for i in [:(b.size+63)/64] do
    cell.modify fun m => {m with head := b.extract (i*64) (min b.size ((i+1)*64))}
    result ← run cell Block.finishRecovery
    require ((← cell.get).head.isEmpty) "receipt head was not copied before POP"
  return result

private def capabilityBoundary (original : Array UInt8) : IO Unit := do
  let cell ← IO.mkRef ({} : Model)
  discard <| ok cell (Frames.configure 512 32 4)
  discard <| ok cell Frames.init
  discard <| ok cell Lemma.Kernel.Objects.init
  let store ← ok cell (Lemma.Kernel.Memory.AddressSpace.create 3)
  let other ← ok cell (Lemma.Kernel.Memory.AddressSpace.create 2)
  discard <| ok cell (Lemma.Kernel.Capability.attach store)
  discard <| ok cell (Lemma.Kernel.Capability.attach other)
  let key ← ok cell (Lemma.Kernel.Objects.createEndpoint store)
  let foreign ← ok cell (Lemma.Kernel.Objects.createEndpoint store)
  let cap ← ok cell (Lemma.Kernel.Capability.grantBoot store key Lemma.User.CapabilityABI.endpointCall)
  let wrong ← ok cell (Lemma.Kernel.Capability.grantBoot store foreign Lemma.User.CapabilityABI.endpointCall)
  let noCall ← ok cell (Lemma.Kernel.Capability.grantBoot store key Lemma.User.CapabilityABI.endpointSend)
  let aliasCap ← ok cell (Lemma.Kernel.Capability.grantBoot other key Lemma.User.CapabilityABI.endpointCall)
  discard <| ok cell (Lemma.Kernel.Capability.activate store)
  discard <| ok cell (Lemma.Kernel.Capability.activate other)
  discard <| ok cell (Lemma.Platform.LemmaSim.DeviceService.configureUSBRecovery 0 0 key)
  let handle ← ok cell (Frames.allocate 1 1)
  let base ← ok cell (Frames.resolvePurpose 1 handle 1)
  let mut m ← cell.get
  for (o,v) in #[(0,handle),(8,base),(16,524288),(40,2),(56,1),(64,12),(72,83),
      (80,1),(88,584),(96,8),(200,1)] do m := write m (Block.state+o) v
  for i in [:73] do m := write m (base+128+i.toUInt64*8) (pack original (i*8))
  cell.set m
  let before ← cell.get
  for handle in #[wrong,noCall] do
    require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store handle 5 91 1 0)).1 =
      Lemma.User.CapabilityABI.denied) "non-block/noCall capability admitted recovery"
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store cap 5 91 1 1)).1 = 16)
    "reserved field admitted recovery"
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSB store cap 5 91 1 0)).1 = 16)
    "historical device root admitted recovery opcode"
  sameMemory before (← cell.get)
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store cap 5 91 1 0)) =
    (Block.pending,1)) "authorized Store recovery did not become Pending"
  let pending ← cell.get
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store cap 5 91 1 0)).1 = Block.busy)
    "second start overwrote pending recovery"
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery other aliasCap 6 91 1 0)).1 =
    Lemma.User.CapabilityABI.denied) "foreign full task descriptor consumed a receipt"
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store cap 6 92 1 0)).1 =
    Block.recoveryInvalid) "foreign ticket consumed a receipt"
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store cap 6 91 2 0)).1 =
    Block.recoveryInvalid) "foreign epoch consumed a receipt"
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store cap 2 8 0 0)).1 =
    Block.busy) "ordinary WRITE overwrote a quarantined recovery"
  sameMemory pending (← cell.get)
  -- Completion comes from the already independently exercised receipt path.
  -- These terminal fields are only a wrapper ownership fixture, not wire proof.
  cell.modify fun m => write (write (write m (Block.state+112) 6) (Block.state+136) 1) (Block.state+56) 0
  require ((← run cell (Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery store cap 6 91 1 0)) =
    (0,1)) "matching authorized terminal receipt was not consumable"
  require (read (← cell.get) (Lemma.Platform.LemmaSim.DeviceService.state+128) = 0)
    "completed wrapper kept another request active"
  IO.println "USB_RECOVERY_CAPABILITY:PASS actual descriptor/capability lookup; Store block right/full descriptor/ticket/epoch/pending/noCall/reserved/old-opcode gates; terminal fields component-only"

def check : IO Unit := do
  let (cell,base,original) ← fresh
  let before ← cell.get
  for (ticket,epoch) in #[(0,1),(91,0),(91,2)] do
    let rejected ← IO.mkRef before
    require ((← run rejected (Block.beginRecovery ticket epoch)).1 = Block.recoveryInvalid) "wrong ticket/epoch admitted"
    sameMemory before (← rejected.get)
    require ((← rejected.get).sent == before.sent) "wrong ticket/epoch changed packet authority"
  for (o,v) in #[(56,0),(200,0),(120,3),(8,base+8),(0,1024)] do
    let rejected ← IO.mkRef (write before (Block.state+o) v)
    require ((← run rejected (Block.beginRecovery 91 1)).1 != Block.pending) "invalid poison/witness/bound/base/generation admitted"
  for o in #[0,8,16,24,32,40,48,56,576] do
    let rejected ← IO.mkRef (write before (base+128+o) (read before (base+128+o) ^^^ 1))
    require ((← run rejected (Block.beginRecovery 91 1)).1 != Block.pending) "corrupt retained frame admitted"
  start cell
  let backup := span (← cell.get) (base+2048) 584
  require (backup = original && read (← cell.get) (Block.state+56) = 1) "HELLO overwrote quarantine backup"
  let waiting ← IO.mkRef {before with connected := true, configured := true}
  require ((← run waiting (Block.beginRecovery 91 1)).1 = Block.pending) "valid request could not wait for a reset"
  require ((← run waiting Block.finishRecovery).1 = Block.pending && (← waiting.get).sent.isEmpty)
    "configuration without an actual reset released a frame"
  waiting.modify fun m => {m with now := 100+Block.recoveryTicks}
  require ((← run waiting Block.finishRecovery).1 = Block.poisoned && read (← waiting.get) (Block.state+56) = 1)
    "finite recovery deadline released poison"
  for (writer,next) in #[(84,12),(83,11),(83,14)] do
    let rejected ← IO.mkRef (← cell.get)
    require ((← hello rejected writer next).1 != Block.pending && read (← rejected.get) (Block.state+56) = 1)
      "wrong HELLO admitted a new namespace or advanced sequence"
    require (span (← rejected.get) (base+2048) 584 = original) "bad HELLO changed retained bytes"
  require ((← hello cell 83 13).1 = Block.pending) "same namespace/retained-next HELLO did not restore original"
  require (span (← cell.get) (base+128) 584 = original && read (← cell.get) (Block.state+56) = 1)
    "HELLO itself released or changed request"
  transmitOriginal cell original
  let awaiting ← cell.get
  let good := receipt 83 12 0 payload
  for b in #[receipt 84 12 0 payload,receipt 83 13 0 payload,receipt 83 12 227 payload,
      receipt 83 12 0 (payload.set! 19 (payload[19]! ^^^ 1)),good.set! 583 (good[583]! ^^^ 1)] do
    let rejected ← IO.mkRef awaiting
    require ((← receive rejected b).1 != 0 && read (← rejected.get) (Block.state+56) = 1 &&
      read (← rejected.get) (Block.state+136) = 0) "invalid receipt released quarantine/epoch"
    require (span (← rejected.get) (base+2048) 584 = original) "bad receipt changed quarantined bytes"
  require ((← receive cell good) = (0,1)) "genuine matching independent receipt did not reconcile"
  let complete ← cell.get
  require (read complete (Block.state+56) = 0 && read complete (Block.state+64) = 13 &&
    read complete (Block.state+40) = 0 && read complete (Block.state+136) = 1) "receipt publication identity differs"
  require ((← run cell (Block.takeRecovery 92 1)).1 = Block.recoveryInvalid) "foreign ticket consumed recovery"
  require ((← run cell (Block.takeRecovery 91 1)) = (0,1)) "completed recovery ticket was not consumable"
  require (read (← cell.get) (Block.state+224) = 0) "complete backup remained adoptable"
  capabilityBoundary original
  IO.println "USB_RECOVERY_ACTION:PASS exact quarantined584-byte request; same namespace/old sequence; actual matching peer receipt only; reset/deadline/epoch/ticket/owner/frame/HELLO/receipt negatives; no target CPU/RTL/Store/Saved claim"
end USBRecoveryTests

open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_6
      #[``Lemma.USB.Block.prepareRecovery, ``Lemma.USB.Block.beginRecovery,
        ``Lemma.USB.Block.finishRecovery, ``Lemma.USB.Block.takeRecovery,
        ``Lemma.USB.Block.recoveryEpoch,
        ``Lemma.Platform.LemmaSim.DeviceService.configureUSBRecovery,
        ``Lemma.Platform.LemmaSim.DeviceService.blockUSBRecovery,
        ``Lemma.Platform.LemmaSim.DeviceService.deferredUSBRecovery] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .kernel_v0_6 suite with
  | .ok _ => pure ()
  | .error diagnostic => throwError diagnostic
  logInfo "USB_RECOVERY_COMPILE:PASS eight real Lean recovery/device roots under existing Kernel6 owned-frame/MMIO/capability authority"

def main : IO Unit := USBRecoveryTests.check
