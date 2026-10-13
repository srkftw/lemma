import Lemma.Documents.MathematicsBytes
import Lemma.Mathematics.ExecutionIdentityV4

/-! Document6 is a distinct closed array execution registry. Original typed
semantics, raw ink and learner event layout are unchanged. Old valid origins
remain exact Known/Unknown; old parser selections continue to reject5. -/
namespace Lemma.Documents.MathematicsArray
open Lemma.Core0.Memory Lemma.User Lemma.Mathematics

def validate (buffer ns page : UInt64) : Action :=
  .bind (Mathematics.field buffer 8) fun s version => if s = 0 then
  if version = 6 then
  .bind (Mathematics.field buffer 0) fun s magic => if s = 0 then
  if magic = Mathematics.magic then
  .bind (Mathematics.validate.validateHeader buffer ns page) fun s _ => if s = 0 then
  ExecutionIdentityV4.validate buffer else .done s 0
  else .done 234 0 else .done s 0
  else MathematicsBytes.validate buffer ns page else .done s 0

/-- The caller has validated the source record. Only the two version words
change; every old active/history identity remains its original registry. -/
def upgrade (buffer : UInt64) : Action :=
  .bind (Mathematics.field buffer 8) fun s version => if s = 0 then
  if version = 6 then .done 0 0 else
  .bind (MathematicsBytes.upgrade buffer) fun s _ => if s = 0 then
  .bind (Mathematics.put buffer 1864 ExecutionIdentityV4.extensionVersion) fun s _ => if s = 0 then
  .bind (Mathematics.put buffer 8 6) fun s _ => .done s 1
  else .done s 0 else .done s 0 else .done s 0

def create (buffer ns page : UInt64) : Action :=
  .bind (MathematicsBytes.create buffer ns page) fun s _ => if s = 0 then
  upgrade buffer else .done s 0

/-- Exact protocol5 completion is allowed only for the still-current immutable
submission. Resource/death/cancel/stale replies cannot invoke publication. -/
def completeExecution (buffer revision goal outcome request budget : UInt64) : Action :=
  if request = 0 then .done 234 0 else if 0x7ffffffffffffffe < request then .done 234 0 else
  if (if budget = 0 then true else budget = 8) = false then .done 234 0 else
  .bind (Mathematics.field buffer 8) fun s version => if s = 0 then if version = 6 then
  .bind (Mathematics.field buffer 136) fun s currentBudget => if s = 0 then if currentBudget = budget then
  .bind (Mathematics.field buffer 144) fun s index => if s = 0 then if index < 8 then
  .bind (Mathematics.completeSubmit buffer revision goal outcome) fun s actual => if s = 0 then
  .bind (ExecutionIdentityV4.publish buffer request index budget) fun s _ => .done s actual
  else .done s 0 else .done 235 0 else .done s 0 else .done 234 0 else .done s 0
  else .done 234 0 else .done s 0

end Lemma.Documents.MathematicsArray
