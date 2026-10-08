import Lemma.Core0.Trap
import Lemma.Core0.Timer

/-!
Closed source syntax for the `core0-v0.4` through `core0-v0.7` Action profiles.

`Action` is syntax inspected by the Core0 frontend, not a target representation.
The only higher-order fields are immediate continuations and one statically resolved
bounded-fold callback.  The selected Action lowering erases every constructor and
continuation to scalar SSA/control flow; no `Action`, closure, allocator, or managed
state monad exists in the freestanding image.
-/

namespace Lemma.Core0.Memory

/-- The three widths admitted by the checked ordinary-RAM interface. -/
inductive Width where
  | w8
  | w32
  | w64
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Width

def bytes : Width → Nat
  | .w8 => 1
  | .w32 => 4
  | .w64 => 8

def bits : Width → Nat
  | .w8 => 8
  | .w32 => 32
  | .w64 => 64

def render : Width → String
  | .w8 => "8"
  | .w32 => "32"
  | .w64 => "64"

end Width

inductive Permission where
  | none
  | readOnly
  | readWrite
  deriving BEq, DecidableEq, Inhabited, Repr

inductive RegionKind where
  | ordinary
  | reserved
  | device
  deriving BEq, DecidableEq, Inhabited, Repr

/-- One immutable entry in the v0.4 authority table.  A runtime region identifier
is still checked against this table; the `UInt8` type itself grants no authority. -/
structure RegionSpec where
  id : UInt8
  name : String
  base : UInt64
  length : Nat
  alignment : Nat
  widths : Array Width
  permission : Permission
  kind : RegionKind
  purpose : String
  deriving BEq, Inhabited, Repr

namespace RegionId

def scratch : UInt8 := 0x01
def input : UInt8 := 0x02
def output : UInt8 := 0x03
def events : UInt8 := 0x04
def image : UInt8 := 0x70
def stack : UInt8 := 0x71
def uart : UInt8 := 0x80
def finisher : UInt8 := 0x81

end RegionId

namespace Status

def ok : UInt8 := 0
def unknownRegion : UInt8 := 1
def reservedRegion : UInt8 := 2
def deviceRegion : UInt8 := 3
def readDenied : UInt8 := 4
def writeDenied : UInt8 := 5
def widthDenied : UInt8 := 6
def outOfBounds : UInt8 := 7
def misaligned : UInt8 := 8
def budgetExceeded : UInt8 := 9

/-- Internal fold-control status.  A callback may use it to terminate the v0.5
fold successfully; it is never emitted as a public protocol result. -/
def iterationStop : UInt8 := 10
def txTimeout : UInt8 := 11
def rxTimeout : UInt8 := 12
def lineError : UInt8 := 13
def malformedFrame : UInt8 := 14
def truncatedFrame : UInt8 := 15
def invalidLength : UInt8 := 16
def unsupportedCommand : UInt8 := 17
def unexpectedTrap : UInt8 := 18
def doubleTrap : UInt8 := 19
def contextMismatch : UInt8 := 20
def missingTimerEvent : UInt8 := 21
def invalidDeadline : UInt8 := 22

def isKnownV04 (status : UInt8) : Bool := status ≤ budgetExceeded

def isKnownV05 (status : UInt8) : Bool := status ≤ unsupportedCommand

def isKnownV06 (status : UInt8) : Bool := status ≤ contextMismatch

def isKnownV07 (status : UInt8) : Bool := status ≤ invalidDeadline

/-- Public v0.5 outcomes exclude the internal fold stop sentinel. -/
def isPublicV05 (status : UInt8) : Bool :=
  status == ok || (txTimeout ≤ status && status ≤ unsupportedCommand)

/-- Public v0.6 outcomes add the three synchronous-trap terminal statuses while
continuing to exclude the internal fold stop sentinel. -/
def isPublicV06 (status : UInt8) : Bool :=
  isPublicV05 status || (unexpectedTrap ≤ status && status ≤ contextMismatch)

/-- Public v0.7 outcomes add bounded timer-observation and source deadline errors. -/
def isPublicV07 (status : UInt8) : Bool :=
  isPublicV06 status || status == missingTimerEvent || status == invalidDeadline

/-- Historical v0.4 predicate retained with its original meaning. -/
def isKnown (status : UInt8) : Bool := isKnownV04 status

end Status

/-- Largest Action-fold budget accepted by the v0.4 checker. -/
def maximumBudgetV04 : Nat := 256

/-- Larger but still static and finite Action-fold budget admitted only by v0.5. -/
def maximumBudgetV05 : Nat := 1000000

/-- Historical name retained for the v0.4 contract and existing manifests. -/
def maximumBudget : Nat := maximumBudgetV04

/-- Static region contract used by the model, exporter, and lowering.  Device
entries are descriptive only and can never reach the ordinary-RAM address path. -/
def regionTable : Array RegionSpec := #[
  {
    id := RegionId.scratch
    name := "scratch"
    base := 0x80801000
    length := 0x1000
    alignment := 8
    widths := #[.w8, .w32, .w64]
    permission := .readWrite
    kind := .ordinary
    purpose := "ordinary checked scratch RAM"
  },
  {
    id := RegionId.input
    name := "input-records"
    base := 0x81000000
    length := 0x1000
    alignment := 8
    widths := #[.w8, .w32, .w64]
    permission := .readOnly
    kind := .ordinary
    purpose := "host-provided immutable input records"
  },
  {
    id := RegionId.output
    name := "output"
    base := 0x80803000
    length := 0x1000
    alignment := 8
    widths := #[.w8, .w32, .w64]
    permission := .readWrite
    kind := .ordinary
    purpose := "checked output buffer"
  },
  {
    id := RegionId.events
    name := "events"
    base := 0x80805000
    length := 0x1000
    alignment := 8
    widths := #[.w32, .w64]
    permission := .readWrite
    kind := .ordinary
    purpose := "fixed-capacity event storage"
  },
  {
    id := RegionId.image
    name := "image"
    base := 0x80000000
    length := 0x007f0000
    alignment := 8
    widths := #[]
    permission := .none
    kind := .reserved
    purpose := "loaded image envelope; denied to the general RAM API"
  },
  {
    id := RegionId.stack
    name := "stack"
    base := 0x807f0000
    length := 0x00010000
    alignment := 8
    widths := #[]
    permission := .none
    kind := .reserved
    purpose := "machine stack; denied to the general RAM API"
  },
  {
    id := RegionId.uart
    name := "uart16550"
    base := 0x10000000
    length := 0x100
    alignment := 8
    widths := #[]
    permission := .none
    kind := .device
    purpose := "device MMIO; excluded from ordinary RAM operations"
  },
  {
    id := RegionId.finisher
    name := "sifive-test"
    base := 0x00100000
    length := 0x1000
    alignment := 8
    widths := #[]
    permission := .none
    kind := .device
    purpose := "VM termination MMIO; excluded from ordinary RAM operations"
  }
]

def findRegion? (id : UInt8) : Option RegionSpec :=
  regionTable.find? (fun region => region.id == id)

def regionIntervalValid (region : RegionSpec) : Bool :=
  region.base.toNat < 2 ^ 64 && region.length ≤ 2 ^ 64 - region.base.toNat

def tableValid : Bool :=
  regionTable.all regionIntervalValid &&
    regionTable.all fun region =>
      region.length > 0 &&
        region.alignment == 8 && region.base.toNat % region.alignment == 0 &&
        region.widths.all fun width =>
          width.bytes ≤ region.length && region.base.toNat % width.bytes == 0

/-- Closed effect syntax.  It intentionally has no `Monad` instance and accepts
no runtime `Action` parameters.  Host-side model execution interprets this syntax;
the target frontend consumes it before LLVM generation. -/
inductive Action where
  | done (status : UInt8) (value : UInt64)
  | bind (first : Action) (next : UInt8 → UInt64 → Action)
  | load8 (region : UInt8) (offset : UInt64)
      (next : UInt8 → UInt64 → Action)
  | load32 (region : UInt8) (offset : UInt64)
      (next : UInt8 → UInt64 → Action)
  | load64 (region : UInt8) (offset : UInt64)
      (next : UInt8 → UInt64 → Action)
  | store8 (region : UInt8) (offset : UInt64) (value : UInt8)
      (next : UInt8 → Action)
  | store32 (region : UInt8) (offset : UInt64) (value : UInt32)
      (next : UInt8 → Action)
  | store64 (region : UInt8) (offset value : UInt64)
      (next : UInt8 → Action)
  | checkReadRange (region : UInt8) (offset length : UInt64)
      (next : UInt8 → Action)
  | checkWriteRange (region : UInt8) (offset length : UInt64)
      (next : UInt8 → Action)
  | boundedFoldU64
      (budget : Nat)
      (step : UInt32 → UInt32 → UInt64 → UInt64 → UInt64 → UInt64 → UInt64 → Action)
      (count : UInt32) (initial ctx0 ctx1 ctx2 ctx3 : UInt64)
      (next : UInt8 → UInt64 → Action)
  /-- Read the fixed UART line-status register.  The byte is zero-extended into
  the standard Action value word. -/
  | uartReadStatus (next : UInt8 → UInt64 → Action)
  /-- Read and consume one byte from the fixed UART receive-buffer register. -/
  | uartReadByte (next : UInt8 → UInt64 → Action)
  /-- Write one byte to the fixed UART transmit-holding register. -/
  | uartWriteByte (value : UInt8) (next : UInt8 → Action)
  /-- Write `0x07` to the fixed UART FIFO-control register. -/
  | uartEnableAndResetFifo (next : UInt8 → Action)
  /-- Execute the authorized machine-mode environment-call fixture.  A returning
  primitive supplies `(0, contextCheckMask)` to the continuation. -/
  | trapEcall (next : UInt8 → UInt64 → Action)
  /-- Execute the authorized machine-mode breakpoint fixture. -/
  | trapBreakpoint (next : UInt8 → UInt64 → Action)
  /-- Enter the controlled unexpected-ecall fatal fixture. -/
  | trapUnexpectedEcall (next : UInt8 → UInt64 → Action)
  /-- Enter the controlled illegal-instruction fatal fixture. -/
  | trapIllegalInstruction (next : UInt8 → UInt64 → Action)
  /-- Read the pinned QEMU machine timer. -/
  | timerReadTime (next : UInt8 → UInt64 → Action)
  /-- Set the pinned hart-zero machine-timer comparator deadline. -/
  | timerSetCompare (deadline : UInt64) (next : UInt8 → UInt64 → Action)
  /-- Read the actual `mip.MTIP` pending bit. -/
  | timerReadPending (next : UInt8 → UInt64 → Action)
  /-- Atomically observe and clear only global `mstatus.MIE`. -/
  | irqSaveDisable (next : UInt8 → UInt64 → Action)
  /-- Restore only global `mstatus.MIE` from a canonical Boolean. -/
  | irqRestore (enabled : Bool) (next : UInt8 → UInt64 → Action)
  /-- Set or clear only `mie.MTIE` from a canonical Boolean. -/
  | timerSetInterrupt (enabled : Bool) (next : UInt8 → UInt64 → Action)
  /-- Enter the quarantined timer/context probe.  Its caller must have MIE clear. -/
  | timerProbe (next : UInt8 → UInt64 → Action)

end Lemma.Core0.Memory
