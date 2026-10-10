"""Independent small malformed artifacts for the new literal-load boundary."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import (validate_readonly_pmp_lookup, validate_machine,
                          validate_user_abi_data, USER_ABI_INITIAL_DATA)
from core0_common import Core0Error


def fixture():
    values=[23533,18724,4681,27471,31565,31183,23405]
    unit={'configuration':'lemmasim-notebook','role':'user','functions':[{
        'source':'Lemma.Ink.Surface.glyph','symbol':'glyph','args':['u64'],'effects':[]}]}
    ir='@switch.table.glyph = private unnamed_addr constant [7 x i64] ['+', '.join('i64 '+str(v) for v in values)+'''], align 8
define i64 @glyph(i64 %arg0) {
entry:
 %bound = icmp ult i64 %arg0, 7
 br i1 %bound, label %lookup, label %done
lookup:
 %pointer = getelementptr inbounds nuw [7 x i64], ptr @switch.table.glyph, i64 0, i64 %arg0
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
        self.assertEqual(len(sites),1);self.assertEqual(tables[0]['index_bound'],7)
        bad=copy.deepcopy(unit);bad['configuration']='normal'
        with self.assertRaises(Core0Error): validate_readonly_pmp_lookup(ir,bad,optimized=True)
        for changed in [ir.replace('constant [7','global [7'),ir.replace('i64 23533','i64 23534'),
                        ir.replace('icmp ult i64 %arg0, 7','icmp ult i64 %arg0, 8'),
                        ir.replace('br i1 %bound, label %lookup, label %done','br i1 %bound, label %done, label %lookup'),
                        ir.replace('i64 0, i64 %arg0','i64 0, i64 7'),
                        ir.replace('ret i64 %result','store i64 0, ptr %pointer\n ret i64 %result')]:
            with self.assertRaises(Core0Error): validate_readonly_pmp_lookup(changed,unit,optimized=True)

    def test_new_pmp_register_is_scoped_to_new_binding(self):
        text=' 80000000: csrr a0, pmpaddr5\n'
        with self.assertRaises(Core0Error): validate_machine(text)
        validate_machine(text,configuration='lemmasim-notebook')
        with self.assertRaises(Core0Error): validate_machine(text,user=True,configuration='lemmasim-notebook')

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
