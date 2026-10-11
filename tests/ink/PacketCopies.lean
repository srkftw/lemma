import Lemma.Kernel.IPCStorage
import Lemma.Services.Store.Format
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only literal byte oracle for both production bounded packet copies.
Aligned words preserve exact forward-copy semantics, including overlap. This
fixture does not emulate the CPU or certify compiler/ownership correctness. -/
namespace PacketCopiesFixture
open Lemma.Core0.Memory
structure State where
  bytes : Std.HashMap UInt64 UInt64 := {}
  reads64 : Nat := 0
  reads8 : Nat := 0
  writes : Nat := 0
  rejectRead : Option UInt64 := none
  rejectWrite : Option UInt64 := none

def get (s : State) (a : UInt64) : UInt64 := s.bytes.getD a 0
def put (s : State) (a v : UInt64) : State := { s with bytes := s.bytes.insert a (v &&& 255) }
def word (s : State) (a : UInt64) : UInt64 := Id.run do
  let mut value := (0 : UInt64)
  for i in [:8] do value := value ||| (get s (a + i.toUInt64) <<< (i.toUInt64 * 8))
  return value

def putWord (s : State) (a v : UInt64) : State := Id.run do
  let mut next := s
  for i in [:8] do next := put next (a + i.toUInt64) (v >>> (i.toUInt64 * 8))
  return next

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => return (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    if budget < count.toNat then execute state (next 9 initial) else
    let mut acc := initial
    let mut status := (0 : UInt8)
    for i in [:count.toNat] do
      if status = 0 then
        let r ← execute state (step i.toUInt32 count acc a b c d)
        status := r.1
        acc := r.2
    execute state (next status acc)
  | .platform op a b _ _ _ _ next =>
    match op with
    | .physicalRead8 | .virtualRead8 =>
      state.modify fun s => { s with reads8 := s.reads8 + 1 }
      if (← state.get).rejectRead = some a then execute state (next 13 0) else
      execute state (next 0 (get (← state.get) a))
    | .physicalWrite8 | .virtualWrite8 =>
      state.modify fun s => { s with writes := s.writes + 1 }
      if (← state.get).rejectWrite = some a then execute state (next 13 0) else
      state.modify fun s => put s a b
      execute state (next 0 0)
    | .physicalRead64 | .virtualRead64 =>
      if a % 8 ≠ 0 then throw <| IO.userError "unaligned word read"
      state.modify fun s => { s with reads64 := s.reads64 + 1 }
      if (← state.get).rejectRead = some a then execute state (next 13 0) else
      execute state (next 0 (word (← state.get) a))
    | .physicalWrite64 | .virtualWrite64 =>
      if a % 8 ≠ 0 then throw <| IO.userError "unaligned word write"
      state.modify fun s => { s with writes := s.writes + 1 }
      if (← state.get).rejectWrite = some a then execute state (next 13 0) else
      state.modify fun s => putWord s a b
      execute state (next 0 0)
    | _ => throw <| IO.userError "unexpected packet copy effect"
  | _ => throw <| IO.userError "unexpected packet copy action"

def literal (s : State) (source destination length : UInt64) : State := Id.run do
  let mut next := s
  for i in [:length.toNat] do next := put next (destination + i.toUInt64) (get next (source + i.toUInt64))
  return next

def check : IO Unit := do
  let mut cases := 0
  for kernel in [false,true] do
    let base := if kernel then (0x82001000 : UInt64) else 0x20000
    for length in [0,1,7,8,13,72,128,192,256,512] do
      for offset in [0,1,7] do
        for distance in [1,8,1024] do
          for reverse in [false,true] do
            let first := base + offset
            let second := first + distance
            let source := if reverse then second else first
            let destination := if reverse then first else second
            let mut initial := ({} : State)
            for i in [:2048] do initial := put initial (base + i.toUInt64) ((i.toUInt64 * 29 + 11) % 256)
            let expected := literal initial source destination length
            let state ← IO.mkRef initial
            let action := if kernel then Lemma.Kernel.IPCStorage.copyBytes source destination length
                          else Lemma.Services.Store.Format.copy source destination length
            let (status,copied) ← execute state action
            let actual ← state.get
            if kernel && 256 < length then
              if status ≠ 255 || actual.reads8 ≠ 0 || actual.reads64 ≠ 0 || actual.writes ≠ 0 then
                throw <| IO.userError "oversized kernel packet changed bytes"
            else
              if status ≠ 0 || copied ≠ length then
                throw <| IO.userError s!"copy byte/guard/overlap mismatch {kernel} {length} {offset} {distance} {reverse}"
              let aligned := (source ||| destination ||| length) &&& 7 == 0
              if aligned then
                if actual.reads64 ≠ length.toNat / 8 || actual.reads8 ≠ 0 then
                  throw <| IO.userError "aligned copy did not use exact complete words"
              else if actual.reads8 ≠ length.toNat || actual.reads64 ≠ 0 then
                throw <| IO.userError "unaligned/partial copy changed its byte semantics"
            let reference := if kernel && 256 < length then initial else expected
            if actual.bytes.size ≠ reference.bytes.size then
              throw <| IO.userError "copy modified bytes outside the guarded region"
            for i in [:2048] do
              if get actual (base + i.toUInt64) ≠ get reference (base + i.toUInt64) then
                throw <| IO.userError s!"literal byte mismatch {kernel} {length} {offset} {distance} {reverse} at {i}"
            cases := cases + 1
  for (source,destination,length) in [(0xfffffffffffffff8,0x21000,16),
                                    (0x21000,0xfffffffffffffff8,16),
                                    (0x21000,0x22000,513)] do
    let state ← IO.mkRef ({} : State)
    let (status,_) ← execute state (Lemma.Services.Store.Format.copy source destination length)
    let actual ← state.get
    if status = 0 || actual.reads64 ≠ 0 || actual.reads8 ≠ 0 || actual.writes ≠ 0 then
      throw <| IO.userError "invalid span accessed memory"
  let mut failures := 0
  for kernel in [false,true] do
    for aligned in [false,true] do
      let source := if aligned then (0x82001000 : UInt64) else 0x82001001
      let destination := source + 1024
      let length := if aligned then (24 : UInt64) else 13
      let unit := if aligned then (8 : UInt64) else 1
      for offset in [0,unit,unit*2] do
        for read in [false,true] do
          let initial : State := if read then { rejectRead := some (source + offset) }
                                 else { rejectWrite := some (destination + offset) }
          let state ← IO.mkRef initial
          let (status,_) ← execute state (if kernel then Lemma.Kernel.IPCStorage.copyBytes source destination length
                                         else Lemma.Services.Store.Format.copy source destination length)
          let actual ← state.get
          let reads := actual.reads64 + actual.reads8
          if status = 0 || reads ≠ offset.toNat / unit.toNat + 1 ||
             actual.writes ≠ offset.toNat / unit.toNat + (if read then 0 else 1) then
            throw <| IO.userError "failed copy continued or reported success"
          failures := failures + 1
  IO.println s!"PASS: {cases} literal packet copies and {failures} injected failures; limits, overflow, overlap, alignment and preserved bytes"
end PacketCopiesFixture
run_cmd do Lean.Elab.Command.liftIO PacketCopiesFixture.check
