import Lemma.Compiler.Format

namespace Lemma.Machine

inductive RegionKind where
  | loaded
  | noLoad
  | hostFixture
  deriving Repr, BEq, Inhabited

structure Region where
  name : String
  start : Nat
  size : Nat
  alignment : Nat
  kind : RegionKind
  deriving Repr, BEq, Inhabited

namespace Region

def stop (r : Region) : Nat := r.start + r.size

def overlaps (a b : Region) : Bool :=
  a.start < b.stop && b.start < a.stop

end Region

structure Layout where
  ram : Region
  image : Region
  stack : Region
  input : Region
  uartBase : Nat
  uartSize : Nat
  testFinisherBase : Nat
  deriving Repr, BEq

/-- LemmaVM v0.1 layout for QEMU `virt`, 128 MiB at 0x80000000. -/
def core0Layout : Layout := {
  ram := ⟨"ram", 0x80000000, 0x08000000, 0x1000, .noLoad⟩
  image := ⟨"image-envelope", 0x80000000, 0x007f0000, 0x1000, .loaded⟩
  stack := ⟨"stack", 0x807f0000, 0x00010000, 16, .noLoad⟩
  input := ⟨"runtime-input", 0x81000000, 0x00001000, 8, .hostFixture⟩
  uartBase := 0x10000000
  uartSize := 0x100
  testFinisherBase := 0x00100000
}

private def aligned (r : Region) : Bool :=
  r.alignment > 0 && r.start % r.alignment == 0 && r.size % r.alignment == 0

private def contained (outer inner : Region) : Bool :=
  outer.start ≤ inner.start && inner.stop ≤ outer.stop

def Layout.validate (l : Layout) : Except String Unit := do
  for r in #[l.ram, l.image, l.stack, l.input] do
    unless aligned r do
      throw s!"layout region {r.name} is not aligned to {r.alignment} bytes"
  for r in #[l.image, l.stack, l.input] do
    unless contained l.ram r do
      throw s!"layout region {r.name} lies outside RAM"
  let reserved := #[l.image, l.stack, l.input]
  for i in [:reserved.size] do
    for j in [i + 1:reserved.size] do
      if reserved[i]!.overlaps reserved[j]! then
        throw s!"layout regions {reserved[i]!.name} and {reserved[j]!.name} overlap"
  unless l.uartSize > 5 do
    throw "UART region does not include the 16550 line-status register"

def Layout.linkerScript (l : Layout) : Except String String := do
  l.validate
  let h := Lemma.Compiler.Format.hexAddr
  pure <| String.intercalate "\n" [
    "OUTPUT_ARCH(riscv)",
    "ENTRY(_start)",
    "SECTIONS", "{",
    s!"  . = {h l.image.start};",
    "  .text : ALIGN(16) { KEEP(*(.text.start)) *(.text .text.*) }",
    "  .rodata : ALIGN(16) { *(.rodata .rodata.*) }",
    "  .data : ALIGN(16) { *(.data .data.* .sdata .sdata.*) }",
    "  . = ALIGN(16);",
    "  __bss_start = .;",
    "  .bss (NOLOAD) : ALIGN(16) {",
    "    *(.bss .bss.* .sbss .sbss.*) *(COMMON)",
    "    . = ALIGN(8);",
    "    __boot_hartid = .; . += 8;",
    "    __boot_dtb = .; . += 8;",
    "  }",
    "  . = ALIGN(16);",
    "  __bss_end = .;",
    "  __image_end = .;",
    s!"  ASSERT(__image_end <= {h l.image.stop}, \"Core0 image exceeds its envelope\")",
    s!"  __stack_bottom = {h l.stack.start};",
    s!"  __stack_top = {h l.stack.stop};",
    s!"  __core0_input = {h l.input.start};",
    "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }",
    "}", ""
  ]

def Layout.manifestJson (l : Layout) : Except String String := do
  l.validate
  let h := Lemma.Compiler.Format.hexAddr
  pure <| String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"ram\": {\"start\": \"" ++ h l.ram.start ++ "\", \"size\": \"" ++ h l.ram.size ++ "\"},",
    "  \"image\": {\"start\": \"" ++ h l.image.start ++ "\", \"size\": \"" ++ h l.image.size ++ "\"},",
    "  \"stack\": {\"start\": \"" ++ h l.stack.start ++ "\", \"size\": \"" ++ h l.stack.size ++ "\", \"alignment\": 16},",
    "  \"input\": {\"start\": \"" ++ h l.input.start ++ "\", \"size\": \"" ++ h l.input.size ++ "\", \"alignment\": 8},",
    "  \"uart_16550\": {\"base\": \"" ++ h l.uartBase ++ "\", \"size\": \"" ++ h l.uartSize ++ "\"},",
    "  \"sifive_test\": {\"base\": \"" ++ h l.testFinisherBase ++ "\"}",
    "}", ""
  ]

end Lemma.Machine
