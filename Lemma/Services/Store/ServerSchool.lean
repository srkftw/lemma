import Lemma.Services.Store.ServerRecovery
import Lemma.Services.Store.ServerAwait

/-! School queue/1 selects the shared mounted/recovery service and immutable
submission-prefix guard. The original roots remain separately executable.
Only dispatch selects the new guard; mount, recovery, leases and barriers reuse
the original Lean implementations. -/
namespace Lemma.Services.Store.ServerSchool
open Lemma.Core0.Memory Lemma.User
private def bad : Action := Server.failed
private def get (o : UInt64) : Action := Server.get o
private def put (o v : UInt64) : Action := Server.put o v

def applicationAwait (sender reply bytes : UInt64) : Action :=
  if 64 ≤ bytes then
  .bind (Protocol.field (Server.incoming+64) 16) fun s operation => if s = 0 then
  if operation = Lemma.Courses.PackageAwaitProtocol.operation then
    ServerAwait.awaitApplication sender reply bytes
  else if RecoveryProtocol.operationValid operation = 1 then ServerRecovery.application sender reply bytes
  else Server.schoolApplication sender reply bytes
  else bad else Server.schoolApplication sender reply bytes

private def receiveAwait (nonblocking : UInt64) : Action :=
  .bind (get 8) fun s endpoint => if s = 0 then
  .bind (if nonblocking = 1 then IPC.tryReceive endpoint Server.incoming IPCABI.maximumPacket
    else IPC.receive endpoint Server.incoming IPCABI.maximumPacket 1000000) fun status bytes =>
  if status = IPCABI.wouldBlock then if bytes = 0 then .done 0 0 else bad else
  if status = IPCABI.timeout then .done 0 0 else if status = 0 then
  .bind (IPC.validate Server.incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.callKind then
  .bind (IPC.field Server.incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field Server.incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  .bind (IPC.field Server.incoming IPCABI.lengthOffset) fun s length => if s = 0 then
  if sender = 0 then bad else if 16 ≤ reply then applicationAwait sender reply length else bad
  else bad else bad else bad else .done 0 0 else bad else bad else bad

def stepAwait : Action :=
  .bind (get 192) fun s phase => if s = 0 then
  if (if phase = 1 then true else if phase = 2 then true else if phase = 3 then true else false) = true then
    .bind ServerRecovery.pumpRecoveryPhase fun s _ => if s = 0 then receiveAwait 1 else bad
  else if phase = 0 then
    .bind Server.courseService fun s _ => if s = 0 then
    .bind ServerAwait.settleWaiters fun s _ => if s = 0 then
    .bind (Engine.field Server.context 0) fun s operation => if s = 0 then
    .bind (get 24) fun s mode => if s = 0 then
    if operation = 0 then receiveAwait 0 else
    .bind (get 128) fun s receipt => if s = 0 then
    if mode = 0 then receiveAwait 1 else if receipt = 1 then receiveAwait 1 else .done 0 0
    else bad else bad else bad else bad else bad
  else bad else bad

private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := Server.context+i.toUInt64*4096
  .bind (Syscall.allocatePage address) fun s value => if s = 0 then
  if value = address then .done 0 (acc+1) else bad else bad
private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64*8) 0) fun s _ => if s = 0 then .done 0 (acc+1) else bad

def main (bootArgument : UInt64) : Action :=
  if bootArgument ≤ 1 then
    .bind (Capability.bootGrant 0) fun s block =>
      if s = 0 then
        .bind (Capability.bootGrant 1) fun s endpoint =>
          if s = 0 then
            .bind (Syscall.identity) fun s identity =>
              if s = 0 then
                .boundedFoldU64 36 allocateStep 36 0 0 0 0 0 fun s pages =>
                  if s = 0 then
                    if pages = 36 then
                      .boundedFoldU64 88 clearStep 88 0 0 0 0 0 fun s fields =>
                        if s = 0 then
                          if fields = 88 then
                            .bind (put 0 block) fun s _ =>
                              if s = 0 then
                                .bind (put 8 endpoint) fun s _ =>
                                  if s = 0 then
                                    .bind (put 16 identity) fun s _ =>
                                      if s = 0 then
                                        .bind (put 112 bootArgument) fun s _ =>
                                          if s = 0 then
                                            .bind (Syscall.call 66 block 0 0 0 0) fun s capacity =>
                                              if s = 0 then
                                                .bind (Engine.mountStart Server.context Server.buffer Server.index0 capacity) fun s _ => if s = 0 then .loop stepAwait else bad
                                              else bad
                                          else bad
                                      else bad
                                  else bad
                              else bad
                          else
                            bad
                        else
                          bad
                    else
                      bad
                  else
                    bad
              else bad
          else bad
      else bad
  else
    bad

end Lemma.Services.Store.ServerSchool
