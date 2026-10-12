"""Fail-closed mutations of the actual optimized Objects-v3 reply quota."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from audit_kernel import validate_readonly_pmp_lookup
from core0_common import Core0Error


class ObjectsV3Readonly(unittest.TestCase):
    def test_actual_guarded_lookup(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/objects-v3-reply-readonly-generated.json').read_text())
        sites, tables = validate_readonly_pmp_lookup(fixture['ir'], fixture['unit'], optimized=True)
        self.assertEqual(len(sites), 1)
        self.assertEqual(tables[0]['values'], [8, 8, 7])
        self.assertEqual((tables[0]['index_bound'], tables[0]['default']), (3, 0))

    def test_mutations_of_bytes_guard_default_and_uses_rejected(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/objects-v3-reply-readonly-generated.json').read_text())
        ir, unit = fixture['ir'], fixture['unit']
        mutations = [ir.replace('i64 7], align', 'i64 8], align'),
                     ir.replace('constant [3', 'global [3'),
                     ir.replace('%arg0, -1', '%arg0, 0'),
                     ir.replace('%switch.tableidx, 3', '%switch.tableidx, 4'),
                     ir.replace('icmp ult', 'icmp slt'),
                     ir.replace('[ 0, %entry ]', '[ 8, %entry ]'),
                     ir.replace('i64 %switch.tableidx', 'i64 %arg0'),
                     ir.replace('br i1 %0, label %switch.lookup, label %if.merge.2', 'br label %switch.lookup'),
                     ir.replace('load i64', 'load i32'),
                     ir.replace('align 8\n  br label', 'align 8\n  %extra = load i64, ptr %switch.gep, align 8\n  br label'),
                     ir + '@foreign = constant i64 0\n']
        for bad in mutations:
            self.assertNotEqual(bad, ir)
            with self.subTest(mutation=bad), self.assertRaises(Core0Error):
                validate_readonly_pmp_lookup(bad, unit, optimized=True)

    def test_wrong_source_role_effects_and_arguments_rejected(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/objects-v3-reply-readonly-generated.json').read_text())
        ir, unit = fixture['ir'], fixture['unit']
        for field, value in [('source', 'Other.replyLimit'), ('args', ['u32']), ('effects', ['checked-access'])]:
            bad = copy.deepcopy(unit)
            bad['functions'][0][field] = value
            with self.assertRaises(Core0Error):
                validate_readonly_pmp_lookup(ir, bad, optimized=True)
        for role in ('user', 'firmware'):
            with self.assertRaises(Core0Error):
                validate_readonly_pmp_lookup(ir, {**unit, 'role': role}, optimized=True)
        with self.assertRaises(Core0Error):
            validate_readonly_pmp_lookup(ir, unit, optimized=False)


if __name__ == '__main__':
    unittest.main()
