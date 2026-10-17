import Lemma.Courses.Package

/-! Original offline reference material. No external textbook or production
license is inferred. Rights/source/edition statements travel with the bytes. -/
namespace Lemma.Courses.PackageReference
open Package

def arithmetic : Course := {
  identity := 1
  edition := 1
  title := "Exact arithmetic: fractions and products"
  sourceAnchor := "Lemma/Courses/PackageReference.lean#arithmetic"
  editionAnchor := "lemma-course-arithmetic/1; package edition 1"
  rightsAnchor := "Original Lemma instructional material. Repository redistribution/license status remains unresolved."
  nodes := #[
    { kind := .explanation, title := "Fractions describe the same amount",
      body := "Multiplying numerator and denominator by the same nonzero integer preserves a fraction. Denominators must be positive in this sequence.",
      exampleText := "1/2 = 3/6 and 1/3 = 2/6.",
      sourceAnchor := "original:fractions-equivalence" },
    { kind := .worked, title := "Add using a common denominator",
      body := "To add two fractions, express both with the same denominator and add their numerators.",
      worked := "1/2 + 1/3 = 3/6 + 2/6 = 5/6. The denominator 6 is nonzero.",
      sourceAnchor := "original:common-denominator",
      logicalPrerequisites := #[0], pedagogicalPrerequisites := #[0] },
    { kind := .exercise .fractionAddition, title := "Your exact fraction",
      body := "Enter an integer numerator and a positive denominator. Several equivalent fractions may describe the same answer.",
      exercise := "Submit N/D equal to 1/2 + 1/3 in Q.",
      hint := "Rewrite both fractions with denominator 6, then add their numerators.",
      sourceAnchor := "original:fraction-addition-goal-1",
      logicalPrerequisites := #[0], pedagogicalPrerequisites := #[1] },
    { kind := .explanation, title := "Distributivity accounts for every term",
      body := "Multiplying two sums requires each term of the first sum to multiply each term of the second. Combine coefficients only after those products are listed.",
      exampleText := "(x+1)(x+1) has products x*x, x*1, 1*x and 1*1.",
      sourceAnchor := "original:distributivity",
      logicalPrerequisites := #[], pedagogicalPrerequisites := #[2] },
    { kind := .worked, title := "Collect powers of x",
      body := "A polynomial identity compares coefficients over Q[x], so it applies to all x in the declared domain.",
      worked := "(x+1)(x+1) = x*x + x + x + 1 = 1 + 2*x + x*x.",
      sourceAnchor := "original:collect-polynomial-coefficients",
      logicalPrerequisites := #[3], pedagogicalPrerequisites := #[3] },
    { kind := .exercise .binomialSquare, title := "Your polynomial coefficients",
      body := "Submit C0, C1 and C2 for the constant, linear and quadratic terms. The checker compares exact coefficients, not sampled values.",
      exercise := "Submit C0+C1*x+C2*x*x equal to (x+1)(x+1) in Q[x].",
      hint := "Write all four products before collecting equal powers of x.",
      sourceAnchor := "original:binomial-square-goal-2",
      logicalPrerequisites := #[3], pedagogicalPrerequisites := #[4] },
    { kind := .exercise .unsupported, title := "Know the checker's boundary",
      body := "The current arithmetic checker has no authority for transcendental identities. Unsupported is a distinct outcome and preserves your writing.",
      exercise := "Explain why checking sin(x)^2+cos(x)^2=1 requires a different admitted checker.",
      hint := "Identify the domain and the missing operations before requesting evidence.",
      sourceAnchor := "original:unsupported-goal-3",
      logicalPrerequisites := #[], pedagogicalPrerequisites := #[5] },
    { kind := .review, title := "Review your reasoning",
      body := "Revisit an attempted exercise and explain its side conditions. An exact result establishes that task result, not your general understanding.",
      review := "Practice after an assisted or invalid attempt. Review later after an unassisted exact attempt. You may override or disable the baseline recommendation.",
      sourceAnchor := "original:explainable-offline-review",
      logicalPrerequisites := #[], pedagogicalPrerequisites := #[2,5] }
  ]
}

end Lemma.Courses.PackageReference
