import Lemma.Core0.IR

/-!
Closed synchronous-trap operation contract for `core0-v0.6`.

These operations denote real machine-mode traps implemented by the generated
machine substrate.  They are not arbitrary foreign calls and accept no caller-
selected cause, PC, CSR value, or instruction encoding.  A returning primitive
produces one `UInt64` context-check mask: zero means the machine sentinel/canary
checks passed and each set bit reports a declared context mismatch.  The source
Action continuation receives status zero and that mask.  The unexpected-ecall
and illegal-instruction fixtures enter the bounded fatal path and therefore do
not return during correct target execution.
-/

namespace Lemma.Core0.Trap

/-- Exact synchronous-trap identities admitted only by `core0-v0.6`. -/
inductive Op where
  | ecall
  | breakpoint
  | unexpectedEcall
  | illegalInstruction
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Op

def all : Array Op := #[
  .ecall,
  .breakpoint,
  .unexpectedEcall,
  .illegalInstruction
]

def stableId : Op → String
  | .ecall => "trap.ecall"
  | .breakpoint => "trap.breakpoint"
  | .unexpectedEcall => "trap.unexpected-ecall"
  | .illegalInstruction => "trap.illegal-instruction"

def render : Op → String := stableId

def llvmSymbol : Op → String
  | .ecall => "core0_trap_ecall"
  | .breakpoint => "core0_trap_breakpoint"
  | .unexpectedEcall => "core0_trap_unexpected_ecall"
  | .illegalInstruction => "core0_trap_illegal_instruction"

end Op

/-- Whether an authorized fixture resumes after machine dispatch or terminates
through the bounded fatal diagnostic path. -/
inductive Disposition where
  | resume
  | fatal
  deriving BEq, DecidableEq, Inhabited, Repr

/-- Immutable frontend/backend contract for one generated trap primitive.
All four primitives have the exact target signature `() -> i64`. -/
structure OpSpec where
  op : Op
  llvmSymbol : String
  arguments : Array Ty := #[]
  result : Ty := .u64
  disposition : Disposition
  deriving BEq, Inhabited, Repr

def opCatalog : Array OpSpec := #[
  { op := .ecall, llvmSymbol := Op.llvmSymbol .ecall, disposition := .resume },
  { op := .breakpoint, llvmSymbol := Op.llvmSymbol .breakpoint, disposition := .resume },
  {
    op := .unexpectedEcall
    llvmSymbol := Op.llvmSymbol .unexpectedEcall
    disposition := .fatal
  },
  {
    op := .illegalInstruction
    llvmSymbol := Op.llvmSymbol .illegalInstruction
    disposition := .fatal
  }
]

def findSpec? (op : Op) : Option OpSpec :=
  opCatalog.find? (fun spec => spec.op == op)

/-- Closed-catalog sanity used by the checked lowering and evidence exporters. -/
def catalogValid : Bool :=
  opCatalog.size == Op.all.size &&
    opCatalog.map (fun spec => spec.op) == Op.all &&
    opCatalog.all fun spec =>
      spec.llvmSymbol == spec.op.llvmSymbol && spec.arguments.isEmpty &&
        spec.result == .u64 &&
        spec.disposition == (match spec.op with
          | .ecall | .breakpoint => .resume
          | .unexpectedEcall | .illegalInstruction => .fatal)

end Lemma.Core0.Trap
