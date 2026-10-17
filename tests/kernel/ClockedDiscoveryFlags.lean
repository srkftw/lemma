import Lemma.Platform.LemmaSim.DescriptorDTB
import Lean

/-! Host-only execution of the genuine private Clocked leaf Action against opaque
raw compiled FDT bytes. This interpreter is never imported into target images. -/
open Lean Elab Command
run_cmd do
  let rows := (← getEnv).constants.toList.filter fun p =>
    p.1.toString.endsWith "DescriptorDTB.leafPropertyClocked"
  unless rows.length = 1 do throwError "exact maintained Clocked leaf required"
  let n := mkIdent rows.head!.1
  elabCommand (← `(def $(mkIdent `observedClockedLeaf) (data bytes code role : UInt64) :
      Lemma.Core0.Memory.Action := $n data bytes code role))

run_cmd do
  let rows := (← getEnv).constants.toList.filter fun p =>
    p.1.toString.endsWith "DescriptorDTB.actualUSBClocked"
  unless rows.length = 1 do throwError "exact maintained actual Clocked register reader required"
  let n := mkIdent rows.head!.1
  elabCommand (← `(def $(mkIdent `observedClockedIdentity) : Lemma.Core0.Memory.Action := $n))

namespace ClockedDiscoveryFlags
open Lemma.Core0.Memory
structure State where
  raw : ByteArray
  flags : UInt64 := 0
  parent : UInt64 := 0
  reads : Nat := 0
  writes : Nat := 0
  failAt : Nat := 100000
  registers : Array UInt64 := #[2,48000000,100000000,1,128,67]
  addresses : Array UInt64 := #[]
  deriving Inhabited
private def check (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw (IO.userError message)
private def dtb : UInt64 := 0x87e00000
private def scratch : UInt64 := Lemma.Platform.LemmaSim.DescriptorDTB.scratch
partial def execute (cell : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute cell first
    execute cell (next s v)
  | .platform op address value _ _ _ _ next =>
    let old ← cell.get
    if op = .physicalRead8 then
      check (dtb ≤ address && address-dtb < old.raw.size.toUInt64) "raw FDT byte bound"
      cell.set {old with reads := old.reads+1}
      execute cell (next (if old.reads = old.failAt then 7 else 0)
        (old.raw[(address-dtb).toNat]!.toUInt64))
    else if op = .physicalRead64 then
      check (address = scratch+64 || address = scratch+72 || address = scratch+176) "unexpected scratch read"
      cell.set {old with reads := old.reads+1}
      execute cell (next (if old.reads = old.failAt then 7 else 0)
        (if address = scratch+64 then old.flags else if address = scratch+72 then old.parent else 12))
    else if op = .physicalWrite64 then
      check (address = scratch+64 || address = scratch+72) "unexpected scratch publication"
      cell.set (if address = scratch+64 then {old with flags := value, writes := old.writes+1}
                else {old with parent := value, writes := old.writes+1})
      execute cell (next 0 0)
    else if op = .deviceRead64 then
      check (0x10010ab0 ≤ address && address ≤ 0x10010ad8 && address % 8 = 0) "actual Clocked register range"
      let index := ((address-0x10010ab0)/8).toNat
      cell.set {old with reads := old.reads+1, addresses := old.addresses.push address}
      execute cell (next (if old.reads = old.failAt then 7 else 0) old.registers[index]!)
    else throw (IO.userError "unmodeled primitive in actual Clocked leaf")
  | .boundedFoldU64 bound step count acc a b c d next =>
    check (count.toNat ≤ bound) "fold bound"
    let mut acc := acc
    let mut status : UInt8 := 0
    for i in [:count.toNat] do
      if status = 0 then
        let (s,v) ← execute cell (step i.toUInt32 count acc a b c d)
        status := s; acc := v
    execute cell (next status acc)
  | _ => throw (IO.userError "unmodeled Action in Clocked leaf")
def properties : Array (UInt64 × UInt64 × UInt64) := #[
  (2008,28,32),(2048,16,33),(2076,4,34),(2092,4,35),(2108,4,38),
  (2124,4,53),(2140,4,56),(2156,4,57),(2172,4,58),
  (2188,4,65),(2204,4,66),(2220,4,67),(2236,4,68),
  (2252,4,92),(2268,4,93),(2284,4,94),(2300,4,95)]
def main : IO Unit := do
  let some path ← IO.getEnv "LEMMA_CLOCKED_DTB" | throw (IO.userError "actual compiled Clocked FDT required")
  let raw ← IO.FS.readBinFile path
  let cell ← IO.mkRef ({raw := raw} : State)
  let mut last : UInt8 := 0
  let mut lastCode : UInt64 := 0
  for (offset,bytes,c) in properties do
    if last = 0 then
      let (s,_) ← execute cell (observedClockedLeaf (dtb+offset) bytes c 13)
      last := s; lastCode := c
  let state ← cell.get
  check (last = 0 && lastCode = 95 && state.flags = 131071) "actual complete Clocked USB leaf flags"
  let facts : Array (UInt64 × UInt64 × UInt64) := #[(2172,58,256),(2188,65,512),(2252,92,8192),
       (2268,93,16384),(2284,94,32768),(2300,95,65536)]
  for (offset,code,flag) in facts do
    let value := raw[offset.toNat+3]!
    let wrong ← IO.mkRef ({raw := raw.set! (offset.toNat+3) (value ^^^ 1)} : State)
    let (s,_) ← execute wrong (observedClockedLeaf (dtb+offset) 4 code 13)
    let result ← wrong.get
    check (s = 169 && result.flags = 0 && result.writes = 0) "wrong immutable Clocked fact accepted"
    let duplicate ← IO.mkRef ({raw := raw} : State)
    let (s,_) ← execute duplicate (observedClockedLeaf (dtb+offset) 4 code 13)
    check (s = 0) "first Clocked fact failed"
    let before ← duplicate.get
    check (before.flags = flag) "Clocked fact uses wrong/nonunique bit"
    let (s,_) ← execute duplicate (observedClockedLeaf (dtb+offset) 4 code 13)
    let after ← duplicate.get
    check (s = 169 && after.flags = flag && after.writes = before.writes) "duplicate Clocked property published"
    let short ← IO.mkRef ({raw := raw} : State)
    let (s,_) ← execute short (observedClockedLeaf (dtb+offset) 3 code 13)
    let result ← short.get
    check (s = 169 && result.reads = 0 && result.writes = 0) "bad Clocked cell width touched memory"
    for index in [:5] do
      let fault ← IO.mkRef ({raw := raw, failAt := index} : State)
      let (s,_) ← execute fault (observedClockedLeaf (dtb+offset) 4 code 13)
      let result ← fault.get
      check (s = 7 && result.flags = 0 && result.writes = 0 && result.reads = index+1) "Clocked read fault prefix changed"
  let positive ← IO.mkRef ({raw := raw} : State)
  let (s,v) ← execute positive observedClockedIdentity
  let state ← positive.get
  check (s = 0 && v = 1 && state.reads = 6 && state.writes = 0 &&
    state.addresses = #[0x10010ab0,0x10010ab8,0x10010ac0,0x10010ac8,0x10010ad0,0x10010ad8])
    "exact six immutable Clocked register reads"
  for index in [:6] do
    let registers := state.registers.set! index (state.registers[index]! ^^^ 1)
    let wrong ← IO.mkRef ({raw := raw, registers := registers} : State)
    let (s,_) ← execute wrong observedClockedIdentity
    let result ← wrong.get
    check (s = 169 && result.reads = index+1 && result.writes = 0) "wrong actual Clocked identity accepted"
    let fault ← IO.mkRef ({raw := raw, failAt := index} : State)
    let (s,_) ← execute fault observedClockedIdentity
    let result ← fault.get
    check (s = 7 && result.reads = index+1 && result.writes = 0) "actual Clocked identity read fault prefix"
  IO.println "CLOCKED_RAW_FDT:PASS17FLAGS_6FACTS_DUPLICATE_WIDTH_30FAULTS_6REGISTERS_12NEGATIVES"
end ClockedDiscoveryFlags
#eval ClockedDiscoveryFlags.main
