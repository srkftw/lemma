import Lemma.Multimodal.TutorAction
import Lemma.Multimodal.Parameterized

namespace MultimodalPoliciesTests
open Lemma.Multimodal
private def expect (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message
def check : IO Unit := do
  let paths ← IO.getEnv "LEMMA_TASK_VECTORS"
  let some path := paths | throw <| IO.userError "independent parameter corpus required"
  let lines ← IO.FS.lines path
  expect (lines.size >= 64) "empty/short task corpus"
  for line in lines do
    let fields := (line.splitOn " ").toArray
    expect (fields.size == 13) "bad independent task vector"
    let values ← fields.mapM fun v => do
      let some n := v.toNat? | throw <| IO.userError "bad independent scalar"
      pure n.toUInt64
    let outcome := Parameterized.check values[0]! values[1]! values[2]! values[3]! values[4]! values[5]!
      values[6]! values[7]! values[8]! values[9]! values[10]! values[11]!
    expect (outcome == values[12]!) "independent parameterized oracle mismatch"
  let admit := TutorAction.reason 1 2 3 4 5 99 100 120 3 0 3 1 2 3 4 4 3 100
  expect (admit == 0) "action positive control"
  expect (TutorAction.reason 1 2 3 4 5 101 100 120 3 0 3 1 2 3 4 4 3 100 == 7) "future observation admitted"
  expect (TutorAction.reason 1 2 3 4 5 99 100 120 0 0 3 1 2 3 4 4 3 100 == 9) "self-attenuated permission admitted"
  expect (TutorAction.reason 1 1 3 4 5 99 100 120 3 0 3 1 2 3 4 4 3 100 == 2) "revoked consent admitted"
  expect (TutorAction.reason 1 2 3 4 4 99 100 120 3 0 3 1 2 3 4 4 3 100 == 5) "completed audio repeated"
  expect (TutorAction.reason 1 2 2 4 5 99 100 120 3 0 3 1 2 3 4 4 3 100 == 3) "stale revision admitted"
  expect (TutorAction.delivery 100 25 1 0 == 4) "partial cancelled speech credited complete"
  expect (TutorAction.delivery 100 100 0 1 == 5) "impossible sink queue admitted"
  IO.println s!"MULTIMODAL_POLICIES:PASS {lines.size} independent parameterized outcomes/action-context/revocation/delivery"
end MultimodalPoliciesTests
#eval MultimodalPoliciesTests.check
