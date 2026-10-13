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
  | readCounterCycle | readCounterTime | readCounterRetired | readSupervisorCounterEnable | writeSupervisorCounterEnable | attemptWriteCounterCycle | attemptWriteCounterTime | attemptWriteCounterRetired | counterEnterSupervisor | counterEnterUser
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Op

def all : Array Op := #[
  .physicalRead8, .physicalRead64, .physicalWrite8, .physicalWrite64,
  .virtualRead8, .virtualRead64, .virtualWrite8, .virtualWrite64,
  .readTime, .setMachineCompare, .forwardSupervisor, .firmwareCall, .syscall,
  .installSatp, .fenceInstruction, .enterUser, .waitInterrupt, .readSupervisorPending,
  .deviceRead32, .deviceWrite32, .deviceRead64, .deviceWrite64,
  .readMisa, .readMachineCycle, .writeMachineCycle, .readMachineRetired, .writeMachineRetired, .readMachineInhibit, .writeMachineInhibit, .readMachineCounterEnable, .writeMachineCounterEnable,
  .readCounterCycle, .readCounterTime, .readCounterRetired, .readSupervisorCounterEnable, .writeSupervisorCounterEnable, .attemptWriteCounterCycle, .attemptWriteCounterTime, .attemptWriteCounterRetired, .counterEnterSupervisor, .counterEnterUser]

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
  | .readCounterCycle => "execution.read-counter-cycle"
  | .readCounterTime => "execution.read-counter-time"
  | .readCounterRetired => "execution.read-counter-retired"
  | .readSupervisorCounterEnable => "execution.read-supervisor-counter-enable"
  | .writeSupervisorCounterEnable => "execution.write-supervisor-counter-enable"
  | .attemptWriteCounterCycle => "execution.attempt-write-counter-cycle"
  | .attemptWriteCounterTime => "execution.attempt-write-counter-time"
  | .attemptWriteCounterRetired => "execution.attempt-write-counter-retired"
  | .counterEnterSupervisor => "execution.counter-enter-supervisor"
  | .counterEnterUser => "execution.counter-enter-user"

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
  | .readCounterCycle => ``Op.readCounterCycle
  | .readCounterTime => ``Op.readCounterTime
  | .readCounterRetired => ``Op.readCounterRetired
  | .readSupervisorCounterEnable => ``Op.readSupervisorCounterEnable
  | .writeSupervisorCounterEnable => ``Op.writeSupervisorCounterEnable
  | .attemptWriteCounterCycle => ``Op.attemptWriteCounterCycle
  | .attemptWriteCounterTime => ``Op.attemptWriteCounterTime
  | .attemptWriteCounterRetired => ``Op.attemptWriteCounterRetired
  | .counterEnterSupervisor => ``Op.counterEnterSupervisor
  | .counterEnterUser => ``Op.counterEnterUser

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
  | .writeSupervisorCounterEnable | .attemptWriteCounterCycle | .attemptWriteCounterTime | .attemptWriteCounterRetired => true
  | _ => false

def isPhysical : Op → Bool
  | .physicalRead8 | .physicalRead64 | .physicalWrite8 | .physicalWrite64 => true
  | _ => false

def admits (profile : Profile) (operation : Op) : Bool :=
  match operation with
  | .physicalRead8 | .physicalRead64 | .physicalWrite8 | .physicalWrite64 =>
      profile.isFirmware || profile.isKernel || profile.isBoot
  | .virtualRead8 | .virtualRead64 | .virtualWrite8 | .virtualWrite64 | .syscall =>
      profile.isUser
  | .readTime | .setMachineCompare | .forwardSupervisor => profile.isFirmware
  | .firmwareCall | .installSatp | .fenceInstruction | .enterUser | .waitInterrupt |
      .readSupervisorPending =>
      profile.isKernel
  | .deviceRead32 | .deviceWrite32 =>
      profile == .kernel_v0_3 || profile == .kernel_v0_4 || profile == .kernel_v0_5 || profile == .kernel_v0_6 || profile == .kernel_v0_7
  | .deviceRead64 | .deviceWrite64 =>
      profile == .kernel_v0_3 || profile == .kernel_v0_4 || profile == .kernel_v0_6 || profile == .kernel_v0_7 || profile == .kernel_v0_5 || profile.isBoot

  | .readMisa | .readMachineCycle | .writeMachineCycle | .readMachineRetired | .writeMachineRetired | .readMachineInhibit | .writeMachineInhibit | .readMachineCounterEnable | .writeMachineCounterEnable => profile == .firmware_v0_2 || profile == .counter_su_v0_1

  | .readCounterCycle | .readCounterTime | .readCounterRetired | .readSupervisorCounterEnable | .writeSupervisorCounterEnable | .attemptWriteCounterCycle | .attemptWriteCounterTime | .attemptWriteCounterRetired | .counterEnterSupervisor | .counterEnterUser => profile == .counter_su_v0_1

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
  | .writeSupervisorCounterEnable | .attemptWriteCounterCycle | .attemptWriteCounterTime | .attemptWriteCounterRetired => 1
  | .counterEnterSupervisor | .counterEnterUser => 2
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
  | .readCounterCycle => some "lemma_exec_read_counter_cycle"
  | .readCounterTime => some "lemma_exec_read_counter_time"
  | .readCounterRetired => some "lemma_exec_read_counter_retired"
  | .readSupervisorCounterEnable => some "lemma_exec_read_supervisor_counter_enable"
  | .writeSupervisorCounterEnable => some "lemma_exec_write_supervisor_counter_enable"
  | .attemptWriteCounterCycle => some "lemma_exec_attempt_write_counter_cycle"
  | .attemptWriteCounterTime => some "lemma_exec_attempt_write_counter_time"
  | .attemptWriteCounterRetired => some "lemma_exec_attempt_write_counter_retired"
  | .counterEnterSupervisor => some "lemma_exec_counter_enter_supervisor"
  | .counterEnterUser => some "lemma_exec_counter_enter_user"
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

/-- Additive interrupt authority: kernel-v0.4 addresses priority14 and
kernel-v0.5 also addresses priority15; kernel-v0.6 additionally addresses priority16. Every other interval and operation
retains its inherited semantics and exact exclusive bounds. -/
def deviceRegionsFor (profile : Profile) (operation : Op) : Array MemoryRegion :=
  if profile.isBoot then
    if operation == .deviceRead64 || operation == .deviceWrite64 then
      #[⟨"boot-nv-controller", 0x10012000, 0x10012400, true⟩]
    else #[]
  else if profile == .kernel_v0_7 then
    let inherited := (deviceRegions operation).map fun region =>
      if region.name == "plic-priority" then { region with stop := 0x0c000048 } else region
    if operation == .deviceRead64 || operation == .deviceWrite64 then
      inherited.push ⟨"boot-nv-controller", 0x10012000, 0x10012400, true⟩
    else inherited
  else if profile == .kernel_v0_6 then
    (deviceRegions operation).map fun region =>
      if region.name == "plic-priority" then { region with stop := 0x0c000044 } else region
  else if profile == .kernel_v0_5 then
    (deviceRegions operation).map fun region =>
      if region.name == "plic-priority" then { region with stop := 0x0c000040 } else region
  else if profile == .kernel_v0_4 then
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
  | .boot_v0_1 => #[
      ⟨"boot-loaded-image", 0x80000000, 0x81f00000, true⟩,
      ⟨"boot-private-scratch", 0x81fc0000, 0x81fc4000, true⟩,
      ⟨"boot-loaded-discovery", 0x87e00000, 0x87e00c00, true⟩]
  | .firmware_v0_1 | .firmware_v0_2 | .counter_su_v0_1 => #[⟨"firmware-storage", Lemma.Platform.LemmaVM.Layout.privateBase,
      Lemma.Platform.LemmaVM.Layout.privateLimit, true⟩]
  | .kernel_v0_1 | .kernel_v0_2 => kernelMemoryRegions
  | .kernel_v0_7 =>
      (kernelMemoryRegions.map fun region =>
        if region.name == "owned-frame-pool" then { region with stop := 0x84000000 } else region).push
        ⟨"boot-private-scratch", 0x81fc0000, 0x81fc4000, true⟩
  | .kernel_v0_3 | .kernel_v0_4 | .kernel_v0_5 | .kernel_v0_6 => kernelMemoryRegions.map fun region =>
      if region.name == "owned-frame-pool" then { region with stop := 0x84000000 } else region
  | .user_v0_1 | .user_v0_2 | .user_v0_3 | .user_v0_4 | .user_v0_5 | .user_v0_6 => #[⟨"user-virtual-domain", 0x10000, 0x40000000, true⟩]
  | _ => #[]

def memoryRegionsValid (profile : Profile) : Bool :=
  Lemma.Platform.LemmaVM.Layout.valid && profile.isExecution && !(memoryRegions profile).isEmpty &&
    (memoryRegions profile).all fun region =>
      region.start < region.stop && region.stop ≤ 2 ^ 64 &&
        region.start % 4096 == 0 && (region.stop % 4096 == 0 ||
          (profile.isBoot && region.name == "boot-loaded-discovery" &&
            region.start == 0x87e00000 && region.stop == 0x87e00c00 && region.writable))

end Lemma.Core0.Execution
