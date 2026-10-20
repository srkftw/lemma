import Lemma.School.Submission

/-! Bounded parser checks. These are hosted validation, not guest execution. -/
open Lemma.School.Submission

private def group (scope : Nat := 1) : Array (Array Nat) :=
  #[#[3, 7 + (2 <<< 8) + (scope <<< 16) + (4 <<< 24) + (17 <<< 32)],
    #[0x504b000000000001, 11], #[2, 6], #[0xfeed, 0x1234]]

private def expectError (rows : Array (Array Nat)) (format : Nat := 2) : IO Unit := do
  if (parseEvents format rows).isOk then throw (IO.userError "malformed remote event accepted")

def main : IO Unit := do
  let (ordinary, remote) ← IO.ofExcept (parseEvents 2 (#[#[3,1]] ++ group ++ group 2))
  let some prepared := remote[0]? | throw (IO.userError "missing prepared event")
  let some raster := remote[1]? | throw (IO.userError "missing raster event")
  if ordinary != #[#[3,1]] || remote.size != 2 || prepared.scope != 1 || raster.scope != 2 then
    throw (IO.userError "remote payload was interpreted as a learner hint")
  if prepared.authority != "02000000000000000600000000000000edfe0000000000003412000000000000" then
    throw (IO.userError "authority byte order differs from guest encoding")
  let legacy ← IO.ofExcept (parseEvents 1 #[#[3,2],#[3,6]])
  if legacy.1.size != 2 || !legacy.2.isEmpty then throw (IO.userError "legacy event changed")
  expectError (group 2)
  expectError (group ++ group)
  expectError (group.extract 0 3)
  expectError group 1
  expectError group 3
  expectError ((group).set! 1 #[0x504b000000000041,11])
  expectError ((group).set! 1 #[0x504b000000000001,0])
  expectError (((group).set! 2 #[0,0]).set! 3 #[0,0])
  expectError #[#[3,8]]
  expectError #[#[3,0x10000000000000000]]
  IO.println "PASS remote parser: exact prepared/raster identity; legacy preserved; payload isolated; ten negatives rejected"
