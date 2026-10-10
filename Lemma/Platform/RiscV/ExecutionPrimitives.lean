import Lemma.Machine.Primitives
import Lemma.Platform.LemmaVM.Layout
import Lemma.Core0.Timer
import Lemma.User.ABI

/-!
Closed integer machine boundary for the maintained kernel. Policy, page-table
construction, syscall validation and scheduling are compiled Lean algorithms.
This module generates only startup, privileged boundaries and context movement.
The historical M-mode monitor primitives are not imported.
-/

namespace Lemma.Platform.RiscV.ExecutionPrimitives

open Lemma.Machine.Primitives
open Lemma.Platform.LemmaVM

inductive Stage where
  | bootstrapM
  | supervisor
  deriving Repr, BEq

def Stage.stableId : Stage → String
  | .bootstrapM => "bootstrap-m"
  | .supervisor => "supervisor"

/-- Closed diagnostic startup selection. The origin probe remains in M-mode
and cannot be confused with an ordinary supervisor transfer. -/
inductive StartupCase where
  | normal
  | machineOriginProbe
  deriving Repr, BEq

def StartupCase.stableId : StartupCase → String
  | .normal => "normal"
  | .machineOriginProbe => "machine-origin-probe"

/-- Quarantined architectural user probes are independent of the M-origin
startup case. Ordinary user images select `none` and contain neither probe. -/
inductive UserStartupCase where
  | none
  | supervisorCsr
  | executeData
  | executeKernel
  | executeMisaligned
  | halfwordEcall
  | returnSupervisor
  | returnMachine
  deriving Repr, BEq

def UserStartupCase.stableId : UserStartupCase → String
  | .none => "none"
  | .supervisorCsr => "supervisor-csr"
  | .executeData => "execute-data"
  | .executeKernel => "execute-kernel"
  | .executeMisaligned => "execute-misaligned"
  | .halfwordEcall => "halfword-ecall"
  | .returnSupervisor => "return-supervisor"
  | .returnMachine => "return-machine"

structure Configuration where
  stage : Stage
  startupCase : StartupCase := .normal
  userStartupCase : UserStartupCase := .none
  kernelMain : String
  firmwareDispatcher : String := ""
  supervisorDispatcher : String := ""
  bootStateAddress : Nat := Layout.metadataBase
  lemmasim : Bool := false
  deriving Repr, BEq

def contextBytes : Nat := Layout.contextBytes
def registerOffset (register : Register) : Nat := register.number * 8
def savedPcOffset : Nat := 256
def savedStatusOffset : Nat := 264
def savedTranslationOrEnableOffset : Nat := 272
def savedKernelStackOffset : Nat := 280

private def ins (instruction : Instruction) : Line := .instruction instruction
private def label (name : String) : Line := .label name
private def offset (value : Nat) : Int := Int.ofNat value
private def registers : Array Register := Register.all.extract 1 32

/-- Only NAPOT intervals from the authoritative pinned layout enter PMP. -/
private def napot (base size : Nat) : Nat := base / 4 ||| (size / 8 - 1)

def pmpAddresses : Array (CSR × Nat) := #[
  (.pmpaddr0, napot Layout.firmwareBase (Layout.firmwareLimit - Layout.firmwareBase)),
  (.pmpaddr1, napot Layout.privateBase (Layout.privateLimit - Layout.privateBase)),
  (.pmpaddr2, napot Layout.ramBase (Layout.ramLimit - Layout.ramBase)),
  (.pmpaddr3, napot Layout.uartBase 0x100),
  (.pmpaddr4, napot Layout.finisherBase 0x1000)
]

/-- Lowest matching entries deny firmware storage to S/U; remaining admitted
RAM is RWX and only UART/finisher MMIO is granted. U permissions are PTE-owned.
Entries are unlocked, leaving the M substrate's own access independent. -/
def pmpConfiguration : Nat := 0x1b1b1f1818

/-- U ECALL and ordinary user faults enter S; S ECALL enters the private M ABI. -/
def exceptionDelegation : Nat := 0xb1ff
def interruptDelegation : Nat := 2

private def initializePmp (lemmasim : Bool) : Array Line := #[ins (.csrWrite .pmpcfg0 .zero)] ++
  (pmpAddresses ++ (if lemmasim then #[
    (.pmpaddr5, napot 0x0c000000 0x800000),
    (.pmpaddr6, napot 0x10001000 0x1000),
    (.pmpaddr7, napot 0x10010000 0x2000)] else #[] : Array (CSR × Nat))).flatMap (fun (csr, value) => #[
    ins (.loadImmediate .t0 value), ins (.csrWrite csr .t0)
  ]) ++ #[
    ins (.loadImmediate .t0 (if lemmasim then 0x1b1b1b1b1b1f1818 else pmpConfiguration)), ins (.csrWrite .pmpcfg0 .t0),
    ins .translationFenceAll
  ]

/-- Startup records are actual CSR readbacks, not assertions of the written
configuration. The allocator's metadata starts after this 128-byte record. -/
private def recordBootState (config : Configuration) : Array Line := #[
  ins (.loadImmediate .t0 config.bootStateAddress),
  ins (.storeDouble .s0 .t0 0), ins (.storeDouble .s1 .t0 8),
  ins (.loadImmediate .t1 (if config.stage == .supervisor then 1 else 0)),
  ins (.storeDouble .t1 .t0 16)
] ++ (#[
  (.pmpcfg0, 24), (.pmpaddr0, 32), (.pmpaddr1, 40), (.pmpaddr2, 48),
  (.pmpaddr3, 56), (.pmpaddr4, 64), (.medeleg, 72), (.mideleg, 80),
  (.mstatus, 88), (.satp, 96)
] : Array (CSR × Nat)).flatMap (fun (csr, slot) => #[
  ins (.csrRead .t1 csr), ins (.storeDouble .t1 .t0 (offset slot))
]) ++ (if config.lemmasim then
  (#[ (.pmpaddr5, 104), (.pmpaddr6, 112), (.pmpaddr7, 120) ] : Array (CSR × Nat)).flatMap
    (fun (csr, slot) => #[ins (.csrRead .t1 csr), ins (.storeDouble .t1 .t0 (offset slot))])
  else #[])

def startup (config : Configuration) : Array Line := #[
  label "_start",
  ins (.csrWrite .mie .zero), ins .maskMachineInterruptEnable,
  ins (.loadImmediate .t0 0x007e6600), ins (.csrClear .mstatus .t0),
  ins (.csrWrite .satp .zero), ins .translationFenceAll,
  ins (.csrWrite .mcounteren .zero), ins (.csrWrite .scounteren .zero),
  ins (.csrWrite .sie .zero), ins (.csrWrite .sscratch .zero),
  ins (.loadImmediate .sp Layout.supervisorStackTop),
  ins (.move .gp .zero), ins (.move .tp .zero),
  ins (.move .s0 .a0), ins (.move .s1 .a1),
  ins (.loadImmediate .t0 Layout.privateBase),
  ins (.storeDouble .zero .t0 0), ins (.storeDouble .zero .t0 8),
  ins (.loadAddress .t0 "__bss_start"), ins (.loadAddress .t1 "__bss_end"),
  label ".Llemma_clear_bss",
  ins (.branchGeUnsigned .t0 .t1 ".Llemma_boot_ready"),
  ins (.storeDouble .zero .t0 0), ins (.addImmediate .t0 .t0 8),
  ins (.jump ".Llemma_clear_bss"),
  label ".Llemma_boot_ready",
  ins (.loadAddress .t0 "__boot_hartid"),
  ins (.storeDouble .s0 .t0 0), ins (.storeDouble .s1 .t0 8),
  ins (.loadImmediate .t0 (UInt64.toNat Lemma.Core0.Timer.MachineTimer.compareAddress)),
  ins (.loadImmediate .t1 0xffffffffffffffff),
  ins .fenceIO, ins (.storeDouble .t1 .t0 0), ins .fenceIO
] ++ initializePmp config.lemmasim ++ #[
  ins (.loadImmediate .t0 exceptionDelegation), ins (.csrWrite .medeleg .t0),
  ins (.loadImmediate .t0 (if config.lemmasim then 514 else interruptDelegation)), ins (.csrWrite .mideleg .t0)
] ++ (if config.startupCase == .machineOriginProbe then #[
  ins (.loadAddress .t0 "lemma_machine_vector"), ins (.csrWrite .mtvec .t0),
  ins (.loadImmediate .t0 Layout.firmwareStackTop), ins (.csrWrite .mscratch .t0)
] else if config.stage == .supervisor then #[
  ins (.loadAddress .t0 "lemma_machine_vector"), ins (.csrWrite .mtvec .t0),
  ins (.loadImmediate .t0 Layout.firmwareStackTop), ins (.csrWrite .mscratch .t0),
  ins (.loadAddress .t0 "lemma_supervisor_vector"), ins (.csrWrite .stvec .t0),
  ins (.loadImmediate .t0 (if config.lemmasim then 514 else 2)), ins (.csrWrite .sie .t0),
  ins (.loadImmediate .t0 (if config.lemmasim then 0x282 else 0x82)), ins (.csrWrite .mie .t0),
  ins (.loadImmediate .t0 0x1baa), ins (.csrClear .mstatus .t0),
  ins (.loadImmediate .t0 0x800), ins (.csrSet .mstatus .t0)
] else #[]) ++ recordBootState config ++
  (if config.startupCase == .machineOriginProbe then #[
    ins (.loadImmediate .a0 0), ins (.loadImmediate .a1 0),
    ins (.loadImmediate .a2 0), ins (.loadImmediate .a3 0),
    ins (.loadImmediate .a4 0), ins (.loadImmediate .a5 0),
    ins (.loadImmediate .a6 0), ins (.loadImmediate .a7 3),
    ins .environmentCall,
    -- A returning call is a different failure from the compiled dispatcher's
    -- rejection, which enters lemma_machine_fatal and finisher status 48.
    label ".Llemma_machine_origin_returned",
    ins (.loadImmediate .t0 Layout.finisherBase),
    ins (.loadImmediate .t1 (52 * 65536 + 0x3333)),
    ins .fenceIO, ins (.storeWord .t1 .t0 0), ins .fenceIO,
    label ".Llemma_machine_origin_halt",
    ins (.jump ".Llemma_machine_origin_halt")
  ] else if config.stage == .supervisor then #[
    ins (.loadAddress .t0 "lemma_supervisor_start"), ins (.csrWrite .mepc .t0),
    ins .machineReturn
  ] else #[ins (.call config.kernelMain)]) ++ #[
    label ".Llemma_boot_halt", ins .waitForInterrupt,
    ins (.jump ".Llemma_boot_halt")
  ]

/-- MRET enters a supervisor-owned call boundary. A returning compiled Action
root therefore has a valid S return address and a controlled S-mode disposition. -/
def supervisorStart (config : Configuration) : Array Line := #[
  label "lemma_supervisor_start", ins (.call config.kernelMain),
  ins (.branchNeZero .a0 "lemma_supervisor_fatal"),
  label ".Llemma_supervisor_park", ins .waitForInterrupt,
  ins (.jump ".Llemma_supervisor_park")
]

private def saveContext (scratch : CSR) (doubleFault : String) : Array Line := #[
  ins (.csrReadWrite .sp scratch .sp),
  ins (.branchEqZero .sp doubleFault),
  ins (.addImmediate .sp .sp (-288)),
  ins (.storeDouble .zero .sp 0),
  ins (.storeDouble .t0 .sp 40),
  ins (.csrReadWrite .t0 scratch .zero),
  ins (.storeDouble .t0 .sp 16)
] ++ (registers.filter fun r => r != .sp && r != .t0).map
  (fun r => ins (.storeDouble r .sp (offset (registerOffset r)))) ++ #[
    ins (.addImmediate .t0 .sp 288), ins (.storeDouble .t0 .sp 280),
    ins (.move .gp .zero), ins (.move .tp .zero)
  ]

private def restoreRegisters (scratch : CSR) : Array Line :=
  (registers.filter fun r => r != .sp && r != .t0).map
    (fun r => ins (.loadDouble r .sp (offset (registerOffset r)))) ++ #[
      ins (.loadDouble .t0 .sp 280), ins (.csrWrite scratch .t0),
      ins (.loadDouble .t0 .sp 40), ins (.loadDouble .sp .sp 16)
    ]

def machineVector (config : Configuration) : Array Line :=
  #[label "lemma_machine_vector"] ++ saveContext .mscratch "lemma_machine_double_fault" ++
  (#[ (.mepc, 256), (.mstatus, 264), (.mie, 272) ] : Array (CSR × Nat)).flatMap
    (fun (csr, slot) => #[ins (.csrRead .t0 csr), ins (.storeDouble .t0 .sp (offset slot))]) ++ #[
      ins (.move .a0 .sp), ins (.csrRead .a1 .mcause), ins (.csrRead .a2 .mtval),
      ins (.call config.firmwareDispatcher),
      ins (.branchNeZero .a0 "lemma_machine_fatal"), ins (.move .sp .a1),
      ins (.loadDouble .t0 .sp 256), ins (.csrWrite .mepc .t0),
      ins (.loadDouble .t0 .sp 264), ins (.csrWrite .mstatus .t0),
      ins (.loadDouble .t0 .sp 272), ins (.csrWrite .mie .t0)
    ] ++ restoreRegisters .mscratch ++ #[ins .machineReturn]

private def supervisorRestore : Array Line := #[
  ins (.loadDouble .t0 .sp 272), ins (.csrWrite .satp .t0),
  ins .translationFenceAll,
  ins (.loadDouble .t0 .sp 256), ins (.csrWrite .sepc .t0),
  ins (.loadDouble .t0 .sp 264), ins (.csrWrite .sstatus .t0)
] ++ restoreRegisters .sscratch ++ #[ins .supervisorReturn]

def supervisorVector (config : Configuration) : Array Line :=
  #[label "lemma_supervisor_vector"] ++ saveContext .sscratch "lemma_supervisor_double_fault" ++
  (#[ (.sepc, 256), (.sstatus, 264), (.satp, 272) ] : Array (CSR × Nat)).flatMap
    (fun (csr, slot) => #[ins (.csrRead .t0 csr), ins (.storeDouble .t0 .sp (offset slot))]) ++ #[
      ins (.move .a0 .sp), ins (.csrRead .a1 .scause), ins (.csrRead .a2 .stval),
      ins (.call config.supervisorDispatcher),
      ins (.branchNeZero .a0 "lemma_supervisor_fatal"), ins (.move .sp .a1)
    ] ++ supervisorRestore

private def fatal (symbol halt : String) (status : Nat) : Array Line := #[
  label symbol, ins (.loadImmediate .t0 Layout.finisherBase),
  ins (.loadImmediate .t1 (status * 65536 + 0x3333)),
  ins .fenceIO, ins (.storeWord .t1 .t0 0), ins .fenceIO,
  label halt, ins (.jump halt)
]

def readTime : Array Line := #[
  label "lemma_exec_read_time", ins .fenceIO,
  ins (.loadImmediate .t0 (UInt64.toNat Lemma.Core0.Timer.MachineTimer.timeAddress)), ins (.loadDouble .a0 .t0 0),
  ins .fenceIO, ins .return
]

def setMachineCompare : Array Line := #[
  label "lemma_exec_set_machine_compare", ins .fenceIO,
  ins (.loadImmediate .t0 (UInt64.toNat Lemma.Core0.Timer.MachineTimer.compareAddress)), ins (.storeDouble .a0 .t0 0),
  ins .fenceIO, ins (.loadImmediate .a0 0), ins .return
]

def forwardSupervisor : Array Line := #[
  label "lemma_exec_forward_supervisor", ins .fenceIO,
  ins (.branchEqZero .a0 ".Llemma_clear_supervisor"),
  ins (.csrSetImmediate .mip 2), ins (.jump ".Llemma_forward_done"),
  label ".Llemma_clear_supervisor", ins (.csrClearImmediate .mip 2),
  label ".Llemma_forward_done", ins .fenceIO,
  ins (.loadImmediate .a0 0), ins .return
]

/-- The six-word function ABI is transported to the private/syscall register
ABI, preserving its real two-word result rather than fabricating status zero. -/
private def callBoundary (symbol : String) : Array Line := #[
  label symbol, ins (.move .a7 .a0),
  ins (.move .a0 .a1), ins (.move .a1 .a2), ins (.move .a2 .a3),
  ins (.move .a3 .a4), ins (.move .a4 .a5),
  ins .environmentCall, ins .return
]

def firmwareCall : Array Line := callBoundary "lemma_exec_firmware_call"
def syscall : Array Line := callBoundary "lemma_exec_syscall"

def installSatp : Array Line := #[
  label "lemma_exec_install_satp", ins (.csrWrite .satp .a0),
  ins .translationFenceAll, ins (.loadImmediate .a0 0), ins .return
]

def fenceInstruction : Array Line := #[
  label "lemma_exec_fence_instruction", ins .instructionFence,
  ins (.loadImmediate .a0 0), ins .return
]

/-- Suspend the S caller in fixed reserved storage before installing the U
context's address space. A trusted dispatcher may later select that exact
S frame, returning to the ordinary compiled caller with its original stack.

The caller holds SIE clear, validates the owned U frame and excludes overlap
with this storage. Only one caller may be suspended. Return status/value and
resource teardown remain compiled policy; the scalar primitive is returnable.
The temporary spill preserves t0/t1 before either is used as an address. -/
def enterUser : Array Line := #[
  label "lemma_exec_enter_user", ins (.addImmediate .sp .sp (-16)),
  ins (.storeDouble .t0 .sp 0), ins (.storeDouble .t1 .sp 8),
  ins (.loadImmediate .t0 Layout.kernelResumeContext),
  ins (.storeDouble .zero .t0 0)
] ++ (registers.filter fun r => r != .sp && r != .t0 && r != .t1).map
  (fun r => ins (.storeDouble r .t0 (offset (registerOffset r)))) ++ #[
  ins (.addImmediate .t1 .sp 16), ins (.storeDouble .t1 .t0 16),
  ins (.loadDouble .t1 .sp 0), ins (.storeDouble .t1 .t0 40),
  ins (.loadDouble .t1 .sp 8), ins (.storeDouble .t1 .t0 48),
  ins (.storeDouble .ra .t0 256),
  ins (.loadImmediate .t1 0x200000100), ins (.storeDouble .t1 .t0 264),
  ins (.csrRead .t1 .satp), ins (.storeDouble .t1 .t0 272),
  ins (.storeDouble .zero .t0 280),
  ins (.addImmediate .sp .sp 16), ins (.move .sp .a0)
] ++ supervisorRestore

def waitInterrupt : Array Line := #[
  label "lemma_exec_wait_interrupt", ins .waitForInterrupt,
  ins (.loadImmediate .a0 0), ins .return
]

/-- Observe the actual delegated software-pending bit while SIE may remain
clear. Return only its canonical 0/1 value, not unrelated interrupt state. -/
def supervisorPending : Array Line := #[
  label "lemma_exec_supervisor_pending", ins (.csrRead .a0 .sip),
  ins (.shiftRightImmediate .a0 .a0 1), ins (.andImmediate .a0 .a0 1),
  ins .return
]

def functions (config : Configuration) : Array (String × Array Line) := #[
  ("_start", startup config),
  ("core0_io_fence", #[label "core0_io_fence", ins .fenceIO, ins .return]),
  ("lemma_exec_read_time", readTime),
  ("lemma_exec_set_machine_compare", setMachineCompare),
  ("lemma_exec_forward_supervisor", forwardSupervisor),
  ("lemma_exec_firmware_call", firmwareCall), ("lemma_exec_syscall", syscall),
  ("lemma_exec_install_satp", installSatp),
  ("lemma_exec_fence_instruction", fenceInstruction),
  ("lemma_exec_enter_user", enterUser), ("lemma_exec_wait_interrupt", waitInterrupt),
  ("lemma_exec_supervisor_pending", supervisorPending),
  ("lemma_machine_fatal", fatal "lemma_machine_fatal" ".Llemma_m_fatal_halt" 48),
  ("lemma_machine_double_fault", fatal "lemma_machine_double_fault" ".Llemma_m_double_halt" 49),
  ("lemma_supervisor_fatal", fatal "lemma_supervisor_fatal" ".Llemma_s_fatal_halt" 50),
  ("lemma_supervisor_double_fault", fatal "lemma_supervisor_double_fault" ".Llemma_s_double_halt" 51)
] ++ (if config.startupCase == .machineOriginProbe then #[
  ("lemma_machine_vector", machineVector config)
] else if config.stage == .supervisor then #[
  ("lemma_supervisor_start", supervisorStart config),
  ("lemma_machine_vector", machineVector config),
  ("lemma_supervisor_vector", supervisorVector config)
] else #[])

private def validSymbol (symbol : String) : Bool :=
  !symbol.isEmpty && symbol.toList.all (fun c => c.isAlphanum || c == '_' || c == '.')

def Configuration.validate (config : Configuration) : Except String Unit := do
  unless Layout.valid do throw "authoritative machine layout is invalid"
  unless validSymbol config.kernelMain do throw "invalid compiled kernel entry symbol"
  if config.userStartupCase != .none then
    unless config.stage == .supervisor && config.startupCase == .normal do
      throw "architectural user probes require normal supervisor startup"
  if config.startupCase == .machineOriginProbe then
    unless config.stage == .bootstrapM do
      throw "machine-origin probe requires bootstrap-M stage"
    unless validSymbol config.firmwareDispatcher do
      throw "machine-origin probe requires a compiled firmware dispatcher symbol"
  if config.stage == .supervisor then
    unless validSymbol config.firmwareDispatcher && validSymbol config.supervisorDispatcher do
      throw "supervisor stage requires both compiled dispatcher symbols"
  unless config.bootStateAddress % 8 == 0 &&
      Layout.metadataBase ≤ config.bootStateAddress &&
      config.bootStateAddress + 128 ≤ Layout.metadataLimit do
    throw "boot-state record must be aligned and contained in kernel metadata"
  unless contextBytes % 16 == 0 && Layout.firmwareStackTop % 16 == 0 &&
      Layout.supervisorStackTop % 16 == 0 do
    throw "execution boundary stack/context alignment is invalid"

private def renderFunction (symbol : String) (lines : Array Line) : List String :=
  [".balign 4", s!".globl {symbol}", s!".type {symbol}, @function"] ++
    lines.toList.map Line.render ++ [s!".size {symbol}, . - {symbol}"]

def primitivePrivilege (symbol : String) : String :=
  if #["_start", "lemma_machine_vector", "lemma_machine_fatal",
      "lemma_machine_double_fault", "lemma_exec_read_time",
      "lemma_exec_set_machine_compare", "lemma_exec_forward_supervisor"].contains symbol then
    "M"
  else "S"

def primitiveEffect (symbol : String) : String :=
  if symbol == "_start" then "boot/privilege/pmp/delegation"
  else if symbol == "lemma_supervisor_start" then "boot-supervisor-entry"
  else if symbol == "lemma_machine_vector" then "machine-trap/context"
  else if symbol == "lemma_supervisor_vector" then "supervisor-trap/context"
  else if symbol.endsWith "fatal" || symbol.endsWith "double_fault" then "fatal-diagnostic"
  else if symbol == "lemma_exec_read_time" then "machine-timer-read"
  else if symbol == "lemma_exec_set_machine_compare" then "machine-timer-write"
  else if symbol == "lemma_exec_forward_supervisor" then "supervisor-notification"
  else if symbol == "lemma_exec_firmware_call" then "private-firmware-call"
  else if symbol == "lemma_exec_syscall" then "user-syscall"
  else if symbol == "lemma_exec_install_satp" then "address-space/invalidation"
  else if symbol == "lemma_exec_fence_instruction" then "instruction-synchronization"
  else if symbol == "lemma_exec_enter_user" then "sanitized-context-return"
  else if symbol == "lemma_exec_wait_interrupt" then "interrupt-wait"
  else if symbol == "lemma_exec_supervisor_pending" then "supervisor-notification-read"
  else "io-order"

/-- The exporter inventories these exact generated symbols/privileges/effects.
User image packaging changes syscall's execution privilege to U explicitly. -/
def primitiveCatalog (config : Configuration) : Array (String × String × String) :=
  (functions config).map fun (symbol, _) =>
    (symbol, primitivePrivilege symbol, primitiveEffect symbol)

def renderStartup (config : Configuration) : Except String String := do
  config.validate
  pure <| String.intercalate "\n" <|
    [".option push", ".option norelax", ".option norvc"] ++
    (functions config).toList.flatMap (fun (name, lines) =>
      [if primitivePrivilege name == "M" then ".section .text.firmware, \"ax\", @progbits"
       else ".section .text.platform, \"ax\", @progbits"] ++ renderFunction name lines) ++
    [".option pop", ".section .note.GNU-stack, \"\", @progbits", ""]

/-- Independent user links receive only the U ECALL transport, never firmware,
PMP, physical-memory, or supervisor-context instructions. -/
def renderUserSyscall : String := String.intercalate "\n" <|
  [".option push", ".option norelax", ".option norvc",
    ".section .text.user_boundary, \"ax\", @progbits"] ++
  renderFunction "lemma_exec_syscall" syscall ++
  [".option pop", ".section .note.GNU-stack, \"\", @progbits", ""]

/-- Exact architectural probe bodies, emitted only for their selected user
configuration. No Core0 source operation can request a privileged CSR. -/
def userAttackFunction : UserStartupCase → Option (String × Array Line)
  | .none => none
  | .supervisorCsr => some ("lemma_user_attack_supervisor_csr", #[
      label "lemma_user_attack_supervisor_csr",
      ins (.csrRead .a0 .sstatus), ins .return
    ])
  | .executeData => some ("lemma_user_attack_execute_data", #[
      label "lemma_user_attack_execute_data",
      ins (.loadImmediate .t0 0x20000), ins (.jumpRegisterZero .t0)
    ])
  | .executeKernel => some ("lemma_user_attack_kernel_fetch", #[
      label "lemma_user_attack_kernel_fetch",
      ins (.loadImmediate .t0 0x80200000), ins (.jumpRegisterZero .t0)
    ])
  | .executeMisaligned => some ("lemma_user_attack_misaligned", #[
      label "lemma_user_attack_misaligned",
      ins (.loadImmediate .t0 0x10002), ins (.jumpRegisterZero .t0)
    ])
  | .halfwordEcall => some ("lemma_user_attack_halfword_ecall", #[
      label "lemma_user_attack_halfword_ecall",
      ins (.loadAddress .t0 ".Llemma_user_halfword_ecall_pair"),
      ins (.addImmediate .t0 .t0 2), ins (.jumpRegisterZero .t0),
      -- ADDI zero,t1,7 encodes 0x00730013. Its upper halfword and the
      -- following fixed zero word form an ECALL at pair+2 on IALIGN16.
      label ".Llemma_user_halfword_ecall_pair",
      ins (.addImmediate .zero .t1 7), ins .zeroInstructionWord
    ])
  | .returnSupervisor => some ("lemma_user_attack_supervisor_return", #[
      label "lemma_user_attack_supervisor_return", ins .supervisorReturn
    ])
  | .returnMachine => some ("lemma_user_attack_machine_return", #[
      label "lemma_user_attack_machine_return", ins .machineReturn
    ])

def userPrimitiveCatalog (userCase : UserStartupCase := .none) :
    Array (String × String × String) := #[
  ("_user_start", "U", "user-entry/exit"),
  ("lemma_exec_syscall", "U", "user-syscall")
] ++ (match userCase with
  | .none => #[]
  | .supervisorCsr => #[
      ("lemma_user_attack_supervisor_csr", "U", "adversarial-supervisor-csr-read")]
  | .executeData => #[
      ("lemma_user_attack_execute_data", "U", "adversarial-nx-fetch")]
  | .executeKernel => #[
      ("lemma_user_attack_kernel_fetch", "U", "adversarial-kernel-fetch")]
  | .executeMisaligned => #[
      ("lemma_user_attack_misaligned", "U", "adversarial-illegal-halfword-fetch")]
  | .halfwordEcall => #[
      ("lemma_user_attack_halfword_ecall", "U", "adversarial-halfword-ecall")]
  | .returnSupervisor => #[
      ("lemma_user_attack_supervisor_return", "U", "adversarial-supervisor-return")]
  | .returnMachine => #[
      ("lemma_user_attack_machine_return", "U", "adversarial-machine-return")])

private def userExit : Array Line := #[
    ins (.loadImmediate .a1 0), ins (.loadImmediate .a2 0),
    ins (.loadImmediate .a3 0), ins (.loadImmediate .a4 0),
    ins (.loadImmediate .a5 0), ins (.loadImmediate .a6 0),
    ins (.loadImmediate .a7 (UInt64.toNat Lemma.User.ABI.exit)),
    ins .environmentCall,
    label ".Luser_exit_returned", ins (.jump ".Luser_exit_returned")
  ]

/-- The independently linked Action root receives its scalar argument on a
sanitized user stack. Ordinary startup is byte-identical to the initial user
boundary. A selected probe first requires that genuine compiled root to return
status zero; failed preconditions exit normally and cannot count as a probe.
Exit must not return; a returning kernel leaves a local preemptible user loop. -/
def renderUserStartup (root : String) (userCase : UserStartupCase := .none) :
    Except String String := do
  unless validSymbol root do throw "invalid compiled user entry symbol"
  let entry : Array Line := (match userAttackFunction userCase with
    | none => #[label "_user_start", ins (.call root)]
    | some (attack, _) => #[
        label "_user_start", ins (.move .gp .zero), ins (.move .tp .zero),
        ins (.call root), ins (.branchNeZero .a0 ".Luser_exit"),
        ins (.call attack), label ".Luser_exit"
      ]) ++ userExit
  let attackSection := match userAttackFunction userCase with
    | none => []
    | some (name, lines) =>
      [".section .text.user_adversarial, \"ax\", @progbits"] ++
      renderFunction name lines
  pure <| String.intercalate "\n" <|
    [".option push", ".option norelax", ".option norvc",
      ".section .text.user_start, \"ax\", @progbits"] ++
    renderFunction "_user_start" entry ++
    [".section .text.user_boundary, \"ax\", @progbits"] ++
    renderFunction "lemma_exec_syscall" syscall ++ attackSection ++
    -- Declarative initial data shared by every independently linked image.
    -- The linker places this 16-byte section at the declared data VA 0x20000;
    -- the loader must copy the nonzero ABI word and zero the remaining BSS.
    [".section .data.user_abi, \"aw\", @progbits", ".balign 8",
      ".quad 0", s!".quad {Lemma.User.ABI.version}"] ++
    [".option pop", ".section .note.GNU-stack, \"\", @progbits", ""]

end Lemma.Platform.RiscV.ExecutionPrimitives
