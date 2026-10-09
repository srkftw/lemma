import Lean.Elab.Tactic.Omega

/-! Indexed ownership model, separate from emitted-code correctness. -/
namespace Lemma.Kernel.Memory.OwnershipModel

def frameBase : Nat := 0x82000000
def frameBytes : Nat := 4096
def frameCount : Nat := 512
abbrev Slot := Fin frameCount
structure State where
  owner : Slot → Nat

def live (s : State) (who : Nat) (slot : Slot) : Prop :=
  0 < who ∧ who < 0xffffffffffffffff ∧ s.owner slot = who
def free (s : State) (slot : Slot) : Prop := s.owner slot = 0
def contains (slot : Slot) (address : Nat) : Prop :=
  frameBase + slot.val * frameBytes ≤ address ∧
    address < frameBase + (slot.val + 1) * frameBytes

/-- Unique owner storage plus disjoint indexed pages prevents live grants to
separate owners from overlapping. This does not certify the LLVM lowering. -/
theorem separate_live_owners (s : State) (a b : Nat) (i j : Slot)
    (ha : live s a i) (hb : live s b j) (hab : a ≠ b) (address : Nat) :
    ¬ (contains i address ∧ contains j address) := by
  have hi : i.val ≠ j.val := by
    intro h
    have hslot : i = j := Fin.ext h
    subst j
    exact hab (ha.2.2.symm.trans hb.2.2)
  unfold contains frameBase frameBytes
  omega

theorem free_is_not_live (s : State) (i : Slot) (who : Nat) (hf : free s i) :
    ¬ live s who i := by
  intro h
  unfold free at hf
  have hz : who = 0 := h.2.2.symm.trans hf
  subst who
  exact Nat.lt_irrefl 0 h.1

theorem admitted_pool_envelope (i : Slot) :
    0x82000000 ≤ frameBase + i.val * frameBytes ∧
      frameBase + (i.val + 1) * frameBytes ≤ 0x82200000 := by
  have hi := i.isLt
  unfold frameCount at hi
  unfold frameBase frameBytes
  omega

end Lemma.Kernel.Memory.OwnershipModel
