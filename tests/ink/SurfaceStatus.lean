import Lemma.Platform.LemmaSim.DeviceService
import Lean.Elab.Command

/-! Host Action boundary fixture only. Literal invalid arguments and a zero
capability must cause no MMIO. The allowed query reads one literal v1 register;
CPU/PLIC/controller lifecycle remain separate actual device observations. -/
namespace SurfaceStatusFixture
open Lemma.Core0.Memory

partial def execute (reads : IO.Ref Nat) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status,value)
  | .bind first next =>
    let (status,value) ← execute reads first
    execute reads (next status value)
  | .platform .deviceRead64 address _ _ _ _ _ next =>
    if address ≠ 0x10010010 then throw <| IO.userError "unexpected status MMIO address"
    reads.modify (· + 1)
    execute reads (next 0 5)
  | .platform .physicalRead64 address _ _ _ _ _ next =>
    if address ≠ 0x80400c58 then throw <| IO.userError "unexpected paper IRQ state read"
    execute reads (next 0 0)
  | _ => throw <| IO.userError "unexpected status fixture operation"

def check : IO Unit := do
  for (fields,pixels) in #[(1,0),(0,1),(0x20200,0x20500)] do
    let reads ← IO.mkRef 0
    let result ← execute reads (Lemma.Platform.LemmaSim.DeviceService.surfaceStatus fields pixels)
    if result ≠ (16,0) || (← reads.get) ≠ 0 then
      throw <| IO.userError "invalid status arguments reached MMIO"
  let reads ← IO.mkRef 0
  let result ← execute reads (Lemma.Platform.LemmaSim.DeviceService.surface 0 0 4 0 0 0)
  if result ≠ (80,0) || (← reads.get) ≠ 0 then
    throw <| IO.userError "unauthorized status query reached MMIO"
  if (← execute reads (Lemma.Platform.LemmaSim.DeviceService.surfaceStatus 0 0)) ≠ (0,5) || (← reads.get) ≠ 1 then
    throw <| IO.userError "valid status query differs from literal single register read"

end SurfaceStatusFixture
open Lean Elab Command
run_cmd do
  liftIO SurfaceStatusFixture.check
  logInfo "SURFACE_STATUS:PASS unauthorized/invalid noMMIO; valid single controller-read; host Action boundary only"
