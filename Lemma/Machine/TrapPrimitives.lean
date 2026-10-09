import Lemma.Machine.Primitives
import Lemma.Machine.TrapLayout

/-!
Structured, integer-only M-mode trap entry/return and target sentinel probes.

The substrate is single-hart and initially non-nested.  `mscratch` holds the
dedicated trap-stack top while foreground code runs and zero while dispatch is
active.  The entry/tail presume their fixed RAM and CSR accesses do not fault;
there is no NMI claim.  A trap observed while the zero latch is active takes a
stackless fatal path.  Sentinel probes are deliberately non-reentrant test
primitives, with a private fixed caller-context anchor.
-/

namespace Lemma.Machine.TrapPrimitives

open Lemma.Machine.Primitives

inductive RestoreMutation where
  | none
  | restoreS3FromS4
  deriving Repr, BEq, Inhabited

def RestoreMutation.stableId : RestoreMutation → String
  | .none => "none"
  | .restoreS3FromS4 => "restore-s3-from-s4"

structure Configuration where
  dispatcher : String
  mutation : RestoreMutation := .none
  deriving Repr, BEq

def frameOffset (register : Register) : Nat := (register.number - 1) * 8

def sentinelValue (register : Register) : Nat :=
  if register == .sp then trapLayout.probeSp
  else 0x3753000000000000 + register.number * 0x10001

def preservedRegisters : Array Register := Register.all.extract 1 32

private def ins (instruction : Instruction) : Line := .instruction instruction

private def label (name : String) : Line := .label name

private def asOffset (value : Nat) : Int := Int.ofNat value

def initializeCanaries : Array Line := trapLayout.canaries.flatMap fun canary => #[
  ins (.loadImmediate .t0 canary.address),
  ins (.loadImmediate .t1 canary.value),
  ins (.storeDouble .t1 .t0 0),
  ins (.loadImmediate .t1 (canary.value + 1)),
  ins (.storeDouble .t1 .t0 8)
]

/-- Separate startup; the historical `Primitives.renderStartup` is untouched. -/
def startup : Array Line := #[
  label "_start",
  ins (.csrWrite .mie .zero),
  ins .maskMachineInterruptEnable,
  ins (.loadAddress .sp "__stack_top"),
  ins (.move .s0 .a0),
  ins (.move .s1 .a1),
  ins (.loadAddress .t0 "__bss_start"),
  ins (.loadAddress .t1 "__bss_end"),
  label ".Ltrap_clear_bss",
  ins (.branchGeUnsigned .t0 .t1 ".Ltrap_boot_ready"),
  ins (.storeDouble .zero .t0 0),
  ins (.addImmediate .t0 .t0 8),
  ins (.jump ".Ltrap_clear_bss"),
  label ".Ltrap_boot_ready",
  ins (.loadAddress .t0 "__boot_hartid"),
  ins (.storeDouble .s0 .t0 0),
  ins (.storeDouble .s1 .t0 8)
] ++ initializeCanaries ++ #[
  ins (.loadAddress .t0 "core0_trap_vector"),
  ins (.csrWrite .mtvec .t0),
  ins (.loadAddress .t0 "__trap_stack_top"),
  ins (.csrWrite .mscratch .t0),
  ins (.call "core0_main"),
  label ".Ltrap_boot_halt",
  ins .waitForInterrupt,
  ins (.jump ".Ltrap_boot_halt")
]

private def csrSnapshots : Array (CSR × Nat) := #[
  (.mstatus, 248), (.mepc, 256), (.mcause, 264), (.mtval, 272), (.mie, 280)
]

private def restoreOffset (mutation : RestoreMutation) (register : Register) : Nat :=
  if mutation == .restoreS3FromS4 && register == .s3 then frameOffset .s4
  else frameOffset register

def vector (config : Configuration) : Array Line := #[
  label "core0_trap_vector",
  ins (.csrReadWrite .sp .mscratch .sp),
  ins (.branchEqZero .sp "core0_trap_double_fault"),
  ins (.addImmediate .sp .sp (-288)),
  -- Capture t0 before the first scratch-register use.
  ins (.storeDouble .t0 .sp 32),
  ins (.csrReadWrite .t0 .mscratch .zero),
  ins (.storeDouble .t0 .sp 8)
] ++ (preservedRegisters.filter fun register => register != .sp && register != .t0).map
  (fun register => ins (.storeDouble register .sp (asOffset (frameOffset register)))) ++
  csrSnapshots.flatMap (fun (csr, offset) => #[
    ins (.csrRead .t0 csr), ins (.storeDouble .t0 .sp (asOffset offset))
  ]) ++ #[
    ins (.move .gp .zero),
    ins (.move .tp .zero),
    ins (.loadDouble .a0 .sp 264),
    ins (.loadDouble .a1 .sp 256),
    ins (.loadDouble .a2 .sp 248),
    ins (.loadDouble .a3 .sp 272),
    ins (.loadDouble .a4 .sp 280),
    ins (.loadAddress .a5 "__trap_ecall_site"),
    ins (.loadAddress .a6 "__trap_ecall_resume"),
    ins (.loadAddress .a7 "__trap_breakpoint_site"),
    ins (.loadAddress .t0 "__trap_breakpoint_resume"),
    ins (.addImmediate .sp .sp (-16)),
    ins (.storeDouble .t0 .sp 0),
    ins (.call config.dispatcher),
    ins (.addImmediate .sp .sp 16),
    ins (.branchNeZero .a0 "core0_trap_fatal_dispatch"),
    ins (.csrWrite .mepc .a1),
    ins (.loadDouble .t0 .sp 248),
    ins (.csrWrite .mstatus .t0),
    ins (.loadDouble .t0 .sp 280),
    ins (.csrWrite .mie .t0)
  ] ++ (preservedRegisters.filter fun register => register != .sp && register != .t0).map
    (fun register => ins (.loadDouble register .sp (asOffset (restoreOffset config.mutation register)))) ++ #[
      ins (.loadDouble .t0 .sp 32),
      ins (.addImmediate .sp .sp 288),
      ins (.csrWrite .mscratch .sp),
      ins (.loadDouble .sp .sp (-280)),
      ins .machineReturn
    ]

private def callerRegisters : Array Register := #[
  .ra, .sp, .gp, .tp, .s0, .s1, .s2, .s3, .s4, .s5, .s6, .s7, .s8, .s9, .s10, .s11
]

private def saveCaller : Array Line := #[ins (.loadAddress .t0 "__trap_probe_context")] ++
  callerRegisters.mapIdx (fun index register =>
    ins (.storeDouble register .t0 (asOffset (index * 8))))

private def restoreCaller : Array Line := #[ins (.loadAddress .t0 "__trap_probe_context")] ++
  (callerRegisters.mapIdx fun index register => (index, register)).filterMap
    (fun (index, register) =>
      if register == .sp then none
      else some (ins (.loadDouble register .t0 (asOffset (index * 8))))) ++ #[
        ins (.loadDouble .sp .t0 8),
        ins .return
      ]

private def compareSnapshot (labelPrefix : String) : Array Line :=
  preservedRegisters.flatMap fun register =>
    let next := s!".L{labelPrefix}_x{register.number}_ok"
    #[
      ins (.loadDouble .t0 .sp (asOffset (frameOffset register))),
      ins (.loadImmediate .t1 (sentinelValue register)),
      ins (.branchEq .t0 .t1 next),
      ins (.loadImmediate .t2 (2 ^ (register.number - 1))),
      ins (.orRegisters .a0 .a0 .t2),
      label next
    ]

private def compareCanaries (labelPrefix : String) : Array Line :=
  (trapLayout.canaries.mapIdx fun index canary => (index, canary)).flatMap fun (index, canary) =>
    (#[0, 1] : Array Nat).flatMap fun word =>
      let next := s!".L{labelPrefix}_canary{index}_{word}_ok"
      #[
        ins (.loadImmediate .t0 (canary.address + word * 8)),
        ins (.loadDouble .t1 .t0 0),
        ins (.loadImmediate .t2 (canary.value + word)),
        ins (.branchEq .t1 .t2 next),
        ins (.loadImmediate .t2 (2 ^ (31 + index))),
        ins (.orRegisters .a0 .a0 .t2),
        label next
      ]

private def resumableProbe (symbol site resume labelPrefix : String)
    (trapInstruction : Instruction) : Array Line :=
  #[label symbol] ++ saveCaller ++
    preservedRegisters.map (fun register => ins (.loadImmediate register (sentinelValue register))) ++ #[
      label site,
      ins trapInstruction,
      label resume
    ] ++
    -- No register is clobbered before every x1..x31 value is captured.  SP is
    -- the fixed probe anchor and has at least 256 writable bytes above it.
    preservedRegisters.map (fun register =>
      ins (.storeDouble register .sp (asOffset (frameOffset register)))) ++ #[
        ins (.loadImmediate .a0 0)
      ] ++ compareSnapshot labelPrefix ++ compareCanaries labelPrefix ++ restoreCaller

def ecallProbe : Array Line := resumableProbe
  "core0_trap_ecall" "__trap_ecall_site" "__trap_ecall_resume" "trap_ecall" .environmentCall

def breakpointProbe : Array Line := resumableProbe
  "core0_trap_breakpoint" "__trap_breakpoint_site" "__trap_breakpoint_resume" "trap_breakpoint" .breakpoint

def unexpectedEcall : Array Line := #[
  label "core0_trap_unexpected_ecall",
  label "__trap_unexpected_ecall_site",
  ins .environmentCall,
  ins (.jump "core0_trap_fatal_dispatch")
]

def illegalInstruction : Array Line := #[
  label "core0_trap_illegal_instruction",
  label "__trap_illegal_instruction_site",
  ins .illegalInstruction,
  ins (.jump "core0_trap_fatal_dispatch")
]

/-- No stack, call, or dependency on interrupted state in either fatal path. -/
private def fatal (symbol halt : String) (status : Nat) : Array Line := #[
  label symbol,
  ins (.loadImmediate .t0 trapLayout.memory.machine.testFinisherBase),
  ins (.loadImmediate .t1 ((status * 2 ^ 16) + 0x3333)),
  ins .fenceIO,
  ins (.storeWord .t1 .t0 0),
  ins .fenceIO,
  label halt,
  ins (.jump halt)
]

def fatalDispatch : Array Line := fatal
  "core0_trap_fatal_dispatch" ".Ltrap_fatal_halt" 18

def doubleFault : Array Line := fatal
  "core0_trap_double_fault" ".Ltrap_double_halt" 19

private def renderFunction (symbol : String) (lines : Array Line) : List String :=
  [".balign 4", s!".globl {symbol}", s!".type {symbol}, @function"] ++
    lines.toList.map Line.render ++ [s!".size {symbol}, . - {symbol}"]

def renderStartup (config : Configuration) : Except String String := do
  trapLayout.validate
  let suffix := (config.dispatcher.drop "core0_action_".length).toString
  unless config.dispatcher.startsWith "core0_action_" &&
      !suffix.isEmpty && suffix.toList.all Char.isDigit do
    throw "trap dispatcher must be a checked Action symbol"
  pure <| String.intercalate "\n" <|
    [".option push", ".option norelax", ".option norvc",
      ".section .text.start, \"ax\", @progbits"] ++
    renderFunction "_start" startup ++
    renderFunction "core0_io_fence" Primitives.ioFence ++
    renderFunction "core0_trap_vector" (vector config) ++
    renderFunction "core0_trap_fatal_dispatch" fatalDispatch ++
    renderFunction "core0_trap_double_fault" doubleFault ++
    renderFunction "core0_trap_ecall" ecallProbe ++
    renderFunction "core0_trap_breakpoint" breakpointProbe ++
    renderFunction "core0_trap_unexpected_ecall" unexpectedEcall ++
    renderFunction "core0_trap_illegal_instruction" illegalInstruction ++
    [".option pop", ".section .note.GNU-stack, \"\", @progbits", ""]

end Lemma.Machine.TrapPrimitives
