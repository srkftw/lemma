import Lemma.Services.Store.Remount
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Actual Lean shadow mount Actions with generic sector reads from a retained
opaque file. The fixture never parses or recovers a journal itself. Its literal
original readonly context is not an RV64 process. No WRITE/BARRIER is allowed. -/
namespace StoreRemountTests
open Lemma.Core0.Memory Lemma.Services.Store

structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  reads : Array UInt64 := #[]
  writeAddresses : Array UInt64 := #[]

private def read (m : Model) (a : UInt64) : UInt64 := m.words.getD a 0
private def write (m : Model) (a v : UInt64) : Model := {m with words := m.words.insert a v}
private def byte (m : Model) (a : UInt64) : UInt64 := (read m (a-a%8) >>> (a%8*8)) &&& 255
private def writeByte (m : Model) (a v : UInt64) : Model :=
  let shift := a%8*8
  write m (a-a%8) ((read m (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((v &&& 255) <<< shift))

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s value => pure (s,value)
  | .bind first next => do
      let (s,value) ← run state first
      run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if budget < count.toNat then throw <| IO.userError "remount exceeded declared fold"
      let mut result := ((0 : UInt8),initial)
      for i in [:count.toNat] do
        if result.1 = 0 then result ← run state (step i.toUInt32 count result.2 a b c d)
      run state (next result.1 result.2)
  | .platform operation a b _ _ _ _ next => do
      if a < 0x40000 || 0x64000 ≤ a then throw <| IO.userError "remount touched outside owned Store fixture"
      match operation with
      | .virtualRead64 => run state (next 0 (read (← state.get) a))
      | .virtualRead8 => run state (next 0 (byte (← state.get) a))
      | .virtualWrite64 =>
          state.modify fun m => {write m a b with writeAddresses := m.writeAddresses.push a}
          run state (next 0 0)
      | .virtualWrite8 =>
          state.modify fun m => {writeByte m a b with writeAddresses := m.writeAddresses.push a}
          run state (next 0 0)
      | _ => throw <| IO.userError "remount acquired syscall/MMIO/external effect"
  | _ => throw <| IO.userError "remount acquired undeclared Action"

private def initial (capacity : UInt64) : Model := Id.run do
  let mut m : Model := {}
  for i in [:512] do m := write m (Remount.current+i.toUInt64*8) (0xaabbccdd00000000+i.toUInt64)
  for (offset,value) in #[(0,0),(24,Remount.currentBuffer),(32,227),(40,11),
      (48,capacity),(104,Remount.firstIndex),(336,1)] do
    m := write m (Remount.current+offset) value
  for i in [:6144] do m := write m (Remount.firstIndex+i.toUInt64*8) (0xfedcba9800000000+i.toUInt64)
  return m

private def originalUnchanged (before after : Model) : IO Unit := do
  for (base,words) in #[(Remount.current,512),(Remount.firstIndex,6144)] do
    for i in [:words] do
      if read before (base+i.toUInt64*8) != read after (base+i.toUInt64*8) then
        throw <| IO.userError "shadow scan/preflight changed the original readonly context/index"

private def scan (state : IO.Ref Model) (mediumBytes : ByteArray) : IO Unit := do
  let mut ended := false
  for _ in [:2500] do
    if !ended then
      let m ← state.get
      let operation := read m (Remount.shadow+0)
      if operation = 0 then ended := true else
      if operation != 1 then throw <| IO.userError "remount attempted WRITE/BARRIER instead of opaque READ"
      let sector := read m (Remount.shadow+16)
      let buffer := read m (Remount.shadow+24)
      if buffer != Remount.shadowBuffer || mediumBytes.size.toUInt64/512 ≤ sector then
        throw <| IO.userError "shadow scan changed buffer ownership or sector bounds"
      let mut after := {m with reads := m.reads.push sector}
      for word in [:64] do
        let offset := sector.toNat*512+word*8
        let value := (List.range 8).foldl (fun value i => value ||| (mediumBytes[offset+i]!.toUInt64 <<< (i.toUInt64*8))) 0
        after := write after (buffer+word.toUInt64*8) value
      state.set after
      let _ ← run state (Engine.complete Remount.shadow 0)
  if !ended then throw <| IO.userError "shadow mount exceeded the independent2500 READ resource bound"

def check (mediumBytes : ByteArray) : IO Unit := do
  if mediumBytes.size != 268435456 then throw <| IO.userError "fixture requires retained complete268MiB opaque medium"
  let before := initial (mediumBytes.size.toUInt64/512)
  for (offset,value) in #[(0,1),(336,0),(24,Remount.currentBuffer+8),(48,1),(104,Remount.secondIndex+8)] do
    let original := write before (Remount.current+offset) value
    let state ← IO.mkRef original
    if (← run state (Remount.start 524288 91 2)).1 = 0 then
      throw <| IO.userError "invalid current state admitted shadow mount"
    if !(← state.get).writeAddresses.isEmpty then throw <| IO.userError "remount guard wrote before validating current state"
    originalUnchanged original (← state.get)
  for (ticket,epoch) in #[(0,2),(91,0)] do
    let state ← IO.mkRef before
    if (← run state (Remount.start 524288 ticket epoch)).1 = 0 || !(← state.get).writeAddresses.isEmpty then
      throw <| IO.userError "zero connection/ticket admitted a mount effect"
  let liveShadow ← IO.mkRef (write before (Remount.shadow+0) 1)
  if (← run liveShadow (Remount.start 524288 91 2)).1 != Remount.busy ||
      !(← liveShadow.get).writeAddresses.isEmpty then throw <| IO.userError "new mount overwrote in-flight shadow state"
  let state ← IO.mkRef before
  if (← run state (Remount.start 524288 91 2)) != (0,Remount.secondIndex) then
    throw <| IO.userError "remount did not choose the unused owned index"
  originalUnchanged before (← state.get)
  if (← run state (Remount.adopt 91 2)).1 != Remount.busy then
    throw <| IO.userError "Pending scan was published"
  originalUnchanged before (← state.get)
  let started ← state.get
  let failed ← IO.mkRef started
  let _ ← run failed (Engine.complete Remount.shadow 165)
  if (← run failed (Remount.adopt 91 2)).1 = 0 then throw <| IO.userError "failed READ made current Store writable"
  originalUnchanged before (← failed.get)
  scan state mediumBytes
  let mounted ← state.get
  originalUnchanged before mounted
  if mounted.reads.isEmpty || read mounted (Remount.shadow+32) != 0 || read mounted (Remount.shadow+336) != 0 ||
      read mounted (Remount.shadow+40) != 11 then throw <| IO.userError "actual Engine did not validate retained Saved11 medium"
  for (offset,value) in #[(3584,0),(3592,2),(3600,92),(3608,3),(0,1),(32,227),(336,1),
      (24,Remount.currentBuffer),(3616,1),(48,1),(3624,Remount.secondIndex),(3632,Remount.firstIndex),
      (104,Remount.firstIndex),(40,0xffffffffffffffff)] do
    let rejected ← IO.mkRef {write mounted (Remount.shadow+offset) value with writeAddresses := #[]}
    if (← run rejected (Remount.adopt 91 2)).1 = 0 || !(← rejected.get).writeAddresses.isEmpty then
      throw <| IO.userError "wrong epoch/ticket/capacity/index/failed scan wrote current state"
    originalUnchanged before (← rejected.get)
  if (← run state (Remount.adopt 91 2)) != (0,11) then throw <| IO.userError "complete mount was not adopted as observed sequence"
  let adopted ← state.get
  if read adopted (Remount.current+104) != Remount.secondIndex || read adopted (Remount.current+24) != Remount.currentBuffer ||
      read adopted (Remount.current+336) != 0 || read adopted (Remount.current+376) != 0 ||
      read adopted (Remount.current+432) != 0 || read adopted (Remount.current+3584) != 0 then
    throw <| IO.userError "adoption kept stale cache, shadow buffer or control metadata"
  for i in [:6144] do
    if read adopted (Remount.firstIndex+i.toUInt64*8) != read before (Remount.firstIndex+i.toUInt64*8) then
      throw <| IO.userError "adoption overwrote previous owned index"
  IO.println s!"STORE_REMOUNT_ACTION:PASS actual Lean Engine validates opaque Saved11 using {mounted.reads.size} READs; current/index unchanged through pending/failure/14 adoption mutants; no WRITE/BARRIER/format/Saved/target CPU claim"
end StoreRemountTests

open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_2
      #[``Lemma.Services.Store.Remount.start, ``Lemma.Services.Store.Remount.adopt] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_2 suite with
  | .ok _ => pure ()
  | .error diagnostic => throwError diagnostic
  logInfo "STORE_REMOUNT_COMPILE:PASS actual shadow start/adoption under existing User2 scalar authority; caller/device epoch reconciliation remains separate"

def main (args : List String) : IO Unit := do
  let [path] := args | throw <| IO.userError "Remount fixture requires one independently bound opaque medium"
  StoreRemountTests.check (← IO.FS.readBinFile path)
