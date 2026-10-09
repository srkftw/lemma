import Lemma.Core0.Memory

/-!
Closed device-operation contract for `core0-v0.5`.

The catalog is deliberately a list of named UART operations rather than a generic
MMIO interface.  Source programs cannot supply a physical address, register offset,
access width, or ordering policy.  Each admitted operation is lowered to one volatile
byte access surrounded by the target IO-ordering primitive.
-/

namespace Lemma.Core0.Device

/-- Direction of the single physical byte access performed by a device operation. -/
inductive Access where
  | read
  | write
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Access

def render : Access → String
  | .read => "read"
  | .write => "write"

end Access

/-- Closed identities understood by the v0.5 frontend and backend. -/
inductive Op where
  | uartReadStatus
  | uartReadByte
  | uartWriteByte
  | uartEnableAndResetFifo
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Op

def all : Array Op := #[
  .uartReadStatus,
  .uartReadByte,
  .uartWriteByte,
  .uartEnableAndResetFifo
]

def stableId : Op → String
  | .uartReadStatus => "uart.read-status"
  | .uartReadByte => "uart.read-byte"
  | .uartWriteByte => "uart.write-byte"
  | .uartEnableAndResetFifo => "uart.enable-reset-fifo"

def render : Op → String := stableId

end Op

/-- Hardware-visible side effects in the pinned QEMU ns16550a model. -/
inductive SideEffect where
  | observeLineStatus
  | consumeReceiveByte
  | transmitByte
  | enableAndResetFifos
  deriving BEq, DecidableEq, Inhabited, Repr

namespace UART

/-- Pinned QEMU `virt` ns16550a byte-register window. -/
def base : UInt64 := 0x10000000
def span : Nat := 0x100
def registerWidthBytes : Nat := 1

/-- RBR and THR share register offset zero, selected by access direction. -/
def rbrOffset : UInt64 := 0
def thrOffset : UInt64 := 0
def rbrThrOffset : UInt64 := rbrOffset
def fcrOffset : UInt64 := 2
def lsrOffset : UInt64 := 5

/-- Enable both FIFOs and reset their current contents. -/
def fcrEnableAndReset : UInt8 := 0x07
def fcrEnableAndClear : UInt8 := fcrEnableAndReset

def lsrDataReady : UInt8 := 0x01
def lsrErrorMask : UInt8 := 0x1e
def lsrThrEmpty : UInt8 := 0x20
def lsrTransmitterEmpty : UInt8 := 0x40

end UART

/-- One immutable entry in the exact v0.5 device-operation catalog. -/
structure OpSpec where
  op : Op
  base : UInt64
  offset : UInt64
  widthBytes : Nat
  access : Access
  /-- `none` means a runtime byte for `uartWriteByte`, or no write for reads. -/
  fixedWriteValue? : Option UInt8
  fenceBefore : Bool
  fenceAfter : Bool
  sideEffect : SideEffect
  deriving BEq, Inhabited, Repr

/-- The complete device catalog.  All accesses are ordered volatile byte accesses. -/
def opCatalog : Array OpSpec := #[
  {
    op := .uartReadStatus
    base := UART.base
    offset := UART.lsrOffset
    widthBytes := UART.registerWidthBytes
    access := .read
    fixedWriteValue? := none
    fenceBefore := true
    fenceAfter := true
    sideEffect := .observeLineStatus
  },
  {
    op := .uartReadByte
    base := UART.base
    offset := UART.rbrOffset
    widthBytes := UART.registerWidthBytes
    access := .read
    fixedWriteValue? := none
    fenceBefore := true
    fenceAfter := true
    sideEffect := .consumeReceiveByte
  },
  {
    op := .uartWriteByte
    base := UART.base
    offset := UART.thrOffset
    widthBytes := UART.registerWidthBytes
    access := .write
    fixedWriteValue? := none
    fenceBefore := true
    fenceAfter := true
    sideEffect := .transmitByte
  },
  {
    op := .uartEnableAndResetFifo
    base := UART.base
    offset := UART.fcrOffset
    widthBytes := UART.registerWidthBytes
    access := .write
    fixedWriteValue? := some UART.fcrEnableAndReset
    fenceBefore := true
    fenceAfter := true
    sideEffect := .enableAndResetFifos
  }
]

def findSpec? (op : Op) : Option OpSpec :=
  opCatalog.find? (fun spec => spec.op == op)

/-- Closed-catalog sanity used by manifests and focused probes. -/
def catalogValid : Bool :=
  opCatalog.size == 4 &&
    opCatalog.map (fun spec => spec.op) == Op.all &&
    opCatalog.all fun spec =>
      spec.base == UART.base && spec.widthBytes == 1 &&
        spec.offset.toNat < UART.span && spec.fenceBefore && spec.fenceAfter

end Lemma.Core0.Device
