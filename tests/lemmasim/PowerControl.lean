import Lemma.Platform.LemmaSim.NotebookKernel
import Lean.Elab.Command
import Std.Data.HashMap

/-! An independent finite RAM/peripheral oracle executes production Lean Actions.
Owned descriptors and capability grants are built by the actual kernel. Literal
MMIO responses exercise authority priority and the typed S-return boundary;
these observations are neither a CPU run nor an arithmetic proof. -/
namespace PowerControlFixture
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory
open Lemma.Platform.LemmaSim
open Lemma.User

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  uart : Array UInt8 := #[]
  mmioReads : Array UInt64 := #[]
  mmioWrites : Array (UInt64 × UInt64) := #[]
  power : UInt64 := 0
  error : UInt64 := 0
  hardwareBusy : Bool := false
  wakeAfterSuspend : Bool := false
  pendingEvents : UInt64 := 0
  plicEnable : UInt64 := 0x7002
  operations : Nat := 0
  waits : Nat := 0

def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  { s with words := if v = 0 then s.words.erase a else s.words.insert a v }
def byte (s : State) (a : UInt64) : UInt64 :=
  (word s (a - a % 8) >>> (a % 8 * 8)) &&& 255
def putByte (s : State) (a v : UInt64) : State :=
  let shift := a % 8 * 8
  put s (a - a % 8) ((word s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) |||
    ((v &&& 255) <<< shift))
def require (b : Bool) (message : String) : IO Unit :=
  if b then pure () else throw <| IO.userError message

partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute ref first
    execute ref (next s v)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    require (count.toNat ≤ budget) "fold exceeds literal budget"
    let mut status : UInt8 := 0
    let mut acc := initial
    for i in [:count.toNat] do
      if status = 0 then
        let result ← execute ref (step i.toUInt32 count acc c0 c1 c2 c3)
        status := result.1
        acc := result.2
    execute ref (next status acc)
  | .uartReadStatus next => execute ref (next 0 0x60)
  | .uartWriteByte value next =>
    ref.modify fun s => { s with uart := s.uart.push value }
    execute ref (next 0)
  | .platform op a b _ _ _ _ next =>
    let current ← ref.get
    require (current.operations < 10000000) "finite oracle exhausted"
    ref.set { current with operations := current.operations + 1 }
    if op == .installSatp then execute ref (next 0 0)
    else if op == .firmwareCall then
      require (a == 2 || a == 4 || a == 5) "unexpected firmware service"
      execute ref (next 0 (if a == 2 then 1000 else 0))
    else if op == .waitInterrupt then
      ref.modify fun s => { s with waits := s.waits + 1 }
      execute ref (next 0 0)
    else if op == .deviceRead64 then
      require (0x10010500 ≤ a && a < 0x10010600 && a % 8 == 0) "unexpected device read"
      ref.modify fun s => { s with mmioReads := s.mmioReads.push a }
      let s ← ref.get
      let value := if a == 0x10010500 then 0x4c505752 else
        if a == 0x10010508 then 1 else if a == 0x10010510 then s.power else
        if a == 0x10010518 then s.error else if a == 0x10010520 then 1 else
        if a == 0x10010530 then s.pendingEvents else if a == 0x10010538 then 3 else
        if a == 0x10010540 then 1 else 0
      execute ref (next 0 value)
    else if op == .deviceWrite64 then
      require (a == 0x10010548 || a == 0x10010550 || a == 0x10010558)
        "unexpected device write (implicit storage/panel operation)"
      ref.modify fun s => { s with mmioWrites := s.mmioWrites.push (a,b) }
      if a == 0x10010558 then
        require (b == 1) "invalid clear-error"
        ref.modify fun s => { s with error := 0 }
      else if a == 0x10010550 then
        require (b ≤ 3) "invalid event ACK"
        ref.modify fun s => { s with pendingEvents := s.pendingEvents &&& ~~~b }
      else if a == 0x10010548 then
        require (b == 1 || b == 2) "invalid power command"
        ref.modify fun s =>
          if b == 2 then { s with power := 0, error := 0 }
          else if s.hardwareBusy then { s with error := 1 }
          else { s with power := if s.wakeAfterSuspend then 0 else 1, error := 0 }
      execute ref (next 0 0)
    else if op == .deviceRead32 then
      require (a == 0x0c002080) "unexpected PLIC read"
      execute ref (next 0 (← ref.get).plicEnable)
    else if op == .deviceWrite32 then
      require (a == 0x0c002080) "unexpected PLIC write"
      ref.modify fun s => { s with plicEnable := b }
      execute ref (next 0 0)
    else
      require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000))
        s!"access outside finite owned RAM {a}"
      match op with
      | .physicalRead64 =>
        require (a % 8 == 0) "unaligned read"
        execute ref (next 0 (word (← ref.get) a))
      | .physicalWrite64 =>
        require (a % 8 == 0) "unaligned write"
        ref.modify fun s => put s a b
        execute ref (next 0 0)
      | .physicalRead8 => execute ref (next 0 (byte (← ref.get) a))
      | .physicalWrite8 =>
        ref.modify fun s => putByte s a b
        execute ref (next 0 0)
      | _ => throw <| IO.userError "unexpected physical primitive"
  | _ => throw <| IO.userError "unexpected Action constructor"

def success (s : IO.Ref State) (a : Action) : IO UInt64 := do
  let (status,value) ← execute s a
  require (status == 0) s!"unexpected status {status}"
  pure value

def denied (s : IO.Ref State) (expected : UInt8) (a : Action) : IO Unit := do
  let before ← s.get
  let (status,_) ← execute s a
  let after ← s.get
  require (status == expected) s!"expected rejection {expected}, observed {status}"
  require (after.words == before.words && after.mmioWrites == before.mmioWrites &&
    after.mmioReads == before.mmioReads && after.uart == before.uart)
    "authority/malformed rejection performed an effect"

def arguments (s : State) (context handle operation reserved : UInt64) : State :=
  put (put (put (put (put s (context+80) handle) (context+88) operation)
    (context+96) reserved) (context+104) 0) (context+112) 0

def main : IO Unit := do
  let ref ← IO.mkRef ({} : State)
  discard <| success ref (Frames.configure 8192 8192 4)
  discard <| success ref Frames.init
  discard <| success ref Objects.init
  discard <| success ref Task.init
  let notebook ← success ref (AddressSpace.create 2)
  let store ← success ref (AddressSpace.create 3)
  discard <| success ref (Capability.attach notebook)
  discard <| success ref (Capability.attach store)
  let powerKey ← success ref (Objects.createEndpoint store)
  let blockKey ← success ref (Objects.createEndpoint store)
  let otherKey ← success ref (Objects.createEndpoint store)
  let power ← success ref (Capability.grantBoot notebook powerKey CapabilityABI.endpointCall)
  let wrong ← success ref (Capability.grantBoot notebook otherKey CapabilityABI.endpointCall)
  let noCall ← success ref (Capability.grantBoot notebook powerKey CapabilityABI.endpointSend)
  let console ← success ref (Capability.grantBoot notebook Objects.consoleKey CapabilityABI.consoleWrite)
  let block ← success ref (Capability.grantBoot store blockKey CapabilityABI.endpointCall)
  discard <| success ref (Capability.activate notebook)
  discard <| success ref (Capability.activate store)
  discard <| success ref (PowerControl.configure 1 powerKey)
  let configured ← ref.get
  -- Reservations reject before even reading the caller's authority table.
  denied ref 16 (PowerControl.call notebook power 1 1 0 0)
  denied ref 72 (PowerControl.call notebook wrong 1 0 0 0)
  denied ref 72 (PowerControl.call store block 1 0 0 0)
  denied ref 72 (PowerControl.call notebook noCall 1 0 0 0)
  denied ref 81 (PowerControl.call notebook console 1 0 0 0)
  -- A notebook handle cannot confer authority in the store's managed table.
  denied ref 80 (PowerControl.call store power 1 0 0 0)
  denied ref 80 (PowerControl.call store (power + 0x10000) 1 0 0 0)
  denied ref 197 (PowerControl.call notebook power 4 0 0 0)
  -- Driver pending beats controller admission and makes no power/PLIC writes.
  ref.modify fun s => put s 0x80400c30 1
  let pending ← ref.get
  let (status,_) ← execute ref (PowerControl.call notebook power 1 0 0 0)
  require (status == 196) "unconsumed guest completion was not BUSY"
  require ((← ref.get).mmioWrites == pending.mmioWrites &&
    (← ref.get).plicEnable == 0x7002 && (← ref.get).power == 0)
    "BUSY drained, masked, or suspended"
  ref.set { configured with hardwareBusy := true }
  let (status,_) ← execute ref (PowerControl.call notebook power 1 0 0 0)
  require (status == 196 && (← ref.get).plicEnable == 0x7002 &&
    (← ref.get).power == 0) "hardware BUSY did not preserve RUN/Pen IRQ"
  -- Literal scheduler row uses the actual allocated/validated task table and
  -- real descriptor. Its running state is the precondition of a captured trap.
  ref.set configured
  let table ← success ref Task.table
  let context ← success ref (AddressSpace.context notebook)
  let kernelRoot ← success ref (AddressSpace.root store)
  ref.modify fun s => put (put (put (put s table notebook) (table+8) 3)
    (Process.control+8) kernelRoot) (Process.resume+272) (AddressSpace.satpWord kernelRoot)
  let ready ← ref.get
  for wake in [false,true] do
    ref.set (arguments { ready with wakeAfterSuspend := wake } context power 1 0)
    let (status,result) ← execute ref (NotebookKernel.deviceCall notebook context 0x400000 68)
    let final ← ref.get
    require (status == 0 && result == 0x80500000) "accepted suspend returned User context"
    require (word final (context+256) == 0x400004 && word final (context+80) == 0 &&
      word final (context+264) == 0x200000020) "stored User reply/PC was not advanced exactly once"
    require (word final (table+8) == 2 && word final (table+24) == 2 &&
      word final (table+72) == 1 && word final (Process.resume+80) == 2)
      "accepted suspend did not publish ready/S scheduler continuation"
    require (final.plicEnable == 0x5002) "suspend lost wake IRQ or left pen loss IRQ enabled"
  ref.set (arguments ready context wrong 1 0)
  let (status,result) ← execute ref (NotebookKernel.deviceCall notebook context 0x400000 68)
  require (status == 0 && result == context && word (← ref.get) (context+80) == 72 &&
    word (← ref.get) (table+8) == 3) "wrong named endpoint changed scheduling authority"
  ref.set { ready with power := 1 }
  let (status,value) ← execute ref PowerControl.step
  require (status == 0 && value == 1 && (← ref.get).waits == 1 &&
    word (← ref.get) (table+8) == 3) "suspended step dispatched or skipped actual WFI"
  -- A named suspend can leave an older raw request latched. A later actual
  -- wake must win over that request, with no immediate suspend command.
  ref.set { ready with power := 0, pendingEvents := 3 }
  let beforeWake ← ref.get
  let (status,value) ← execute ref PowerControl.step
  let awake ← ref.get
  require (status == 0 && value == 0 && awake.power == 0 && awake.pendingEvents == 0 &&
    awake.waits == beforeWake.waits && awake.plicEnable == 0x7002)
    "observed wake plus stale request resuspended or lost the wake"
  require (awake.mmioWrites.toList.drop beforeWake.mmioWrites.size == [(0x10010550,3)])
    "wake priority issued a new power command or acknowledged the wrong observed mask"
  IO.println "PASS independent Lean power authority, priority, S-return, and WFI policy"

end PowerControlFixture
run_cmd do
  Lean.Elab.Command.liftTermElabM do
    PowerControlFixture.main
