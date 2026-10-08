import Lean
import Lemma.Core0.Frontend
import Lemma.Core0.Semantics

namespace Lemma.Core0

open Lean Elab Command

/-- Check a normal Lean declaration and its reachable bodies against Core0 v0.1. -/
syntax (name := core0Check) "#core0_check " ident : command
syntax (name := core0CheckV02) "#core0_check_v0_2 " ident : command
syntax (name := core0CheckV03) "#core0_check_v0_3 " ident : command

elab_rules : command
  | `(#core0_check $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLower env name with
      | .error diag => throwErrorAt decl diag.render
      | .ok program =>
          logInfoAt decl m!"Core0 accepted `{name}`\n{program.renderManifest}"

  | `(#core0_check_v0_2 $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLowerForProfile env .v0_2 name with
      | .error diag => throwErrorAt decl diag.render
      | .ok program =>
          logInfoAt decl m!"Core0 v0.2 accepted `{name}`\n{program.renderManifest}"

  | `(#core0_check_v0_3 $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLowerForProfile env .v0_3 name with
      | .error diag => throwErrorAt decl diag.render
      | .ok program =>
          logInfoAt decl m!"Core0 v0.3 accepted `{name}`\n{program.renderManifest}"

end Lemma.Core0
