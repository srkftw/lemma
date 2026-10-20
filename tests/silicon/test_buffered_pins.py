# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_buffered_pins import buffer_kind, repairable_signal_input


def library(kind, pin, function, sense):
    return f'''cell ({kind}) {{
      pin (A) {{ direction : "input"; }}
      pin ({pin}) {{ direction : "output"; function : "{function}";
        timing () {{ related_pin : "A"; timing_sense : {sense}; }} }}
    }}'''


class OriginalBufferFunctions(unittest.TestCase):
    def test_read_enable_is_an_original_signal_input_with_closed_exclusions(self):
        for pin in ('A_DIN[0]', 'A_DIN[63]', 'A_ADDR[0]', 'A_ADDR[7]',
                    'A_MEN', 'A_REN', 'A_WEN'):
            self.assertTrue(repairable_signal_input(pin, 'INPUT'), pin)
            self.assertFalse(repairable_signal_input(pin, 'OUTPUT'), pin)
            self.assertFalse(repairable_signal_input(pin, 'INOUT'), pin)
        for pin in ('A_CLK', 'A_BIST_REN', 'A_BIST_DIN[0]', 'A_DLY', 'A_BM[0]',
                    'A_DOUT[0]', 'VDD!', 'VDDARRAY!', 'VSS!', 'A_REN_suffix'):
            self.assertFalse(repairable_signal_input(pin, 'INPUT'), pin)

    def test_original_quoted_direction_and_parenthesized_inverter(self):
        self.assertEqual(buffer_kind('sg13g2_dlygate4sd3_1', library(
            'sg13g2_dlygate4sd3_1', 'X', 'A', 'positive_unate')), ('X', 0))
        self.assertEqual(buffer_kind('sg13g2_inv_1', library(
            'sg13g2_inv_1', 'Y', '!(A)', 'negative_unate')), ('Y', 1))

    def test_function_or_unateness_cannot_be_waived(self):
        for function, sense in [('!A', 'positive_unate'), ('A&B', 'positive_unate'),
                                ('A', 'negative_unate')]:
            with self.subTest(function=function, sense=sense), self.assertRaises(ValueError):
                buffer_kind('sg13g2_buf_2', library('sg13g2_buf_2', 'X', function, sense))

    def test_unrelated_logic_is_a_driver_boundary(self):
        self.assertIsNone(buffer_kind('sg13g2_nand2_1', ''))
