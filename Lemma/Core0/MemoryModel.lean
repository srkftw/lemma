import Lemma.Core0.ActionIR

/-!
Finite executable semantics for the v0.4 Action syntax.

The model stores only named ordinary regions, never a forged flat host address
space.  Accepted reads and writes append observable events.  The target lowering
uses volatile LLVM accesses for this profile so optimization cannot erase a
successful modeled access; volatility here does not classify RAM as MMIO and does
not imply an IO fence.
-/

namespace Lemma.Core0.Memory.Model

inductive Operation where
  | load (width : Width)
  | store (width : Width)
  | checkReadRange
  | checkWriteRange
  deriving BEq, Inhabited, Repr

inductive Event where
  | read (width : Width) (region : UInt8) (offset value : UInt64)
  | write (width : Width) (region : UInt8) (offset value : UInt64)
  deriving BEq, Inhabited, Repr

structure RegionImage where
  id : UInt8
  bytes : Array UInt8
  deriving BEq, Inhabited, Repr

structure State where
  regions : Array RegionImage
  events : Array Event := #[]
  deriving BEq, Inhabited, Repr

namespace State

/-- A finite zero-filled image for every ordinary region.  Reserved and device
regions deliberately have no byte storage in the general-memory model. -/
def zeroed : State := {
  regions := regionTable.foldl (init := #[]) fun images region =>
    if region.kind == .ordinary then
      images.push { id := region.id, bytes := Array.replicate region.length 0 }
    else images
}

def findImage? (state : State) (id : UInt8) : Option RegionImage :=
  state.regions.find? (fun image => image.id == id)

def replaceImage (state : State) (updated : RegionImage) : State := {
  state with
  regions := state.regions.map fun image => if image.id == updated.id then updated else image
}

def appendEvent (state : State) (event : Event) : State :=
  { state with events := state.events.push event }

end State

structure Outcome where
  status : UInt8
  value : UInt64
  deriving BEq, Inhabited, Repr

structure Evaluation where
  outcome : Outcome
  state : State
  deriving BEq, Inhabited, Repr

inductive DiagnosticCode where
  | fuelExhausted
  | malformedState
  | deviceActionUnsupported
  | trapActionUnsupported
  | timerActionUnsupported
  | executionActionUnsupported
  | loopActionUnsupported
  deriving BEq, DecidableEq, Inhabited, Repr

structure Diagnostic where
  code : DiagnosticCode
  message : String
  deriving Inhabited, Repr

private def permissionAllows (permission : Permission) (access : MemoryAccess) : Bool :=
  match permission, access with
  | .readOnly, .read => true
  | .readWrite, _ => true
  | _, _ => false

private def permissionFailure : MemoryAccess → UInt8
  | .read => Status.readDenied
  | .write => Status.writeDenied

/-- Ordered, subtraction-based single-access guard.  In particular, it never
computes `offset + width` before establishing containment. -/
def accessStatus (access : MemoryAccess) (width : Width) (regionId : UInt8)
    (offset : UInt64) : UInt8 :=
  match findRegion? regionId with
  | none => Status.unknownRegion
  | some region =>
      if region.kind == .reserved then Status.reservedRegion
      else if region.kind == .device then Status.deviceRegion
      else if !permissionAllows region.permission access then permissionFailure access
      else if !region.widths.contains width then Status.widthDenied
      else if width.bytes > region.length then Status.outOfBounds
      else
        let remaining := region.length - width.bytes
        if offset.toNat > remaining then Status.outOfBounds
        else if offset.toNat % width.bytes != 0 then Status.misaligned
        else Status.ok

/-- Ordered range guard used by the buffer algorithms.  Zero-length ranges are
valid at the one-past-end offset and perform no read/write event. -/
def rangeStatus (access : MemoryAccess) (regionId : UInt8) (offset length : UInt64) : UInt8 :=
  match findRegion? regionId with
  | none => Status.unknownRegion
  | some region =>
      if region.kind == .reserved then Status.reservedRegion
      else if region.kind == .device then Status.deviceRegion
      else if !permissionAllows region.permission access then permissionFailure access
      else if offset.toNat > region.length then Status.outOfBounds
      else
        let remaining := region.length - offset.toNat
        if length.toNat > remaining then Status.outOfBounds else Status.ok

private def readLittleEndian (bytes : Array UInt8) (offset count : Nat) : UInt64 :=
  UInt64.ofNat <| (List.range count).foldl (init := 0) fun value index =>
    value + (bytes.getD (offset + index) 0).toNat * 2 ^ (8 * index)

private def writeLittleEndian (bytes : Array UInt8) (offset count : Nat)
    (value : UInt64) : Array UInt8 :=
  (List.range count).foldl (init := bytes) fun result index =>
    result.set! (offset + index) <|
      UInt8.ofNat ((value.toNat / 2 ^ (8 * index)) % 256)

def deniedTransition (state : State) (operation : Operation) (region : UInt8)
    (offset amount : UInt64) (status : UInt8) : Outcome × State :=
  -- Keep the full attempted operation in this interface so callers and proofs
  -- state precisely which guard rejected it.  Rejection itself is deliberately
  -- unobservable in the access trace: only successful physical accesses append.
  let _ := operation
  let _ := region
  let _ := offset
  let _ := amount
  (⟨status, 0⟩, state)

def load (state : State) (width : Width) (region : UInt8) (offset : UInt64) :
    Except Diagnostic (Outcome × State) := do
  let status := accessStatus .read width region offset
  unless status == Status.ok do
    return deniedTransition state (.load width) region offset (UInt64.ofNat width.bytes) status
  let some image := state.findImage? region
    | throw {
        code := .malformedState
        message := s!"ordinary region {region.toNat} has no finite model image"
      }
  let value := readLittleEndian image.bytes offset.toNat width.bytes
  let state := state.appendEvent (.read width region offset value)
  pure (⟨Status.ok, value⟩, state)

def store (state : State) (width : Width) (region : UInt8) (offset value : UInt64) :
    Except Diagnostic (Outcome × State) := do
  let status := accessStatus .write width region offset
  unless status == Status.ok do
    return deniedTransition state (.store width) region offset (UInt64.ofNat width.bytes) status
  let some image := state.findImage? region
    | throw {
        code := .malformedState
        message := s!"ordinary region {region.toNat} has no finite model image"
      }
  let bytes := writeLittleEndian image.bytes offset.toNat width.bytes value
  let state := (state.replaceImage { image with bytes }).appendEvent
    (.write width region offset value)
  pure (⟨Status.ok, 0⟩, state)

def checkRange (state : State) (access : MemoryAccess) (region : UInt8)
    (offset length : UInt64) : Outcome × State :=
  let status := rangeStatus access region offset length
  -- A range check is a pure preflight.  Both acceptance and rejection leave the
  -- successful-access trace unchanged.
  (⟨status, 0⟩, state)

/-- Total, fuel-bounded interpreter for source Action syntax.  The fuel diagnostic
is a model traversal outcome and is distinct from semantic status 9. -/
def evaluate : Nat → State → Action → Except Diagnostic Evaluation
  | 0, _, _ => .error {
      code := .fuelExhausted
      message := "Action model traversal fuel exhausted"
    }
  | fuel + 1, state, action => do
      match action with
      | .done status value => pure { outcome := ⟨status, value⟩, state }
      | .bind first next =>
          let first ← evaluate fuel state first
          evaluate fuel first.state (next first.outcome.status first.outcome.value)
      | .load8 region offset next =>
          let (outcome, state) ← load state .w8 region offset
          evaluate fuel state (next outcome.status outcome.value)
      | .load32 region offset next =>
          let (outcome, state) ← load state .w32 region offset
          evaluate fuel state (next outcome.status outcome.value)
      | .load64 region offset next =>
          let (outcome, state) ← load state .w64 region offset
          evaluate fuel state (next outcome.status outcome.value)
      | .store8 region offset value next =>
          let (outcome, state) ← store state .w8 region offset value.toUInt64
          evaluate fuel state (next outcome.status)
      | .store32 region offset value next =>
          let (outcome, state) ← store state .w32 region offset value.toUInt64
          evaluate fuel state (next outcome.status)
      | .store64 region offset value next =>
          let (outcome, state) ← store state .w64 region offset value
          evaluate fuel state (next outcome.status)
      | .checkReadRange region offset length next =>
          let (outcome, state) := checkRange state .read region offset length
          evaluate fuel state (next outcome.status)
      | .checkWriteRange region offset length next =>
          let (outcome, state) := checkRange state .write region offset length
          evaluate fuel state (next outcome.status)
      | .boundedFoldU64 budget step count initial ctx0 ctx1 ctx2 ctx3 next =>
          if count.toNat > budget then
            evaluate fuel state (next Status.budgetExceeded initial)
          else
            let rec go : Nat → UInt32 → UInt64 → State →
                Except Diagnostic Evaluation
              | 0, _, accumulator, state =>
                  evaluate fuel state (next Status.ok accumulator)
              | remaining + 1, index, accumulator, state => do
                  let result ← evaluate fuel state
                    (step index count accumulator ctx0 ctx1 ctx2 ctx3)
                  if result.outcome.status == Status.ok then
                    go remaining (index + 1) result.outcome.value result.state
                  else
                    evaluate fuel result.state
                      (next result.outcome.status result.outcome.value)
            go count.toNat 0 initial state
      | .uartReadStatus _ => .error {
          code := .deviceActionUnsupported
          message := "the core0-v0.4 finite RAM model does not interpret UART actions"
        }
      | .uartReadByte _ => .error {
          code := .deviceActionUnsupported
          message := "the core0-v0.4 finite RAM model does not interpret UART actions"
        }
      | .uartWriteByte _ _ => .error {
          code := .deviceActionUnsupported
          message := "the core0-v0.4 finite RAM model does not interpret UART actions"
        }
      | .uartEnableAndResetFifo _ | .uartEnableAndResetFifo14 _ => .error {
          code := .deviceActionUnsupported
          message := "the core0-v0.4 finite RAM model does not interpret UART actions"
        }
      | .trapEcall _ => .error {
          code := .trapActionUnsupported
          message := "the finite RAM model does not simulate synchronous trap actions"
        }
      | .trapBreakpoint _ => .error {
          code := .trapActionUnsupported
          message := "the finite RAM model does not simulate synchronous trap actions"
        }
      | .trapUnexpectedEcall _ => .error {
          code := .trapActionUnsupported
          message := "the finite RAM model does not simulate synchronous trap actions"
        }
      | .trapIllegalInstruction _ => .error {
          code := .trapActionUnsupported
          message := "the finite RAM model does not simulate synchronous trap actions"
        }
      | .timerReadTime _ | .timerSetCompare _ _ | .timerReadPending _ |
          .irqSaveDisable _ | .irqRestore _ _ | .timerSetInterrupt _ _ |
          .timerProbe _ => .error {
          code := .timerActionUnsupported
          message := "the finite RAM model does not simulate timer/interrupt actions"
        }
      | .loop _ => .error {
          code := .loopActionUnsupported
          message := "the finite RAM model does not execute unbounded production loops"
        }
      | .managed2 .. | .managedSums2 .. => .error {
          code := .executionActionUnsupported
          message := "the finite RAM model does not execute managed allocation/ownership IR"
        }
      | .platform .. => .error {
          code := .executionActionUnsupported
          message := "the finite RAM model does not simulate production privilege/memory actions"
        }


def evaluateDefault (state : State) (action : Action) : Except Diagnostic Evaluation :=
  evaluate 65536 state action

end Lemma.Core0.Memory.Model
