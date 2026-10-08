import Lean
import Lemma.Core0.Frontend
import Lemma.Core0.Semantics

namespace Lemma.Core0

open Lean Elab Command

/-- Check a normal Lean declaration and its reachable bodies against Core0 v0.1. -/
syntax (name := core0Check) "#core0_check " ident : command

elab_rules : command
  | `(#core0_check $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLower env name with
      | .error diag => throwErrorAt decl diag.render
      | .ok program =>
          logInfoAt decl m!"Core0 accepted `{name}`\n{program.renderManifest}"

end Lemma.Core0
