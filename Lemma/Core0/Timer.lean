import Lemma.Core0.IR

/-!
Closed timer/interrupt operation contract for `core0-v0.7`.

The catalog names the only machine services callable by checked source.  It does
not expose a generic MMIO address, CSR number, foreign symbol, fence policy, or
trap entry.  The two Boolean controls are source `Bool` values but cross the
machine ABI only after canonical zero extension to `i64`.
-/

namespace Lemma.Core0.Timer

/-- Exact timer and interrupt-control identities admitted only by `core0-v0.7`. -/
inductive Op where
  | readTime
  | setCompare
  | readPending
  | irqSaveDisable
  | irqRestore
  | setInterrupt
  | probe
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Op

def all : Array Op := #[
  .readTime,
  .setCompare,
  .readPending,
  .irqSaveDisable,
  .irqRestore,
  .setInterrupt,
  .probe
]

def stableId : Op → String
  | .readTime => "timer.read-time"
  | .setCompare => "timer.set-compare"
  | .readPending => "timer.read-pending"
  | .irqSaveDisable => "irq.save-disable"
  | .irqRestore => "irq.restore"
  | .setInterrupt => "timer.set-interrupt"
  | .probe => "timer.probe"

def render : Op → String := stableId

def sourceIdentity : Op → String
  | .readTime => "Lemma.Core0.Memory.Action.timerReadTime"
  | .setCompare => "Lemma.Core0.Memory.Action.timerSetCompare"
  | .readPending => "Lemma.Core0.Memory.Action.timerReadPending"
  | .irqSaveDisable => "Lemma.Core0.Memory.Action.irqSaveDisable"
  | .irqRestore => "Lemma.Core0.Memory.Action.irqRestore"
  | .setInterrupt => "Lemma.Core0.Memory.Action.timerSetInterrupt"
  | .probe => "Lemma.Core0.Memory.Action.timerProbe"

def llvmSymbol : Op → String
  | .readTime => "core0_timer_read_time"
  | .setCompare => "core0_timer_set_compare"
  | .readPending => "core0_timer_read_pending"
  | .irqSaveDisable => "core0_irq_save_disable"
  | .irqRestore => "core0_irq_restore"
  | .setInterrupt => "core0_timer_set_interrupt"
  | .probe => "core0_timer_probe"

end Op

inductive MMIOAccess where
  | read
  | write
  deriving BEq, DecidableEq, Inhabited, Repr

namespace MMIOAccess

def render : MMIOAccess → String
  | .read => "read"
  | .write => "write"

end MMIOAccess

/-! Pinned QEMU `virt` machine-timer addresses used by the Gate 8 profile. -/
namespace MachineTimer

def timeAddress : UInt64 := 0x0200bff8
def compareAddress : UInt64 := 0x02004000
def registerWidthBytes : Nat := 8

end MachineTimer

/-- A closed, ordered 64-bit timer MMIO operation. -/
structure MMIOContract where
  address : UInt64
  widthBytes : Nat
  access : MMIOAccess
  fenceBefore : Bool
  fenceAfter : Bool
  deriving BEq, Inhabited, Repr

/-- Meaning of the `i64` returned by one machine primitive. -/
inductive ResultMeaning where
  | time
  | zero
  | pendingBit
  | previousGlobalMIE
  | probeMask
  deriving BEq, DecidableEq, Inhabited, Repr

/-- Closed hardware/state meaning.  In particular, the CSR operations name the
only bit they may observe or change; this is not a generic CSR escape hatch. -/
inductive StateOperation where
  | readMachineTime
  | writeMachineCompare
  | readMIPMTIP
  | saveDisableMstatusMIE
  | restoreMstatusMIE
  | setMieMTIE
  | quarantinedProbe
  deriving BEq, DecidableEq, Inhabited, Repr

namespace StateOperation

def render : StateOperation → String
  | .readMachineTime => "read-mtime"
  | .writeMachineCompare => "write-mtimecmp"
  | .readMIPMTIP => "read-mip-mtip"
  | .saveDisableMstatusMIE => "save-disable-mstatus-mie"
  | .restoreMstatusMIE => "restore-mstatus-mie-only"
  | .setMieMTIE => "set-mie-mtie-only"
  | .quarantinedProbe => "quarantined-real-interrupt-context-probe"

end StateOperation

def mstatusMIEBit : Nat := 3
def mieMTIEBit : Nat := 7
def mipMTIPBit : Nat := 7

/-- Immutable source and machine ABI contract for one timer operation.
`sourceArguments` describe the constructor arguments. `machineArguments` make
the two canonical Bool-to-i64 ABI conversions explicit. Every primitive returns
exactly one `i64`; Action status is supplied separately as zero by the lowering. -/
structure OpSpec where
  op : Op
  sourceIdentity : String
  llvmSymbol : String
  sourceArguments : Array Ty
  machineArguments : Array Ty
  result : Ty := .u64
  resultMeaning : ResultMeaning
  stateOperation : StateOperation
  mmio? : Option MMIOContract := none
  canonicalBoolArgument : Bool := false
  requiresGlobalMIEDisabled : Bool := false
  fenceBefore : Bool := true
  fenceAfter : Bool := true
  deriving BEq, Inhabited, Repr

def opCatalog : Array OpSpec := #[
  {
    op := .readTime
    sourceIdentity := Op.sourceIdentity .readTime
    llvmSymbol := Op.llvmSymbol .readTime
    sourceArguments := #[]
    machineArguments := #[]
    resultMeaning := .time
    stateOperation := .readMachineTime
    mmio? := some {
      address := MachineTimer.timeAddress
      widthBytes := MachineTimer.registerWidthBytes
      access := .read
      fenceBefore := true
      fenceAfter := true
    }
  },
  {
    op := .setCompare
    sourceIdentity := Op.sourceIdentity .setCompare
    llvmSymbol := Op.llvmSymbol .setCompare
    sourceArguments := #[.u64]
    machineArguments := #[.u64]
    resultMeaning := .zero
    stateOperation := .writeMachineCompare
    mmio? := some {
      address := MachineTimer.compareAddress
      widthBytes := MachineTimer.registerWidthBytes
      access := .write
      fenceBefore := true
      fenceAfter := true
    }
  },
  {
    op := .readPending
    sourceIdentity := Op.sourceIdentity .readPending
    llvmSymbol := Op.llvmSymbol .readPending
    sourceArguments := #[]
    machineArguments := #[]
    resultMeaning := .pendingBit
    stateOperation := .readMIPMTIP
  },
  {
    op := .irqSaveDisable
    sourceIdentity := Op.sourceIdentity .irqSaveDisable
    llvmSymbol := Op.llvmSymbol .irqSaveDisable
    sourceArguments := #[]
    machineArguments := #[]
    resultMeaning := .previousGlobalMIE
    stateOperation := .saveDisableMstatusMIE
  },
  {
    op := .irqRestore
    sourceIdentity := Op.sourceIdentity .irqRestore
    llvmSymbol := Op.llvmSymbol .irqRestore
    sourceArguments := #[.bool]
    machineArguments := #[.u64]
    resultMeaning := .zero
    stateOperation := .restoreMstatusMIE
    canonicalBoolArgument := true
  },
  {
    op := .setInterrupt
    sourceIdentity := Op.sourceIdentity .setInterrupt
    llvmSymbol := Op.llvmSymbol .setInterrupt
    sourceArguments := #[.bool]
    machineArguments := #[.u64]
    resultMeaning := .zero
    stateOperation := .setMieMTIE
    canonicalBoolArgument := true
  },
  {
    op := .probe
    sourceIdentity := Op.sourceIdentity .probe
    llvmSymbol := Op.llvmSymbol .probe
    sourceArguments := #[]
    machineArguments := #[]
    resultMeaning := .probeMask
    stateOperation := .quarantinedProbe
    requiresGlobalMIEDisabled := true
  }
]

def findSpec? (op : Op) : Option OpSpec :=
  opCatalog.find? (fun spec => spec.op == op)

/-- Closed-catalog sanity shared by frontend probes, lowering, and exporters. -/
def catalogValid : Bool :=
  opCatalog.size == Op.all.size &&
    opCatalog.map (fun spec => spec.op) == Op.all &&
    opCatalog.all fun spec =>
      spec.sourceIdentity == spec.op.sourceIdentity &&
        spec.llvmSymbol == spec.op.llvmSymbol && spec.result == .u64 &&
        spec.fenceBefore && spec.fenceAfter &&
        spec.sourceArguments.size == spec.machineArguments.size &&
        (if spec.canonicalBoolArgument then
          spec.sourceArguments == #[.bool] && spec.machineArguments == #[.u64]
        else spec.sourceArguments == spec.machineArguments) &&
        (match spec.mmio? with
          | none => true
          | some mmio =>
              mmio.widthBytes == MachineTimer.registerWidthBytes &&
                mmio.fenceBefore && mmio.fenceAfter &&
                ((spec.op == .readTime && mmio.address == MachineTimer.timeAddress &&
                    mmio.access == .read) ||
                  (spec.op == .setCompare && mmio.address == MachineTimer.compareAddress &&
                    mmio.access == .write))) &&
        (spec.requiresGlobalMIEDisabled == (spec.op == .probe)) &&
        spec.stateOperation == (match spec.op with
          | .readTime => .readMachineTime
          | .setCompare => .writeMachineCompare
          | .readPending => .readMIPMTIP
          | .irqSaveDisable => .saveDisableMstatusMIE
          | .irqRestore => .restoreMstatusMIE
          | .setInterrupt => .setMieMTIE
          | .probe => .quarantinedProbe)

end Lemma.Core0.Timer
