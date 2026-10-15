import Lemma.Services.Store.Server
import Lemma.Services.Store.Remount
import Lemma.Services.Store.RecoveryProtocol

/-! Opt-in server only. All ordinary operations use the existing course-guarded
dispatcher. Recovery owns one full sender/ns/ticket, never formats, never calls
the old settle path while copying a shadow context, and never returns Saved.
192phase/200owner/208ns/216ticket/224candidateEpoch/232epoch/240oldSequence/
248shadowSubmitted/256receipt/264error/272sequence/280durabilityWitness. Receipt1Pending/2complete/
3failed is separate from the old checkpoint and staging leases. -/
namespace Lemma.Services.Store.ServerRecovery
open Lemma.Core0.Memory Lemma.User
private def bad : Action := Server.failed
private def get (o : UInt64) : Action := Server.get o
private def put (o v : UInt64) : Action := Server.put o v

private def response (reply operation ns sequence detail epoch : UInt64) (status : UInt8) : Action :=
  .bind (Protocol.header Server.outgoing operation ns 0 sequence detail 8) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing+8) RecoveryProtocol.version) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing+64) epoch) fun s _ => if s = 0 then
  .bind (IPC.reply reply Server.outgoing 72 status.toUInt64) fun s sent =>
  if sent = 0 then if s = 0 then .done 0 0 else
  if s = CapabilityABI.invalidHandle then .done 0 0 else if s = IPCABI.peerDied then .done 0 0 else
  if s = IPCABI.revoked then .done 0 0 else bad else bad
  else bad else bad else bad

private def currentResponse (reply operation ns : UInt64) (status : UInt8) : Action :=
  .bind (Engine.field Server.context 40) fun s sequence => if s = 0 then
  response reply operation ns sequence 3 0 status else bad

def status (sender reply operation ns ticket : UInt64) : Action :=
  .bind (get 200) fun s owner =>
    if s = 0 then
      .bind (get 208) fun s storedNs =>
        if s = 0 then
          .bind (get 216) fun s storedTicket =>
            if s = 0 then
              if owner = sender then
                if storedNs = ns then
                  if storedTicket = ticket then
                    .bind (get 256) fun s receipt =>
                      if s = 0 then
                        .bind (get 232) fun s epoch =>
                          if s = 0 then
                            .bind (get 272) fun s sequence =>
                              if s = 0 then
                                if receipt = 1 then
                                  .bind (get 224) fun s candidate =>
                                    if s = 0 then
                                      response reply operation ns sequence 1 candidate 0
                                    else bad
                                else
                                  if receipt = 2 then
                                    response reply operation ns sequence 2 epoch 0
                                  else
                                    .bind (get 264) fun s error =>
                                      if s = 0 then
                                        if receipt = 3 then
                                          if error = 227 then
                                            response reply operation ns sequence 3 epoch 227
                                          else
                                            response reply operation ns sequence 3 epoch RecoveryProtocol.invalid
                                        else
                                          currentResponse reply operation ns Protocol.wrongOwner
                                      else bad
                              else bad
                          else bad
                      else bad
                  else
                    currentResponse reply operation ns Protocol.wrongOwner
                else
                  currentResponse reply operation ns Protocol.wrongOwner
              else
                currentResponse reply operation ns Protocol.wrongOwner
            else bad
        else bad
    else bad

private def failRecovery (error : UInt8) : Action :=
  .bind (put 24 3) fun s _ => if s = 0 then
  .bind (put 264 error.toUInt64) fun s _ => if s = 0 then
  .bind (put 256 3) fun s _ => if s = 0 then put 192 0 else bad else bad else bad

def begin (sender reply ns ticket : UInt64) : Action :=
  .bind (get 256) fun s receipt =>
    if s = 0 then
      .bind (get 200) fun s owner =>
        if s = 0 then
          .bind (get 208) fun s oldNs =>
            if s = 0 then
              .bind (get 216) fun s oldTicket =>
                if s = 0 then
                  if (if owner = sender then if oldNs = ns then if oldTicket = ticket then if receipt = 1 then (1 : UInt64) else if receipt = 2 then 1 else 0 else 0 else 0 else 0) = 1 then
                    status sender reply 14 ns ticket
                  else
                    if receipt = 1 then
                      currentResponse reply 14 ns Protocol.busy
                    else
                      .bind (get 192) fun s phase =>
                        if s = 0 then
                          .bind (get 24) fun s mode =>
                            if s = 0 then
                              .bind (get 32) fun s submitted =>
                                if s = 0 then
                                  .bind (get 40) fun s pendingReply =>
                                    if s = 0 then
                                      .bind (get 48) fun s stagedOwner =>
                                        if s = 0 then
                                          .bind (get 128) fun s checkpoint =>
                                            if s = 0 then
                                              .bind (Engine.field Server.context 0) fun s operation =>
                                                if s = 0 then
                                                  .bind (Engine.field Server.context 336) fun s readonly =>
                                                    if s = 0 then
                                                      if mode = 3 then
                                                        if readonly = 1 then
                                                          if phase ||| submitted ||| pendingReply ||| stagedOwner ||| operation = 0 then
                                                            if checkpoint = 1 then
                                                              currentResponse reply 14 ns Protocol.busy
                                                            else
                                                              .bind (Engine.field Server.context 40) fun s sequence =>
                                                                if s = 0 then
                                                                  .bind (get 0) fun s block =>
                                                                    if s = 0 then
                                                                      .bind (Syscall.call 66 block 7 0 0 0) fun s epoch =>
                                                                        if s = 0 then
                                                                          if epoch = 0xffffffffffffffff then
                                                                            currentResponse reply 14 ns RecoveryProtocol.invalid
                                                                          else
                                                                            .bind (Syscall.call 66 block 5 ticket (epoch+1) 0) fun control candidate =>
                                                                              if control = 168 then
                                                                                if candidate = epoch+1 then
                                                                                  .bind (put 200 sender) fun s _ =>
                                                                                    if s = 0 then
                                                                                      .bind (put 208 ns) fun s _ =>
                                                                                        if s = 0 then
                                                                                          .bind (put 216 ticket) fun s _ =>
                                                                                            if s = 0 then
                                                                                              .bind (put 224 candidate) fun s _ =>
                                                                                                if s = 0 then
                                                                                                  .bind (put 232 0) fun s _ =>
                                                                                                    if s = 0 then
                                                                                                      .bind (put 240 sequence) fun s _ =>
                                                                                                        if s = 0 then
                                                                                                          .bind (put 248 0) fun s _ =>
                                                                                                            if s = 0 then
                                                                                                              .bind (put 280 0) fun s _ => if s = 0 then
                                                                                                              .bind (put 272 sequence) fun s _ =>
                                                                                                                if s = 0 then
                                                                                                                  .bind (put 264 0) fun s _ =>
                                                                                                                    if s = 0 then
                                                                                                                      .bind (put 256 1) fun s _ =>
                                                                                                                        if s = 0 then
                                                                                                                          .bind (put 192 1) fun s _ =>
                                                                                                                            if s = 0 then
                                                                                                                              status sender reply 14 ns ticket
                                                                                                                            else bad
                                                                                                                        else bad
                                                                                                                    else bad
                                                                                                                else bad
                                                                                                              else bad
                                                                                                            else bad
                                                                                                        else bad
                                                                                                    else bad
                                                                                                else bad
                                                                                            else bad
                                                                                        else bad
                                                                                    else bad
                                                                                else
                                                                                  bad
                                                                              else
                                                                                currentResponse reply 14 ns (if control = 162 then Protocol.busy else RecoveryProtocol.invalid)
                                                                        else bad
                                                                    else bad
                                                                else bad
                                                          else
                                                            currentResponse reply 14 ns Protocol.busy
                                                        else
                                                          currentResponse reply 14 ns RecoveryProtocol.invalid
                                                      else
                                                        currentResponse reply 14 ns RecoveryProtocol.invalid
                                                    else bad
                                                else bad
                                            else bad
                                        else bad
                                    else bad
                                else bad
                            else bad
                        else bad
                else bad
            else bad
        else bad
    else bad

def application (sender reply bytes : UInt64) : Action :=
  if bytes = 64 then
  .bind (Protocol.field (Server.incoming+64) 16) fun s operation => if s = 0 then
  if RecoveryProtocol.operationValid operation = 1 then
  .bind (Protocol.field (Server.incoming+64) 0) fun s magic => if s = 0 then
  .bind (Protocol.field (Server.incoming+64) 8) fun s version => if s = 0 then
  .bind (Protocol.field (Server.incoming+64) 24) fun s ns => if s = 0 then
  .bind (Protocol.field (Server.incoming+64) 32) fun s object => if s = 0 then
  .bind (Protocol.field (Server.incoming+64) 40) fun s ticket => if s = 0 then
  .bind (Protocol.field (Server.incoming+64) 48) fun s offset => if s = 0 then
  .bind (Protocol.field (Server.incoming+64) 56) fun s count => if s = 0 then
  if magic = Protocol.magic then if version = RecoveryProtocol.version then
  if RecoveryProtocol.shape operation ns object ticket offset count bytes = 1 then
    if operation = 14 then begin sender reply ns ticket else status sender reply operation ns ticket
  else currentResponse reply operation ns RecoveryProtocol.invalid
  else currentResponse reply operation ns RecoveryProtocol.invalid
  else currentResponse reply operation ns RecoveryProtocol.invalid
  else bad else bad else bad else bad else bad else bad else bad
  else Server.courseApplication sender reply bytes else bad
  else Server.courseApplication sender reply bytes

private def receive (nonblocking : UInt64) : Action :=
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
  if sender = 0 then bad else if 16 ≤ reply then application sender reply length else bad
  else bad else bad else bad else .done 0 0 else bad else bad else bad

private def resolveFrame : Action :=
  .bind (get 0) fun s block => if s = 0 then
  .bind (get 216) fun s ticket => if s = 0 then
  .bind (get 224) fun s expectedEpoch => if s = 0 then
  .bind (Syscall.call 66 block 6 ticket expectedEpoch 0) fun status epoch =>
  if status = 168 then .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else bad else
  if status = 0 then if epoch = expectedEpoch then
  .bind (Engine.field Server.context 48) fun s capacity => if s = 0 then
  .bind (Remount.start capacity ticket epoch) fun s _ => if s = 0 then
  .bind (put 232 epoch) fun s _ => if s = 0 then put 192 2 else bad
  else failRecovery RecoveryProtocol.invalid else bad
  else failRecovery RecoveryProtocol.invalid else failRecovery Format.transportFailed
  else bad else bad else bad

private def shadowPump : Action :=
  .bind (Engine.field Remount.shadow 0) fun s operation => if s = 0 then
  if operation = 0 then .done 0 0 else if operation = 1 then
  .bind (get 0) fun s block => if s = 0 then
  .bind (get 248) fun s submitted => if s = 0 then
  if submitted = 0 then
    .bind (Engine.field Remount.shadow 16) fun s sector => if s = 0 then
    .bind (Syscall.call 66 block 1 sector Remount.shadowBuffer 0) fun status _ =>
    if status = 168 then put 248 1 else
    .bind (Engine.complete Remount.shadow status) fun s _ =>
    if s = 0 then .done 0 0 else if 220 ≤ s then if s ≤ 230 then .done 0 0 else bad else bad
    else bad
  else if submitted = 1 then
    .bind (Syscall.call 66 block 4 0 Remount.shadowBuffer 0) fun status _ =>
    if status = 168 then .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else bad else
    .bind (put 248 0) fun s _ => if s = 0 then
    .bind (Engine.complete Remount.shadow status) fun s _ =>
    if s = 0 then .done 0 0 else if 220 ≤ s then if s ≤ 230 then .done 0 0 else bad else bad else bad
  else bad else bad else bad else failRecovery RecoveryProtocol.invalid else bad

private def shadowValidated : Action :=
  .bind (Engine.field Remount.shadow 0) fun s operation => if s = 0 then
  if operation = 0 then
  .bind (get 216) fun s ticket => if s = 0 then
  .bind (get 232) fun s epoch => if s = 0 then
  .bind (Remount.inspect ticket epoch) fun status _ =>
  if status = 0 then put 192 3 else
  if status = Remount.invalid then failRecovery Format.transportFailed else
  if status = Remount.busy then failRecovery Format.transportFailed else bad
  else bad else bad else .done 0 0 else bad

private def shadowAdopt : Action :=
  .bind (get 280) fun s durable => if s = 0 then
  if durable = 1 then
  .bind (Engine.field Remount.shadow 0) fun s operation => if s = 0 then
  if operation = 0 then
  .bind (get 216) fun s ticket => if s = 0 then
  .bind (get 232) fun s epoch => if s = 0 then
  .bind (Remount.adopt ticket epoch) fun status sequence =>
  if status = 0 then
  .bind (put 272 sequence) fun s _ => if s = 0 then
  .bind (put 256 2) fun s _ => if s = 0 then
  .bind (put 24 1) fun s _ => if s = 0 then put 192 0 else bad else bad else bad
  else if status = Remount.invalid then failRecovery Format.transportFailed else
    if status = Remount.busy then failRecovery Format.transportFailed else bad
  else bad else bad
  else .done 0 0 else bad
  else bad else bad

private def durabilityBarrier : Action :=
  .bind (get 0) fun s block => if s = 0 then
  .bind (get 248) fun s submitted => if s = 0 then
  if submitted = 0 then
    .bind (Syscall.call 66 block 3 0 0 0) fun status _ =>
    if status = 168 then put 248 1 else failRecovery Format.transportFailed
  else if submitted = 1 then
    .bind (Syscall.call 66 block 4 0 Remount.shadowBuffer 0) fun status _ =>
    if status = 168 then .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else bad else
    .bind (put 248 0) fun s _ => if s = 0 then
    if status = 0 then
    .bind (put 280 1) fun s _ => if s = 0 then shadowAdopt else bad
    else failRecovery Format.transportFailed else bad
  else bad else bad else bad

def step : Action :=
  .bind (get 192) fun s phase => if s = 0 then
  if phase = 1 then
    .bind resolveFrame fun s _ => if s = 0 then receive 1 else bad
  else if phase = 2 then
    .bind shadowPump fun s _ => if s = 0 then
    .bind (get 192) fun s stillActive => if s = 0 then
    .bind (if stillActive = 2 then shadowValidated else .done 0 0) fun s _ => if s = 0 then receive 1 else bad else bad else bad
  else if phase = 3 then
    .bind durabilityBarrier fun s _ => if s = 0 then receive 1 else bad
  else if phase = 0 then
    .bind Server.courseService fun s _ => if s = 0 then
    .bind (Engine.field Server.context 0) fun s operation => if s = 0 then
    .bind (get 24) fun s mode => if s = 0 then
    if operation = 0 then receive 0 else
    .bind (get 128) fun s receipt => if s = 0 then
    if mode = 0 then receive 1 else if receipt = 1 then receive 1 else .done 0 0
    else bad else bad else bad else bad
  else bad else bad

private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := Server.context+i.toUInt64*4096
  .bind (Syscall.allocatePage address) fun s value => if s = 0 then
  if value = address then .done 0 (acc+1) else bad else bad
private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64*8) 0) fun s _ => if s = 0 then .done 0 (acc+1) else bad

def mainRecoveryCourse (bootArgument : UInt64) : Action :=
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
                      .boundedFoldU64 38 clearStep 38 0 0 0 0 0 fun s fields =>
                        if s = 0 then
                          if fields = 38 then
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
                                                .bind (Engine.mountStart Server.context Server.buffer Server.index0 capacity) fun s _ => if s = 0 then .loop step else bad
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


/-- Shared recovery-only phase boundary for the additive mounted Store.
It performs no receive, normal settlement or mount publication. The caller must
retain the original read-only context until these existing phases complete. -/
def pumpRecoveryPhase : Action :=
  .bind (get 192) fun s phase => if s = 0 then
  if phase = 1 then resolveFrame else
  if phase = 2 then
    .bind shadowPump fun s _ => if s = 0 then
    .bind (get 192) fun s stillActive => if s = 0 then
    if stillActive = 2 then shadowValidated else .done 0 0
    else bad else bad
  else if phase = 3 then durabilityBarrier else bad
  else bad

end Lemma.Services.Store.ServerRecovery
