import Lemma.Compiler.Test.DeviceABI
import Lemma.Machine.MemoryLayout

/-!
Pinned QEMU `virt`/ns16550a contract for the Gate 6 device image.

This is deliberately a machine-specific additive layout.  It reuses the
validated Gate 5 RAM policy, but MMIO is never projected into that general RAM
interface.  The UART facts are tied to the immutable QEMU source revision and
to the DTB emitted by that exact machine.
-/

namespace Lemma.Machine

open Lemma.Compiler.Test.DeviceABI

structure DeviceLayout where
  memory : MemoryLayout
  qemuVersion : String
  qemuRevision : String
  qemuSourceArchiveSha256 : String
  dtbNode : String
  uartCompatible : String
  deriving Repr, BEq

def deviceLayout : DeviceLayout := {
  memory := memoryLayout
  qemuVersion := "11.1.1"
  qemuRevision := "c3d48b7d1e89604920e5b81b91140c2ad39a1943"
  qemuSourceArchiveSha256 :=
    "079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482"
  dtbNode := "/soc/serial@10000000"
  uartCompatible := "ns16550a"
}

def DeviceLayout.validate (layout : DeviceLayout) : Except String Unit := do
  layout.memory.validate
  unless layout == deviceLayout do
    throw "Gate 6 device layout differs from the pinned LemmaVM contract"
  unless layout.memory.machine.uartBase == uartBase &&
      layout.memory.machine.uartSize == uartSpan do
    throw "Gate 6 UART interval differs from the base machine layout"
  unless uartRegisterShift == 0 && uartRegisterWidthBytes == 1 &&
      uartImplementedBytes == 8 do
    throw "Gate 6 UART register geometry differs from pinned QEMU"
  unless uartRbrOffset == 0 && uartThrOffset == 0 && uartFcrOffset == 2 &&
      uartIirOffset == 2 && uartLsrOffset == 5 do
    throw "Gate 6 UART register offsets differ from pinned QEMU"

def DeviceLayout.linkerScript (layout : DeviceLayout) : Except String String := do
  layout.validate
  layout.memory.linkerScript

def DeviceLayout.machineManifestJson (layout : DeviceLayout) : Except String String := do
  layout.validate
  layout.memory.machine.manifestJson

def DeviceLayout.deviceContractJson (layout : DeviceLayout) : Except String String := do
  layout.validate
  pure <| String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"contract_version\": \"core0-v0.5\",",
    "  \"machine\": \"qemu-virt-rv64-single-hart\",",
    "  \"qemu\": {\"version\":\"11.1.1\",\"revision\":\"c3d48b7d1e89604920e5b81b91140c2ad39a1943\",\"source_archive_sha256\":\"079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482\"},",
    "  \"dtb\": {\"node\":\"/soc/serial@10000000\",\"compatible\":\"ns16550a\",\"base\":\"0x0000000010000000\",\"span\":256,\"clock_hz\":3686400,\"interrupt\":10},",
    "  \"register_file\": {\"shift\":0,\"access_width_bytes\":1,\"implemented_bytes\":8,\"byte_order\":\"little-endian\"},",
    "  \"registers\": [",
    "    {\"name\":\"RBR\",\"offset\":0,\"access\":\"read\",\"side_effect\":\"consume-rx-fifo-byte-and-clear-DR-when-empty\"},",
    "    {\"name\":\"THR\",\"offset\":0,\"access\":\"write\",\"side_effect\":\"clear-THRE-and-TEMT\"},",
    "    {\"name\":\"FCR\",\"offset\":2,\"access\":\"write\",\"initial_value\":7,\"side_effect\":\"enable-fifo-and-clear-rx-tx\"},",
    "    {\"name\":\"LSR\",\"offset\":5,\"access\":\"read\",\"side_effect\":\"clear-BI-and-OE\"}",
    "  ],",
    "  \"lsr_bits\": {\"data_ready\":1,\"error_mask\":30,\"thr_empty\":32,\"transmitter_empty\":64},",
    "  \"compiler_access\": {\"type\":\"volatile-i8\",\"alignment\":1,\"ordering\":\"fence iorw,iorw immediately before and after every operation\"},",
    "  \"interrupt_use\": \"none; Gate 6 is polling-only\",",
    "  \"general_ram_api_access\": false",
    "}", ""
  ]

end Lemma.Machine
