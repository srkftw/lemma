import Lemma.School.Store
open Lean Lemma.School

def main (arguments : List String) : IO Unit := do
  if let [root,digest,limit] := arguments then
    let limit ← IO.ofExcept (limit.toNat?.toExcept "invalid test limit")
    Store.requireArtifact root digest limit
    IO.println "artifact-admitted"
    return
  let valid : State := {school := "school", deployment := "deployment", operator := "owner"}
  let record : Record := {sequence := 1, kind := "attempt", key := "a", actor := "learner", time := 5, data := Json.null}
  let rows := #[
    ("empty-valid",valid),
    ("ordered-valid",{valid with clock := 5, records := #[record]}),
    ("budget-zero",{valid with budgets := {maxEvents := 0}}),
    ("budget-over",{valid with budgets := {maxQueued := 257}}),
    ("generation-zero",{valid with generation := 0}),
    ("generation-range",{valid with generation := 0x7fffffffffffffff}),
    ("clock-range",{valid with clock := 0x7fffffffffffffff}),
    ("read-clock-ahead-valid",{valid with clock := 1}),
    ("record-future",{valid with clock := 4, records := #[record]}),
    ("record-rollback",{valid with clock := 4, records := #[record,{record with sequence := 2, time := 4}]}),
    ("sequence-gap",{valid with clock := 5, records := #[{record with sequence := 2}]}),
    ("actor-empty",{valid with clock := 5, records := #[{record with actor := ""}]}),
    ("key-empty",{valid with clock := 5, records := #[{record with key := ""}]}),
    ("kind-invalid",{valid with clock := 5, records := #[{record with kind := "bad kind"}]}),
    ("digest-invalid",{valid with clock := 5, records := #[{record with artifacts := #["../../unsafe"]}]})]
  let fields ← IO.ofExcept (toJson {valid with schema := "lemma-school-state/1"}).getObj?
  let oldFields := fields.erase "clockEpoch" |>.erase "clockEpochSequence" |>.erase "clockAnchor" |>.erase "clockBase"
  let legacy := Store.decodeState (Json.obj oldFields)
  let migrationChecks := [
    ("legacy-decode-valid",toJson (legacy.toOption.any (fun state => state.clockEpoch.isEmpty &&
      state.clockEpochSequence == 0 && state.clockAnchor == 0 && state.clockBase == 0))),
    ("legacy-malformed-present",toJson (Store.decodeState (Json.obj (oldFields.insert "clockEpoch" (toJson (7:Nat))))).isOk),
    ("v2-missing-fields",toJson (Store.decodeState (Json.obj (oldFields.insert "schema" (toJson "lemma-school-state/2")))).isOk)]
  IO.println (Json.mkObj ((rows.toList.map fun (name,state) =>
    (name,match Store.validateState state with | .ok _ => toJson true | .error _ => toJson false)) ++ migrationChecks)).compress
