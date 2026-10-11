import Lemma.Ink.Geometry
import Lean.Elab.Command

/-! Literal examples check the production integer expressions through Lean's
ordinary evaluator. This host fixture is not a guest-execution certificate. -/
open Lean Elab Command
open Lemma.Ink.Geometry

run_cmd do
  unless pixel 0 1650 == 0 && pixel 0x1000000 1650 == 1649 &&
      pixel 0x800000 1650 == 824 && pixel 0x800000 1404 == 701 do
    throwError "normalized mapping literal mismatch"
  unless covered 10 10 0 10 20 10 4095 4095 512 4095 &&
      covered 10 11 0 10 20 10 4095 4095 512 4095 &&
      !(covered 10 12 0 10 20 10 4095 4095 512 4095) do
    throwError "horizontal coverage literal mismatch"
  unless covered 10 10 20 10 0 10 4095 4095 512 4095 &&
      covered 10 10 20 20 0 0 4095 4095 512 4095 &&
      !(covered 10 12 20 20 0 0 4095 4095 512 4095) do
    throwError "signed projection/cross literal mismatch"
  unless covered 0 0 0 0 0 0 0 0 256 0 &&
      !(covered 1 0 0 0 0 0 0 0 256 0) do
    throwError "degenerate point literal mismatch"
  unless pressureWidth 1024 0 4095 == 256 && pressureWidth 1024 4095 4095 == 1024 &&
      pressureWidth 1024 0 0 == 1024 do
    throwError "pressure capability literal mismatch"
  logInfo "INK_GEOMETRY_EXAMPLES:PASS"
