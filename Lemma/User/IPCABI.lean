/-! Copied-message IPC ABI v1. User requests supply payload bytes, not a wire
header. The kernel stamps the authenticated sender and receiver-local reply
authority. Every packet has a 64-byte header and at most 192 payload bytes.
Blocking is a kernel/scheduler outcome; no private pending status reaches User.
-/
namespace Lemma.User.IPCABI

def version : UInt64 := 1
def send : UInt64 := 20
def receive : UInt64 := 21
def callBegin : UInt64 := 22
def callWait : UInt64 := 23
def reply : UInt64 := 24
def cancel : UInt64 := 25

def nonblocking : UInt64 := 0
def blocking : UInt64 := 1
def minimumTicks : UInt64 := 1000
def maximumTicks : UInt64 := 10000000
def headerBytes : UInt64 := 64
def maximumPayload : UInt64 := 192
def maximumPacket : UInt64 := 256
def queueCapacity : UInt64 := 4
def replyCapacity : UInt64 := 8

def messageMagic : UInt64 := 0x31504349414d454c
def sendKind : UInt64 := 1
def callKind : UInt64 := 2
def replyKind : UInt64 := 3
def magicOffset : UInt64 := 0
def kindOffset : UInt64 := 8
def senderOffset : UInt64 := 16
def requestOffset : UInt64 := 24
def replyOffset : UInt64 := 32
def lengthOffset : UInt64 := 40
def statusOffset : UInt64 := 48
def reservedOffset : UInt64 := 56
def payloadOffset : UInt64 := 64

def wouldBlock : UInt8 := 12
def queueFull : UInt8 := 92
def timeout : UInt8 := 93
def canceled : UInt8 := 94
def peerDied : UInt8 := 96
def invalidTransaction : UInt8 := 97
def bufferTooSmall : UInt8 := 98
def inFlight : UInt8 := 99
def alreadyCompleted : UInt8 := 100
def invalidPacket : UInt8 := 101
def revoked : UInt8 := 83
def invalidArgument : UInt8 := 16
def denied : UInt8 := 72

end Lemma.User.IPCABI
