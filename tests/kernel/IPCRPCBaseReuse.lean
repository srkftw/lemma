import tests.kernel.IPCCallBaseReuse
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.Kernel Lemma.User
open CallBorrowFaults

namespace RPCBorrow
def same (snapshot : State) (old fresh : Action) (baseTrace : Array Request) : IO (Nat × Nat) := do
  require (baseTrace.all fun r => r.op = .physicalRead64 && r.status = 0) "only successful immutable whole-base reads may be projected"
  let beforeRef ← IO.mkRef snapshot
  let afterRef ← IO.mkRef snapshot
  let before ← execute beforeRef old
  let after ← execute afterRef fresh
  let a ← beforeRef.get
  let b ← afterRef.get
  require (before == after && a.words == b.words) s!"actual result/RAM differ {before} vs {after}"
  let mut i := 0
  let mut j := 0
  while i < a.requests.size do
    let first := a.requests.extract i (i+baseTrace.size)
    let second := b.requests.extract j (j+baseTrace.size)
    if first == baseTrace && first != second then i := i+baseTrace.size else
      require (j < b.requests.size && a.requests[i]! == b.requests[j]!) s!"ordered request differs beyond independently validated whole-base duplication at {i}/{j}"
      i := i+1
      j := j+1
  require (j == b.requests.size) "new request suffix"
  return (a.requests.size,b.requests.size)

def faults (snapshot : State) (old fresh : Action) (baseTrace : Array Request) : IO Nat := do
  let ref ← IO.mkRef snapshot
  discard <| execute ref old
  let unique := (← ref.get).requests.foldl (fun acc row => if acc.contains row.address then acc else acc.push row.address) (#[] : Array UInt64)
  for address in unique do
    discard <| same {snapshot with failRead := some address} old fresh baseTrace
    discard <| same {snapshot with failWrite := some address} old fresh baseTrace
  return unique.size*2

def check (expanded : Bool) : IO Unit := do
  let ref ← IO.mkRef ({} : State)
  discard <| success ref (Frames.configure (if expanded then 8192 else 512) (if expanded then 8192 else 32) 4)
  discard <| success ref Frames.init
  discard <| success ref Objects.init
  let server ← success ref (AddressSpace.create 2)
  let caller ← success ref (AddressSpace.create 3)
  discard <| success ref (Capability.attach server)
  discard <| success ref (Capability.attach caller)
  let endpoint ← success ref (Objects.createEndpoint server)
  let receiver ← success ref (Capability.grantBoot server endpoint CapabilityABI.endpointReceive)
  let sender ← success ref (Capability.grantBoot caller endpoint CapabilityABI.endpointCall)
  discard <| success ref (Capability.activate server)
  discard <| success ref (Capability.activate caller)
  let callerPage ← success ref (Frames.allocate 3 4)
  let serverPage ← success ref (Frames.allocate 2 4)
  discard <| success ref (AddressSpace.mapUser caller 0x40000 callerPage 3)
  discard <| success ref (AddressSpace.mapUser server 0x40000 serverPage 3)
  let callerPA ← success ref (Frames.resolvePurpose 3 callerPage 4)
  let serverPA ← success ref (Frames.resolvePurpose 2 serverPage 4)
  for i in [:24] do ref.modify fun s => put s (callerPA+i.toUInt64*8) (0x0102030405060708+i.toUInt64)
  for i in [:8] do ref.modify fun s => put s (serverPA+256+i.toUInt64*8) (0x0807060504030201+i.toUInt64)
  let empty := reset (← ref.get)
  discard <| success ref (IPC.callBeginWithLimit IPCABI.lemmaSimMaximumTicks caller sender 0x40000 192 77 1000000)
  let offered := reset (← ref.get)
  let baseRef ← IO.mkRef offered
  discard <| success baseRef (AddressSpace.base server)
  let baseTrace := (← baseRef.get).requests
  let oldReceive := IPC.receive server receiver 0x40000 256 0 IPCABI.nonblocking
  let newReceive := IPC.receiveWithLimit IPCABI.lemmaSimMaximumTicks server receiver 0x40000 256 0 IPCABI.nonblocking
  let received ← same offered oldReceive newReceive baseTrace
  let receiveFaults ← faults offered oldReceive newReceive baseTrace
  for capacity in #[0,63,64,255,256,257] do
    discard <| same offered (IPC.receive server receiver 0x40000 capacity 0 IPCABI.nonblocking)
      (IPC.receiveWithLimit IPCABI.lemmaSimMaximumTicks server receiver 0x40000 capacity 0 IPCABI.nonblocking) baseTrace
  for pointer in #[0x40001,0x40fff,0x50000,0xffffffffffffffff] do
    discard <| same offered (IPC.receive server receiver pointer 256 0 IPCABI.nonblocking)
      (IPC.receiveWithLimit IPCABI.lemmaSimMaximumTicks server receiver pointer 256 0 IPCABI.nonblocking) baseTrace
  for handle in #[receiver+16,0] do
    discard <| same offered (IPC.receive server handle 0x40000 256 0 IPCABI.nonblocking)
      (IPC.receiveWithLimit IPCABI.lemmaSimMaximumTicks server handle 0x40000 256 0 IPCABI.nonblocking) baseTrace
  discard <| same empty oldReceive newReceive baseTrace
  let deliveredRef ← IO.mkRef offered
  discard <| success deliveredRef oldReceive
  let delivered := reset (← deliveredRef.get)
  let replyHandle := word delivered (serverPA+32)
  require (replyHandle > 0) "actual one-use reply handle"
  let oldReply := IPC.reply server replyHandle 0x40100 64 0
  let newReply := IPC.replyLocal server replyHandle 0x40100 64 0
  let replied ← same delivered oldReply newReply baseTrace
  let replyFaults ← faults delivered oldReply newReply baseTrace
  for length in #[0,64,128,189,192,193] do
    discard <| same delivered (IPC.reply server replyHandle 0x40100 length 0)
      (IPC.replyLocal server replyHandle 0x40100 length 0) baseTrace
  for pointer in #[0x40101,0x40fff,0x50000,0xffffffffffffffff] do
    discard <| same delivered (IPC.reply server replyHandle pointer 64 0)
      (IPC.replyLocal server replyHandle pointer 64 0) baseTrace
  for handle in #[replyHandle+16,0] do
    discard <| same delivered (IPC.reply server handle 0x40100 64 0)
      (IPC.replyLocal server handle 0x40100 64 0) baseTrace
  for status in #[0,255,256] do
    discard <| same delivered (IPC.reply server replyHandle 0x40100 64 status)
      (IPC.replyLocal server replyHandle 0x40100 64 status) baseTrace
  discard <| same {offered with now := 1001000} oldReceive newReceive baseTrace
  discard <| same {delivered with now := 1001000} oldReply newReply baseTrace
  IO.println s!"IPC_RPC_BORROW_ACTIONS:PASS pool{if expanded then 8192 else 512} Receive{received.1}->{received.2},Reply{replied.1}->{replied.2}; ordered exact result/RAM/payload/authority/partialfault behavior after only duplicate immutable base-read projection; receiveFaults{receiveFaults},replyFaults{replyFaults}"
end RPCBorrow

#eval RPCBorrow.check false
#eval RPCBorrow.check true
