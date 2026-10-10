/-! Authoritative Task 003 single-hart RV64 boot and owned-memory layout.
The frame pool is a reserved subset of the pinned 128 MiB RAM, not all RAM.
No host-assigned task frames or page tables appear in this layout. -/
namespace Lemma.Platform.LemmaVM.Layout

def ramBase : Nat := 0x80000000
def ramLimit : Nat := 0x88000000
def firmwareBase : Nat := 0x80000000
def firmwareLimit : Nat := 0x80010000
def privateBase : Nat := 0x80100000
def privateLimit : Nat := 0x80110000
def firmwareStackTop : Nat := 0x80110000
def supervisorBase : Nat := 0x80200000
def supervisorLimit : Nat := 0x80300000
def metadataValue : UInt64 := 0x80400000
def metadataBase : Nat := metadataValue.toNat
def metadataLimit : Nat := 0x80500000
/-- Checked owner1/purpose1 object-table handle. Zero retains legacy profiles;
managed entries initialize this control cell before constructing any task. -/
def capabilityControlValue : UInt64 := 0x80400620
/-- Boot-cleared checked input-frame handle. Zero selects the historical raw
UART route; service boot may publish it once and has no runtime reset API. -/
def inputControlValue : UInt64 := 0x80400660
def supervisorStackBase : Nat := 0x80500000
def supervisorStackTop : Nat := 0x80510000
/-- The first stack page is fixed supervisor context storage; live call stacks
start above it. This context is reserved, never a task-owned allocator frame. -/
def kernelResumeContext : Nat := 0x80500000
def contextBytes : Nat := 288
def bootStackFloor : Nat := 0x80501000
def packageBase : Nat := 0x80600000
def packageLimit : Nat := 0x80700000
def poolValue : UInt64 := 0x82000000
def poolBase : Nat := poolValue.toNat
def poolLimit : Nat := 0x82200000
def frameBytesValue : UInt64 := 4096
def frameCountValue : UInt64 := 512
def frameBytes : Nat := frameBytesValue.toNat
def frameCount : Nat := frameCountValue.toNat
def taskKernelStackPagesValue : UInt64 := 2
def taskKernelStackBytesValue : UInt64 := 8192
def taskKernelStackPages : Nat := taskKernelStackPagesValue.toNat
def taskKernelStackBytes : Nat := taskKernelStackBytesValue.toNat
def userTextBase : Nat := 0x10000
def userTextLimit : Nat := 0x1f000
def userDataBase : Nat := 0x20000
def userDataBytes : Nat := 4096
def userStackBase : Nat := 0x3fffc000
def userStackPages : Nat := 2
def uartBase : Nat := 0x10000000
def finisherBase : Nat := 0x00100000
def dtbReserveBase : Nat := 0x87e00000
def dtbReserveLimit : Nat := 0x88000000

structure Interval where
  name : String
  base : Nat
  limit : Nat
  purpose : String
  deriving Repr

def intervals : Array Interval := #[
  ⟨"firmware", firmwareBase, firmwareLimit, "M-mode code, denied to S/U by PMP"⟩,
  ⟨"firmware-private", privateBase, privateLimit, "M stack and trap storage"⟩,
  ⟨"supervisor", supervisorBase, supervisorLimit, "S code and immutable data"⟩,
  ⟨"metadata", metadataBase, metadataLimit, "kernel-owned fixed-capacity objects"⟩,
  ⟨"supervisor-stack", supervisorStackBase, supervisorStackTop, "reserved resume context and boot/reaper stack"⟩,
  ⟨"boot-package", packageBase, packageLimit, "immutable separately compiled user images"⟩,
  ⟨"frame-pool", poolBase, poolLimit, "runtime allocator's sole frame supply"⟩,
  ⟨"dtb-reserve", dtbReserveBase, dtbReserveLimit, "pinned QEMU boot DTB envelope"⟩
]

def valid : Bool :=
  poolLimit - poolBase == frameCount * frameBytes &&
  taskKernelStackPages == 2 && taskKernelStackBytes == taskKernelStackPages * frameBytes &&
  contextBytes < taskKernelStackBytes &&
  supervisorStackBase ≤ kernelResumeContext && kernelResumeContext % 16 == 0 &&
  contextBytes == 288 && contextBytes % 16 == 0 &&
  kernelResumeContext + contextBytes ≤ bootStackFloor &&
  bootStackFloor % frameBytes == 0 && bootStackFloor < supervisorStackTop &&
  intervals.all (fun i => ramBase ≤ i.base && i.base < i.limit && i.limit ≤ ramLimit &&
    i.base % frameBytes == 0 && i.limit % frameBytes == 0) &&
  intervals.all (fun a => intervals.all (fun b =>
    a.name == b.name || a.limit ≤ b.base || b.limit ≤ a.base))

end Lemma.Platform.LemmaVM.Layout
