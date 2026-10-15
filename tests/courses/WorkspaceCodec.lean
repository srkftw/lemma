import Lemma.Courses.WorkspaceCodec

/-! Independent RAM/effect interpreter of the maintained guest Actions.
The oracle lays out bitmap groups from raw words independently. No CPU,
Store barrier, checker result or mathematical authority is asserted here. -/
namespace WorkspaceCodecTests
open Lemma.Core0.Memory Lemma.Courses Lemma.Documents

def source : UInt64 := 0x10000
def packed : UInt64 := 0x12000
def restored : UInt64 := 0x14000
def doc : UInt64 := 0x16000
structure Model where
  memory : Array UInt64 := Array.replicate 4096 0
  reads : Array UInt64 := #[]
  writes : Array UInt64 := #[]
  readFault : UInt64 := 0
  writeFault : UInt64 := 0
private def index (a : UInt64) : IO Nat := do
  unless a % 8 == 0 && source ≤ a && a < source+32768 do
    throw <| IO.userError "codec escaped independent aligned RAM"
  return ((a-source)/8).toNat
private def set (r : IO.Ref Model) (a v : UInt64) : IO Unit := do
  let i ← index a
  r.modify fun m => {m with memory := m.memory.set! i v}
private def word (r : IO.Ref Model) (a : UInt64) : IO UInt64 := do
  let i ← index a
  return (← r.get).memory[i]!
partial def run (r : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
    let (s,v) ← run r first
    run r (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if budget < count.toNat then throw <| IO.userError "codec fold exceeded declared bound"
    let mut result := (0,initial)
    for i in [:count.toNat] do
      if result.1 == 0 then result ← run r (step i.toUInt32 count result.2 a b c d)
    run r (next result.1 result.2)
  | .platform op a b _ _ _ _ next => do
    let m ← r.get
    if op == .virtualRead64 then
      r.set {m with reads := m.reads.push a}
      if m.readFault == a then run r (next 17 0)
      else run r (next 0 (← word r a))
    else if op == .virtualWrite64 then
      if m.writeFault == a then run r (next 18 0)
      else
        set r a b
        r.modify fun m => {m with writes := m.writes.push a}
        run r (next 0 0)
    else throw <| IO.userError "codec acquired undeclared byte/device/syscall authority"
  | _ => throw <| IO.userError "codec acquired undeclared Action"
private def expect (b : Bool) (why : String) : IO Unit :=
  unless b do throw <| IO.userError why
private def ok (r : IO.Ref Model) (a : Action) : IO UInt64 := do
  let result ← run r a
  expect (result.1 == 0) s!"real guest Action failed {result.1}"
  return result.2
private def raw (r : IO.Ref Model) (a : UInt64) : IO (Array UInt64) := do
  let mut values := #[]
  for i in [:464] do values := values.push (← word r (a+i.toUInt64*8))
  return values
private def oracle (values : Array UInt64) : Array UInt64 := Id.run do
  let mut bits := #[]
  for group in [:8] do
    let mut mask : UInt64 := 0
    for j in [:64] do
      let i := group*64+j
      if i < values.size && values[i]! != 0 then mask := mask ||| (1 <<< j.toUInt64)
    bits := bits.push mask
  let data := values.filter (· != 0)
  return #[0x3243574b504d454c,2,3712,96+data.size.toUInt64*8] ++ bits ++ data

def check : IO Unit := do
  let r ← IO.mkRef ({} : Model)
  let _ ← ok r (MathematicsClosure.create doc 1 1)
  let _ ← ok r (PackageWorkspace.create source doc 1 1)
  -- Real admitted record transitions supply ordinary revision/assistance/history
  -- data. They are fixture inputs, never substituted for checker execution.
  for iteration in [:5] do
    if iteration > 0 then
      let _ ← ok r (Mathematics.edit doc 56 1)
      let _ ← ok r (Mathematics.hint doc)
      let _ ← ok r (PackageWorkspace.stageRefresh source doc restored)
      for i in [:464] do set r (source+i.toUInt64*8) (← word r (restored+i.toUInt64*8))
      let revision ← word r (doc+40)
      let _ ← ok r (MathematicsClosure.completeExecution doc revision 1 2 (11+iteration.toUInt64) 8)
      let _ ← ok r (PackageWorkspace.stageCompletedUnknown source doc (11+iteration.toUInt64) restored)
      for i in [:464] do set r (source+i.toUInt64*8) (← word r (restored+i.toUInt64*8))
    let values ← raw r source
    let expected := oracle values
    let before ← r.get
    let length ← ok r (WorkspaceCodec.encode source packed 1 1)
    expect (length == expected.size.toUInt64*8 && length ≤ 3808) "encoded length disagrees with independent bitmap layout"
    for i in [:expected.size] do
      expect ((← word r (packed+i.toUInt64*8)) == expected[i]!) "encoded word differs from independent oracle"
    expect ((← raw r source) == values) "encoder changed active source"
    expect ((← ok r (WorkspaceCodec.recordLength packed)) == length) "envelope header length differs"
    let _ ← ok r (WorkspaceCodec.decode packed length restored 1 1)
    expect ((← raw r restored) == values) "roundtrip lost original workspace/Doc8/history bytes"
    expect ((← ok r (WorkspaceCodec.recordLength source)) == 3712) "legacy raw header not admitted"
    let good ← r.get
    -- Exercise the actual complete restore path, including in-place replacement
    -- of the compressed source after private validation. The Store sector-copy
    -- helper intentionally admits at most512 bytes and is never used here.
    let restoredBytes ← ok r (WorkspaceCodec.restore packed length restored packed 1 1)
    expect (restoredBytes == 3712 && (← raw r packed) == values && (← raw r source) == values)
      "complete3712-byte staging restore failed or changed the live source"
    r.set {good with reads := #[], writes := #[], writeFault := packed+24}
    let failedRestore ← run r (WorkspaceCodec.restore packed length restored packed 1 1)
    expect (failedRestore.1 == 18 && ((← r.get).writes.filter (fun a => packed ≤ a && a < packed+3712)) ==
        #[packed,packed+8,packed+16] && (← raw r source) == values)
      "full staging restore lost actual copy fault prefix or changed live source"
    r.set {good with reads := #[], writes := #[]}
    let overlapRestore ← run r (WorkspaceCodec.restore packed length restored restored 1 1)
    expect (overlapRestore.1 == 240 && (← r.get).reads.isEmpty && (← r.get).writes.isEmpty)
      "restore accepted scratch/output alias"
    r.set good
    for (offset,value,status) in #[(0,0,241),(8,3,241),(16,3704,240),(24,88,240),
        (24,length+8,240),(88,65536,240),(96,0,240)] do
      r.set {good with reads := #[], writes := #[]}
      set r (packed+offset) value
      let result ← run r (WorkspaceCodec.decode packed length restored 1 1)
      expect (result.1.toUInt64 == status) s!"malformed envelope field admitted/masked {offset}/{result.1}"
      expect ((← raw r source) == values) "malformed decode changed live source"
      if offset != 96 then expect ((← r.get).writes.isEmpty) "shape rejection wrote decoded staging"
    r.set {good with reads := #[], writes := #[]}
    set r (packed+32) ((← word r (packed+32)) ^^^ 1)
    let badCount ← run r (WorkspaceCodec.decode packed length restored 1 1)
    expect (badCount.1 == 240 && (← r.get).writes.isEmpty) "bitmap population mismatch wrote output"
    for point in #[packed,packed+88,packed+96] do
      r.set {good with reads := #[], writes := #[], readFault := point}
      let result ← run r (WorkspaceCodec.decode packed length restored 1 1)
      expect (result.1 == 17) "actual compressed read error hidden"
    r.set {good with reads := #[], writes := #[], writeFault := restored+24}
    let result ← run r (WorkspaceCodec.decode packed length restored 1 1)
    expect (result.1 == 18 && (← r.get).writes == #[restored,restored+8,restored+16])
      "decoded write fault lost actual prefix/error"
    r.set {good with reads := #[], writes := #[], readFault := source+24}
    let failed ← run r (WorkspaceCodec.encode source packed 1 1)
    expect (failed.1 == 17 && (← r.get).writes.isEmpty) "invalid/faulted source published encoded bytes"
    r.set {good with reads := #[], writes := #[], writeFault := packed+8}
    let failed ← run r (WorkspaceCodec.encode source packed 1 1)
    expect (failed.1 == 18 && (← r.get).writes == #[packed] && (← word r packed) == 0)
      "encoder staging fault fabricated complete header or rolled back prefix"
    r.set good
    for (a,b) in #[(source,source),(source,source+8),(source+1,packed),
        (0xfffffffffffffff8,packed),(source,0xfffffffffffffff8)] do
      r.modify fun m => {m with reads := #[], writes := #[]}
      let rejected ← run r (WorkspaceCodec.encode a b 1 1)
      expect (rejected.1 == 240 && (← r.get).reads.isEmpty && (← r.get).writes.isEmpty)
        "overlap/alignment/overflow escaped pre-effect guard"
    IO.println s!"WORKSPACE_CODEC_WORDS revision={iteration} raw=464 stored={expected.size} bytes={length}"
    r.set {before with memory := good.memory, reads := #[], writes := #[]}
  IO.println "WORKSPACE_CODEC:PASS independent exact layout/roundtrip/legacy/malformed/bitmap/fault-prefix/alias checks; guest execution and durability separate"
end WorkspaceCodecTests

def main : IO Unit := WorkspaceCodecTests.check
