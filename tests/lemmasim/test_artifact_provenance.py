"""Independent small malformed artifacts for the new literal-load boundary."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import (validate_readonly_pmp_lookup, validate_machine,
                          validate_user_abi_data, USER_ABI_INITIAL_DATA,
                          validate_ir)
from core0_common import Core0Error


def fixture():
    # Fixed literal expected font table, independently written as artifact bytes.
    values=[10530,8778,21973,1488,0,448,0,4772,
            31599,11415,29671,29647,23497,31183,31215,29330,31727,31695,
            0,0,0,3640,0,0,0,11245,27566,31015,27502,31143,31140,31087,23533,29847,
            0,0,18727,24557,24573,31599,31716,31609,27565,31183,29842,23407,23402,23423,23213,23186]
    unit={'configuration':'lemmasim-notebook','role':'user','functions':[{
        'source':'Lemma.Ink.Surface.letter','symbol':'letter','args':['u64'],'effects':[]}]}
    ir='@switch.table.letter = private unnamed_addr constant [50 x i64] ['+', '.join('i64 '+str(v) for v in values)+'''], align 8
define i64 @letter(i64 %arg0) {
entry:
 %index = add i64 %arg0, -40
 %bound = icmp ult i64 %index, 50
 br i1 %bound, label %lookup, label %done
lookup:
 %pointer = getelementptr inbounds nuw [50 x i64], ptr @switch.table.letter, i64 0, i64 %index
 %loaded = load i64, ptr %pointer, align 8
 br label %done
done:
 %result = phi i64 [ %loaded, %lookup ], [ 31207, %entry ]
 ret i64 %result
}
'''
    return ir,unit


class LemmaSimArtifactBoundaries(unittest.TestCase):
    def test_literal_is_bounded_readonly_and_keeps_historical_scope(self):
        ir,unit=fixture();sites,tables=validate_readonly_pmp_lookup(ir,unit,optimized=True)
        self.assertEqual(len(sites),1);self.assertEqual(tables[0]['index_bound'],50)
        bad=copy.deepcopy(unit);bad['configuration']='normal'
        with self.assertRaises(Core0Error): validate_readonly_pmp_lookup(ir,bad,optimized=True)
        for changed in [ir.replace('constant [50','global [50'),ir.replace('i64 31599','i64 31600'),
                        ir.replace('i64 31015','i64 0'),ir.replace('i64 31015','i64 31014'),
                        ir.replace('i64 21973','i64 21974'),ir.replace('i64 31609','i64 31608'),
                        ir.replace('add i64 %arg0, -40','add i64 %arg0, -41'),
                        ir.replace('icmp ult i64 %index, 50','icmp ult i64 %index, 51'),
                        ir.replace('br i1 %bound, label %lookup, label %done','br i1 %bound, label %done, label %lookup'),
                        ir.replace('i64 0, i64 %index','i64 0, i64 50'),
                        ir.replace('ret i64 %result','store i64 0, ptr %pointer\n ret i64 %result')]:
            with self.assertRaises(Core0Error): validate_readonly_pmp_lookup(changed,unit,optimized=True)

    def test_new_pmp_register_is_scoped_to_new_binding(self):
        text=' 80000000: csrr a0, pmpaddr5\n'
        with self.assertRaises(Core0Error): validate_machine(text)
        validate_machine(text,configuration='lemmasim-notebook')
        with self.assertRaises(Core0Error): validate_machine(text,user=True,configuration='lemmasim-notebook')

    def test_o0_cannot_masquerade_as_an_o2_literal_lowering(self):
        ir,unit=fixture()
        unit.update(used_execution_ops=[],used_device_ops=[],used_loops=[])
        ir='target triple = "riscv64-unknown-unknown-elf"\n'+ir
        self.assertEqual(len(validate_ir(ir,unit,optimized=True,optimization='O2')['readonly_optimizer_tables']),1)
        with self.assertRaises(Core0Error):
            validate_ir(ir,unit,optimized=True,optimization='O0')
        with self.assertRaises(Core0Error):
            validate_ir(ir,unit,optimized=True,optimization='unknown')

    def test_notebook_initializer_owner_requires_exact_new_profile(self):
        section='  [ 3] .data.user_abi PROGBITS 0000000000000000 000040 000010 00 WA 0 0 8\n'
        assembly='.section .data.user_abi, "aw", @progbits\n.balign 8\n.quad 0\n.quad 1\n.option pop\n'
        for owner in ['users/store/startup.o', 'users/notebook/startup.o']:
            with self.assertRaises(Core0Error):
                validate_user_abi_data(section,USER_ABI_INITIAL_DATA,'',assembly,object_file=owner)
            self.assertEqual(validate_user_abi_data(section,USER_ABI_INITIAL_DATA,'',assembly,
                object_file=owner,configuration='lemmasim-notebook')['words'],[0,1])
        with self.assertRaises(Core0Error):
            validate_user_abi_data(section,USER_ABI_INITIAL_DATA,'',assembly,
                object_file='users/foreign/startup.o',configuration='lemmasim-notebook')


if __name__=='__main__': unittest.main()
