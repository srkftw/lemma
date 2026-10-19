import Lemma.School.Client
import Lemma.Multimodal.TutorPackage
import Lemma.Multimodal.SchoolPacket

open Lemma.School.Client
open Lemma.Core0.Memory
namespace SchoolClientTests
private def expect (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message
private def rejected {α : Type} : Except String α → Bool
  | .error _ => true
  | .ok _ => false
private def binding : SessionBinding := {
  school := "owner-school", actor := "learner-a", enrollment := "enrollment-1",
  session := "school-session-1", guestSession := 99,
  course := 17, revision := 2, policy := 4, generation := 3, expires := 500 }
private def ask : GuestAsk := {
  session := 99, consent := 1, revision := 7, object := 0x504b000000000001,
  sequence := 11, source := 17, edition := 2, task_id := 3,
  cutoff := 100, now := 101, deadline := 140, grants := 1 }
private def input : AssistInput := {
  school := "owner-school", actor := "learner-a", session := "school-session-1",
  course := 17, revision := 2, policy := 4, generation := 3, now := 200, ask }
private def word (bytes : ByteArray) (offset : Nat) : UInt64 :=
  (List.range 8).foldl (fun n i => n ||| (bytes[offset+i]!.toUInt64 <<< (i*8).toUInt64)) 0
private def encode (values : Array UInt64) : ByteArray := Id.run do
  let mut out := ByteArray.empty
  for value in values do
    for i in [:8] do out := out.push ((value >>> (i*8).toUInt64).toUInt8)
  return out
private def base : UInt64 := 0x80000000
private def seed (memory : ByteArray) (offset : Nat) (bytes : ByteArray) : ByteArray :=
  bytes.data.foldl (init := (memory,offset)) (fun (out,n) b => (out.set! n b,n+1)) |>.1
partial def run (memory : IO.Ref ByteArray) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
    let (s,v) ← run memory first
    run memory (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if count.toNat > budget then throw <| IO.userError "school client exceeded Action budget"
    let mut result := (0,initial)
    for i in [:count.toNat] do
      if result.1 == 0 then result ← run memory (step i.toUInt32 count result.2 a b c d)
    run memory (next result.1 result.2)
  | .platform op address value _ _ _ _ next => do
    let m ← memory.get
    let bytes := if op == .virtualRead64 || op == .virtualWrite64 || op == .physicalRead64 || op == .physicalWrite64 then 8 else 1
    unless op == .virtualRead8 || op == .virtualRead64 || op == .virtualWrite8 || op == .virtualWrite64 || op == .physicalRead8 || op == .physicalRead64 || op == .physicalWrite8 || op == .physicalWrite64 do
      throw <| IO.userError "undeclared school client effect"
    if address < base || address - base + bytes > m.size.toUInt64 || address%bytes != 0 then
      throw <| IO.userError "school client memory bounds or alignment"
    let offset := (address-base).toNat
    if op == .virtualRead8 || op == .virtualRead64 || op == .physicalRead8 || op == .physicalRead64 then
      let mut value : UInt64 := 0
      for i in [:bytes.toNat] do value := value ||| (m[offset+i]!.toUInt64 <<< (i*8).toUInt64)
      run memory (next 0 value)
    else
      let mut out := m
      for i in [:bytes.toNat] do out := out.set! (offset+i) ((value >>> (i*8).toUInt64).toUInt8)
      memory.set out
      run memory (next 0 0)
  | _ => throw <| IO.userError "undeclared school client Action"

def main : IO Unit := do
  expect (!rejected (admit binding input)) "valid enrolled context rejected"
  let changes := #[
    { input with school := "other-school" }, { input with actor := "other-learner" },
    { input with session := "other-session" }, { input with course := 18 },
    { input with revision := 3 }, { input with policy := 5 },
    { input with generation := 4 }, { input with now := 500 },
    { input with independent := true }, { input with ask := { ask with session := 100 } },
    { input with ask := { ask with source := 18 } }, { input with ask := { ask with edition := 3 } },
    { input with ask := { ask with now := 141 } }, { input with ask := { ask with cutoff := 102 } },
    { input with ask := { ask with grants := 3 } }, { input with ask := { ask with sequence := 0x100000000 } }]
  for changed in changes do expect (rejected (admit binding changed)) "misrouted/stale/out-of-scope assistance admitted"
  expect (rejected (admit { binding with cancelled := true } input)) "cancelled school session admitted"
  expect (rejected (admit { binding with enrollment := "" } input)) "absent enrollment admitted"
  let bytes ← IO.ofExcept <| handleLegacyAssist binding input "Rewrite both fractions over a shared denominator."
  expect (word bytes 24 == 60001 && word bytes 32 == 11) "immutable action package identity differs"
  let bodySpan := word bytes 248
  let body := bytes.extract (bodySpan &&& (0xffffffff : UInt64)).toNat ((bodySpan &&& (0xffffffff : UInt64))+(bodySpan >>> 32)).toNat
  expect (body.extract 0 23 == "UNVERIFIED ASSISTANCE: ".toUTF8) "visible assistance label missing"
  expect (rejected (package input "π")) "unsupported package text silently accepted"
  let context := encode #[99,1,7,0x504b000000000001,10,1,17,2,3,512,0]
  let m := seed (seed (ByteArray.mk (Array.replicate 16384 0)) 4096 bytes) 1024 context
  let memory ← IO.mkRef m
  let check (clock : UInt64) := Lemma.Multimodal.TutorPackage.validate (base+4096) bytes.size.toUInt64 (base+12288) (base+1024) clock
  expect ((← run memory (check 101)) == (0,1)) "actual guest packet admission rejected school publisher"
  for (offset,value,now,reason) in (#[(8,2,101,2),(16,8,101,3),(32,11,101,5),(40,0,101,9),(0,100,101,1),(0,99,141,8)] : Array (Nat × UInt64 × UInt64 × UInt64)) do
    memory.set <| seed m (1024+offset) (encode #[value])
    expect ((← run memory (check now)) == (0,32+reason)) "guest cancellation/revision/expiry/replay gate did not reject"
  let joined : SessionBinding := {binding with authority:="0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20",bindingRecord:=27}
  let invitation ← IO.ofExcept <| Lemma.School.Client.invitation joined ask
  let initial := seed (seed (ByteArray.mk (Array.replicate 16384 0)) 4096 invitation) 1024 context
  memory.set initial
  expect ((← run memory (Lemma.Multimodal.SchoolPacket.decode (base+4096) invitation.size.toUInt64 (base+12288) 1)) == (0,1)) "actual guest invitation decoder rejected authored JOIN"
  expect ((← run memory (Lemma.Multimodal.SchoolPacket.acceptInvitation (base+4096) (base+12288) (base+2048) (base+1024) 101)) == (0,0)) "actual guest explicit JOIN binding rejected"
  let accepted ← memory.get
  expect (word accepted 2048 == Lemma.Multimodal.SchoolPacket.magic && word accepted (2048+48) == 27) "guest JOIN tag/record differs"
  let schoolAction ← IO.ofExcept <| handleAssist joined input "List four products before collecting powers."
  let actionState := seed accepted 4096 schoolAction
  memory.set actionState
  expect ((← run memory (Lemma.Multimodal.SchoolPacket.decode (base+4096) schoolAction.size.toUInt64 (base+12288) 2)) == (0,1)) "actual guest school-action decoder rejected v3"
  let decoded ← memory.get
  let schoolCheck := Lemma.Multimodal.SchoolPacket.actionReason (base+12288) (base+1024) (base+2048) 101
  expect ((← run memory schoolCheck) == (0,0)) "v3 joined action failed actual guest validation"
  expect ((← run memory (Lemma.Multimodal.TutorPackage.annotationReason (base+4096) (base+12288))) == (0,0)) "v3 visible unverified label failed"
  for (offset,value,reason) in (#[(2048,0,20),(2048+16,0,21),(2048+48,28,22),(2048+56,4,23),
      (2048+64,139,24),(2048+72,5,25),(2048+80,100,26),(2048+88,18,27),(2048+96,3,27),
      (1024+16,8,3),(1024+8,2,2),(1024+32,11,5)] : Array (Nat × UInt64 × UInt64)) do
    memory.set (seed decoded offset (encode #[value]))
    expect ((← run memory schoolCheck) == (0,reason)) "cross-school/binding/generation/deadline/policy/session/publication/revision/revocation/replay admitted"
  -- Every reserved v2 field is still zero in v3, and each nonzero mutation
  -- fails the unchanged underlying action validator rather than acquiring scope.
  for offset in #[168,176,184] do
    memory.set (seed decoded (12288+offset) (encode #[1]))
    expect ((← run memory schoolCheck) == (0,17)) "v3 repurposed an old reserved word"
  memory.set (seed decoded (12288+0) (encode #[2]))
  expect ((← run memory schoolCheck) == (0,13)) "school v3 silently accepted the old action version"
  memory.set (seed decoded (12288+56) (encode #[102]))
  expect ((← run memory schoolCheck) == (0,7)) "v3 school action started before its declared start"
  let cold := seed initial 1024 (encode #[100,1,7,0x504b000000000001,50,1,17,2,3,512,0])
  memory.set cold
  let _ ← run memory (Lemma.Multimodal.SchoolPacket.decode (base+4096) invitation.size.toUInt64 (base+12288) 1)
  expect ((← run memory (Lemma.Multimodal.SchoolPacket.acceptInvitation (base+4096) (base+12288) (base+2048) (base+1024) 101)) == (0,26)) "old invitation admitted after a new cold ASK session"
  IO.println "SCHOOL_CLIENT:PASS legacyv2 + explicit104B JOIN/v3-256B actual guest admission; fullauthority/binding/generation/publication/policy/cancel/expiry/revision/replay; reservedzeros preserved"
end SchoolClientTests

def main : IO Unit := SchoolClientTests.main
