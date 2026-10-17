import Lemma.Platform.LemmaSim.DescriptorDTB
import Lean

/-! Host-only execution of the genuine private Wire leaf Action against opaque
raw compiled FDT bytes. This interpreter is never imported into target images. -/
open Lean Elab Command
run_cmd do
  let rows := (← getEnv).constants.toList.filter fun p =>
    p.1.toString.endsWith "DescriptorDTB.leafPropertyWire"
  unless rows.length = 1 do throwError "exact maintained Wire leaf required"
  let n := mkIdent rows.head!.1
  elabCommand (← `(def $(mkIdent `observedWireLeaf) (data bytes code role : UInt64) :
      Lemma.Core0.Memory.Action := $n data bytes code role))

namespace WireDiscoveryFlags
open Lemma.Core0.Memory
structure State where
  raw : ByteArray
  flags : UInt64 := 0
  parent : UInt64 := 0
  reads : Nat := 0
  writes : Nat := 0
  failAt : Nat := 100000
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
        (if address = scratch+64 then old.flags else if address = scratch+72 then old.parent else 10))
    else if op = .physicalWrite64 then
      check (address = scratch+64 || address = scratch+72) "unexpected scratch publication"
      cell.set (if address = scratch+64 then {old with flags := value, writes := old.writes+1}
                else {old with parent := value, writes := old.writes+1})
      execute cell (next 0 0)
    else throw (IO.userError "unmodeled primitive in actual Wire leaf")
  | .boundedFoldU64 bound step count acc a b c d next =>
    check (count.toNat ≤ bound) "fold bound"
    let mut acc := acc
    let mut status : UInt8 := 0
    for i in [:count.toNat] do
      if status = 0 then
        let (s,v) ← execute cell (step i.toUInt32 count acc a b c d)
        status := s; acc := v
    execute cell (next status acc)
  | _ => throw (IO.userError "unmodeled Action in Wire leaf")
def properties : Array (UInt64 × UInt64 × UInt64) := #[
  (2008,25,32),(2048,16,33),(2076,4,34),(2092,4,35),(2108,4,38),
  (2124,4,53),(2140,4,56),(2156,4,57),(2172,4,58),
  (2188,4,65),(2204,4,66),(2220,4,67),(2236,4,68)]
def main : IO Unit := do
  let some path ← IO.getEnv "LEMMA_WIRE_DTB" | throw (IO.userError "actual compiled Wire FDT required")
  let raw ← IO.FS.readBinFile path
  let cell ← IO.mkRef ({raw := raw} : State)
  let mut last : UInt8 := 0
  let mut code : UInt64 := 0
  for (offset,bytes,c) in properties do
    if last = 0 then
      let (s,_) ← execute cell (observedWireLeaf (dtb+offset) bytes c 13)
      last := s; code := c
  let state ← cell.get
  if (← IO.getEnv "LEMMA_WIRE_LEGACY_FAILURE") = some "1" then
    check (last = 169 && code = 58 && state.flags = 255) "original real Wire duplicate flag failure differs"
    IO.println "WIRE_ORIGINAL_RAW_FDT:REPRODUCED169_CODE58_FLAGS255"
  else
    check (last = 0 && state.flags = 8191) "corrected actual full Wire leaf requiredflags"
    let wrong ← IO.mkRef ({raw := raw.set! 2175 1, flags := 255, parent := 2} : State)
    let (s,_) ← execute wrong (observedWireLeaf (dtb+2172) 4 58 13)
    let result ← wrong.get
    check (s = 169 && result.flags = 255 && result.writes = 0) "wrong decoded boundary accepted"
    let duplicate ← IO.mkRef ({raw := raw, flags := 255, parent := 2} : State)
    let (s,_) ← execute duplicate (observedWireLeaf (dtb+2172) 4 58 13)
    check (s = 0) "first decoded property failed"
    let before ← duplicate.get
    let (s,_) ← execute duplicate (observedWireLeaf (dtb+2172) 4 58 13)
    let after ← duplicate.get
    check (s = 169 && before.flags = 511 && after.flags = before.flags && after.writes = before.writes) "duplicate property was published"
    let short ← IO.mkRef ({raw := raw, flags := 255} : State)
    let (s,_) ← execute short (observedWireLeaf (dtb+2172) 3 58 13)
    let state ← short.get
    check (s = 169 && state.reads = 0 && state.writes = 0) "bad cell width touched memory"
    for index in [:5] do
      let fault ← IO.mkRef ({raw := raw, flags := 255, failAt := index} : State)
      let (s,_) ← execute fault (observedWireLeaf (dtb+2172) 4 58 13)
      let state ← fault.get
      check (s = 7 && state.flags = 255 && state.writes = 0 && state.reads = index+1) "read error/write prefix changed"
    IO.println "WIRE_RAW_FDT_FLAGS:PASS8191_WRONGBOUNDARY_DUPLICATE_WIDTH_5FAULTS"
end WireDiscoveryFlags
#eval WireDiscoveryFlags.main
