import Lemma.Platform.LemmaSim.Descriptor
import Std.Data.HashMap

/-! Host-only raw bytes/register fixture executing maintained discovery Actions.
It contains no parser or admission implementation. Input FDTs and descriptor
bytes must come from the selected build; mutations exercise the real guest. -/
namespace PaperDiscoveryFixture
open Lemma.Core0.Memory Lemma.Platform.LemmaSim
structure State where
 words : Std.HashMap UInt64 UInt64 := {}
 dtb : ByteArray
 descriptor : ByteArray
 paperVersion : UInt64 := 2
 stage : UInt64 := 3584
 operations : Nat := 0
 ramWrites : Nat := 0
 deriving Inhabited
private def require (b : Bool) (s : String) : IO Unit := unless b do throw <| IO.userError s
private def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
private def rawWord (b : ByteArray) (offset : Nat) : UInt64 := Id.run do
 let mut v : UInt64 := 0
 for i in [:8] do v := v ||| (b[offset+i]!.toUInt64 <<< (i*8).toUInt64)
 return v
partial def run (r : IO.Ref State) (a : Action) : IO (UInt8 × UInt64) := do
 match a with
 | .done s v => pure (s,v)
 | .bind first next => let (s,v) ← run r first; run r (next s v)
 | .boundedFoldU64 budget step count initial a b c d next =>
  require (count.toNat ≤ budget) "fixture fold exceeded admission"
  let mut status : UInt8 := 0; let mut value := initial
  for i in [:count.toNat] do
   if status = 0 then
    let result ← run r (step i.toUInt32 count value a b c d)
    status := result.1; value := result.2
  run r (next status value)
 | .platform op a b _ _ _ _ next =>
  r.modify fun s => {s with operations := s.operations+1}
  let s ← r.get
  require (s.operations < 2000000) "fixture finite primitive budget exceeded"
  if op == .deviceRead64 then
   let value ← if 0x10010400≤a && a<0x10010500 then pure (rawWord s.descriptor (a-0x10010400).toNat) else
    if a=0x10010000 then pure 0x4c505050 else if a=0x10011000 then pure 0x4c50504e else
    if a=0x10010008 then pure s.paperVersion else if a=0x100100b8 then pure s.stage else
    if a=0x10011008 then pure 1 else if a=0x10010020 then pure 1650 else if a=0x10010028 then pure 2200 else
    if a=0x10011048 then pure 4095 else if a=0x10010600 then pure 0x31544b50454c4d4c else
    if a=0x10010a00 then pure 0x315645444253554c else if a=0x10012000 then pure 0x564e424c else
    if a=0x10010608 || a=0x10010a08 || a=0x10012008 then pure 1 else
    if a=0x10012010 then pure 65544 else throw <| IO.userError s!"unexpected PIO64 {a}"
   run r (next 0 value)
  else if op == .deviceRead32 then
   let value ← if a=0x10001000 then pure 0x74726976 else if a=0x10001004 || a=0x10001008 then pure 2 else throw <| IO.userError "unexpected PIO32"
   run r (next 0 value)
  else if op == .physicalRead8 then
   if 0x87e00000≤a && a<0x87e00000+s.dtb.size.toUInt64 then
    run r (next 0 s.dtb[(a-0x87e00000).toNat]!.toUInt64)
   else throw <| IO.userError "read outside actual bounded FDT"
  else if op == .physicalRead64 then
   require (a%8=0 && 0x80400000≤a && a<0x80500000) "physical read outside private metadata"
   run r (next 0 (word s a))
  else if op == .physicalWrite64 then
   require (a%8=0 && 0x80400000≤a && a<0x80500000) "physical write outside private metadata"
   r.modify fun s => {s with words := s.words.insert a b,ramWrites := s.ramWrites+1}
   run r (next 0 0)
  else throw <| IO.userError s!"unexpected discovery primitive {op.stableId}"
 | _ => throw <| IO.userError "unexpected discovery Action"
def check (directory : System.FilePath) (binding : UInt64) : IO Unit := do
 let dtb ← IO.FS.readBinFile (directory/"platform.dtb")
 let descriptor ← IO.FS.readBinFile (directory/"descriptor.bin")
 let start : State := {dtb,descriptor,words := ({} : Std.HashMap UInt64 UInt64).insert 0x80400008 0x87e00000}
 let r ← IO.mkRef start
 let result ← run r (Descriptor.validateBindingNext binding)
 require (result.1=0) s!"valid descriptor{binding} rejected {result}"
 for (version,stage) in #[(1,3584),(2,2048),(2,3592),(3,3584)] do
  r.set {start with paperVersion := version,stage}
  require ((← run r (Descriptor.validateBindingNext binding)).1=169) "actual mismatched controller admitted"
 for changed in #[0,7,10,0xffffffffffffffff] do
  r.set start
  require ((← run r (Descriptor.validateBindingNext changed)) == (169,0)) "non-successor binding admitted"
  require ((← r.get).operations=0) "invalid selector performed I/O"
 IO.println s!"PAPER_DISCOVERY:PASS binding{binding}; actual maintained descriptor/FDT/Paper2 admission and mismatched controller/selector rejection"
end PaperDiscoveryFixture
def main (args : List String) : IO Unit := do
 match args with
 | [directory,binding] => PaperDiscoveryFixture.check directory (binding.toNat!.toUInt64)
 | _ => throw <| IO.userError "require directory binding8or9"
