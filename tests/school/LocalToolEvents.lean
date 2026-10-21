import Lemma.School.Submission

/-! Hosted structural/provenance validation. Target execution and actual IPC
are separately observed; these checks make no guest execution claim. -/
open Lemma.School.Submission

private def group (scope : Nat := 1) (outcome : Nat := 0) : Array (Array Nat) :=
  #[#[3,8 + (1 <<< 8) + (scope <<< 16) + (8 <<< 24) + (outcome <<< 32)],
    #[if scope == 2 then 4 else 0,17],
    #[Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity.toNat,803],#[2,4],
    #[0,0x504b000000000001],#[10,12],#[if scope == 2 then 5 else 0,if scope == 2 then 6 else 0],#[0,0]]

private def fail (rows : Array (Array Nat)) (format : Nat := 3) : IO Unit := do
  if (parseDocumentEvents format rows).isOk then throw (IO.userError "malformed local tool accepted")

private def exposure (rows : Array (Array Nat)) (node : Nat := 4) : IO (Bool × Bool × Array Lean.Json) := do
  let parsed ← IO.ofExcept (parseDocumentEvents 3 rows)
  return localToolAssistance parsed.localTools 1 5 803 2 node 0 2 1

def main : IO Unit := do
  let prepared := group
  let applied := group 2 1
  let cancelled := group 3 3
  let parsed ← IO.ofExcept (parseDocumentEvents 3 (#[#[3,1]] ++ prepared ++ applied))
  if parsed.ordinary != #[#[3,1]] || parsed.localTools.size != 2 || !parsed.remote.isEmpty then
    throw (IO.userError "local calculation payload interpreted as learner hint or remote assistance")
  let (exposed,uncertain,observations) ← exposure (prepared ++ applied)
  if !exposed || uncertain || observations.size != 2 then
    throw (IO.userError "applied local calculation classification differs")
  let (pending,pendingUncertain,_) ← exposure prepared
  if !pending || !pendingUncertain then throw (IO.userError "interrupted prepared request lost uncertainty")
  let (cancelledExposure,cancelledUncertain,_) ← exposure (prepared ++ cancelled)
  if cancelledExposure || cancelledUncertain then throw (IO.userError "no-apply terminal counted as delivered answer")
  let (other,_,_) ← exposure (prepared ++ applied) 6
  if other then throw (IO.userError "another known activity acquired calculation exposure")
  let (changedGoal,_,_) := localToolAssistance parsed.localTools 1 5 803 2 4 0 2 2
  if !changedGoal then throw (IO.userError "later editable goal erased exact original activity exposure")
  let unknown := (prepared.set! 2 #[Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity.toNat,0]).set! 3 #[0,0]
  let (unknownExposure,unknownUncertain,_) ← exposure unknown
  if !unknownExposure || !unknownUncertain then throw (IO.userError "offline unknown context falsely independent")
  fail applied
  fail cancelled
  fail (prepared ++ prepared)
  fail (prepared ++ applied ++ cancelled)
  fail (prepared ++ cancelled ++ applied)
  fail (prepared.extract 0 7)
  fail prepared 2
  fail (prepared.set! 7 #[1,0])
  fail (prepared.set! 2 #[0,803])
  fail (prepared.set! 3 #[0,4])
  fail (prepared.set! 4 #[0,0x504b000000000041])
  fail (prepared.set! 5 #[10,0])
  fail (prepared ++ (applied.set! 1 #[5,17]))
  fail (prepared ++ (applied.set! 4 #[1,0x504b000000000001]))
  fail (prepared ++ (applied.set! 0 #[3,8 + (1 <<< 8) + (2 <<< 16) + (8 <<< 24) + (2 <<< 32)]))
  fail (prepared.set! 0 #[3,8 + (1 <<< 8) + (1 <<< 16) + (8 <<< 24) + (1 <<< 56)])
  IO.println "PASS hosted local tool provenance: applied, pending, cancelled, other activity, unknown context; sixteen malformed histories rejected"
