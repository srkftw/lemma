"""Actual LLVM Reader19 owner fixture, host observer only; never a target image."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import _jump_assembly_guard
from core0_common import Core0Error
SYMBOL='lemma_user_notebook_core0_action_165'
ASSEMBLY='lemma_user_notebook_core0_action_165:   # @lemma_user_notebook_core0_action_165\n.Lfunc_begin537:\n# %bb.0:                                # %entry\n\taddi\tsp, sp, -32\n\tsd\tra, 24(sp)                      # 8-byte Folded Spill\n\tsd\ts0, 16(sp)                      # 8-byte Folded Spill\n\tsd\ts1, 8(sp)                       # 8-byte Folded Spill\n\tli\ta0, 160\n\tcall\tlemma_user_notebook_core0_action_7\n\tmv\ts0, a0\n\tmv\ts1, a1\n\tcall\tlemma_user_notebook_core0_scalar_0\n\tbnez\ta0, .LBB537_11\n# %bb.1:                                # %action.if.else.1\n\tli\ta0, 11\n\tbltu\ta0, s1, .LBB537_5\n# %bb.2:                                # %action.if.else.1\n\tslli\ta0, s1, 3\n.Lpcrel_hi179:\n\tauipc\ta1, %pcrel_hi(.LJTI537_0)\n\taddi\ta1, a1, %pcrel_lo(.Lpcrel_hi179)\n\tadd\ta0, a0, a1\n\tld\ta0, 0(a0)\n\tmv\ts0, s1\n\tjr\ta0\n.LBB537_3:                              # %action.if.then.6\n\tcall\tlemma_user_notebook_core0_action_146\n\tj\t.LBB537_10\n.LBB537_4:                              # %action.if.then.12\n\tcall\tlemma_user_notebook_core0_action_158\n\tj\t.LBB537_10\n.LBB537_5:                              # %action.if.else.25\n\tli\ta0, 234\n\tcall\tlemma_user_notebook_core0_action_123\n\tj\t.LBB537_10\n.LBB537_6:                              # %action.if.then.18\n\tli\ta0, 1\n\tj\t.LBB537_9\n.LBB537_7:                              # %action.if.then.21\n\tli\ta0, 2\n\tj\t.LBB537_9\n.LBB537_8:                              # %action.if.then.24\n\tli\ta0, 3\n.LBB537_9:                              # %action.if.merge.2\n\tcall\tlemma_user_notebook_core0_action_164\n.LBB537_10:                             # %action.if.merge.2\n\tmv\ts0, a0\n.LBB537_11:                             # %action.if.merge.2\n\tandi\ta0, s0, 255\n\tli\ta1, 0\n\tld\tra, 24(sp)                      # 8-byte Folded Reload\n\tld\ts0, 16(sp)                      # 8-byte Folded Reload\n\tld\ts1, 8(sp)                       # 8-byte Folded Reload\n\taddi\tsp, sp, 32\n\tret\n.Lfunc_end537:\n\t.size\tlemma_user_notebook_core0_action_165, .Lfunc_end537-lemma_user_notebook_core0_action_165\n'
TARGETS=['.LBB537_11', '.LBB537_6', '.LBB537_7', '.LBB537_8', '.LBB537_5', '.LBB537_5', '.LBB537_5', '.LBB537_5', '.LBB537_3', '.LBB537_3', '.LBB537_4', '.LBB537_4']

def guard(assembly=ASSEMBLY,**changed):
 options={'source':'Lemma.Applications.Notebook.readerRecoverableTransactionPump','configuration':'lemmasim-silicon-usb-clocked-reader-entry2-bulk-notebook','image_key':'notebook'}
 return _jump_assembly_guard(assembly,SYMBOL,'.LJTI537_0',TARGETS,12,0,**{**options,**changed})
class ReaderRecoveryJumpGuard(unittest.TestCase):
 def test_exact_phase_copy_preserves_loaded_target_and_unsigned_guard(self):
  for configuration in ('lemmasim-silicon-usb-clocked-reader-entry2-bulk-notebook','lemmasim-silicon-usb-clocked-reader-entry2-bulk-initialize'):
   r=guard(configuration=configuration);self.assertTrue(r['guard_dominates_load']);self.assertEqual(r['target_preserving_state_copy'],{'instruction':'mv s0,s1','phase_register':'s1','return_register':'s0','preserved_target_register':'a0'})
 def test_different_source_role_or_historical_configuration_rejects(self):
  for change in ({'source':'Other.pump'},{'image_key':'store'},{'configuration':'lemmasim-silicon-usb-clocked-package-entry2-bulk-notebook'},{'configuration':'lemmasim-silicon-usb-clocked-reader-entry2-bulk-any'}):
   with self.subTest(change=change),self.assertRaises(Core0Error):guard(**change)
 def test_overwritten_target_other_state_copy_and_signed_or_wrong_bound_reject(self):
  for before,after in [('mv\ts0, s1','mv\ta0, s1'),('mv\ts0, s1','mv\ts0, a0'),('li\ta0, 11','li\ta0, 10'),('bltu\ta0, s1','blt\ta0, s1')]:
   self.assertIn(before,ASSEMBLY)
   with self.subTest(before=before),self.assertRaises(Core0Error):guard(ASSEMBLY.replace(before,after))
if __name__=='__main__':unittest.main()
