import Lemma.Kernel.Objects
import Lemma.Kernel.IPCStorage
import Lean.Elab.Command

/-! Execute the actual production read Actions against an independently
controlled primitive outcome. These are semantic failure/order tests, not a
proof of the compiler, hardware or physical memory. No result enters a guest. -/
namespace PoolReadRefinement
open Lemma.Core0.Memory

private def require (condition : Bool) (message : String) : IO Unit :=
  if condition then pure () else throw <| IO.userError message

private partial def execute (events : IO.Ref (Array UInt64)) (status : UInt8)
    (value : UInt64) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s, v)
  | .bind first next =>
    let (s, v) ← execute events status value first
    execute events status value (next s v)
  | .platform .physicalRead64 address b c d e f next =>
    require (b = 0 && c = 0 && d = 0 && e = 0 && f = 0)
      "changed physical-read arguments"
    events.modify (·.push address)
    execute events status value (next status value)
  | _ => throw <| IO.userError "unexpected operation in production get"

def main : IO Unit := do
  let addresses : Array UInt64 := #[0, 0x80400000, 0x81fffff8, 0x82000000,
    0x82000001, 0x82000008, 0x821ffff8, 0x821ffff9, 0x82200000,
    0x83fffff8, 0xfffffffffffffff8, 0xffffffffffffffff]
  let mut checked := 0
  for (name, get) in #[("Objects", Lemma.Kernel.Objects.get),
                       ("IPCStorage", Lemma.Kernel.IPCStorage.get)] do
    for address in addresses do
      -- Even injected errors on an otherwise admissible address must retain
      -- the original fatal mapping. No inferred-success branch may discard it.
      for status in #[0, 255] do
        let events ← IO.mkRef #[]
        let value := address ^^^ 0x6c656d6d615f7264
        let actual ← execute events status value (get address)
        let expected := if status = 0 then (0, value) else (255, 0)
        require (actual = expected) (name ++ " changed status/value")
        require ((← events.get) = #[address]) (name ++ " changed read order/count/address")
        checked := checked + 1
  IO.println s!"POOL_READ_REFINEMENT:PASS {checked} production Action boundary/error observations; compiler/RV64 execution separate"

end PoolReadRefinement
open Lean Elab Command
run_cmd liftIO PoolReadRefinement.main
