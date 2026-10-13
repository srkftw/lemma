import Lemma.Core0.Execution

open Lemma.Core0 Lemma.Core0.Execution
private def require (b : Bool) (label : String) : IO Unit :=
  if b then pure () else throw <| IO.userError label
private def contains (p : Profile) (address width : Nat) (write : Bool) : Bool :=
  (memoryRegions p).any fun r => r.start ≤ address && width ≤ r.stop - address &&
    address < r.stop && (!write || r.writable)
#eval show IO Unit from do
  require (memoryRegionsValid .boot_v0_1) "bounded3072 discovery authority invalid"
  require (memoryRegions .boot_v0_1 == #[
    ⟨"boot-loaded-image",0x80000000,0x81f00000,true⟩,
    ⟨"boot-private-scratch",0x81fc0000,0x81fc4000,true⟩,
    ⟨"boot-loaded-discovery",0x87e00000,0x87e00c00,true⟩]) "boot intervals differ"
  require (contains .boot_v0_1 0x87e00000 8 true && contains .boot_v0_1 0x87e00bf8 8 true &&
    contains .boot_v0_1 0x87e00bff 1 true && !contains .boot_v0_1 0x87e00bf9 8 true &&
    !contains .boot_v0_1 0x87e00c00 1 true && !contains .boot_v0_1 0x87dfffff 1 true)
    "discovery byte/word exclusive boundaries differ"
  require (deviceRegionsFor .boot_v0_1 .deviceRead64 == #[⟨"boot-nv-controller",0x10012000,0x10012400,true⟩] &&
    deviceRegionsFor .boot_v0_1 .deviceWrite32 == #[]) "boot NV width/aperture differs"
  for op in ([.virtualRead64,.virtualWrite64,.syscall,.installSatp,.enterUser,.firmwareCall,
      .readTime,.writeMachineCycle,.waitInterrupt,.deviceRead32] : List Op) do
    require (!Op.admits .boot_v0_1 op) "boot inherited forbidden execution authority"
  for p in ([.firmware_v0_1,.kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,.kernel_v0_5,.kernel_v0_6,
      .user_v0_1,.user_v0_2] : List Profile) do
    require (memoryRegionsValid p) "historical region alignment invalid"
    require (!contains p 0x81fc0000 8 true && !contains p 0x87e00000 8 true)
      "historical profile gained boot write authority"
    require (!(deviceRegionsFor p .deviceRead64).any (fun r => r.name == "boot-nv-controller"))
      "historical profile gained NV aperture"
  IO.println "BOOT_AUTHORITY:PASS exactdiscovery/width/exclusivebounds/deniedops/legacyregions"
