# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_lvs_alias import cdl_alias, verilog_alias, require_originals


class ReferenceAliases(unittest.TestCase):
    def setUp(self):
        self.cdl = '.SUBCKT macro A_DIN<1> A_DIN<0> VDD! VDDARRAY! VSS!\nM0 A_DIN<1> A_DIN<0> VSS! VSS! nmos w=1u l=0.13u\n.ENDS\n'
        self.verilog = '\n'.join('macro m%d (.\\VDD! (VDDlogic), .\\VDDARRAY! (VDDARRAY), .\\VSS! (VSS));' % i for i in range(3))

    def test_roundtrip_keeps_device_parameters_and_three_supplies(self):
        c, v = cdl_alias(self.cdl), verilog_alias(self.verilog, True)
        require_originals(c, self.cdl, v, self.verilog)
        self.assertIn('w=1u l=0.13u', c)
        self.assertEqual(v.count('(VDDlogic)'), 3)
        self.assertEqual(v.count('(VDDARRAY)'), 3)
        self.assertEqual(v.count('(VSS)'), 3)

    def test_reference_mutations_reject(self):
        c, v = cdl_alias(self.cdl), verilog_alias(self.verilog, True)
        for changed in (c.replace('A_DIN[1]', 'A_DIN[0]', 1), c.replace('w=1u', 'w=2u')):
            with self.assertRaises(ValueError):require_originals(changed, self.cdl, v, self.verilog)
        with self.assertRaises(ValueError):require_originals(c, self.cdl, v.replace('(VSS)', '(VDDlogic)', 1), self.verilog)

    def test_case_insensitive_or_numeric_reader_collisions_reject(self):
        for changed in (self.cdl + ' lemma_lvs_VSS', self.cdl + ' LEMMA_LVS_VSS', self.cdl + ' A_DIN[1]', self.cdl.replace('<1>', '<01>')):
            with self.assertRaises(ValueError):cdl_alias(changed)
        with self.assertRaises(ValueError):verilog_alias(self.verilog + ' LEMMA_LVS_VSS', True)

    def test_missing_real_power_connection_rejects(self):
        with self.assertRaises(ValueError):verilog_alias(self.verilog.replace('.\\VSS! ', '.missing ', 1), True)


if __name__ == '__main__':
    unittest.main()
