import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Numerics.Quantized

/-! Actual freestanding bounded worker. All wire parsing, checked-buffer access,
admission, inference, encoding and finite session control are elaborated Lean.
The worker echoes lease metadata; durable school authority owns lease validity.
No filesystem, host runtime, trained constants or foreign model enters this image. -/
namespace Lemma.School.Worker
open Lemma.Core0.Memory
open Lemma.Platform.LemmaVM.ConsoleDevice

def readyByte (i : UInt32) : UInt8 :=
  if i = 0 then 76 else if i = 1 then 69 else if i = 2 then 77
  else if i = 3 then 77 else if i = 4 then 65 else if i = 5 then 95
  else if i = 6 then 83 else if i = 7 then 67 else if i = 8 then 72
  else if i = 9 then 79 else if i = 10 then 79 else if i = 11 then 76
  else if i = 12 then 47 else if i = 13 then 49 else if i = 14 then 10
  else if i = 15 then 82 else if i = 16 then 69 else if i = 17 then 65
  else if i = 18 then 68 else if i = 19 then 89 else 10

def readyStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  Action.bind (sendByte (readyByte i)) fun s _ => Action.done s (acc + 1)

def receiveStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  Action.bind receiveByte fun s byte =>
    if s = 0 then
      Action.store8 RegionId.scratch (base + i.toUInt64) byte.toUInt8 fun ws =>
        Action.done ws (acc + 1)
    else Action.done s acc

def receive (count : UInt32) (base : UInt64) : Action :=
  Action.boundedFoldU64 72 receiveStep count 0 base 0 0 0 fun s n => Action.done s n

def responseHeader (index : UInt32) (status : UInt8) (request : UInt64) : UInt8 :=
  if index = 0 then 76 else if index = 1 then 77 else if index = 2 then 83
  else if index = 3 then 56 else if index = 4 then 1 else if index = 5 then status
  else if index = 6 then 32 else if index = 7 then 0
  else (request >>> ((index.toUInt64 - 8) * 8)).toUInt8

def responseStep (i _ : UInt32) (acc status request _ _ : UInt64) : Action :=
  if i < 16 then
    Action.bind (sendByte (responseHeader i status.toUInt8 request)) fun s _ =>
      Action.done s (acc + 1)
  else
    Action.load8 RegionId.output (i.toUInt64 - 16) fun s byte =>
      if s = 0 then
        Action.bind (sendByte byte.toUInt8) fun ss _ => Action.done ss (acc + 1)
      else Action.done s acc

def reply (status : UInt8) (request generation fence model score : UInt64) : Action :=
  Action.store64 RegionId.output 0 generation fun s0 =>
    if s0 = 0 then Action.store64 RegionId.output 8 fence fun s1 =>
      if s1 = 0 then Action.store64 RegionId.output 16 model fun s2 =>
        if s2 = 0 then Action.store64 RegionId.output 24 score fun s3 =>
          if s3 = 0 then
            Action.boundedFoldU64 48 responseStep 48 0 status.toUInt64 request 0 0
              fun s n => Action.done s n
          else Action.done s3 0
        else Action.done s2 0
      else Action.done s1 0
    else Action.done s0 0

def evaluate (request generation fence model w0 w1 bias x0 x1 mask : UInt64) : Action :=
  if request = 0 then reply 32 request generation fence model 0
  else if generation = 0 then reply 32 request generation fence model 0
  else if fence = 0 then reply 32 request generation fence model 0
  else if model = 0 then reply 32 request generation fence model 0
  else if Lemma.Numerics.Quantized.validParameters w0 w1 bias then
    if Lemma.Numerics.Quantized.validFeatures x0 x1 mask then
      reply 0 request generation fence model (Lemma.Numerics.Quantized.score w0 w1 bias x0 x1)
    else reply 31 request generation fence model 0
  else reply 30 request generation fence model 0

def infer (request : UInt64) : Action :=
  Action.load64 RegionId.scratch 16 fun s0 generation =>
    if s0 = 0 then Action.load64 RegionId.scratch 24 fun s1 fence =>
      if s1 = 0 then Action.load64 RegionId.scratch 32 fun s2 model =>
        if s2 = 0 then Action.load64 RegionId.scratch 40 fun s3 w0 =>
          if s3 = 0 then Action.load64 RegionId.scratch 48 fun s4 w1 =>
            if s4 = 0 then Action.load64 RegionId.scratch 56 fun s5 bias =>
              if s5 = 0 then Action.load64 RegionId.scratch 64 fun s6 x0 =>
                if s6 = 0 then Action.load64 RegionId.scratch 72 fun s7 x1 =>
                  if s7 = 0 then Action.load64 RegionId.scratch 80 fun s8 mask =>
                    if s8 = 0 then evaluate request generation fence model w0 w1 bias x0 x1 mask
                    else Action.done s8 0
                  else Action.done s7 0
                else Action.done s6 0
              else Action.done s5 0
            else Action.done s4 0
          else Action.done s3 0
        else Action.done s2 0
      else Action.done s1 0
    else Action.done s0 0

def dispatch (header : UInt32) (request : UInt64) : Action :=
  let version := header &&& 255
  let command := (header >>> 8) &&& 255
  let length := (header >>> 16) &&& 255
  let flags := header >>> 24
  if version = 1 then
    if flags = 0 then
      if command = 1 then
        if length = 72 then infer request else reply 16 request 0 0 0 0
      else if command = 2 then
        if length = 0 then
          Action.bind (reply 0 request 0 0 0 0) fun s _ =>
            if s = 0 then Action.done 10 0 else Action.done s 0
        else reply 16 request 0 0 0 0
      else reply 17 request 0 0 0 0
    else reply 14 request 0 0 0 0
  else reply 14 request 0 0 0 0

def readRequest : Action :=
  Action.bind (receive 16 0) fun hs _ =>
    if hs = 0 then
      Action.load32 RegionId.scratch 0 fun ms magic =>
        if ms = 0 then Action.load32 RegionId.scratch 4 fun fs fields =>
          if fs = 0 then Action.load64 RegionId.scratch 8 fun rs request =>
            if rs = 0 then
              let length := (fields >>> 16) &&& 255
              if length ≤ 72 then
                Action.bind (receive length.toUInt32 16) fun ps _ =>
                  if ps = 0 then
                    if magic = 0x38514d4c then dispatch fields.toUInt32 request
                    else reply 14 request 0 0 0 0
                  else Action.done ps 0
              else Action.done 16 0
            else Action.done rs 0
          else Action.done fs 0
        else Action.done ms 0
    else Action.done hs 0

def requestStep (_ _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  Action.bind readRequest fun s _ => Action.done s (acc + 1)

def entry : Action :=
  Action.uartEnableAndResetFifo fun s =>
    if s = 0 then
      Action.boundedFoldU64 21 readyStep 21 0 0 0 0 0 fun readyStatus _ =>
        if readyStatus = 0 then
          Action.boundedFoldU64 64 requestStep 64 0 0 0 0 0 fun finalStatus _ =>
            if finalStatus = 10 then Action.bind drain fun ds _ => Action.done ds 0
            else if finalStatus = 0 then Action.done 9 0 else Action.done finalStatus 0
        else Action.done readyStatus 0
    else Action.done s 0

end Lemma.School.Worker
