import Lemma.School.Authoring
import Lemma.Mathematics.Exact

/-! Original redistributable fixture unit. It deliberately does not claim to
be derived from the unavailable owner textbook collection. This reference
proof is checked by Lean; arbitrary learner proofs require teacher review. -/
namespace Lemma.School.FixtureUnit
open Authoring
open Lemma.Courses

/-- A source-grounded reference theorem; not a checker for handwritten proofs. -/
theorem square_successor (x : Nat) : (x+1)*(x+1) = x*x+2*x+1 := by
  simp [Nat.add_mul, Nat.mul_add, Nat.add_assoc, Nat.two_mul]

-- The source is a small, explicitly redistributable fixture. Exact file identity
-- is checked by the source-registry resolution test, independently of this path.
def sourceText : String := include_str "../../fixtures/school/Distributivity.txt"
def sourceDigest : String := Digest.sha256String sourceText

def registry : SourceRegistry.Registry := {
  sources := #[{
    id := "lemma-distributivity-fixture", title := "Distributivity and the square of a sum",
    authors := #["Lemma task 008 fixture authorship"], edition := "1",
    publication := "Original task fixture, 2026", bibliographicStatus := .verified,
    bibliographicEvidence := "Maintained source fixture header and eight numbered sections inspected",
    fileDigest := sourceDigest, mediaType := "text/plain",
    ownerLocation := "fixtures/school/Distributivity.txt",
    rights := "Explicit permission in fixture: copy, modify, redistribute for any purpose; fixture only" }] }

private def anchor (index : Nat) : SourceRegistry.Anchor := {
  id := s!"fixture:section-{index}", sourceId := "lemma-distributivity-fixture", edition := "1",
  fileDigest := sourceDigest, sectionLabel := toString index, verification := .verified,
  evidence := "Exact maintained fixture paragraph; no OCR or inferred textbook correspondence" }

private def assessment (checker : String := "teacher-review/1") (independent : Bool := false)
    (referenceTheorem : Option String := none) : Assessment := {
  checker, independent, referenceTheorem,
  criteria := #["State the domain and justify each equality", "Account for every product term"] }

private def activity (id : String) (node : Nat) (kind : ActivityKind)
    (goal : Package.Goal := .unsupported) (assistance : Assistance := .hint)
    (independent : Bool := false) : Activity := {
  id, node, kind, goal, assistance,
  assessment := assessment (if goal == .binomialSquare then "lemma-exact/1:binomialSquare" else "teacher-review/1") independent
    (if kind == .independentReasoning then some "Lemma.School.FixtureUnit.square_successor" else none) }

def unit : Authoring.Unit := {
  course := {
    identity := 801, edition := 1, title := "Why the cross terms matter",
    sourceAnchor := "lemma-distributivity-fixture; exact source digest in unit registry",
    editionAnchor := "Original redistributable fixture, edition 1",
    rightsAnchor := "Fixture permits copying/modification/redistribution; no claim for missing textbooks or repository license",
    nodes := #[
      { kind := .explanation, title := "Prepare: equality and distribution",
        body := "For natural numbers, multiplication distributes over addition. Replacing equal expressions preserves equality. Name the domain before manipulating an expression.",
        exampleText := "3*(4+1)=3*4+3*1=15.", hint := "List which term multiplies each summand.", sourceAnchor := "fixture:section-1" },
      { kind := .worked, title := "A worked square with four products",
        body := "Every term in the left sum multiplies every term in the right sum. The two middle products are different contributions, even though they have equal values.",
        worked := "(3+1)*(3+1)=3*3+3*1+1*3+1*1=9+3+3+1=16.",
        hint := "Draw a two by two product table.", sourceAnchor := "fixture:section-2", logicalPrerequisites := #[0] },
      { kind := .exercise .unsupported, title := "Reconstruct the definition",
        body := "Explain what a polynomial identity claims. Contrast that claim with an equality checked at one chosen value.",
        exercise := "Write a definition using the phrase for every value in a declared domain.",
        hint := "Specify the quantifier and the domain.", sourceAnchor := "fixture:section-3", logicalPrerequisites := #[0] },
      { kind := .exercise .binomialSquare, title := "Collect exact coefficients",
        body := "Write the coefficients in constant, linear, quadratic order. This installed exact checker supports the fixed goal (x+1)*(x+1) in Q[x].",
        exercise := "Submit C0+C1*x+C2*x*x equal to (x+1)*(x+1).",
        hint := "List four products before combining equal powers.", sourceAnchor := "fixture:section-4", logicalPrerequisites := #[1,2] },
      { kind := .exercise .unsupported, title := "Analyse the dropped-term argument",
        body := "A learner claims (x+1)*(x+1)=x*x+1 by squaring each term separately. Locate the invalid step and supply a counterexample.",
        exercise := "Explain the missing products and compare both sides at x=1.",
        hint := "Compare the four-product table with the proposed right side.", sourceAnchor := "fixture:section-5", logicalPrerequisites := #[1,2] },
      { kind := .exercise .unsupported, title := "Independent reasoning",
        body := "Give a symbolic proof over natural numbers. Your writing is retained for teacher review. The checked reference theorem does not verify your submission.",
        exercise := "Prove for every natural x: (x+1)*(x+1)=x*x+2*x+1. State the domain and justify each equality.",
        sourceAnchor := "fixture:section-6", logicalPrerequisites := #[1,2] },
      { kind := .exercise .unsupported, title := "Transfer to unequal constants",
        body := "Use the same product accounting for two different constants. This transfer task requires teacher review because its goal differs from the installed exact checker.",
        exercise := "Expand (x+2)*(x+3), collect coefficients, and justify the identity symbolically.",
        hint := "Make a fresh two by two product table.", sourceAnchor := "fixture:section-7", logicalPrerequisites := #[1,2] },
      { kind := .review, title := "Later reconstruction",
        body := "After the scheduled delay, reconstruct the four-product argument without assistance. Explain why two cross terms appear and diagnose the dropped-term argument.",
        review := "The review remains tied to this unit edition and review-policy version. A due software event is not evidence of retention.",
        sourceAnchor := "fixture:section-8", logicalPrerequisites := #[2] }
    ] },
  learningGoals := #["Use distributivity with explicit domains", "Distinguish symbolic identity from sampled equality", "Justify cross terms and refute dropped-term arguments"],
  notationGuide := #["x denotes a natural number in the reference theorem", "Q[x] is the installed exact coefficient checker domain"],
  sources := registry, anchors := (Array.range 8).map (fun i => anchor (i+1)),
  activities := #[activity "prepare" 0 .preparation, activity "worked" 1 .preparation .unsupported .worked,
    activity "define" 2 .definition, activity "coefficients" 3 .routine .binomialSquare,
    activity "invalid" 4 .invalidArgument, activity "reason" 5 .independentReasoning .unsupported .none true,
    activity "transfer" 6 .transfer, activity "later-review" 7 .review .unsupported .none true],
  relations := #[
    {fromActivity := "prepare", toActivity := "worked", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "prepare", toActivity := "define", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "worked", toActivity := "coefficients", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "define", toActivity := "coefficients", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "worked", toActivity := "invalid", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "define", toActivity := "invalid", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "worked", toActivity := "reason", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "define", toActivity := "reason", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "worked", toActivity := "transfer", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "define", toActivity := "transfer", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "define", toActivity := "later-review", kind := .prerequisite, origin := "Author-curated fixture", reviewed := true},
    {fromActivity := "invalid", toActivity := "reason", kind := .related, origin := "Author-curated fixture"},
    {fromActivity := "reason", toActivity := "invalid", kind := .related, origin := "Author-curated fixture"}],
  review := {
    version := "lemma-review-schedule/1", delaySeconds := 86400, activityId := "later-review",
    uncertainty := "Uncertain provisional estimate; synthetic schedule establishes software operation only"} }

/-- Independent finite checker examples use the maintained exact checker and
vary both valid/invalid coefficients; no permissive proof checker is invented. -/
def checkerExamples : Array UInt64 :=
  #[Lemma.Mathematics.Exact.polynomial 1 1 1 1 1 2 1 8,
    Lemma.Mathematics.Exact.polynomial 1 1 1 1 1 0 1 8,
    Lemma.Mathematics.Exact.polynomial 1 1 1 1 1 2 2 8]

end Lemma.School.FixtureUnit
