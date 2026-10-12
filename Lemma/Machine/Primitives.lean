namespace Lemma.Machine.Primitives

/-- Registers used by the generated entry stub.  Keeping them structured makes
the startup primitive reviewable without maintaining a target `.S` source. -/
inductive Register where
  | zero | ra | sp | gp | tp | t0 | t1 | t2 | s0 | s1
  | a0 | a1 | a2 | a3 | a4 | a5 | a6 | a7
  | s2 | s3 | s4 | s5 | s6 | s7 | s8 | s9 | s10 | s11
  | t3 | t4 | t5 | t6
  deriving Repr, BEq, DecidableEq, Inhabited

def Register.render : Register → String
  | .zero => "zero"
  | .ra => "ra"
  | .sp => "sp"
  | .gp => "gp"
  | .tp => "tp"
  | .t0 => "t0"
  | .t1 => "t1"
  | .t2 => "t2"
  | .a0 => "a0"
  | .a1 => "a1"
  | .a2 => "a2"
  | .a3 => "a3"
  | .a4 => "a4"
  | .a5 => "a5"
  | .a6 => "a6"
  | .a7 => "a7"
  | .s0 => "s0"
  | .s1 => "s1"
  | .s2 => "s2"
  | .s3 => "s3"
  | .s4 => "s4"
  | .s5 => "s5"
  | .s6 => "s6"
  | .s7 => "s7"
  | .s8 => "s8"
  | .s9 => "s9"
  | .s10 => "s10"
  | .s11 => "s11"
  | .t3 => "t3"
  | .t4 => "t4"
  | .t5 => "t5"
  | .t6 => "t6"

/-- Complete architectural x0..x31 order, independent of the ABI spelling. -/
def Register.all : Array Register := #[
  .zero, .ra, .sp, .gp, .tp, .t0, .t1, .t2, .s0, .s1,
  .a0, .a1, .a2, .a3, .a4, .a5, .a6, .a7,
  .s2, .s3, .s4, .s5, .s6, .s7, .s8, .s9, .s10, .s11,
  .t3, .t4, .t5, .t6
]

def Register.number (register : Register) : Nat :=
  (Register.all.toList.idxOf register)

/-- The M-mode substrates cannot name arbitrary CSRs. -/
inductive CSR where
  | mstatus | mie | mtvec | mscratch | mepc | mcause | mtval | mip
  | medeleg | mideleg | pmpcfg0 | pmpaddr0 | pmpaddr1 | pmpaddr2 | pmpaddr3 | pmpaddr4 | pmpaddr5 | pmpaddr6 | pmpaddr7
  | mcounteren | scounteren
  | sstatus | sie | stvec | sscratch | sepc | scause | stval | sip | satp
  | misa | mcycle | minstret | mcountinhibit
  deriving Repr, BEq, DecidableEq

def CSR.render : CSR → String
  | .mstatus => "mstatus"
  | .mie => "mie"
  | .mtvec => "mtvec"
  | .mscratch => "mscratch"
  | .mepc => "mepc"
  | .mcause => "mcause"
  | .mtval => "mtval"
  | .mip => "mip"
  | .medeleg => "medeleg"
  | .mideleg => "mideleg"
  | .pmpcfg0 => "pmpcfg0"
  | .pmpaddr0 => "pmpaddr0"
  | .pmpaddr1 => "pmpaddr1"
  | .pmpaddr2 => "pmpaddr2"
  | .pmpaddr3 => "pmpaddr3"
  | .pmpaddr4 => "pmpaddr4"
  | .pmpaddr5 => "pmpaddr5"
  | .pmpaddr6 => "pmpaddr6"
  | .pmpaddr7 => "pmpaddr7"
  | .mcounteren => "mcounteren"
  | .scounteren => "scounteren"
  | .sstatus => "sstatus"
  | .sie => "sie"
  | .stvec => "stvec"
  | .sscratch => "sscratch"
  | .sepc => "sepc"
  | .scause => "scause"
  | .stval => "stval"
  | .sip => "sip"
  | .satp => "satp"
  | .misa => "misa"
  | .mcycle => "mcycle"
  | .minstret => "minstret"
  | .mcountinhibit => "mcountinhibit"

inductive Instruction where
  | loadAddress (dst : Register) (symbol : String)
  | branchGeUnsigned (lhs rhs : Register) (target : String)
  | storeDouble (src base : Register) (offset : Int)
  | storeWord (src base : Register) (offset : Int)
  | loadDouble (dst base : Register) (offset : Int)
  | loadImmediate (dst : Register) (value : Nat)
  | addImmediate (dst src : Register) (value : Int)
  | andImmediate (dst src : Register) (value : Nat)
  | shiftRightImmediate (dst src : Register) (bits : Nat)
  | orRegisters (dst lhs rhs : Register)
  | branchEq (lhs rhs : Register) (target : String)
  | branchNe (lhs rhs : Register) (target : String)
  | branchEqZero (src : Register) (target : String)
  | branchNeZero (src : Register) (target : String)
  | csrRead (dst : Register) (csr : CSR)
  | csrWrite (csr : CSR) (src : Register)
  | csrReadWrite (dst : Register) (csr : CSR) (src : Register)
  | csrSet (csr : CSR) (src : Register)
  | csrClear (csr : CSR) (src : Register)
  | csrSetImmediate (csr : CSR) (mask : Nat)
  | csrClearImmediate (csr : CSR) (mask : Nat)
  | csrReadClearImmediate (dst : Register) (csr : CSR) (mask : Nat)
  | maskMachineInterruptEnable
  | environmentCall
  | breakpoint
  | illegalInstruction
  /-- Fixed zero word for a closed architectural instruction-pair probe. No
  operand or arbitrary instruction encoding can be supplied. -/
  | zeroInstructionWord
  | machineReturn
  | supervisorReturn
  | move (dst src : Register)
  | jump (target : String)
  | jumpRegisterZero (base : Register)
  | call (symbol : String)
  | fenceIO
  | translationFenceAll
  | instructionFence
  | return
  | waitForInterrupt
  deriving Repr, BEq

def Instruction.render : Instruction → String
  | .loadAddress dst symbol => s!"la {dst.render}, {symbol}"
  | .branchGeUnsigned lhs rhs target => s!"bgeu {lhs.render}, {rhs.render}, {target}"
  | .storeDouble src base offset => s!"sd {src.render}, {offset}({base.render})"
  | .storeWord src base offset => s!"sw {src.render}, {offset}({base.render})"
  | .loadDouble dst base offset => s!"ld {dst.render}, {offset}({base.render})"
  | .loadImmediate dst value => s!"li {dst.render}, {value}"
  | .addImmediate dst src value => s!"addi {dst.render}, {src.render}, {value}"
  | .andImmediate dst src value => s!"andi {dst.render}, {src.render}, {value}"
  | .shiftRightImmediate dst src bits => s!"srli {dst.render}, {src.render}, {bits}"
  | .orRegisters dst lhs rhs => s!"or {dst.render}, {lhs.render}, {rhs.render}"
  | .branchEq lhs rhs target => s!"beq {lhs.render}, {rhs.render}, {target}"
  | .branchNe lhs rhs target => s!"bne {lhs.render}, {rhs.render}, {target}"
  | .branchEqZero src target => s!"beqz {src.render}, {target}"
  | .branchNeZero src target => s!"bnez {src.render}, {target}"
  | .csrRead dst csr => s!"csrr {dst.render}, {csr.render}"
  | .csrWrite csr src => s!"csrw {csr.render}, {src.render}"
  | .csrReadWrite dst csr src => s!"csrrw {dst.render}, {csr.render}, {src.render}"
  | .csrSet csr src => s!"csrs {csr.render}, {src.render}"
  | .csrClear csr src => s!"csrc {csr.render}, {src.render}"
  | .csrSetImmediate csr mask => s!"csrsi {csr.render}, {mask}"
  | .csrClearImmediate csr mask => s!"csrci {csr.render}, {mask}"
  | .csrReadClearImmediate dst csr mask => s!"csrrci {dst.render}, {csr.render}, {mask}"
  | .maskMachineInterruptEnable => "csrci mstatus, 8"
  | .environmentCall => "ecall"
  | .breakpoint => "ebreak"
  | .illegalInstruction => ".word 0x0000000b"
  | .zeroInstructionWord => ".word 0x00000000"
  | .machineReturn => "mret"
  | .supervisorReturn => "sret"
  | .move dst src => s!"mv {dst.render}, {src.render}"
  | .jump target => s!"j {target}"
  | .jumpRegisterZero base => s!"jalr zero, 0({base.render})"
  | .call symbol => s!"call {symbol}"
  | .fenceIO => "fence iorw, iorw"
  | .translationFenceAll => "sfence.vma zero, zero"
  | .instructionFence => "fence.i"
  | .return => "ret"
  | .waitForInterrupt => "wfi"

inductive Line where
  | label (name : String)
  | instruction (value : Instruction)
  deriving Repr, BEq

def Line.render : Line → String
  | .label name => name ++ ":"
  | .instruction value => "  " ++ value.render

/-- The only assembly-shaped target fragment.  It is generated from the typed
instruction list below, establishes `sp`, clears `.bss`, and calls LLVM code. -/
def startup : Array Line := #[
  .label "_start",
  .instruction (.loadAddress .sp "__stack_top"),
  .instruction (.move .s0 .a0),
  .instruction (.move .s1 .a1),
  .instruction (.loadAddress .t0 "__bss_start"),
  .instruction (.loadAddress .t1 "__bss_end"),
  .label ".Lcore0_clear_bss",
  .instruction (.branchGeUnsigned .t0 .t1 ".Lcore0_ready"),
  .instruction (.storeDouble .zero .t0 0),
  .instruction (.addImmediate .t0 .t0 8),
  .instruction (.jump ".Lcore0_clear_bss"),
  .label ".Lcore0_ready",
  .instruction (.loadAddress .t0 "__boot_hartid"),
  .instruction (.storeDouble .s0 .t0 0),
  .instruction (.storeDouble .s1 .t0 8),
  .instruction (.call "core0_main"),
  .label ".Lcore0_halt",
  .instruction .waitForInterrupt,
  .instruction (.jump ".Lcore0_halt")
]

def ioFence : Array Line := #[
  .label "core0_io_fence",
  .instruction .fenceIO,
  .instruction .return
]

def renderStartup : String :=
  String.intercalate "\n" <| [
    ".option push",
    ".option norelax",
    ".option norvc",
    ".section .text.start, \"ax\", @progbits",
    ".balign 4",
    ".globl _start",
    ".type _start, @function"
  ] ++ startup.toList.map Line.render ++ [
    ".size _start, . - _start",
    ".globl core0_io_fence",
    ".type core0_io_fence, @function"
  ] ++ ioFence.toList.map Line.render ++ [
    ".size core0_io_fence, . - core0_io_fence",
    ".option pop",
    ".section .note.GNU-stack, \"\", @progbits",
    ""
  ]

end Lemma.Machine.Primitives
