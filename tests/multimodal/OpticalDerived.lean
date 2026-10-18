import Lemma.Multimodal.OpticalDerived
namespace OpticalDerivedHost
open Lemma.Core0.Memory
structure Model where
  frame : ByteArray
  params : ByteArray
  output : ByteArray := ByteArray.mk (Array.replicate 320 165)
  reads : Nat := 0
  writes : Nat := 0
  failAt : Nat := 0
private def within (address base extent : UInt64) : Bool := if address < base then false else address-base ≤ extent-8
private def readWord (data : ByteArray) (position : Nat) : UInt64 := Id.run do
  let mut v : UInt64 := 0
  for i in [:8] do v := v ||| (data[position+i]!.toUInt64 <<< (i.toUInt64*8))
  return v
partial def run (r : IO.Ref Model) : Action → IO (UInt8 × UInt64)
 | .done s v => pure (s,v)
 | .bind first next => do
   let (s,v) ← run r first
   run r (next s v)
 | .boundedFoldU64 budget step count initial a b c d next => do
   if budget < count.toNat then throw <| IO.userError "declared fold exceeded"
   let mut s : UInt8 := 0
   let mut v := initial
   for i in [:count.toNat] do
     if s = 0 then
       let result ← run r (step i.toUInt32 count v a b c d)
       s := result.1
       v := result.2
   run r (next s v)
 | .platform op address value _ _ _ _ next => do
   let m ← r.get
   if address%8 != 0 then throw <| IO.userError "unaligned source word"
   if m.failAt != 0 && m.reads+m.writes+1 = m.failAt then
     r.set {m with reads := m.reads+1}
     run r (next 71 0)
   else if op == .physicalRead64 then
     let v ← if within address 0x80410000 768 then pure <| readWord m.frame (address-0x80410000).toNat
       else if within address 0x80411000 464 then pure <| readWord m.params (address-0x80411000).toNat
       else throw <| IO.userError "out-of-span source read"
     r.set {m with reads := m.reads+1}
     run r (next 0 v)
   else if op == .physicalWrite64 then
     unless within address 0x80412000 320 do throw <| IO.userError "out-of-span result write"
     let mut data := m.output
     for i in [:8] do data := data.set! ((address-0x80412000).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)
     r.set {m with output := data,writes := m.writes+1}
     run r (next 0 0)
   else throw <| IO.userError "undeclared effect"
 | _ => throw <| IO.userError "undeclared Action"
def main (args : List String) : IO Unit := do
  let directory := System.FilePath.mk (args.headD "/missing")
  let list := ((← IO.FS.readFile (directory/"cases.txt")).splitOn "\n").filter (· != "")
  for name in list do
    let dir := directory/name
    let frame ← IO.FS.readBinFile (dir/"frame.bin")
    let params ← IO.FS.readBinFile (dir/"params.bin")
    unless frame.size = 768 && params.size = 464 do throw <| IO.userError "source size"
    let r ← IO.mkRef { frame,params : Model }
    let (status,value) ← run r (Lemma.Multimodal.OpticalDerived.evaluate 0x80410000 0x80411000 0x80412000)
    unless status = 0 do throw <| IO.userError s!"Action failed {name}/{status}"
    let m ← r.get
    IO.FS.writeBinFile (dir/"actual-lean.bin") m.output
    IO.println s!"{name} {value} {m.reads} {m.writes}"
end OpticalDerivedHost
def main := OpticalDerivedHost.main
