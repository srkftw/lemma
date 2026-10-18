import Lemma.Core0.Execution
import Lemma.Platform.RiscV.ExecutionPrimitives
import Lemma.Multimodal.Permissions
import Lean
open Lemma.Core0 Lemma.Core0.Execution
private def contains (p : Profile) (a : Nat) (o : Op := .deviceRead64) : Bool :=
  (deviceRegionsFor p o).any fun r => r.start ≤ a && a + (if o == .deviceRead32 then 4 else 8) ≤ r.stop
#eval do
  let old := #[Profile.kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,.kernel_v0_5,
    .kernel_v0_6,.kernel_v0_7,.kernel_v0_8,.boot_v0_1,.boot_v0_2,.firmware_v0_1,.user_v0_1,.user_v0_7]
  for p in old do
    if contains p 0x10014000 then throw <| IO.userError "historical profile acquired controller authority"
    if contains p 0x0c00004c .deviceRead32 then throw <| IO.userError "historical profile acquired IRQ19"
  unless contains .kernel_v0_9 0x10014000 && contains .kernel_v0_9 0x10015ff8 &&
      !contains .kernel_v0_9 0x10016000 && !contains .kernel_v0_9 0x10013ff8 &&
      !contains .kernel_v0_9 0x10012000 && !contains .kernel_v0_9 0x10013000 &&
      contains .kernel_v0_9 0x0c00004c .deviceRead32 do
    throw <| IO.userError "Kernel9 region boundary differs"
  let c : Lemma.Platform.RiscV.ExecutionPrimitives.Configuration := {
    stage := .supervisor, kernelMain := "kernel",firmwareDispatcher := "fw",
    supervisorDispatcher := "dispatch",lemmasim := true,multimodal := true }
  unless c.validate.isOk && !({c with productBoot := true}).validate.isOk &&
    !({c with commonOFDM := true}).validate.isOk && !({c with lemmasim := false}).validate.isOk &&
    !({c with stage := .bootstrapM}).validate.isOk do
    throw <| IO.userError "exclusive PMP selector failed"
  let p := Lemma.Multimodal.Permissions.permits
  unless p 1 4 1 1 1 1 100 0 = 7 && p 3 2 1 2 1 1 100 0 = 4 &&
      p 3 2 1 1 1 2 100 0 = 4 && p 3 2 1 1 1 1 100 100 = 8 &&
      p 3 2 1 1 1 1 100 99 = 0 &&
      Lemma.Multimodal.Permissions.nextEpoch 0x7ffffffffffffffe = 0 do
    throw <| IO.userError "purpose/epoch/session/expiry boundary failed"
  IO.println "MULTIMODAL_AUTHORITY:PASS"
