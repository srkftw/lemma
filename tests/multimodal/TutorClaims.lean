import Lemma.Multimodal.TutorAction

/-! Independent bounded memory execution of the real copied-action validator.
Unknown mathematical claim classes cannot manufacture checked authority. -/
namespace TutorClaimTests
open Lemma.Core0.Memory
def base : UInt64 := 0x80000000
def context : UInt64 := base+1024
def source : UInt64 := base+4096
def output : UInt64 := base+12288
structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 16384 0xa5)
  operations : Nat := 0
  failAt : Nat := 0
  writes : Nat := 0
private def offset (address bytes : UInt64) : Except String Nat := do
  if address < base || 16384 < bytes || 16384-bytes < address-base then
    throw "independent crypto memory bounds"
  return (address-base).toNat
partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
      let (s,v) ← run state first
      run state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if budget < count.toNat then throw <| IO.userError "crypto exceeded declared loop"
      let mut s : UInt8 := 0
      let mut v := initial
      for i in [:count.toNat] do
        if s == 0 then
          let result ← run state (step i.toUInt32 count v a b c d)
          s := result.1
          v := result.2
      run state (next s v)
  | .platform op address value _ _ _ _ next => do
      let m ← state.get
      let bytes := if op == .physicalRead64 || op == .physicalWrite64 || op == .virtualRead64 || op == .virtualWrite64 then 8 else 1
      unless op == .physicalRead8 || op == .physicalRead64 || op == .physicalWrite8 || op == .physicalWrite64 || op == .virtualRead8 || op == .virtualRead64 || op == .virtualWrite8 || op == .virtualWrite64 do
        throw <| IO.userError "crypto acquired undeclared effect"
      if bytes == 8 && address%8 != 0 then throw <| IO.userError "unaligned crypto word"
      let position ← IO.ofExcept <| offset address bytes
      let operation := m.operations+1
      state.set {m with operations := operation}
      if m.failAt == operation then run state (next 71 0) else
      if op == .physicalRead8 || op == .physicalRead64 || op == .virtualRead8 || op == .virtualRead64 then
        let mut word : UInt64 := 0
        for i in [:bytes.toNat] do
          word := word ||| (m.memory[position+i]!.toUInt64 <<< (i.toUInt64*8))
        run state (next 0 word)
      else
        let mut data := m.memory
        for i in [:bytes.toNat] do data := data.set! (position+i) ((value >>> (i.toUInt64*8)).toUInt8)
        state.set {m with memory := data, operations := operation, writes := m.writes+1}
        run state (next 0 0)
  | _ => throw <| IO.userError "crypto acquired an undeclared Action"

private def unhex (s : String) : ByteArray := Id.run do
  let chars := s.toList.toArray
  let mut out := ByteArray.empty
  for i in [:chars.size/2] do
    let digit (c : Char) := if c <= '9' then c.toNat-48 else c.toNat-87
    out := out.push ((digit chars[2*i]!*16+digit chars[2*i+1]!).toUInt8)
  return out
private def seedAt (m : Model) (offset : Nat) (b : ByteArray) : Model := Id.run do
  let mut memory := m.memory
  for i in [:b.size] do memory := memory.set! (offset+i) b[i]!
  return {m with memory}
private def bytesAt (m : Model) (offset count : Nat) : ByteArray := m.memory.extract offset (offset+count)

private def encodeWords (words : Array UInt64) : ByteArray := Id.run do
  let mut out := ByteArray.empty
  for word in words do
    for i in [:8] do out := out.push ((word >>> (i*8).toUInt64).toUInt8)
  return out

def claimKinds : IO Unit := do
  let contextWords : Array UInt64 := #[1,1,2,5,0,1,1,1,31,512,0]
  let words : Array UInt64 := #[2,1,1,2,5,1,99,100,120,1,0,1,0,5,0,2,3,1,1,31,1,0,0,0]
  for (kind,expected) in #[(0,0),(1,0),(2,14),(3,14),(0xffffffffffffffff,14)] do
    let m := seedAt (seedAt ({} : Model) 4096 (encodeWords (words.set! 12 kind))) 9000 (encodeWords contextWords)
    let state ← IO.mkRef m
    let result ← run state (Lemma.Multimodal.TutorAction.validate (base+4096) (base+9000) 100)
    unless result == (0,expected) do throw <| IO.userError s!"claim kind {kind} result {result} expected {expected}"
  IO.println "TUTOR_CLAIM_KINDS:PASS zero/no-declared-claims one/pending-check all-unsupported-rejected"
end TutorClaimTests
#eval TutorClaimTests.claimKinds
