import StoreProbe

/-! Host-only behavioral probe of actual elaborated guest Actions. Expected
sector traces and bytes below are independently literal; no cache transition
function is used to compute their oracle. This is not RV64 acceptance. -/
namespace StoreReadCache
open StoreProbe
open Lemma.Services.Store

def pattern (i : Nat) : UInt8 := UInt8.ofNat (i % 251)

def read (vm : IO.Ref VM) (ns object offset count : UInt64) : IO Unit := do
  let _ ← action vm (Engine.readStart context ns object offset count payload)
  drive vm

def bytesAre (vm : IO.Ref VM) (offset count : Nat) : IO Unit := do
  let memory := (← vm.get).memory
  for i in [:count] do
    require (memory[payload.toNat + i]! == pattern (offset + i)) s!"literal read mismatch byte{i}"

def readTrace (vm : IO.Ref VM) : IO (Array String) := do
  pure <| (← vm.get).trace.filter fun row => row.startsWith "1:80:" || row.startsWith "1:81:"

def main : IO Unit := do
  let some output ← IO.getEnv "LEMMA_CACHE_OUT" | throw <| IO.userError "LEMMA_CACHE_OUT required"
  require (!(← (System.FilePath.mk output).pathExists)) "cache probe refuses existing output"
  IO.FS.createDirAll output
  let vm ← IO.mkRef ({} : VM)
  let _ ← action vm (Engine.formatStart context buffer index capacity)
  drive vm
  setPayload vm (ByteArray.mk (Array.ofFn (n := 1024) fun i => pattern i.val))
  let _ ← action vm (Engine.appendStart context 1 7 1 payload 1024 1)
  drive vm
  append vm 2 7 2 "different namespace"
  drive vm
  read vm 1 7 0 128
  bytesAre vm 0 128
  -- The transport page may be reused while the immutable private cache lives.
  vm.modify fun st => { st with memory := writeWord st.memory buffer 0xffffffffffffffff }
  for offset in [128, 256, 384] do
    read vm 1 7 offset 128
    bytesAre vm offset.toNat 128
  require ((← readTrace vm) == #["1:80:8:2", "1:81:9:2"]) "four128B replies reread their header/body"
  read vm 1 7 480 128
  bytesAre vm 480 128
  require ((← readTrace vm) == #["1:80:8:2", "1:81:9:2", "1:81:10:2"]) "cross-sector boundary skipped/repeated I/O"
  read vm 1 7 608 128
  bytesAre vm 608 128
  require ((← readTrace vm).size == 3) "next same-sector reply missed window"
  let (bad, _) ← run vm (Engine.readStart context 1 7 1025 128 payload)
  require (bad == Format.malformed && (← get vm 336) == 0) "bad range changed store authority"
  read vm 2 7 0 19
  require ((← readTrace vm).toList.drop 3 == ["1:80:12:2", "1:81:13:2"]) "namespace cache key omitted"
  require ((ByteArray.mk ((← vm.get).memory.extract payload.toNat (payload.toNat + 19))).utf8Decode? == some "different namespace".toList.toArray) "namespace bytes crossed"
  read vm 1 7 0 128
  bytesAre vm 0 128
  -- Index revision changes happen through real append completion.
  append vm 1 7 3 "replacement"
  require ((← get vm 376) == 0 && (← get vm 432) == 0) "write did not invalidate cache before submission"
  drive vm
  read vm 1 7 0 11
  require ((← get vm 400) == 3) "replacement reused old sequence"
  require ((ByteArray.mk ((← vm.get).memory.extract payload.toNat (payload.toNat + 11))).utf8Decode? == some "replacement".toList.toArray) "replacement returned stale bytes"
  let beforeCheckpoint ← vm.get
  let _ ← action vm (Engine.checkpointStart context nextIndex)
  require ((← get vm 376) == 0 && (← get vm 432) == 0) "checkpoint source read retained old cache"
  drive vm
  read vm 1 7 0 11
  require ((← get vm 408) == 2) "checkpoint reused prior generation"
  let restored ← cold (← vm.get)
  mount restored
  require ((← get restored 376) == 0 && (← get restored 432) == 0) "mount inherited volatile read window"
  read restored 1 7 0 11
  -- Even when media stays valid, transport failure discards both valid bits.
  let failed ← IO.mkRef beforeCheckpoint
  let _ ← action failed (Engine.readStart context 2 7 0 19 payload)
  let (transport, _) ← run failed (Engine.complete context 1)
  require (transport == Format.transportFailed) "failed read became cache success"
  require ((← get failed 376) == 0 && (← get failed 432) == 0) "read error retained window"
  require ((← get failed 40) == 3) "read failure altered commit sequence"
  -- A stale generation cannot pass even with identical index/source/sequence.
  let stale ← IO.mkRef beforeCheckpoint
  let _ ← action stale (Engine.put context 56 2)
  let _ ← action stale (Engine.readStart context 1 7 0 11 payload)
  require ((← get stale 8) == 80) "generation not part of cache key"
  step stale Format.malformed
  require ((← get stale 376) == 0 && (← get stale 432) == 0) "malformed header retained window"
  writeArtifacts output "cached-recovery" restored
  IO.FS.writeFile (System.FilePath.mk output / "reads.trace") (String.intercalate "\n" (← readTrace vm).toList ++ "\n")
  IO.println "STORE_READ_CACHE_HOST_ACTION_PASS (not RV64/device acceptance)"

end StoreReadCache
#eval StoreReadCache.main
