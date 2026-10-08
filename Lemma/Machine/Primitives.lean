namespace Lemma.Machine.Primitives

/-- Registers used by the generated entry stub.  Keeping them structured makes
the startup primitive reviewable without maintaining a target `.S` source. -/
inductive Register where
  | zero | ra | sp | t0 | t1 | a0 | a1 | s0 | s1
  deriving Repr, BEq

def Register.render : Register → String
  | .zero => "zero"
  | .ra => "ra"
  | .sp => "sp"
  | .t0 => "t0"
  | .t1 => "t1"
  | .a0 => "a0"
  | .a1 => "a1"
  | .s0 => "s0"
  | .s1 => "s1"

inductive Instruction where
  | loadAddress (dst : Register) (symbol : String)
  | branchGeUnsigned (lhs rhs : Register) (target : String)
  | storeDouble (src base : Register) (offset : Int)
  | addImmediate (dst src : Register) (value : Int)
  | move (dst src : Register)
  | jump (target : String)
  | call (symbol : String)
  | fenceIO
  | return
  | waitForInterrupt
  deriving Repr, BEq

def Instruction.render : Instruction → String
  | .loadAddress dst symbol => s!"la {dst.render}, {symbol}"
  | .branchGeUnsigned lhs rhs target => s!"bgeu {lhs.render}, {rhs.render}, {target}"
  | .storeDouble src base offset => s!"sd {src.render}, {offset}({base.render})"
  | .addImmediate dst src value => s!"addi {dst.render}, {src.render}, {value}"
  | .move dst src => s!"mv {dst.render}, {src.render}"
  | .jump target => s!"j {target}"
  | .call symbol => s!"call {symbol}"
  | .fenceIO => "fence iorw, iorw"
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
