import examples.foundation.TimerConformance
import Lemma.Compiler.Test.TimerExport

/-! Fixed Gate 8 export entry point for the machine-timer conformance suite. -/

open Lemma.Examples.Foundation.Timer

#core0_export_timer_suite [foreground, dispatch]
