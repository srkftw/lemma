import Lemma.Courses.PackageAwaitProtocol

/-! Host-only independent finite decision-table check for the actual ordinary
Lean predicate. This is neither a proof nor RV64 or mount qualification. -/
namespace CourseAwaitResultTests
open Lemma.Courses

private def expected (status mode sequence generation : UInt64) : UInt64 :=
  let errors : Array (UInt64 × UInt64) := #[(93,0),(220,0),(221,2),(222,0),(223,3),(231,0)]
  let sequenceValid := sequence < 0x8000000000000000
  let success := status == 0 && mode == 1 && generation != 0 && generation < 0x8000000000000000
  if sequenceValid && (success || errors.contains (status,mode)) then 1 else 0

def check : IO Unit := do
  let statuses := (List.range 256).toArray.map UInt64.ofNat ++ #[256,511,0x8000000000000000,0xffffffffffffffff]
  let modes : Array UInt64 := #[0,1,2,3,4,0xffffffffffffffff]
  let sequences : Array UInt64 := #[0,1,0x7fffffffffffffff,0x8000000000000000,0xffffffffffffffff]
  let generations : Array UInt64 := #[0,1,0x7fffffffffffffff,0x8000000000000000,0xffffffffffffffff]
  let mut checked := 0
  for status in statuses do
    for mode in modes do
      for sequence in sequences do
        for generation in generations do
          if PackageAwaitProtocol.resultValid status mode sequence generation != expected status mode sequence generation then
            throw <| IO.userError s!"ordinary source predicate disagrees with independent literal reply table: {status}/{mode}/{sequence}/{generation}"
          checked := checked+1
  IO.println s!"COURSE_AWAIT_RESULT_TABLE:PASS {checked} ordinary-source cases; no CPU/mount/durability claim"
end CourseAwaitResultTests

def main : IO Unit := CourseAwaitResultTests.check
