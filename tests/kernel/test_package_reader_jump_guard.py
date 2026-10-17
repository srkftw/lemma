"""Reader index rebinding observer; the actual whole object qualifies separately."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import _jump_assembly_guard
from core0_common import Core0Error

# Instruction/label positions from the retained actual Package Reader object.
# This is a host observer fixture, never an RV64 application or compiler input.
ASSEMBLY='''reader:
.Lfunc_begin0:
 addi sp,sp,-16
 sd ra,8(sp)
 sd s0,0(sp)
 mv s0,a0
 call readerActive
 bnez a0,.LBB0_2
 li a1,72
 mv a0,s0
 call readerGet
 beqz a0,.LBB0_4
.LBB0_2:
 li a1,0
.LBB0_3:
 andi a0,a0,255
 ld ra,8(sp)
 ld s0,0(sp)
 addi sp,sp,16
 ret
.LBB0_4:
 li a0,5
 bltu a0,a1,.LBB0_11
 mv a0,a1
 li a1,0
 slli a0,a0,3
.Lpcrel_hi0:
 auipc a2,%pcrel_hi(.LJTI0_0)
 addi a2,a2,%pcrel_lo(.Lpcrel_hi0)
 add a0,a0,a2
 ld a2,0(a0)
 li a0,94
 jr a2
.LBB0_6:
 li a1,96
 mv a0,s0
 call readerGet
 j .LBB0_3
.LBB0_7:
 mv a0,s0
 call readerPoll
 j .LBB0_3
.LBB0_8:
 mv a0,s0
 call readerBegin
 j .LBB0_2
.LBB0_9:
 li a1,120
 mv a0,s0
 call readerGet
 mv a2,a0
 mv a0,a1
 beqz a2,.LBB0_2
 mv a0,a2
 j .LBB0_2
.LBB0_11:
 li a1,0
 li a0,240
 j .LBB0_3
.Lfunc_end0:
 .size reader,.Lfunc_end0-reader
'''
TARGETS=['.LBB0_6','.LBB0_8','.LBB0_7','.LBB0_7','.LBB0_9','.LBB0_3']
OPTIONS={'source':'Lemma.Courses.PackageReader.step',
 'configuration':'lemmasim-silicon-package-closure-entry2-bulk-notebook','image_key':'notebook'}

def guard(assembly=ASSEMBLY,**changed):
    return _jump_assembly_guard(assembly,'reader','.LJTI0_0',TARGETS,6,0,**{**OPTIONS,**changed})

class PackageReaderJumpGuard(unittest.TestCase):
    def test_selected_bound_rebind_and_dominating_guard(self):
        for configuration in ('lemmasim-silicon-package-closure-entry2-bulk-notebook',
                              'lemmasim-silicon-package-closure-entry2-bulk-initialize',
                              'lemmasim-silicon-package-chooser-bulk-notebook',
                              'lemmasim-silicon-package-chooser-bulk-initialize',
                              'lemmasim-silicon-usb-clocked-reader-entry2-bulk-notebook',
                              'lemmasim-silicon-usb-clocked-reader-entry2-bulk-initialize'):
            report=guard(configuration=configuration)
            self.assertTrue(report['guard_dominates_load'])
            self.assertEqual(report['bounded_index_rebind'],{'instruction':'mv a0,a1',
                'instruction_index':18,'bounded_register':'a1','scaled_register':'a0'})

    def test_bound_source_transfer_overwrite_and_bypass_reject(self):
        for before,after in (('li a0,5','li a0,4'),('bltu a0,a1','blt a0,a1'),
                             ('mv a0,a1\n li a1,0','mv a0,a2\n li a1,0'),
                             ('mv a0,a1\n li a1,0','mv a0,a1\n li a0,0'),
                             ('bltu a0,a1,.LBB0_11','bltu a0,a1,.LBB0_4'),
                             ('slli a0,a0,3','slli a0,a0,2'),
                             ('li a0,94','li a2,94'),('mv s0,a0','mv s0,a1')):
            with self.subTest(before=before),self.assertRaises(Core0Error):
                guard(ASSEMBLY.replace(before,after))

    def test_no_other_source_image_or_configuration_acquires_rebinding(self):
        for changed in ({'source':'Other.step'},{'image_key':'course'},
                        {'configuration':'lemmasim-silicon-course-await-bulk-notebook'},
                        {'configuration':'lemmasim-silicon-package-closure-entry2-bulk-any'}):
            with self.subTest(changed=changed),self.assertRaises(Core0Error):guard(**changed)

if __name__=='__main__':unittest.main()
