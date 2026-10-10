import Lean
import Lemma.Services.Store.Engine

/-! Host-only focused probe of the actual elaborated guest Action declarations.
It supplies only virtual byte memory and sector read/write/flush effects. It is
not the simulator backend, live document recovery, or RV64 execution evidence.
The independent Python oracle parses the exported disk bytes separately. -/
namespace StoreProbe
open Lemma.Core0.Memory
open Lemma.Services.Store

def context : UInt64 := 0x1000
def buffer : UInt64 := 0x2000
def index : UInt64 := 0x10000
def nextIndex : UInt64 := 0x80000
def payload : UInt64 := 0xf0000
def capacity : UInt64 := 4096

structure VM where
  memory : Array UInt8 := Array.replicate 0x100000 0
  pending : Array UInt8 := Array.replicate (4096 * 512) 0
  durable : Array UInt8 := Array.replicate (4096 * 512) 0
  trace : Array String := #[]

def readWord (bytes : Array UInt8) (address : UInt64) (width : Nat := 8) : UInt64 := Id.run do
  let mut value : UInt64 := 0
  for i in [:width] do
    value := value ||| (bytes[address.toNat + i]!.toUInt64 <<< UInt64.ofNat (8 * i))
  return value

def writeWord (bytes : Array UInt8) (address value : UInt64) (width : Nat := 8) : Array UInt8 := Id.run do
  let mut output := bytes
  for i in [:width] do
    output := output.set! (address.toNat + i) ((value >>> UInt64.ofNat (8 * i)).toUInt8)
  return output

partial def run (vm : IO.Ref VM) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status, value)
  | .bind first next => do
      let (status, value) ← run vm first
      run vm (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next => do
      if budget < count.toNat then run vm (next 9 initial) else
      let mut value := initial
      let mut status : UInt8 := 0
      for i in [:count.toNat] do
        if status = 0 then
          let (s, v) ← run vm (step (UInt32.ofNat i) count value c0 c1 c2 c3)
          status := s
          value := v
      run vm (next (if status = 10 then 0 else status) value)
  | .platform operation a b _ _ _ _ next => do
      if a.toNat > 0x100000 - 8 then throw <| IO.userError "probe memory bounds" else
      match operation with
      | .virtualRead8 =>
          let value := readWord (← vm.get).memory a 1
          run vm (next 0 value)
      | .virtualRead64 =>
          let value := readWord (← vm.get).memory a
          run vm (next 0 value)
      | .virtualWrite8 =>
          vm.modify fun state => { state with memory := writeWord state.memory a b 1 }
          run vm (next 0 0)
      | .virtualWrite64 =>
          vm.modify fun state => { state with memory := writeWord state.memory a b }
          run vm (next 0 0)
      | _ => throw <| IO.userError "probe rejects non-memory platform operation"
  | _ => throw <| IO.userError "probe rejects unsupported Action"

def require (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message

def action (vm : IO.Ref VM) (program : Action) : IO UInt64 := do
  let (status, value) ← run vm program
  require (status == 0) s!"actual store Action failed status{status}"
  pure value

def get (vm : IO.Ref VM) (offset : UInt64) : IO UInt64 := do
  pure <| readWord (← vm.get).memory (context + offset)

def step (vm : IO.Ref VM) (expectedStatus : UInt8 := 0) : IO Unit := do
  let operation ← get vm 0
  let phase ← get vm 8
  let sector ← get vm 16
  let ack ← get vm 40
  let before ← vm.get
  require (operation ≥ 1 && operation ≤ 3) "invalid real store operation"
  require (sector < capacity || operation == 3) "invalid real store sector"
  vm.modify fun state => { state with trace := state.trace.push s!"{operation}:{phase}:{sector}:{ack}" }
  if operation = 1 then
    vm.modify fun state => { state with memory := Id.run do
      let mut memory := state.memory
      for i in [:512] do
        memory := memory.set! (buffer.toNat + i) state.pending[sector.toNat * 512 + i]!
      return memory }
  else if operation = 2 then
    vm.modify fun state => { state with pending := Id.run do
      let mut disk := state.pending
      for i in [:512] do
        disk := disk.set! (sector.toNat * 512 + i) state.memory[buffer.toNat + i]!
      return disk }
  else vm.modify fun state => { state with durable := state.pending }
  let (status, _) ← run vm (Engine.complete context 0)
  require (status == expectedStatus) s!"unexpected actual store completion status{status}"
  if 16 ≤ phase && phase ≤ 20 then require ((← get vm 40) == ack) "acknowledged before final flush"
  if operation != 3 then require ((← vm.get).durable == before.durable) "write changed stable medium"

def drive (vm : IO.Ref VM) (stopPhase : UInt64 := 0) : IO Unit := do
  let mut finished := false
  for _ in [:20000] do
    if !finished then
      let operation ← get vm 0
      let phase ← get vm 8
      if operation = 0 || (stopPhase != 0 && phase = stopPhase) then finished := true else step vm
  require finished "bounded store probe did not terminate"

def setPayload (vm : IO.Ref VM) (bytes : ByteArray) : IO Unit :=
  vm.modify fun state => { state with memory := Id.run do
    let mut memory := state.memory
    for i in [:bytes.size] do memory := memory.set! (payload.toNat + i) bytes[i]!
    return memory }

def append (vm : IO.Ref VM) (ns object tx : UInt64) (text : String) : IO Unit := do
  let bytes := text.toUTF8
  setPayload vm bytes
  let _ ← action vm (Engine.appendStart context ns object tx payload (UInt64.ofNat bytes.size) 1)

def cold (old : VM) : IO (IO.Ref VM) := IO.mkRef { pending := old.durable, durable := old.durable }

def mount (vm : IO.Ref VM) : IO Unit := do
  let _ ← action vm (Engine.mountStart context buffer index capacity)
  drive vm

def writeArtifacts (directory name : String) (vm : IO.Ref VM) : IO Unit := do
  let state ← vm.get
  IO.FS.writeBinFile (System.FilePath.mk directory / (name ++ ".img")) (ByteArray.mk state.durable)
  IO.FS.writeFile (System.FilePath.mk directory / (name ++ ".trace")) (String.intercalate "\n" state.trace.toList ++ "\n")

def fixture : IO (IO.Ref VM) := do
  let vm ← IO.mkRef ({} : VM)
  let _ ← action vm (Engine.formatStart context buffer index capacity)
  drive vm
  append vm 1 1 1 "first notebook"
  drive vm
  append vm 2 1 2 "second notebook"
  drive vm
  append vm 1 1 3 "first revised"
  drive vm
  require ((← get vm 40) == 3) "fixture acknowledgement"
  pure vm

def main (arguments : List String) : IO UInt32 := do
  let directory := arguments.headD "build/lemmasim/store-probe"
  IO.FS.createDirAll directory
  let vm ← fixture
  writeArtifacts directory "append" vm
  let _ ← action vm (Engine.checkpointStart context nextIndex)
  drive vm
  require ((← get vm 56) == 2) "checkpoint did not advance root"
  require ((← get vm 40) == 3) "checkpoint changed sequence"
  writeArtifacts directory "checkpoint" vm
  let restored ← cold (← vm.get)
  mount restored
  require ((← get restored 40) == 3) "cold recovery failed"
  let _ ← action restored (Engine.readStart context 1 1 0 13 payload)
  drive restored
  let memory := (← restored.get).memory
  require ((ByteArray.mk (memory.extract payload.toNat (payload.toNat + 13))).utf8Decode? == some "first revised".toList.toArray) "ordinary record consumer read"
  let _ ← action restored (Engine.readStart context 1 1 7 128 payload)
  drive restored
  require ((← get restored 352) == 6) "short read did not report actual length"
  require ((ByteArray.mk ((← restored.get).memory.extract payload.toNat (payload.toNat + 6))).utf8Decode? == some "evised".toList.toArray) "short read bytes"
  let _ ← action restored (Engine.readStart context 1 1 13 128 payload)
  drive restored
  require ((← get restored 352) == 0) "EOF did not return an empty short read"
  let _ ← action restored (Engine.readStart context 1 1 14 128 payload)
  step restored Format.malformed
  require ((← get restored 336) == 0) "bad client range made another notebook read-only"
  let (absent, _) ← run restored (Engine.lookup context 3 1)
  require (absent == Format.notFound) "namespace isolation lookup"
  writeArtifacts directory "recovered" restored
  let base ← restored.get
  for phase in [16, 17, 18, 19, 20, 21] do
    let interrupted ← cold base
    mount interrupted
    append interrupted 1 2 4 "pending fourth object"
    drive interrupted phase
    require ((← get interrupted 40) == 3) "cut fixture acknowledged pending work"
    let recovered ← cold (← interrupted.get)
    mount recovered
    require ((← get recovered 40) == 3) s!"cut phase{phase} lost acknowledged work"
    writeArtifacts directory s!"cut-{phase}" recovered
  let torn ← cold base
  mount torn
  append torn 1 2 4 "torn publication"
  drive torn 20
  let tornSector ← get torn 16
  torn.modify fun state => { state with durable := Id.run do
    let mut disk := state.durable
    for i in [:48] do disk := disk.set! (tornSector.toNat * 512 + i) state.memory[buffer.toNat + i]!
    return disk }
  let tornRecovery ← cold (← torn.get)
  mount tornRecovery
  require ((← get tornRecovery 40) == 3) "torn publication lost acknowledged work"
  writeArtifacts directory "torn-publication" tornRecovery
  let failed ← cold base
  mount failed
  append failed 1 2 4 "failed flush"
  drive failed 19
  let (status, _) ← run failed (Engine.complete context 1)
  require (status == Format.transportFailed) "failed flush not rejected"
  require ((← get failed 40) == 3) "failed flush acknowledged"
  let failedRecovery ← cold (← failed.get)
  mount failedRecovery
  writeArtifacts directory "failed-flush" failedRecovery
  let durablePending ← cold base
  mount durablePending
  append durablePending 1 2 4 "durable before ack"
  drive durablePending 21
  durablePending.modify fun state => { state with durable := state.pending }
  let durablePendingRecovery ← cold (← durablePending.get)
  mount durablePendingRecovery
  require ((← get durablePendingRecovery 40) == 4) "wholly durable unacknowledged transaction did not recover"
  writeArtifacts directory "flushed-before-ack" durablePendingRecovery
  for phase in [32, 33, 34, 35, 36, 37, 38, 39, 40] do
    let interrupted ← cold base
    mount interrupted
    let _ ← action interrupted (Engine.checkpointStart context nextIndex)
    drive interrupted phase
    let recovered ← cold (← interrupted.get)
    mount recovered
    require ((← get recovered 40) == 3) s!"checkpoint cut phase{phase} lost acknowledged work"
    writeArtifacts directory s!"checkpoint-cut-{phase}" recovered
  let completed ← cold base
  mount completed
  append completed 1 2 4 "durable fourth"
  drive completed
  require ((← get completed 40) == 4) "final flush did not acknowledge"
  let afterAck ← cold (← completed.get)
  mount afterAck
  require ((← get afterAck 40) == 4) "acknowledged transaction lost on cold mount"
  writeArtifacts directory "after-ack" afterAck
  IO.println "STORE_PROBE_HOST_ACTION_PASS (not RV64/device acceptance)"
  pure 0

end StoreProbe

def main := StoreProbe.main
