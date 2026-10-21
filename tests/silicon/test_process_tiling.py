# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_enclosure import GeometryError
from silicon_pen_process import process_tiling_script, connected_reference_signal_bytes


class ProcessTilingTests(unittest.TestCase):
    def setUp(self):
        self.original = (Path(__file__).resolve().parents[2] / 'tooling/silicon/process.tcl').read_text()

    def test_default_keeps_exact_original_recipe(self):
        self.assertEqual(process_tiling_script(self.original, None), self.original)

    def test_600um_changes_partition_and_requires_exact_rule_table(self):
        result = process_tiling_script(self.original, 600)
        self.assertEqual(result.count('drc style drc(full)'), 1)
        self.assertIn('drc *stepsize 600um', result)
        self.assertIn('if {$before_rules ne $after_rules}', result)
        self.assertEqual(result.count('    drc *halo\n'), 2)
        self.assertNotIn('drc ignore', result)
        self.assertTrue(result.endswith(self.original.split('    drc style drc(full)\n')[1]))

    def test_mutants_cannot_reduce_halo_rules_or_change_scope(self):
        for mutant in (self.original.replace('drc(full)', 'drc(fast)'),
                       self.original.replace('    drc style drc(full)\n', ''),
                       self.original + '    drc style drc(full)\n',
                       self.original + 'drc *halo 0\n',
                       self.original + 'drc ignore Metal1\n'):
            with self.subTest(mutant=mutant[-60:]), self.assertRaises(GeometryError):
                process_tiling_script(mutant, 600)
        with self.assertRaises(GeometryError):
            process_tiling_script(self.original, 599)

    def test_connected_reference_accepts_only_two_exact_pg_serializers(self):
        suffix = ('module lemma_pen (clk,\n    write,\n    addr,\n    wdata,\n'
                  '    VDDlogic,\n    VDDARRAY,\n    VSS);\n'
                  ' inout VDDlogic;\n inout VDDARRAY;\n inout VSS;\n'
                  ' cell u (.VDD(VDDlogic), .VSS(VSS), .A(addr[3]));\n')
        prefix = suffix.replace('    wdata,\n    VDDlogic,\n    VDDARRAY,\n    VSS);', '    wdata);')
        prefix = prefix.replace('    write,\n    addr,',
                                '    write,\n    VDDlogic,\n    VDDARRAY,\n    VSS,\n    addr,')
        expected = connected_reference_signal_bytes(suffix)
        self.assertEqual(connected_reference_signal_bytes(prefix), expected)
        for form in (suffix, prefix):
            for mutant in (form.replace('.VDD(VDDlogic)', '.VDD(VSS)'),
                           form.replace('addr[3]', 'addr[2]')):
                self.assertNotEqual(connected_reference_signal_bytes(mutant), expected)
            for mutant in (form.replace(' inout VSS;\n', ''),
                           form.replace('    VDDARRAY,', '    VDDARRAY,\n    extra,'),
                           form.replace('    VDDlogic,', '    VDDlogic2,'),
                           form + ' inout VSS;\n'):
                with self.subTest(mutant=mutant), self.assertRaises(ValueError):
                    connected_reference_signal_bytes(mutant)
