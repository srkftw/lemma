import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import multimodal_budget as b

class Budget(unittest.TestCase):
    def test_independent_spec_totals(self):
        # Literal expectations copied from attached section8, independently of
        # the multiplicative producer. Catch channel/rate/slot substitutions.
        self.assertEqual(b.reference('economy')['upstream_payload_Bps'],3902720)
        self.assertEqual(b.reference('stress')['upstream_payload_Bps'],28094720)
        self.assertEqual(b.reference('economy')['two_second_payload_bytes'],7805440)
        self.assertEqual(b.reference('stress')['two_second_payload_bytes'],56189440)
        self.assertEqual(b.reference('stress',True)['upstream_payload_Bps'],39015680)
        self.assertEqual(b.reference('stress',True)['downstream_pcm_Bps'],384000)
    def test_fullspeed_never_admits_economy(self):
        r=b.account('economy',False,window_ms=100,upstream_bps=12000000,downstream_bps=12000000)
        self.assertIn('upstream-wire-capacity',r['rejection_reasons'])
        self.assertGreater(r['wire_upstream_Bps'],3902720)
    def test_memory_and_link_independent(self):
        r=b.account('stress',True,window_ms=2000,upstream_bps=1000000000,downstream_bps=1000000000)
        self.assertIn('owned-memory-pool',r['rejection_reasons'])
        self.assertNotIn('upstream-wire-capacity',r['rejection_reasons'])
    def test_feasible_arithmetic_is_not_execution(self):
        r=b.account('stress',True,window_ms=20,upstream_bps=1000000000,downstream_bps=1000000000)
        self.assertTrue(r['arithmetic_feasible'])
        self.assertEqual(r['real_time_factor'],'UNMEASURED')
        self.assertIn('NOT_ADMITTED',r['admitted_profile_mode'])
        self.assertEqual(r['raw_retention'],'disabled')
    def test_bad_inputs_fail(self):
        for bad in (0,-1,2001,True):
            with self.assertRaises(ValueError): b.account('stress',True,window_ms=bad,upstream_bps=1,downstream_bps=1)
        with self.assertRaises(ValueError): b.product((1 << 32,1 << 32))
        with self.assertRaises(ValueError): b.reference('imaginary')
