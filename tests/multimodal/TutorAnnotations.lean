import Lemma.Multimodal.TutorAction
import Lemma.Multimodal.TutorPackage

/-! Independent bounded memory execution of the real copied-action validator.
Unknown mathematical claim classes cannot manufacture checked authority. -/
namespace TutorAnnotationTests
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

private def expect (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message
private def model (claim : UInt64) (body : ByteArray) (declared : UInt64) : Model :=
  seedAt (seedAt (seedAt ({} : Model) (4096+248) (encodeWords #[(declared <<< 32) ||| 904]))
    (12288+96) (encodeWords #[claim])) 5000 body

def annotations : IO Unit := do
  let prefixes := #["UNVERIFIED ASSISTANCE: ","UNVERIFIED ASSISTANCE - CHECKING PENDING: "]
  for claim in [:2] do
    let body := (prefixes[claim]! ++ "A bounded generated explanation.").toUTF8
    let original := model claim.toUInt64 body body.size.toUInt64
    let state ← IO.mkRef original
    let result ← run state (Lemma.Multimodal.TutorPackage.annotationReason source output)
    expect (result == (0,0)) "exact independent visible prefix rejected"
    for i in [:prefixes[claim]!.toUTF8.size] do
      let wrong := body.set! i (body[i]! ^^^ 1)
      state.set (model claim.toUInt64 wrong wrong.size.toUInt64)
      let result ← run state (Lemma.Multimodal.TutorPackage.annotationReason source output)
      expect (result == (0,19)) s!"visible prefix byte {i} mutation accepted"
    for length in [:prefixes[claim]!.toUTF8.size] do
      state.set (model claim.toUInt64 body length.toUInt64)
      let result ← run state (Lemma.Multimodal.TutorPackage.annotationReason source output)
      expect (result == (0,19)) "short/omitted visible prefix accepted"
    let wrongPrefix := (prefixes[1-claim]! ++ "A bounded generated explanation.").toUTF8
    state.set (model claim.toUInt64 wrongPrefix wrongPrefix.size.toUInt64)
    let result ← run state (Lemma.Multimodal.TutorPackage.annotationReason source output)
    expect (result == (0,19)) "wrong checking-declaration prefix accepted"
  let state ← IO.mkRef <| model 2 "untrusted self-checked class".toUTF8 27
  let result ← run state (Lemma.Multimodal.TutorPackage.annotationReason source output)
  expect (result == (0,0)) "annotation masked the action validator's unsupported claim reason14"
  for requested in #[(0 : UInt64),1,2] do
    for selected in #[(0 : UInt64),1,60001,65535] do
      for marked in #[(0 : UInt64),1] do
        let expected := if requested == 1 && selected == 60001 && marked == 0 then 18 else 0
        expect (Lemma.Multimodal.TutorPackage.requiredMarkerReason requested selected marked == expected) "dedicated tutor intent broadened historical package identity semantics"
  IO.println "TUTOR_ANNOTATIONS:PASS exact23/42-byte guest-visible labels/each-byte negatives/short-prefix/claim2-order/dedicated-intent historical identity matrix"
end TutorAnnotationTests
#eval TutorAnnotationTests.annotations
