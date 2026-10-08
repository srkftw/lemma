import Lean
import Lemma.Compiler.LLVMValidate
import Lemma.Machine.ScalarHarness

/-!
Compile-time positive and negative tests for the structured LLVM validator.

Every negative check requires a distinguishing diagnostic fragment; an unrelated
rejection therefore cannot make the suite pass.  These checks exercise Lemma's
validator itself and do not replace LLVM verification or target execution.
-/

namespace Lemma.Compiler.Test.CFGValidation

open Lean Elab Command
open Lemma.Compiler LLVM
open Lemma.Machine

private def ssa (name : String) : LLVM.Operand := .local name
private def i1 (value : Nat) : LLVM.Operand := .int .i1 value
private def i8 (value : Nat) : LLVM.Operand := .int .i8 value
private def i32 (value : Nat) : LLVM.Operand := .int .i32 value
private def i64 (value : Nat) : LLVM.Operand := .int .i64 value

private def validDiamond : LLVM.Function := {
  name := "validation_diamond"
  returnType := .i64
  parameters := #[{ ty := .i1, name := "condition" }]
  blocks := #[
    {
      label := "entry"
      instructions := #[.branch (ssa "condition") "then" "else"]
    },
    { label := "then", instructions := #[.jump "merge"] },
    { label := "else", instructions := #[.jump "merge"] },
    {
      label := "merge"
      instructions := #[
        .phi "result" .i64 #[(i64 11, "then"), (i64 29, "else")],
        .ret .i64 (ssa "result")
      ]
    }
  ]
}

/-!
The canonical bounded-fold shape is also kept here independently of the Core0
lowerer.  This makes loop-sensitive validator regressions fail while elaborating
the library, before an exporter can render malformed SSA.
-/
private def validLoopCallback : LLVM.Function := {
  name := "validation_loop_callback"
  returnType := .i32
  returnExtension := some .signext
  parameters := #[
    { ty := .i32, name := "index" },
    { ty := .i32, name := "accumulator" }
  ]
  parameterExtensions := #[some .signext, some .signext]
  blocks := #[{
    label := "entry"
    instructions := #[
      .bin "next" .add .i32 (ssa "index") (ssa "accumulator"),
      .ret .i32 (ssa "next")
    ]
  }]
}

private def validLoop : LLVM.Function := {
  name := "validation_bounded_loop"
  returnType := .i64
  parameters := #[
    { ty := .i32, name := "count" },
    { ty := .i32, name := "initial" }
  ]
  parameterExtensions := #[some .signext, some .signext]
  blocks := #[
    {
      label := "entry"
      instructions := #[
        .icmp "within_budget" .ule .i32 (ssa "count") (i32 8),
        .branch (ssa "within_budget") "loop.preheader" "loop.exhausted"
      ]
    },
    { label := "loop.preheader", instructions := #[.jump "loop.header"] },
    {
      label := "loop.exhausted"
      instructions := #[
        .zext "exhausted.initial" .i32 (ssa "initial") .i64,
        .bin "exhausted.tag" .or .i64 (ssa "exhausted.initial")
          (i64 9223372036854775808),
        .jump "loop.outcome"
      ]
    },
    {
      label := "loop.header"
      instructions := #[
        .phi "loop.index" .i32
          #[(i32 0, "loop.preheader"), (ssa "loop.next-index", "loop.body")],
        .phi "loop.accumulator" .i32
          #[(ssa "initial", "loop.preheader"), (ssa "loop.next-accumulator", "loop.body")],
        .icmp "loop.continue" .ult .i32 (ssa "loop.index") (ssa "count"),
        .branch (ssa "loop.continue") "loop.body" "loop.done"
      ]
    },
    {
      label := "loop.body"
      instructions := #[
        .abiCall (some "loop.next-accumulator") .i32 (some .signext)
          validLoopCallback.name #[
            { ty := .i32, value := ssa "loop.index", extension := some .signext },
            { ty := .i32, value := ssa "loop.accumulator", extension := some .signext }
          ],
        .bin "loop.next-index" .add .i32 (ssa "loop.index") (i32 1),
        .jump "loop.header"
      ]
    },
    {
      label := "loop.done"
      instructions := #[
        .zext "loop.value" .i32 (ssa "loop.accumulator") .i64,
        .jump "loop.outcome"
      ]
    },
    {
      label := "loop.outcome"
      instructions := #[
        .phi "result" .i64 #[(ssa "loop.value", "loop.done"),
          (ssa "exhausted.tag", "loop.exhausted")],
        .ret .i64 (ssa "result")
      ]
    }
  ]
}

private def validLoopModule : LLVM.Module := {
  sourceName := "CFG validator bounded loop test"
  functions := #[validLoopCallback, validLoop]
}

private def loopMissingBackedgeInput : LLVM.Function := {
  validLoop with
  name := "loop_missing_backedge_input"
  blocks := validLoop.blocks.modify 3 fun block => {
    block with instructions := block.instructions.modify 0 (fun _ =>
      .phi "loop.index" .i32 #[(i32 0, "loop.preheader")])
  }
}

private def loopDuplicateBackedgeInput : LLVM.Function := {
  validLoop with
  name := "loop_duplicate_backedge_input"
  blocks := validLoop.blocks.modify 3 fun block => {
    block with instructions := block.instructions.modify 0 (fun _ =>
      .phi "loop.index" .i32 #[(i32 0, "loop.preheader"),
        (ssa "loop.next-index", "loop.body"), (i32 1, "loop.body")])
  }
}

private def loopNonDominatingLatchValue : LLVM.Function := {
  validLoop with
  name := "loop_non_dominating_latch_value"
  blocks := (validLoop.blocks.modify 2 fun block => {
    block with instructions := #[
      .bin "wrong.latch" .add .i32 (ssa "initial") (i32 1)
    ] ++ block.instructions
  }).modify 3 fun block => {
    block with instructions := block.instructions.modify 0 (fun _ =>
      .phi "loop.index" .i32 #[(i32 0, "loop.preheader"),
        (ssa "wrong.latch", "loop.body")])
  }
}

private def loopIncorrectPhiType : LLVM.Function := {
  validLoop with
  name := "loop_incorrect_phi_type"
  blocks := validLoop.blocks.modify 3 fun block => {
    block with instructions := block.instructions.modify 0 (fun _ =>
      .phi "loop.index" .i64 #[(i64 0, "loop.preheader"),
        (ssa "loop.next-index", "loop.body")])
  }
}

private def loopBackedgeToEntry : LLVM.Function := {
  validLoop with
  name := "loop_backedge_to_entry"
  blocks := validLoop.blocks.modify 4 fun block => {
    block with instructions := block.instructions.modify 2 fun _ => .jump "entry"
  }
}

private def loopCallbackArityMismatch : LLVM.Function := {
  validLoop with
  name := "loop_callback_arity_mismatch"
  blocks := validLoop.blocks.modify 4 fun block => {
    block with instructions := block.instructions.modify 0 (fun _ =>
      .abiCall (some "loop.next-accumulator") .i32 (some .signext)
        validLoopCallback.name #[
          { ty := .i32, value := ssa "loop.index", extension := some .signext }
        ])
  }
}

private def loopCallbackMismatchModule : LLVM.Module := {
  sourceName := "CFG validator loop callback mismatch"
  functions := #[validLoopCallback, loopCallbackArityMismatch]
}

private def scalarRoot : LoweredRoot := {
  id := 1
  source := .mkSimple "validationScalarRoot"
  llvm := "validation_scalar_root"
  signature := { args := #[.u64], result := .u64 }
}

private def scalarConfiguration : Lemma.Compiler.Test.ScalarABI.Configuration := {
  suiteId := 1
  sourceSeed := 2
  runtimeSeed := 3
}

private def legacyRoot : LLVM.Function := {
  name := "validation_legacy_root"
  returnType := .i64
  parameters := #[
    { ty := .i64, name := "arg0" },
    { ty := .i64, name := "arg1" },
    { ty := .i64, name := "arg2" }
  ]
  blocks := #[{
    label := "entry"
    instructions := #[.ret .i64 (ssa "arg0")]
  }]
}

private def scalarUserRoot : LLVM.Function := {
  name := scalarRoot.llvm
  returnType := .i64
  parameters := #[{ ty := .i64, name := "arg0" }]
  parameterExtensions := #[none]
  blocks := #[{
    label := "entry"
    instructions := #[.ret .i64 (ssa "arg0")]
  }]
}

private def legacyHarnessModule : LLVM.Module := {
  sourceName := "CFG validator legacy harness test"
  declarations := Lemma.Machine.Harness.declarations
  functions := #[legacyRoot] ++
    Lemma.Machine.Harness.functions core0Layout legacyRoot.name
}

private def scalarHarnessModule : LLVM.Module := {
  sourceName := "CFG validator scalar harness test"
  declarations := Lemma.Machine.ScalarHarness.declarations
  functions := #[scalarUserRoot] ++
    Lemma.Machine.ScalarHarness.functions core0Layout scalarConfiguration #[scalarRoot]
}

private def missingTerminator : LLVM.Function := {
  name := "missing_terminator"
  returnType := .i64
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[.bin "value" .add .i64 (i64 1) (i64 2)]
  }]
}

private def earlyTerminator : LLVM.Function := {
  name := "early_terminator"
  returnType := .i64
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[.ret .i64 (i64 1), .ret .i64 (i64 2)]
  }]
}

private def unknownTarget : LLVM.Function := {
  name := "unknown_target"
  returnType := .void
  parameters := #[]
  blocks := #[{ label := "entry", instructions := #[.jump "absent"] }]
}

private def unreachableBlock : LLVM.Function := {
  name := "unreachable_block"
  returnType := .i64
  parameters := #[]
  blocks := #[
    { label := "entry", instructions := #[.ret .i64 (i64 1)] },
    { label := "dead", instructions := #[.ret .i64 (i64 2)] }
  ]
}

private def duplicateBlocks : LLVM.Function := {
  name := "duplicate_blocks"
  returnType := .void
  parameters := #[]
  blocks := #[
    { label := "entry", instructions := #[.jump "duplicate"] },
    { label := "duplicate", instructions := #[.retVoid] },
    { label := "duplicate", instructions := #[.retVoid] }
  ]
}

private def phiMissingPredecessor : LLVM.Function := {
  validDiamond with
  name := "phi_missing_predecessor"
  blocks := validDiamond.blocks.modify 3 fun block => {
    block with instructions := #[
      .phi "result" .i64 #[(i64 11, "then")],
      .ret .i64 (ssa "result")
    ]
  }
}

private def phiDuplicatePredecessor : LLVM.Function := {
  validDiamond with
  name := "phi_duplicate_predecessor"
  blocks := validDiamond.blocks.modify 3 fun block => {
    block with instructions := #[
      .phi "result" .i64
        #[(i64 11, "then"), (i64 12, "then"), (i64 29, "else")],
      .ret .i64 (ssa "result")
    ]
  }
}

private def phiUnknownPredecessor : LLVM.Function := {
  validDiamond with
  name := "phi_unknown_predecessor"
  blocks := validDiamond.blocks.modify 3 fun block => {
    block with instructions := #[
      .phi "result" .i64
        #[(i64 11, "then"), (i64 29, "else"), (i64 31, "ghost")],
      .ret .i64 (ssa "result")
    ]
  }
}

private def phiAfterOrdinaryInstruction : LLVM.Function := {
  validDiamond with
  name := "phi_after_instruction"
  blocks := validDiamond.blocks.modify 3 fun block => {
    block with instructions := #[
      .bin "ordinary" .add .i64 (i64 1) (i64 2),
      .phi "result" .i64 #[(i64 11, "then"), (i64 29, "else")],
      .ret .i64 (ssa "result")
    ]
  }
}

private def useBeforeDefinition : LLVM.Function := {
  name := "use_before_definition"
  returnType := .i64
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[
      .bin "first" .add .i64 (ssa "later") (i64 1),
      .bin "later" .add .i64 (i64 2) (i64 3),
      .ret .i64 (ssa "first")
    ]
  }]
}

private def ordinaryNonDominance : LLVM.Function := {
  name := "ordinary_non_dominance"
  returnType := .i64
  parameters := #[{ ty := .i1, name := "condition" }]
  blocks := #[
    {
      label := "entry"
      instructions := #[.branch (ssa "condition") "left" "right"]
    },
    {
      label := "left"
      instructions := #[
        .bin "left_value" .add .i64 (i64 1) (i64 2),
        .jump "merge"
      ]
    },
    { label := "right", instructions := #[.jump "merge"] },
    {
      label := "merge"
      instructions := #[.ret .i64 (ssa "left_value")]
    }
  ]
}

private def phiEdgeNonDominance : LLVM.Function := {
  name := "phi_edge_non_dominance"
  returnType := .i64
  parameters := #[{ ty := .i1, name := "condition" }]
  blocks := #[
    {
      label := "entry"
      instructions := #[.branch (ssa "condition") "left" "right"]
    },
    {
      label := "left"
      instructions := #[
        .bin "left_value" .add .i64 (i64 1) (i64 2),
        .jump "merge"
      ]
    },
    { label := "right", instructions := #[.jump "merge"] },
    {
      label := "merge"
      instructions := #[
        .phi "result" .i64 #[(i64 0, "left"), (ssa "left_value", "right")],
        .ret .i64 (ssa "result")
      ]
    }
  ]
}

private def wrongBranchType : LLVM.Function := {
  name := "wrong_branch_type"
  returnType := .i64
  parameters := #[{ ty := .i64, name := "condition" }]
  blocks := #[
    {
      label := "entry"
      instructions := #[.branch (ssa "condition") "yes" "no"]
    },
    { label := "yes", instructions := #[.ret .i64 (i64 1)] },
    { label := "no", instructions := #[.ret .i64 (i64 0)] }
  ]
}

private def wrongReturnType : LLVM.Function := {
  name := "wrong_return_type"
  returnType := .i64
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[.ret .i32 (i32 0)]
  }]
}

private def wrongOperandType : LLVM.Function := {
  name := "wrong_operand_type"
  returnType := .i64
  parameters := #[{ ty := .i32, name := "narrow" }]
  blocks := #[{
    label := "entry"
    instructions := #[
      .bin "result" .add .i64 (ssa "narrow") (i64 1),
      .ret .i64 (ssa "result")
    ]
  }]
}

private def outOfRangeLiteral : LLVM.Function := {
  name := "out_of_range_literal"
  returnType := .i1
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[.ret .i1 (i1 2)]
  }]
}

private def unaryTarget : LLVM.Function := {
  name := "unary_target"
  returnType := .i64
  parameters := #[{ ty := .i64, name := "arg0" }]
  blocks := #[{
    label := "entry"
    instructions := #[.ret .i64 (ssa "arg0")]
  }]
}

private def wrongCallArity : LLVM.Function := {
  name := "wrong_call_arity"
  returnType := .i64
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[
      .call (some "result") .i64 unaryTarget.name #[],
      .ret .i64 (ssa "result")
    ]
  }]
}

private def wrongCallResultType : LLVM.Function := {
  name := "wrong_call_result_type"
  returnType := .i32
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[
      .call (some "result") .i32 unaryTarget.name #[(.i64, i64 7)],
      .ret .i32 (ssa "result")
    ]
  }]
}

private def extendedTarget : LLVM.Function := {
  name := "extended_target"
  returnType := .i8
  returnExtension := some .zeroext
  parameters := #[{ ty := .i8, name := "arg0" }]
  parameterExtensions := #[some .zeroext]
  blocks := #[{
    label := "entry"
    instructions := #[.ret .i8 (ssa "arg0")]
  }]
}

private def omittedCallExtensions : LLVM.Function := {
  name := "omitted_call_extensions"
  returnType := .i8
  parameters := #[]
  blocks := #[{
    label := "entry"
    instructions := #[
      .call (some "result") .i8 extendedTarget.name #[(.i8, i8 7)],
      .ret .i8 (ssa "result")
    ]
  }]
}

private def arityMismatchModule : LLVM.Module := {
  sourceName := "call arity mismatch"
  functions := #[unaryTarget, wrongCallArity]
}

private def resultMismatchModule : LLVM.Module := {
  sourceName := "call result mismatch"
  functions := #[unaryTarget, wrongCallResultType]
}

private def extensionMismatchModule : LLVM.Module := {
  sourceName := "call extension mismatch"
  functions := #[extendedTarget, omittedCallExtensions]
}

private def hasFragment (message fragment : String) : Bool :=
  fragment != "" && (message.splitOn fragment).length > 1

private def expectPass (label : String) (result : Except String Unit) : CommandElabM Unit := do
  match result with
  | .ok () => pure ()
  | .error message => throwError m!"CFG validator positive `{label}` failed: {message}"

private def expectReject (label fragment : String) (result : Except String Unit) :
    CommandElabM Unit := do
  match result with
  | .ok () => throwError m!"CFG validator negative `{label}` unexpectedly passed"
  | .error message =>
      unless hasFragment message fragment do
        throwError m!"CFG validator negative `{label}` failed for the wrong reason; expected `{fragment}`, got: {message}"

run_cmd do
  let mut checks := 0
  let pass (count : Nat) (label : String) (result : Except String Unit) : CommandElabM Nat := do
    expectPass label result
    pure (count + 1)
  let reject (count : Nat) (label fragment : String)
      (result : Except String Unit) : CommandElabM Nat := do
    expectReject label fragment result
    pure (count + 1)

  checks ← pass checks "diamond" (LLVM.validateFunction validDiamond)
  checks ← pass checks "harness-exit-failure"
    (LLVM.validateFunction (Lemma.Machine.Harness.exitFailure core0Layout))
  checks ← pass checks "harness-exit-success"
    (LLVM.validateFunction (Lemma.Machine.Harness.exitSuccess core0Layout))
  checks ← pass checks "harness-uart-putc"
    (LLVM.validateFunction (Lemma.Machine.Harness.uartPutc core0Layout))
  checks ← pass checks "harness-uart-drain"
    (LLVM.validateFunction (Lemma.Machine.Harness.uartDrain core0Layout))
  checks ← pass checks "harness-put-hex64"
    (LLVM.validateFunction Lemma.Machine.Harness.putHex64)
  checks ← pass checks "harness-main"
    (LLVM.validateFunction (Lemma.Machine.Harness.main core0Layout legacyRoot.name))
  checks ← pass checks "scalar-harness-main" (LLVM.validateFunction
    (Lemma.Machine.ScalarHarness.main core0Layout scalarConfiguration #[scalarRoot]))
  checks ← pass checks "legacy-harness-module" (LLVM.validateModule legacyHarnessModule)
  checks ← pass checks "scalar-harness-module" (LLVM.validateModule scalarHarnessModule)
  checks ← pass checks "bounded-loop-module" (LLVM.validateModule validLoopModule)

  checks ← reject checks "missing-terminator" "final instruction is not a terminator"
    (LLVM.validateFunction missingTerminator)
  checks ← reject checks "early-terminator" "terminator appears before final instruction"
    (LLVM.validateFunction earlyTerminator)
  checks ← reject checks "unknown-target" "targets unknown block"
    (LLVM.validateFunction unknownTarget)
  checks ← reject checks "unreachable-block" "contains unreachable blocks"
    (LLVM.validateFunction unreachableBlock)
  checks ← reject checks "duplicate-block" "duplicate block label"
    (LLVM.validateFunction duplicateBlocks)
  checks ← reject checks "phi-missing-predecessor" "predecessor set differs"
    (LLVM.validateFunction phiMissingPredecessor)
  checks ← reject checks "phi-duplicate-predecessor" "repeats predecessor"
    (LLVM.validateFunction phiDuplicatePredecessor)
  checks ← reject checks "phi-unknown-predecessor" "predecessor set differs"
    (LLVM.validateFunction phiUnknownPredecessor)
  checks ← reject checks "phi-placement" "is not in the block's phi prefix"
    (LLVM.validateFunction phiAfterOrdinaryInstruction)
  checks ← reject checks "use-before-definition" "uses `%later` before its definition"
    (LLVM.validateFunction useBeforeDefinition)
  checks ← reject checks "ordinary-non-dominance" "from non-dominating block `%left`"
    (LLVM.validateFunction ordinaryNonDominance)
  checks ← reject checks "phi-edge-non-dominance" "does not dominate predecessor `%right`"
    (LLVM.validateFunction phiEdgeNonDominance)
  checks ← reject checks "wrong-branch-type" "branch condition expects `i1`"
    (LLVM.validateFunction wrongBranchType)
  checks ← reject checks "wrong-return-type" "returns `i32` from function returning `i64`"
    (LLVM.validateFunction wrongReturnType)
  checks ← reject checks "wrong-operand-type" "left operand expects `i64`"
    (LLVM.validateFunction wrongOperandType)
  checks ← reject checks "literal-range" "literal 2 is outside `i1`"
    (LLVM.validateFunction outOfRangeLiteral)
  checks ← reject checks "call-arity" "call arity disagrees"
    (LLVM.validateModule arityMismatchModule)
  checks ← reject checks "call-result" "call return type disagrees"
    (LLVM.validateModule resultMismatchModule)
  checks ← reject checks "call-extensions" "omits required ABI extensions"
    (LLVM.validateModule extensionMismatchModule)
  checks ← reject checks "loop-missing-backedge-input" "predecessor set differs"
    (LLVM.validateFunction loopMissingBackedgeInput)
  checks ← reject checks "loop-duplicate-backedge-input" "repeats predecessor `%loop.body`"
    (LLVM.validateFunction loopDuplicateBackedgeInput)
  checks ← reject checks "loop-non-dominating-latch-value"
    "does not dominate predecessor `%loop.body`"
    (LLVM.validateFunction loopNonDominatingLatchValue)
  checks ← reject checks "loop-incorrect-phi-type" "expects `i64`, but `%loop.next-index` has `i32`"
    (LLVM.validateFunction loopIncorrectPhiType)
  checks ← reject checks "loop-backedge-to-entry" "entry block has predecessors"
    (LLVM.validateFunction loopBackedgeToEntry)
  checks ← reject checks "loop-callback-arity" "ABI call arity disagrees"
    (LLVM.validateModule loopCallbackMismatchModule)

  unless checks == 36 do
    throwError m!"CFG validator suite count changed: {checks} != 36"
  logInfo m!"CFG validator: {checks} compile-time checks passed"

end Lemma.Compiler.Test.CFGValidation
