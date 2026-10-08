import Lemma.Core0

namespace Lemma.Examples.Foundation.Gate3Reject.UnsupportedProfileModel

open Lemma.Core0

#guard Profile.ofContractVersion? "core0-v0.3" == none

def rejectedProgram : Program := {
  contractVersion := "core0-v0.3"
  root := .mkSimple "unsupportedProfileRoot"
  functions := #[]
  usedPrimitives := #[]
}

#eval match evalProgram rejectedProgram #[] with
  | .error diagnostic => IO.println diagnostic.render
  | .ok _ => throw <| IO.userError "unsupported Core0 contract unexpectedly evaluated"

end Lemma.Examples.Foundation.Gate3Reject.UnsupportedProfileModel
