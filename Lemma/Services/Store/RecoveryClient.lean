import Lemma.Services.Store.RecoveryProtocol
import Lemma.User.IPC

namespace Lemma.Services.Store.RecoveryClient
open Lemma.Core0.Memory Lemma.User
def beginCall (endpoint outgoing operation ns ticket request : UInt64) : Action :=
  if RecoveryProtocol.shape operation ns 0 ticket 0 0 64 = 1 then
  .bind (RecoveryProtocol.header outgoing operation ns ticket) fun s _ => if s = 0 then
  IPC.callBegin endpoint outgoing 64 request IPCABI.lemmaSimMaximumTicks else .done s 0
  else .done RecoveryProtocol.invalid 0

private def validate (incoming operation ns request bytes : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind =>
    if s = 0 then
      if kind = IPCABI.replyKind then
        .bind (IPC.field incoming IPCABI.requestOffset) fun s actualRequest =>
          if s = 0 then
            .bind (IPC.field incoming IPCABI.senderOffset) fun s sender =>
              if s = 0 then
                .bind (IPC.field incoming IPCABI.replyOffset) fun s reply =>
                  if s = 0 then
                    .bind (IPC.field incoming IPCABI.statusOffset) fun s app =>
                      if s = 0 then
                        if actualRequest = request then
                          if 0 < sender then
                            if reply = 0 then
                              if bytes = 136 then
                                .bind (Protocol.field (incoming+64) 0) fun s magic =>
                                  if s = 0 then
                                    .bind (Protocol.field (incoming+64) 8) fun s version =>
                                      if s = 0 then
                                        .bind (Protocol.field (incoming+64) 16) fun s observedOperation =>
                                          if s = 0 then
                                            .bind (Protocol.field (incoming+64) 24) fun s observedNs =>
                                              if s = 0 then
                                                .bind (Protocol.field (incoming+64) 32) fun s object =>
                                                  if s = 0 then
                                                    .bind (Protocol.field (incoming+64) 40) fun s sequence =>
                                                      if s = 0 then
                                                        .bind (Protocol.field (incoming+64) 48) fun s detail =>
                                                          if s = 0 then
                                                            .bind (Protocol.field (incoming+64) 56) fun s count =>
                                                              if s = 0 then
                                                                .bind (Memory.read64 (incoming+128)) fun s epoch =>
                                                                  if s = 0 then
                                                                    if magic = Protocol.magic then
                                                                      if version = RecoveryProtocol.version then
                                                                        if observedOperation = operation then
                                                                          if RecoveryProtocol.operationValid operation = 1 then
                                                                            if observedNs = ns then
                                                                              if object = 0 then
                                                                                if count = 8 then
                                                                                  if sequence ≤ Format.maximumSequence then
                                                                                    if app = 0 then
                                                                                      if epoch = 0 then
                                                                                        .done IPCABI.invalidPacket 0
                                                                                      else
                                                                                        if detail = 1 then
                                                                                          .done 0 sequence
                                                                                        else
                                                                                          if detail = 2 then
                                                                                            .done 0 sequence
                                                                                          else
                                                                                            .done IPCABI.invalidPacket 0
                                                                                    else
                                                                                      if (if app = 227 then (1 : UInt64) else if app = 231 then 1 else if app = 232 then 1 else if app = 234 then 1 else 0) = 1 then
                                                                                        if detail = 3 then
                                                                                          .done app.toUInt8 sequence
                                                                                        else
                                                                                          .done IPCABI.invalidPacket 0
                                                                                      else
                                                                                        .done IPCABI.invalidPacket 0
                                                                                  else
                                                                                    .done IPCABI.invalidPacket 0
                                                                                else
                                                                                  .done IPCABI.invalidPacket 0
                                                                              else
                                                                                .done IPCABI.invalidPacket 0
                                                                            else
                                                                              .done IPCABI.invalidPacket 0
                                                                          else
                                                                            .done IPCABI.invalidPacket 0
                                                                        else
                                                                          .done IPCABI.invalidPacket 0
                                                                      else
                                                                        .done IPCABI.invalidPacket 0
                                                                    else
                                                                      .done IPCABI.invalidPacket 0
                                                                  else .done s 0
                                                              else .done s 0
                                                          else .done s 0
                                                      else .done s 0
                                                  else .done s 0
                                              else .done s 0
                                          else .done s 0
                                      else .done s 0
                                  else .done s 0
                              else
                                .done IPCABI.invalidPacket 0
                            else
                              .done IPCABI.invalidPacket 0
                          else
                            .done IPCABI.invalidPacket 0
                        else
                          .done IPCABI.invalidPacket 0
                      else .done s 0
                  else .done s 0
              else .done s 0
          else .done s 0
      else
        .done IPCABI.invalidPacket 0
    else .done s 0

def pollCall (transaction incoming operation ns request : UInt64) : Action :=
  .bind (Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0) fun s bytes =>
  if s = IPCABI.wouldBlock then if bytes = 0 then .done s 0 else .done IPCABI.invalidPacket 0 else
  if s = 0 then validate incoming operation ns request bytes else .done s 0
end Lemma.Services.Store.RecoveryClient
