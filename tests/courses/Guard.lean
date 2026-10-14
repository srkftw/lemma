import Lemma.Services.Store.Server
import Lemma.Courses.PackageReference

/-! Independent finite RAM executes the actual opt-in Store Actions. It permits
only RAM, a fixed time sample and opaque IPC replies; any backing syscall fails.
This is a component fixture, not RV64 execution or a durable-media qualification. -/
namespace CourseGuardTests
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Services.Store
open Lemma.Courses

structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 327680 0)
  reads : Array UInt64 := #[]
  writes : Array UInt64 := #[]
  replies : Array (UInt64 × Array UInt64) := #[]
  failRead : Option Nat := none

private def read (model : Model) (address width : UInt64) : Except String UInt64 := do
  if address < 0x20000 || model.memory.size.toUInt64 < width ||
      model.memory.size.toUInt64 - width < address - 0x20000 then throw "guard fixture read escaped owned RAM"
  return (List.range width.toNat).foldl (fun value i =>
    value ||| (model.memory[(address-0x20000).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0

private def set (model : Model) (address value : UInt64) : IO Model := do
  let _ ← IO.ofExcept <| read model address 8
  let memory := (List.range 8).foldl (fun bytes i =>
    bytes.set! ((address-0x20000).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) model.memory
  return {model with memory}

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
      let (s,value) ← run state first
      run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if budget < count.toNat then throw <| IO.userError "guard fixture exceeded a genuine fold bound"
      let mut status : UInt8 := 0
      let mut value := initial
      for i in [:count.toNat] do
        if status == 0 then
          let (s,result) ← run state (step i.toUInt32 count value a b c d)
          status := s
          value := result
      run state (next status value)
  | .platform operation a b c d e f next => do
      let model ← state.get
      match operation with
        | .virtualRead8 | .virtualRead64 =>
          state.modify fun m => {m with reads := m.reads.push a}
          if model.failRead == some model.reads.size then run state (next 33 0) else
          let width := if operation == .virtualRead8 then 1 else 8
          run state (next 0 (← IO.ofExcept <| read model a width))
        | .virtualWrite8 | .virtualWrite64 =>
          let width := if operation == .virtualWrite8 then 1 else 8
          let _ ← IO.ofExcept <| read model a width
          let memory := (List.range width.toNat).foldl (fun bytes i =>
            bytes.set! ((a-0x20000).toNat+i) ((b >>> (i.toUInt64*8)).toUInt8)) model.memory
          state.set {model with memory, writes := model.writes.push a}
          run state (next 0 0)
        | .syscall =>
          if a == ABI.time then
            if b ||| c ||| d ||| e ||| f != 0 then throw <| IO.userError "time sample arguments changed"
            run state (next 0 100)
          else if a == IPCABI.reply then
            if b != 16 || c != Server.outgoing || d != 64 || f != 0 then
              throw <| IO.userError "guard acquired malformed reply authority/framing"
            let mut words : Array UInt64 := #[]
            for i in [:8] do words := words.push (← IO.ofExcept <| read model (c+i.toUInt64*8) 8)
            state.modify fun m => {m with replies := m.replies.push (e,words)}
            run state (next 0 0)
          else throw <| IO.userError "preflight acquired backing I/O or an undeclared syscall"
        | _ => throw <| IO.userError "guard acquired undeclared platform effects"
  | _ => throw <| IO.userError "guard acquired undeclared Action syntax"

private def initial : IO Model := do
  let mut model : Model := {}
  for (address,value) in #[(Server.state+24,1),(Server.context+24,Server.buffer),
      (Server.context+40,37),(Server.context+48,4096),(Server.context+56,1),
      (Server.context+72,8),(Server.context+80,2044),(Server.context+96,37),
      (Server.context+104,Server.index0)] do model ← set model address value
  return model

private def request (model : Model) (operation ns object count : UInt64) : IO Model := do
  let mut result := model
  for (offset,value) in #[(0,0x31525453414d454c),(8,1),(16,operation),(24,ns),
      (32,object),(40,7),(48,0),(56,count)] do
    result ← set result (Server.incoming+64+offset) value
  return result

private def observed (model : Model) (action : Action) : IO ((UInt8 × UInt64) × Model) := do
  let state ← IO.mkRef model
  let value ← run state action
  return (value,← state.get)

def check : IO Unit := do
  let key : UInt64 := 0x4350000100000001
  let empty ← initial
  let (value,unchanged) ← observed empty (Server.courseAbsent 1 key)
  if value != (0,0) || unchanged.memory != empty.memory || !unchanged.writes.isEmpty then
    throw <| IO.userError "empty-edition preflight mutated state"
  for kind in #[1,2] do
    let row := Server.index0 + 456*48 -- independently calculated pinned hash slot
    let present ← set (← set (← set empty row 1) (row+8) key) (row+40) kind
    let (value,unchanged) ← observed present (Server.courseAbsent 1 key)
    if value != (223,0) || unchanged.memory != present.memory || !unchanged.writes.isEmpty then
      throw <| IO.userError "installed/tombstoned key was reused or mutated"
    for operation in #[2,6] do
      let offered ← request present operation 1 key (if operation == 2 then 4040 else 0)
      let (value,rejected) ← observed offered (Server.courseApplication 11 16 64)
      if value != (0,0) || rejected.replies.size != 1 || rejected.replies[0]!.1 != 223 ||
          rejected.memory.extract (Server.state-0x20000).toNat (Server.state+192-0x20000).toNat !=
          offered.memory.extract (Server.state-0x20000).toNat (Server.state+192-0x20000).toNat ||
          rejected.memory.extract 131072 135168 != offered.memory.extract 131072 135168 then
        throw <| IO.userError "reject altered staging/engine state or entered backing work"
  for key in #[0x4350000000000001,0x4350000100000000] do
    let (value,rejected) ← observed empty (Server.courseAbsent 1 key)
    if value != (220,0) || !rejected.reads.isEmpty || !rejected.writes.isEmpty then
      throw <| IO.userError "invalid reserved key touched metadata"
  for call in [:3] do
    let (value,rejected) ← observed {empty with failRead := some call} (Server.courseAbsent 1 key)
    if value != (33,0) || rejected.reads.size != call+1 || !rejected.writes.isEmpty then
      throw <| IO.userError "guard read failure lost status/continued/mutated"
  for ns in #[1,2] do
    let offered ← request empty 2 ns 42 128
    let (legacy,a) ← observed offered (Server.application 11 16 64)
    let (guarded,b) ← observed offered (Server.courseApplication 11 16 64)
    if legacy != guarded || a.memory != b.memory || a.replies != b.replies then
      throw <| IO.userError "ordinary namespace/object staging behavior changed"
  let image ← match Package.encode PackageReference.arithmetic with
    | .ok image => pure image | .error error => throw <| IO.userError error.render
  let mut staged ← request empty 4 1 key 0
  for (offset,value) in #[(48,11),(64,1),(72,key),(80,7),(88,image.size.toUInt64),(96,image.size.toUInt64)] do
    staged ← set staged (Server.state+offset) value
  let memory := image.data.foldl (fun (pair : ByteArray × Nat) byte =>
    (pair.1.set! ((Server.payload-0x20000).toNat + pair.2) byte,pair.2+1)) (staged.memory,0) |>.1
  staged := {staged with memory}
  let (queued,accepted) ← observed staged (Server.courseApplication 11 16 64)
  if queued != (0,0) || !accepted.replies.isEmpty || (← IO.ofExcept <| read accepted Server.context 8) != 2 then
    throw <| IO.userError "valid package commit did not defer to the real append engine"
  let corrupted := {staged with memory := staged.memory.set! ((Server.payload-0x20000).toNat+image.size-1) 0}
  let (_,rejected) ← observed corrupted (Server.courseApplication 11 16 64)
  if rejected.replies.size != 1 || rejected.replies[0]!.1 != 229 ||
      (← IO.ofExcept <| read rejected Server.context 8) != 0 then
    throw <| IO.userError "corrupt package started an append or hid integrity failure"
  IO.println "COURSE_STORE_GUARD:PASS absent/present/tombstone keys,begin/delete no-I/O rejection,invalid keys,exact read faults,two ordinary namespaces,full package commit deferred and corrupt package rejected"

end CourseGuardTests

def main : IO Unit := CourseGuardTests.check
