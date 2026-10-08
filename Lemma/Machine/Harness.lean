import Lemma.Compiler.LLVMIR
import Lemma.Machine.Layout

namespace Lemma.Machine.Harness

open Lemma.Compiler.LLVM

private def value (name : String) : Operand := .local name
private def int1 (value : Bool) : Operand := .int .i1 (if value then 1 else 0)
private def int8 (value : Nat) : Operand := .int .i8 value
private def int32 (value : Nat) : Operand := .int .i32 value
private def int64 (value : Nat) : Operand := .int .i64 value

def exitFailure (layout : Layout) : Function := {
  name := "core0_exit_failure"
  returnType := .void
  parameters := #[]
  linkage := some "internal"
  attributes := #["noreturn", "nounwind"]
  blocks := #[
    {
      label := "entry"
      instructions := #[
        .ptrFromInt "finisher" layout.testFinisherBase,
        .call none .void "core0_io_fence" #[],
        .store .i32 (int32 0x13333) (value "finisher") 4 true,
        .call none .void "core0_io_fence" #[],
        .jump "halt"
      ]
    },
    { label := "halt", instructions := #[.jump "halt"] }
  ]
}

def exitSuccess (layout : Layout) : Function := {
  name := "core0_exit_success"
  returnType := .void
  parameters := #[]
  linkage := some "internal"
  attributes := #["noreturn", "nounwind"]
  blocks := #[
    {
      label := "entry"
      instructions := #[
        .ptrFromInt "finisher" layout.testFinisherBase,
        .call none .void "core0_uart_drain" #[],
        .call none .void "core0_io_fence" #[],
        .store .i32 (int32 0x5555) (value "finisher") 4 true,
        .call none .void "core0_io_fence" #[],
        .jump "halt"
      ]
    },
    { label := "halt", instructions := #[.jump "halt"] }
  ]
}

/-- Ordered 16550 byte output with a one-million-iteration bound.  Failure
terminates the VM through the declared SiFive test device, so a stuck UART can
never be reported as a target pass. -/
def uartPutc (layout : Layout) : Function := {
  name := "core0_uart_putc"
  returnType := .void
  parameters := #[⟨.i8, "ch"⟩]
  linkage := some "internal"
  blocks := #[
    {
      label := "entry"
      instructions := #[
        .ptrFromInt "thr" layout.uartBase,
        .ptrFromInt "lsr" (layout.uartBase + 5),
        .jump "poll"
      ]
    },
    {
      label := "poll"
      instructions := #[
        .phi "count" .i32 #[(int32 0, "entry"), (value "next", "wait")],
        .call none .void "core0_io_fence" #[],
        .load "status" .i8 (value "lsr") 1 true,
        .call none .void "core0_io_fence" #[],
        .bin "txbit" .and .i8 (value "status") (int8 0x20),
        .icmp "ready" .ne .i8 (value "txbit") (int8 0),
        .branch (value "ready") "write" "wait"
      ]
    },
    {
      label := "wait"
      instructions := #[
        .bin "next" .add .i32 (value "count") (int32 1),
        .icmp "expired" .uge .i32 (value "next") (int32 1000000),
        .branch (value "expired") "timeout" "poll"
      ]
    },
    {
      label := "write"
      instructions := #[
        .call none .void "core0_io_fence" #[],
        .store .i8 (value "ch") (value "thr") 1 true,
        .call none .void "core0_io_fence" #[],
        .retVoid
      ]
    },
    {
      label := "timeout"
      instructions := #[
        .call none .void "core0_exit_failure" #[],
        .unreachable
      ]
    }
  ]
}

/-- Wait for the transmitter to become completely empty before requesting VM
shutdown, so the final framed byte is observable before QEMU exits. -/
def uartDrain (layout : Layout) : Function := {
  name := "core0_uart_drain"
  returnType := .void
  parameters := #[]
  linkage := some "internal"
  blocks := #[
    {
      label := "entry"
      instructions := #[
        .ptrFromInt "lsr" (layout.uartBase + 5),
        .jump "poll"
      ]
    },
    {
      label := "poll"
      instructions := #[
        .phi "count" .i32 #[(int32 0, "entry"), (value "next", "wait")],
        .call none .void "core0_io_fence" #[],
        .load "status" .i8 (value "lsr") 1 true,
        .call none .void "core0_io_fence" #[],
        .bin "empty_bit" .and .i8 (value "status") (int8 0x40),
        .icmp "empty" .ne .i8 (value "empty_bit") (int8 0),
        .branch (value "empty") "done" "wait"
      ]
    },
    {
      label := "wait"
      instructions := #[
        .bin "next" .add .i32 (value "count") (int32 1),
        .icmp "expired" .uge .i32 (value "next") (int32 1000000),
        .branch (value "expired") "timeout" "poll"
      ]
    },
    { label := "done", instructions := #[.retVoid] },
    {
      label := "timeout"
      instructions := #[
        .call none .void "core0_exit_failure" #[],
        .unreachable
      ]
    }
  ]
}

private def hexDigitInstructions (shift : Nat) (index : Nat) : Array Instruction :=
  let stem := s!"hex{index}"
  let shifted := stem ++ "_shifted"
  let nibble := stem ++ "_nibble"
  let decimal := stem ++ "_decimal"
  let number := stem ++ "_number"
  let letter := stem ++ "_letter"
  let ascii := stem ++ "_ascii"
  let byte := stem ++ "_byte"
  #[
    .bin shifted .lshr .i64 (value "value") (int64 shift),
    .bin nibble .and .i64 (value shifted) (int64 15),
    .icmp decimal .ult .i64 (value nibble) (int64 10),
    .bin number .add .i64 (value nibble) (int64 48),
    .bin letter .add .i64 (value nibble) (int64 87),
    .select ascii (value decimal) .i64 (value number) (value letter),
    .trunc byte .i64 (value ascii) .i8,
    .call none .void "core0_uart_putc" #[(.i8, value byte)]
  ]

def putHex64 : Function := {
  name := "core0_put_hex64"
  returnType := .void
  parameters := #[⟨.i64, "value"⟩]
  linkage := some "internal"
  blocks := #[{
    label := "entry"
    instructions := Id.run do
      let mut instructions := #[]
      for i in [:16] do
        instructions := instructions ++ hexDigitInstructions (60 - 4 * i) i
      instructions := instructions.push .retVoid
      return instructions
  }]
}

private def callsForString (text : String) : Array Instruction :=
  text.toUTF8.foldl (init := #[]) fun instructions byte =>
    instructions.push (.call none .void "core0_uart_putc" #[(.i8, int8 byte.toNat)])

private def inputLoad (name : String) (address : Nat) : Array Instruction := #[
  .ptrFromInt (name ++ "_ptr") address,
  .load name .i64 (value (name ++ "_ptr")) 8 true
]

/-- Machine harness around the compiled Core0 root.  The fixture is injected by
QEMU after code generation and contains magic, case id, and three UInt64 inputs. -/
def main (layout : Layout) (rootSymbol : String) : Function := {
  name := "core0_main"
  returnType := .void
  parameters := #[]
  attributes := #["noreturn", "nounwind"]
  blocks := #[
    {
      label := "entry"
      instructions := inputLoad "magic" layout.input.start ++ #[
        .icmp "magic_ok" .eq .i64 (value "magic") (int64 0x313030414d4d454c),
        .branch (value "magic_ok") "run" "bad_input"
      ]
    },
    {
      label := "bad_input"
      instructions := callsForString "ERROR:INPUT\n" ++ #[
        .call none .void "core0_exit_failure" #[],
        .unreachable
      ]
    },
    {
      label := "run"
      instructions := inputLoad "case_id" (layout.input.start + 8) ++
        inputLoad "arg0" (layout.input.start + 16) ++
        inputLoad "arg1" (layout.input.start + 24) ++
        inputLoad "arg2" (layout.input.start + 32) ++ #[
          .call (some "result") .i64 rootSymbol #[(.i64, value "arg0"), (.i64, value "arg1"), (.i64, value "arg2")]
        ] ++ callsForString "LEMMA_CORE0/1\nRESULT:" ++ #[
          .call none .void "core0_put_hex64" #[(.i64, value "case_id")]
        ] ++ callsForString ":" ++ #[
          .call none .void "core0_put_hex64" #[(.i64, value "result")]
        ] ++ callsForString "\n" ++ #[
          .call none .void "core0_exit_success" #[],
          .unreachable
        ]
    }
  ]
}

def functions (layout : Layout) (rootSymbol : String) : Array Function := #[
  exitFailure layout,
  exitSuccess layout,
  uartPutc layout,
  uartDrain layout,
  putHex64,
  main layout rootSymbol
]

def declarations : Array Declaration := #[
  { name := "core0_io_fence", returnType := .void, parameters := #[] }
]

end Lemma.Machine.Harness
