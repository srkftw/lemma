import Lemma.Core0.IR
import Lemma.Platform.LemmaVM.Layout

/-! Closed privilege-specific operations for the first freestanding kernel and user
profiles. The catalog is shared by checking, lowering and artifact provenance.
It is not a generic extern, CSR or physical-address escape hatch. -/

namespace Lemma.Core0.Execution

inductive Op where
  | physicalRead8 | physicalRead64 | physicalWrite8 | physicalWrite64
  | virtualRead8 | virtualRead64 | virtualWrite8 | virtualWrite64
  | readTime | setMachineCompare | forwardSupervisor
  | firmwareCall | syscall | installSatp | fenceInstruction | enterUser | waitInterrupt
  | readSupervisorPending
  | deviceRead32 | deviceWrite32 | deviceRead64 | deviceWrite64

  | readMisa | readMachineCycle | writeMachineCycle | readMachineRetired | writeMachineRetired | readMachineInhibit | writeMachineInhibit | readMachineCounterEnable | writeMachineCounterEnable
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Op

def all : Array Op := #[
  .physicalRead8, .physicalRead64, .physicalWrite8, .physicalWrite64,
  .virtualRead8, .virtualRead64, .virtualWrite8, .virtualWrite64,
  .readTime, .setMachineCompare, .forwardSupervisor, .firmwareCall, .syscall,
  .installSatp, .fenceInstruction, .enterUser, .waitInterrupt, .readSupervisorPending,
  .deviceRead32, .deviceWrite32, .deviceRead64, .deviceWrite64,
  .readMisa, .readMachineCycle, .writeMachineCycle, .readMachineRetired, .writeMachineRetired, .readMachineInhibit, .writeMachineInhibit, .readMachineCounterEnable, .writeMachineCounterEnable]

def stableId : Op → String
  | .physicalRead8 => "execution.physical-read8"
  | .physicalRead64 => "execution.physical-read64"
  | .physicalWrite8 => "execution.physical-write8"
  | .physicalWrite64 => "execution.physical-write64"
  | .virtualRead8 => "execution.virtual-read8"
  | .virtualRead64 => "execution.virtual-read64"
  | .virtualWrite8 => "execution.virtual-write8"
  | .virtualWrite64 => "execution.virtual-write64"
  | .readTime => "execution.read-time"
  | .setMachineCompare => "execution.set-machine-compare"
  | .forwardSupervisor => "execution.forward-supervisor"
  | .firmwareCall => "execution.firmware-call"
  | .syscall => "execution.syscall"
  | .installSatp => "execution.install-satp"
  | .fenceInstruction => "execution.fence-instruction"
  | .enterUser => "execution.enter-user"
  | .waitInterrupt => "execution.wait-interrupt"
  | .readSupervisorPending => "execution.supervisor-pending"
  | .deviceRead32 => "lemmasim.device-read32"
  | .deviceWrite32 => "lemmasim.device-write32"
  | .deviceRead64 => "lemmasim.device-read64"
  | .deviceWrite64 => "lemmasim.device-write64"
  | .readMisa => "execution.read-misa"
  | .readMachineCycle => "execution.read-machine-cycle"
  | .writeMachineCycle => "execution.write-machine-cycle"
  | .readMachineRetired => "execution.read-machine-retired"
  | .writeMachineRetired => "execution.write-machine-retired"
  | .readMachineInhibit => "execution.read-machine-inhibit"
  | .writeMachineInhibit => "execution.write-machine-inhibit"
  | .readMachineCounterEnable => "execution.read-machine-counter-enable"
  | .writeMachineCounterEnable => "execution.write-machine-counter-enable"

def sourceIdentity : Op → Lean.Name
  | .physicalRead8 => ``Op.physicalRead8
  | .physicalRead64 => ``Op.physicalRead64
  | .physicalWrite8 => ``Op.physicalWrite8
  | .physicalWrite64 => ``Op.physicalWrite64
  | .virtualRead8 => ``Op.virtualRead8
  | .virtualRead64 => ``Op.virtualRead64
  | .virtualWrite8 => ``Op.virtualWrite8
  | .virtualWrite64 => ``Op.virtualWrite64
  | .readTime => ``Op.readTime
  | .setMachineCompare => ``Op.setMachineCompare
  | .forwardSupervisor => ``Op.forwardSupervisor
  | .firmwareCall => ``Op.firmwareCall
  | .syscall => ``Op.syscall
  | .installSatp => ``Op.installSatp
  | .fenceInstruction => ``Op.fenceInstruction
  | .enterUser => ``Op.enterUser
  | .waitInterrupt => ``Op.waitInterrupt
  | .readSupervisorPending => ``Op.readSupervisorPending
  | .deviceRead32 => ``Op.deviceRead32
  | .deviceWrite32 => ``Op.deviceWrite32
  | .deviceRead64 => ``Op.deviceRead64
  | .deviceWrite64 => ``Op.deviceWrite64
  | .readMisa => ``Op.readMisa
  | .readMachineCycle => ``Op.readMachineCycle
  | .writeMachineCycle => ``Op.writeMachineCycle
  | .readMachineRetired => ``Op.readMachineRetired
  | .writeMachineRetired => ``Op.writeMachineRetired
  | .readMachineInhibit => ``Op.readMachineInhibit
  | .writeMachineInhibit => ``Op.writeMachineInhibit
  | .readMachineCounterEnable => ``Op.readMachineCounterEnable
  | .writeMachineCounterEnable => ``Op.writeMachineCounterEnable

def ofSourceIdentity? (name : Lean.Name) : Option Op :=
  all.find? fun operation => operation.sourceIdentity == name

def widthBytes? : Op → Option Nat
  | .physicalRead8 | .physicalWrite8 | .virtualRead8 | .virtualWrite8 => some 1
  | .physicalRead64 | .physicalWrite64 | .virtualRead64 | .virtualWrite64 => some 8
  | .deviceRead32 | .deviceWrite32 => some 4
  | .deviceRead64 | .deviceWrite64 => some 8
  | _ => none

def isWrite : Op → Bool
  | .physicalWrite8 | .physicalWrite64 | .virtualWrite8 | .virtualWrite64 => true
  | .deviceWrite32 | .deviceWrite64 => true
  | .writeMachineCycle | .writeMachineRetired | .writeMachineInhibit | .writeMachineCounterEnable => true
  | _ => false

def isPhysical : Op → Bool
  | .physicalRead8 | .physicalRead64 | .physicalWrite8 | .physicalWrite64 => true
  | _ => false

def admits (profile : Profile) (operation : Op) : Bool :=
  match operation with
  | .physicalRead8 | .physicalRead64 | .physicalWrite8 | .physicalWrite64 =>
      profile.isFirmware || profile.isKernel
  | .virtualRead8 | .virtualRead64 | .virtualWrite8 | .virtualWrite64 | .syscall =>
      profile == .user_v0_1
  | .readTime | .setMachineCompare | .forwardSupervisor => profile.isFirmware
  | .firmwareCall | .installSatp | .fenceInstruction | .enterUser | .waitInterrupt |
      .readSupervisorPending =>
      profile.isKernel
  | .deviceRead32 | .deviceWrite32 | .deviceRead64 | .deviceWrite64 =>
      profile == .kernel_v0_3 || profile == .kernel_v0_4

  | .readMisa | .readMachineCycle | .writeMachineCycle | .readMachineRetired | .writeMachineRetired | .readMachineInhibit | .writeMachineInhibit | .readMachineCounterEnable | .writeMachineCounterEnable => profile == .firmware_v0_2

/-- Number of meaningful source operands; the remaining six-word slots must be
literal zero. Firmware/syscall operands are number followed by five payloads. -/
def argumentCount : Op → Nat
  | .physicalWrite8 | .physicalWrite64 | .virtualWrite8 | .virtualWrite64 => 2
  | .deviceWrite32 | .deviceWrite64 => 2
  | .deviceRead32 | .deviceRead64 => 1
  | .physicalRead8 | .physicalRead64 | .virtualRead8 | .virtualRead64 |
      .setMachineCompare | .installSatp | .enterUser => 1
  | .forwardSupervisor => 1
  | .writeMachineCycle | .writeMachineRetired | .writeMachineInhibit | .writeMachineCounterEnable => 1
  | .firmwareCall | .syscall => 6
  | _ => 0

def primitiveSymbol? : Op → Option String
  | .readTime => some "lemma_exec_read_time"
  | .setMachineCompare => some "lemma_exec_set_machine_compare"
  | .forwardSupervisor => some "lemma_exec_forward_supervisor"
  | .firmwareCall => some "lemma_exec_firmware_call"
  | .syscall => some "lemma_exec_syscall"
  | .installSatp => some "lemma_exec_install_satp"
  | .fenceInstruction => some "lemma_exec_fence_instruction"
  | .enterUser => some "lemma_exec_enter_user"
  | .waitInterrupt => some "lemma_exec_wait_interrupt"
  | .readSupervisorPending => some "lemma_exec_supervisor_pending"
  | .readMisa => some "lemma_exec_read_misa"
  | .readMachineCycle => some "lemma_exec_read_machine_cycle"
  | .writeMachineCycle => some "lemma_exec_write_machine_cycle"
  | .readMachineRetired => some "lemma_exec_read_machine_retired"
  | .writeMachineRetired => some "lemma_exec_write_machine_retired"
  | .readMachineInhibit => some "lemma_exec_read_machine_inhibit"
  | .writeMachineInhibit => some "lemma_exec_write_machine_inhibit"
  | .readMachineCounterEnable => some "lemma_exec_read_machine_counter_enable"
  | .writeMachineCounterEnable => some "lemma_exec_write_machine_counter_enable"
  | _ => none

end Op

/-- Device accesses are separate from ordinary physical RAM authority. The
fixed catalog admits only the selected controller register widths. -/
def Op.isDevice (op : Op) : Bool :=
  op == .deviceRead32 || op == .deviceWrite32 || op == .deviceRead64 || op == .deviceWrite64

inductive ResultKind where
  | word | checked
  deriving BEq, DecidableEq, Inhabited, Repr

structure OpSpec where
  operation : Op
  sourceIdentity : Lean.Name
  stableId : String
  sourceArguments : Array Ty
  meaningfulArguments : Nat
  primitiveSymbol? : Option String
  machineArguments : Array Ty
  result : Ty := .u64
  resultKind : ResultKind
  widthBytes? : Option Nat
  write : Bool
  physical : Bool
  deriving BEq, Inhabited, Repr

def specification (operation : Op) : OpSpec := {
  operation
  sourceIdentity := operation.sourceIdentity
  stableId := operation.stableId
  sourceArguments := Array.replicate 6 .u64
  meaningfulArguments := operation.argumentCount
  primitiveSymbol? := operation.primitiveSymbol?
  machineArguments := if operation.primitiveSymbol?.isSome then
    Array.replicate operation.argumentCount .u64 else #[]
  resultKind := if operation == .firmwareCall || operation == .syscall then .checked else .word
  widthBytes? := operation.widthBytes?
  write := operation.isWrite
  physical := operation.isPhysical
}

def opCatalog : Array OpSpec := Op.all.map specification

def Op.spec (operation : Op) : OpSpec := specification operation

def findSpec? (operation : Op) : Option OpSpec :=
  opCatalog.find? fun spec => spec.operation == operation

def catalogValid : Bool :=
  opCatalog.size == Op.all.size && opCatalog.all fun spec =>
    spec == specification spec.operation && spec.meaningfulArguments ≤ 6 &&
      (spec.widthBytes?.isSome != spec.primitiveSymbol?.isSome)

/-- Half-open accessible intervals. These are compiler authority bounds; kernel
ownership checks and hardware mappings impose the stronger runtime policy. -/
structure MemoryRegion where
  name : String
  start : Nat
  stop : Nat
  writable : Bool
  deriving BEq, Inhabited, Repr

def deviceRegions (operation : Op) : Array MemoryRegion :=
  if operation == .deviceRead32 || operation == .deviceWrite32 then #[
    ⟨"virtio-block", 0x10001000, 0x10001200, true⟩,
    ⟨"plic-priority", 0x0c000004, 0x0c000038, true⟩,
    ⟨"plic-s-enable", 0x0c002080, 0x0c002084, true⟩,
    ⟨"plic-s-context", 0x0c201000, 0x0c201008, true⟩]
  else if operation == .deviceRead64 || operation == .deviceWrite64 then #[
    ⟨"paper-controller", 0x10010000, 0x10011000, true⟩,
    ⟨"pen-controller", 0x10011000, 0x10012000, true⟩]
  else #[]

/-- Additive Power-v1 authority: only kernel-v0.4 can address PLIC priority14.
No other device interval or language operation changes; historical callers
continue to use deviceRegions and the same exact exclusive priority bound. -/
def deviceRegionsFor (profile : Profile) (operation : Op) : Array MemoryRegion :=
  if profile == .kernel_v0_4 then
    (deviceRegions operation).map fun region =>
      if region.name == "plic-priority" then { region with stop := 0x0c00003c } else region
  else deviceRegions operation

def kernelMemoryRegions : Array MemoryRegion := #[
      ⟨"kernel-image", Lemma.Platform.LemmaVM.Layout.supervisorBase,
        Lemma.Platform.LemmaVM.Layout.supervisorLimit, false⟩,
      ⟨"kernel-metadata", Lemma.Platform.LemmaVM.Layout.metadataBase,
        Lemma.Platform.LemmaVM.Layout.metadataLimit, true⟩,
      ⟨"kernel-boot-stack", Lemma.Platform.LemmaVM.Layout.supervisorStackBase,
        Lemma.Platform.LemmaVM.Layout.supervisorStackTop, true⟩,
      ⟨"boot-package", Lemma.Platform.LemmaVM.Layout.packageBase,
        Lemma.Platform.LemmaVM.Layout.packageLimit, false⟩,
      ⟨"owned-frame-pool", Lemma.Platform.LemmaVM.Layout.poolBase,
        Lemma.Platform.LemmaVM.Layout.poolLimit, true⟩,
      ⟨"boot-dtb", Lemma.Platform.LemmaVM.Layout.dtbReserveBase,
        Lemma.Platform.LemmaVM.Layout.dtbReserveLimit, false⟩]

def memoryRegions : Profile → Array MemoryRegion
  | .firmware_v0_1 | .firmware_v0_2 => #[⟨"firmware-storage", Lemma.Platform.LemmaVM.Layout.privateBase,
      Lemma.Platform.LemmaVM.Layout.privateLimit, true⟩]
  | .kernel_v0_1 | .kernel_v0_2 => kernelMemoryRegions
  | .kernel_v0_3 | .kernel_v0_4 => kernelMemoryRegions.map fun region =>
      if region.name == "owned-frame-pool" then { region with stop := 0x84000000 } else region
  | .user_v0_1 => #[⟨"user-virtual-domain", 0x10000, 0x40000000, true⟩]
  | _ => #[]

def memoryRegionsValid (profile : Profile) : Bool :=
  Lemma.Platform.LemmaVM.Layout.valid && profile.isExecution && !(memoryRegions profile).isEmpty &&
    (memoryRegions profile).all fun region =>
      region.start < region.stop && region.stop ≤ 2 ^ 64 &&
        region.start % 4096 == 0 && region.stop % 4096 == 0

end Lemma.Core0.Execution
