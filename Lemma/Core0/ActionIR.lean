import Lemma.Core0.IR
import Lemma.Core0.Device
import Lemma.Core0.Memory
import Lemma.Core0.Trap
import Lemma.Core0.Timer

/-!
Backend-neutral checked effect syntax for `core0-v0.4` through `core0-v0.7`.

This is separate from scalar `Expr`: an Action is never assigned a scalar target
type.  Continuation binders are scalar locals and the compiler erases the enclosing
Action node to structured control flow.
-/

namespace Lemma.Core0

inductive MemoryAccess where
  | read
  | write
  deriving BEq, DecidableEq, Inhabited, Repr

namespace MemoryAccess

def render : MemoryAccess → String
  | .read => "read"
  | .write => "write"

end MemoryAccess

/-- Potential effects of a checked Action declaration.  Branches carry the union
of both branches; runtime traces still contain only operations actually selected. -/
structure EffectSet where
  checkedAccess : Bool := false
  ramRead : Bool := false
  ramWrite : Bool := false
  mmioRead : Bool := false
  mmioWrite : Bool := false
  ioOrder : Bool := false
  syncTrap : Bool := false
  machineState : Bool := false
  timerState : Bool := false
  interruptState : Bool := false
  physicalRead : Bool := false
  physicalWrite : Bool := false
  virtualRead : Bool := false
  virtualWrite : Bool := false
  firmwareCall : Bool := false
  userSyscall : Bool := false
  addressSpace : Bool := false
  instructionSync : Bool := false
  privilegeTransition : Bool := false
  waitState : Bool := false
  mayDiverge : Bool := false
  deriving BEq, DecidableEq, Inhabited, Repr

namespace EffectSet

def empty : EffectSet := {}
def check : EffectSet := { checkedAccess := true }
def read : EffectSet := { checkedAccess := true, ramRead := true }
def write : EffectSet := { checkedAccess := true, ramWrite := true }
def deviceRead : EffectSet := { mmioRead := true, ioOrder := true }
def deviceWrite : EffectSet := { mmioWrite := true, ioOrder := true }
def trap : EffectSet := { syncTrap := true, machineState := true }
def timerRead : EffectSet := {
  mmioRead := true, ioOrder := true, machineState := true, timerState := true
}
def timerWrite : EffectSet := {
  mmioWrite := true, ioOrder := true, machineState := true, timerState := true
}
def interrupt : EffectSet := {
  ioOrder := true, machineState := true, interruptState := true
}
def timerInterrupt : EffectSet := {
  ioOrder := true, machineState := true, timerState := true, interruptState := true
}

def union (left right : EffectSet) : EffectSet := {
  checkedAccess := left.checkedAccess || right.checkedAccess
  ramRead := left.ramRead || right.ramRead
  ramWrite := left.ramWrite || right.ramWrite
  mmioRead := left.mmioRead || right.mmioRead
  mmioWrite := left.mmioWrite || right.mmioWrite
  ioOrder := left.ioOrder || right.ioOrder
  syncTrap := left.syncTrap || right.syncTrap
  machineState := left.machineState || right.machineState
  timerState := left.timerState || right.timerState
  interruptState := left.interruptState || right.interruptState
  physicalRead := left.physicalRead || right.physicalRead
  physicalWrite := left.physicalWrite || right.physicalWrite
  virtualRead := left.virtualRead || right.virtualRead
  virtualWrite := left.virtualWrite || right.virtualWrite
  firmwareCall := left.firmwareCall || right.firmwareCall
  userSyscall := left.userSyscall || right.userSyscall
  addressSpace := left.addressSpace || right.addressSpace
  instructionSync := left.instructionSync || right.instructionSync
  privilegeTransition := left.privilegeTransition || right.privilegeTransition
  waitState := left.waitState || right.waitState
  mayDiverge := left.mayDiverge || right.mayDiverge
}

instance : Union EffectSet := ⟨union⟩

def subset (left right : EffectSet) : Bool :=
  (!left.checkedAccess || right.checkedAccess) &&
    (!left.ramRead || right.ramRead) &&
    (!left.ramWrite || right.ramWrite) &&
    (!left.mmioRead || right.mmioRead) &&
    (!left.mmioWrite || right.mmioWrite) &&
    (!left.ioOrder || right.ioOrder) &&
    (!left.syncTrap || right.syncTrap) &&
    (!left.machineState || right.machineState) &&
    (!left.timerState || right.timerState) &&
    (!left.interruptState || right.interruptState) &&
    (!left.physicalRead || right.physicalRead) &&
    (!left.physicalWrite || right.physicalWrite) &&
    (!left.virtualRead || right.virtualRead) &&
    (!left.virtualWrite || right.virtualWrite) &&
    (!left.firmwareCall || right.firmwareCall) &&
    (!left.userSyscall || right.userSyscall) &&
    (!left.addressSpace || right.addressSpace) &&
    (!left.instructionSync || right.instructionSync) &&
    (!left.privilegeTransition || right.privilegeTransition) &&
    (!left.waitState || right.waitState) &&
    (!left.mayDiverge || right.mayDiverge)

def render (effects : EffectSet) : String :=
  let names :=
    (if effects.checkedAccess then ["checked-access"] else []) ++
    (if effects.ramRead then ["fixed-ram-read"] else []) ++
    (if effects.ramWrite then ["fixed-ram-write"] else []) ++
    (if effects.mmioRead then ["mmio-read"] else []) ++
    (if effects.mmioWrite then ["mmio-write"] else []) ++
    (if effects.ioOrder then ["io-order"] else []) ++
    (if effects.syncTrap then ["sync-trap"] else []) ++
    (if effects.machineState then ["machine-state"] else []) ++
    (if effects.timerState then ["timer-state"] else []) ++
    (if effects.interruptState then ["interrupt-state"] else []) ++
    (if effects.physicalRead then ["physical-read"] else []) ++
    (if effects.physicalWrite then ["physical-write"] else []) ++
    (if effects.virtualRead then ["virtual-read"] else []) ++
    (if effects.virtualWrite then ["virtual-write"] else []) ++
    (if effects.firmwareCall then ["firmware-call"] else []) ++
    (if effects.userSyscall then ["user-syscall"] else []) ++
    (if effects.addressSpace then ["address-space"] else []) ++
    (if effects.instructionSync then ["instruction-sync"] else []) ++
    (if effects.privilegeTransition then ["privilege-transition"] else []) ++
    (if effects.waitState then ["wait-state"] else []) ++
    (if effects.mayDiverge then ["may-diverge"] else [])
  "[" ++ String.intercalate "," names ++ "]"

end EffectSet

def executionEffects : Execution.Op → EffectSet
  | .physicalRead8 | .physicalRead64 => { checkedAccess := true, physicalRead := true }
  | .physicalWrite8 | .physicalWrite64 => { checkedAccess := true, physicalWrite := true }
  | .virtualRead8 | .virtualRead64 => { checkedAccess := true, virtualRead := true }
  | .virtualWrite8 | .virtualWrite64 => { checkedAccess := true, virtualWrite := true }
  | .readTime => .timerRead
  | .setMachineCompare => .timerWrite
  | .forwardSupervisor => { machineState := true, interruptState := true, ioOrder := true }
  | .firmwareCall => { firmwareCall := true, machineState := true, ioOrder := true }
  | .syscall => { userSyscall := true, privilegeTransition := true, ioOrder := true }
  | .installSatp => { machineState := true, addressSpace := true, ioOrder := true }
  | .fenceInstruction => { instructionSync := true, ioOrder := true }
  | .enterUser => { privilegeTransition := true, machineState := true, physicalRead := true }
  | .waitInterrupt => { waitState := true, interruptState := true }
  | .readSupervisorPending => { interruptState := true }
  | .deviceRead32 | .deviceRead64 => { checkedAccess := true, mmioRead := true, ioOrder := true }
  | .deviceWrite32 | .deviceWrite64 => { checkedAccess := true, mmioWrite := true, ioOrder := true }

  | .readMisa | .readMachineCycle | .writeMachineCycle | .readMachineRetired | .writeMachineRetired | .readMachineInhibit | .writeMachineInhibit | .readMachineCounterEnable | .writeMachineCounterEnable => { machineState := true }

structure ActionSignature where
  args : Array Ty
  deriving BEq, Inhabited, Repr

structure MemoryOpUse where
  access : MemoryAccess
  width? : Option Memory.Width
  range : Bool := false
  deriving BEq, Inhabited, Repr

namespace MemoryOpUse

def stableId (use : MemoryOpUse) : String :=
  if use.range then
    s!"ram.check-{use.access.render}-range"
  else
    s!"ram.{use.access.render}{use.width?.map Memory.Width.render |>.getD "?"}"

end MemoryOpUse

structure ActionIterationUse where
  stableId : String
  budget : Nat
  callback : Lean.Name
  deriving BEq, Inhabited, Repr

structure ActionLoopUse where
  stableId : String := "action.loop"
  callback : Lean.Name
  deriving BEq, Inhabited, Repr

def boundedFoldU64StableId : String := "action.u64.bounded-fold"

/-- Checked Action tree.  Every embedded value is ordinary checked scalar Core0 IR. -/
inductive ActionExpr where
  | done (status value : Expr)
  | bind (first : ActionExpr) (status value : Param) (next : ActionExpr)
  | load (width : Memory.Width) (region offset : Expr)
      (status value : Param) (next : ActionExpr)
  | store (width : Memory.Width) (region offset value : Expr)
      (status : Param) (next : ActionExpr)
  | checkRange (access : MemoryAccess) (region offset length : Expr)
      (status : Param) (next : ActionExpr)
  | ite (condition : Expr) (thenBranch elseBranch : ActionExpr)
  | call (callee : Lean.Name) (args : List Expr)
  | loop (callback : Lean.Name)
  | boundedFoldU64 (budget : Nat) (callback : Lean.Name)
      (count initial ctx0 ctx1 ctx2 ctx3 : Expr)
      (status value : Param) (next : ActionExpr)
  | uartReadStatus (status value : Param) (next : ActionExpr)
  | uartReadByte (status value : Param) (next : ActionExpr)
  | uartWriteByte (value : Expr) (status : Param) (next : ActionExpr)
  | uartEnableAndResetFifo (status : Param) (next : ActionExpr)
  | uartEnableAndResetFifo14 (status : Param) (next : ActionExpr)
  | trap (operation : Trap.Op) (status value : Param) (next : ActionExpr)
  | timer (operation : Timer.Op) (argument? : Option Expr)
      (status value : Param) (next : ActionExpr)
  | platform (operation : Execution.Op) (arguments : Array Expr)
      (status value : Param) (next : ActionExpr)
  deriving BEq, Inhabited, Repr

def ActionExpr.renderNormalized : ActionExpr → String
  | .done status value =>
      s!"(action.done {status.renderNormalized} {value.renderNormalized})"
  | .bind first status value next =>
      s!"(action.bind {first.renderNormalized} " ++
        s!"(status %{status.id}) (value %{value.id}) {next.renderNormalized})"
  | .load width region offset status value next =>
      s!"(action.load{width.render} {region.renderNormalized} {offset.renderNormalized} " ++
        s!"(status %{status.id}) (value %{value.id}) {next.renderNormalized})"
  | .store width region offset value status next =>
      s!"(action.store{width.render} {region.renderNormalized} {offset.renderNormalized} " ++
        s!"{value.renderNormalized} (status %{status.id}) {next.renderNormalized})"
  | .checkRange access region offset length status next =>
      s!"(action.check-{access.render}-range {region.renderNormalized} " ++
        s!"{offset.renderNormalized} {length.renderNormalized} " ++
        s!"(status %{status.id}) {next.renderNormalized})"
  | .ite condition thenBranch elseBranch =>
      s!"(action.ite {condition.renderNormalized} {thenBranch.renderNormalized} " ++
        s!"{elseBranch.renderNormalized})"
  | .call callee args =>
      let rendered := String.intercalate " " (args.map Expr.renderNormalized)
      s!"(action.call {callee} [{rendered}])"
  | .loop callback => s!"(action.loop callback={callback};repeat-status=0;return-nonzero-status-value)"
  | .boundedFoldU64 budget callback count initial ctx0 ctx1 ctx2 ctx3 status value next =>
      s!"(action.bounded-fold-u64 budget={budget} callback={callback} " ++
        s!"count={count.renderNormalized} initial={initial.renderNormalized} " ++
        s!"ctx=[{ctx0.renderNormalized} {ctx1.renderNormalized} " ++
        s!"{ctx2.renderNormalized} {ctx3.renderNormalized}] " ++
        s!"(status %{status.id}) (value %{value.id}) {next.renderNormalized})"
  | .uartReadStatus status value next =>
      s!"(action.uart-read-status (status %{status.id}) (value %{value.id}) " ++
        s!"{next.renderNormalized})"
  | .uartReadByte status value next =>
      s!"(action.uart-read-byte (status %{status.id}) (value %{value.id}) " ++
        s!"{next.renderNormalized})"
  | .uartWriteByte byte status next =>
      s!"(action.uart-write-byte {byte.renderNormalized} (status %{status.id}) " ++
        s!"{next.renderNormalized})"
  | .uartEnableAndResetFifo status next =>
      s!"(action.uart-enable-reset-fifo (status %{status.id}) {next.renderNormalized})"
  | .uartEnableAndResetFifo14 status next =>
      s!"(action.uart-enable-reset-fifo-trigger14 (status %{status.id}) {next.renderNormalized})"
  | .trap operation status value next =>
      s!"(action.trap {operation.stableId} (status %{status.id}) " ++
        s!"(value %{value.id}) {next.renderNormalized})"
  | .timer operation argument? status value next =>
      let argument := argument?.map Expr.renderNormalized |>.getD "none"
      s!"(action.timer {operation.stableId} (argument {argument}) " ++
        s!"(status %{status.id}) (value %{value.id}) {next.renderNormalized})"
  | .platform operation arguments status value next =>
      let rendered := String.intercalate " " (arguments.toList.map Expr.renderNormalized)
      s!"(action.platform {operation.stableId} [{rendered}] " ++
        s!"(status %{status.id}) (value %{value.id}) {next.renderNormalized})"

structure ActionFunction where
  name : Lean.Name
  signature : ActionSignature
  params : Array Param
  body : ActionExpr
  /-- Ordinary scalar dependencies, checked under the same selected Action profile. -/
  scalarDependencies : Array Lean.Name
  /-- Direct Action-returning calls, bounded-fold callbacks, and loop callbacks. -/
  actionDependencies : Array Lean.Name
  directEffects : EffectSet
  /-- Exact transitive closure over `actionDependencies`. -/
  effects : EffectSet
  deriving BEq, Inhabited, Repr

structure CheckedActionRoot where
  id : Nat
  source : Lean.Name
  signature : ActionSignature
  deriving BEq, Inhabited, Repr

structure CheckedActionSuite where
  contractVersion : String := "core0-v0.4"
  roots : Array CheckedActionRoot
  /-- Dependency-first ordinary scalar closure. -/
  scalarFunctions : Array Function
  /-- Dependency-first Action closure. -/
  actionFunctions : Array ActionFunction
  usedPrimitives : Array String
  usedIterations : Array IterationUse := #[]
  usedMemoryOps : Array MemoryOpUse
  usedActionIterations : Array ActionIterationUse := #[]
  usedLoops : Array ActionLoopUse := #[]
  /-- Exact closed v0.5 device identities, in first-use order. -/
  usedDeviceOps : Array Device.Op := #[]
  /-- Exact closed v0.6 synchronous-trap identities, in first-use order. -/
  usedTrapOps : Array Trap.Op := #[]
  /-- Exact closed v0.7 timer/interrupt identities, in first-use order. -/
  usedTimerOps : Array Timer.Op := #[]
  /-- Exact checked execution primitive signatures, not just friendly names. -/
  usedExecutionOps : Array Execution.OpSpec := #[]
  deriving BEq, Inhabited, Repr

def CheckedActionSuite.findActionFunction? (suite : CheckedActionSuite)
    (name : Lean.Name) : Option ActionFunction :=
  suite.actionFunctions.find? (fun function => function.name == name)

def CheckedActionSuite.findScalarFunction? (suite : CheckedActionSuite)
    (name : Lean.Name) : Option Function :=
  suite.scalarFunctions.find? (fun function => function.name == name)

end Lemma.Core0
