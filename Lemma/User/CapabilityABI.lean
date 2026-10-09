/-! Additive managed-task capability ABI v1. The caller is always obtained from
the verified running context. Numeric handles and rights requests grant nothing
without a matching live entry in that caller's kernel-held table. -/
namespace Lemma.User.CapabilityABI

def version : UInt64 := 1
def bootGrant : UInt64 := 9
def info : UInt64 := 10
def check : UInt64 := 11
def duplicate : UInt64 := 12
def close : UInt64 := 13
def revoke : UInt64 := 14
def console : UInt64 := 15
def createEndpoint : UInt64 := 16
def transfer : UInt64 := 17
def scopedTarget : UInt64 := 18
def inspect : UInt64 := 19

def consoleType : UInt64 := 1
def endpointType : UInt64 := 2
def managementType : UInt64 := 3
def directoryType : UInt64 := 4

def consoleRead : UInt64 := 1
def consoleWrite : UInt64 := 2
def endpointSend : UInt64 := 4
def endpointReceive : UInt64 := 8
def endpointCall : UInt64 := 16
def duplicateRight : UInt64 := 32
def revokeRight : UInt64 := 64
def managementCreate : UInt64 := 128
def managementGrant : UInt64 := 256
def managementInspect : UInt64 := 512
def directoryDiscover : UInt64 := 1024

def consoleMask : UInt64 := 35
def endpointMask : UInt64 := 124
def managementMask : UInt64 := 928
def directoryMask : UInt64 := 1056
def knownRights : UInt64 := 2047

def invalidHandle : UInt8 := 80
def wrongType : UInt8 := 81
def revoked : UInt8 := 83
def tableFull : UInt8 := 89
def objectFull : UInt8 := 90
def generationExhausted : UInt8 := 91
def denied : UInt8 := 72
def invalidArgument : UInt8 := 16
def fatal : UInt8 := 255

def typeValid (kind : UInt64) : Bool :=
  if kind = consoleType then true else if kind = endpointType then true else
  if kind = managementType then true else if kind = directoryType then true else false

def typeMask (kind : UInt64) : UInt64 :=
  if kind = consoleType then consoleMask else if kind = endpointType then endpointMask else
  if kind = managementType then managementMask else if kind = directoryType then directoryMask else 0

def rightsSubset (requested available : UInt64) : Bool :=
  if requested &&& available = requested then true else false

def rightsValid (kind rights : UInt64) : Bool :=
  if typeValid kind = true then
    if rights = 0 then false else rightsSubset rights (typeMask kind)
  else false

end Lemma.User.CapabilityABI
