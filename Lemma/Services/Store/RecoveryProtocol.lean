import Lemma.Services.Store.Protocol

/-! Opt-in recovery control framing. It does not change journal formats or
historical requestVersion/shape. Epoch is a receipt from the selected kernel
client and complete shadow scan, not a host authentication/MMIO fact. -/
namespace Lemma.Services.Store.RecoveryProtocol
open Lemma.Core0.Memory
def version : UInt64 := 3
def invalid : UInt8 := 234
def operationValid (operation : UInt64) : UInt64 :=
  if operation = 14 then 1 else if operation = 15 then 1 else 0
def shape (operation ns object ticket offset count bytes : UInt64) : UInt64 :=
  if operationValid operation = 1 then
    if ns = 1 then
      if object = 0 then
        if ticket = 0 then 0 else
        if offset = 0 then
          if count = 0 then
            if bytes = 64 then 1 else 0
          else 0
        else 0
      else 0
    else 0
  else 0
def header (packet operation ns ticket : UInt64) : Action :=
  .bind (Protocol.header packet operation ns 0 ticket 0 0) fun s _ => if s = 0 then
  Lemma.User.Memory.write64 (packet+8) version else .done s 0
end Lemma.Services.Store.RecoveryProtocol
