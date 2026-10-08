import Lemma.Compiler.Test.BoundedExport
import examples.foundation.BoundedConformance

/-! Canonical `core0-v0.3` Gate 4 root order; IDs are one-based. -/

#core0_export_bounded_suite [
  Lemma.Examples.Foundation.Bounded.sumFold,
  Lemma.Examples.Foundation.Bounded.sumFoldChanged,
  Lemma.Examples.Foundation.Bounded.bitMixFold,
  Lemma.Examples.Foundation.Bounded.nestedFold,
  Lemma.Examples.Foundation.Bounded.helperFold,
  Lemma.Examples.Foundation.Bounded.zeroBudgetFold,
  Lemma.Examples.Foundation.Bounded.maxBudgetFold
]
