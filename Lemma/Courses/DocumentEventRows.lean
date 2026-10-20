/-! Typed document-event row boundaries shared by read-only learner consumers.
An event header occupies one row. Remote provenance has three payload rows;
local-tool provenance has seven. Payload words are arbitrary data and must
never be interpreted as another learner-event descriptor. Validation remains
the document validator's responsibility. -/
namespace Lemma.Courses.DocumentEventRows

def supportedFormat (version : UInt64) : Bool :=
  if version = 1 then true else if version = 2 then true else
  if version = 3 then true else false

def payloadRows (descriptor : UInt64) : UInt64 :=
  if descriptor &&& 255 = 7 then 3 else
  if descriptor &&& 255 = 8 then 7 else 0

/-- Low32 bits belong to the consuming observation; high32 count payload rows
still to skip. All current observations fit in the low byte. -/
def observation (state : UInt64) : UInt64 := state &&& 0xffffffff
def remaining (state : UInt64) : UInt64 := state >>> 32
def beginPayload (state descriptor : UInt64) : UInt64 :=
  observation state ||| (payloadRows descriptor <<< 32)
def skipPayload (state : UInt64) : UInt64 :=
  observation state ||| ((remaining state - 1) <<< 32)

end Lemma.Courses.DocumentEventRows
