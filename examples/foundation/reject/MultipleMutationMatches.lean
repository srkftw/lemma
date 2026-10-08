import Lemma.Compiler.Test.Export

namespace Lemma.Examples.Foundation.Reject.MultipleMutationMatches

def addTwice (x y : UInt64) : UInt64 :=
  let first := x + y
  let second := x + y
  first + second

def entry (_selector x y : UInt64) : UInt64 :=
  addTwice x y

#core0_export_fault "add-as-sub" entry addTwice

end Lemma.Examples.Foundation.Reject.MultipleMutationMatches
