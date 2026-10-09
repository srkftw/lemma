import Lean
import Lemma.Core0.Frontend
import Lemma.Core0.Semantics

namespace Lemma.Core0

open Lean Elab Command

/-- Check a normal Lean declaration and its reachable bodies against Core0 v0.1. -/
syntax (name := core0Check) "#core0_check " ident : command
syntax (name := core0CheckV02) "#core0_check_v0_2 " ident : command
syntax (name := core0CheckV03) "#core0_check_v0_3 " ident : command
syntax (name := core0CheckV04) "#core0_check_v0_4 " ident : command
syntax (name := core0CheckV05) "#core0_check_v0_5 " ident : command
syntax (name := core0CheckActionV06) "#core0_check_action_v06 " ident : command
syntax (name := core0CheckActionV07) "#core0_check_action_v07 " ident : command

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

  | `(#core0_check_v0_4 $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLowerActionSuiteV04 env #[name] with
      | .error diag => throwErrorAt decl diag.render
      | .ok suite =>
          let summary := s!"Core0 v0.4 Action accepted `{name}` " ++
            s!"(roots={suite.roots.size}, action-functions={suite.actionFunctions.size}, " ++
            s!"scalar-functions={suite.scalarFunctions.size})"
          logInfoAt decl summary

  | `(#core0_check_v0_5 $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLowerActionSuiteV05 env #[name] with
      | .error diag => throwErrorAt decl diag.render
      | .ok suite =>
          let summary := s!"Core0 v0.5 Action accepted `{name}` " ++
            s!"(roots={suite.roots.size}, action-functions={suite.actionFunctions.size}, " ++
            s!"scalar-functions={suite.scalarFunctions.size}, " ++
            s!"device-ops={suite.usedDeviceOps.size})"
          logInfoAt decl summary

  | `(#core0_check_action_v06 $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLowerActionSuiteV06 env #[name] with
      | .error diag => throwErrorAt decl diag.render
      | .ok suite =>
          let summary := s!"Core0 v0.6 Action accepted `{name}` " ++
            s!"(roots={suite.roots.size}, action-functions={suite.actionFunctions.size}, " ++
            s!"scalar-functions={suite.scalarFunctions.size}, " ++
            s!"device-ops={suite.usedDeviceOps.size}, " ++
            s!"trap-ops={suite.usedTrapOps.size})"
          logInfoAt decl summary

  | `(#core0_check_action_v07 $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      match checkAndLowerActionSuiteV07 env #[name] with
      | .error diag => throwErrorAt decl diag.render
      | .ok suite =>
          let summary := s!"Core0 v0.7 Action accepted `{name}` " ++
            s!"(roots={suite.roots.size}, action-functions={suite.actionFunctions.size}, " ++
            s!"scalar-functions={suite.scalarFunctions.size}, " ++
            s!"device-ops={suite.usedDeviceOps.size}, " ++
            s!"trap-ops={suite.usedTrapOps.size}, " ++
            s!"timer-ops={suite.usedTimerOps.size})"
          logInfoAt decl summary

end Lemma.Core0
