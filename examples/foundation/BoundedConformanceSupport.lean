/-! Closed helpers and callbacks for the `core0-v0.3` bounded-loop corpus. -/

namespace Lemma.Examples.Foundation.Bounded.Support

def helperMix (index accumulator : UInt32) : UInt32 :=
  let multiplied := index * 0x9e3779b9
  (accumulator ^^^ multiplied) + 0x7f4a7c15

def nestedInnerStep (index accumulator : UInt32) : UInt32 :=
  accumulator + index + 3

end Lemma.Examples.Foundation.Bounded.Support
