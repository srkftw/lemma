import examples.foundation.Monitor
import Lemma.Compiler.Test.MonitorExport

/-! Fixed Gate 9 export entry point for the interactive monitor image. -/

open Lemma.Examples.Foundation

#core0_export_monitor_image [Monitor.foreground, Timer.dispatch]
