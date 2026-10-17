"""Cold deployment guards; no guest or cold execution is claimed."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_usb_cold_boundary import validate_cold_binding


class RetainedColdDeployment(unittest.TestCase):
    def args(self, profile, sequence=11, high_water=72):
        return SimpleNamespace(profile=profile, saved_sequence=sequence, high_water=high_water)

    def boundary(self, **updates):
        return dict(status='PASS', source_before_after_equal=True, saved_sequence=11, high_water=72, **updates)

    def test_historical_absent_profile_remains_usb8(self):
        validate_cold_binding(self.args('lemma-silicon-dev/0.8.0'), self.boundary())
        validate_cold_binding(self.args('lemma-silicon-dev/0.8.0', 5, 36),
                              dict(status='PASS', source_before_after_equal=True, saved_sequence=5, high_water=36))

    def test_wire11_requires_its_explicit_boundary(self):
        validate_cold_binding(self.args('lemma-silicon-dev/0.11.0'),
                              self.boundary(profile='lemma-silicon-dev/0.11.0'))
        for profile in (None, 'lemma-silicon-dev/0.8.0', 'lemma-silicon-dev/0.13.0'):
            data = self.boundary()
            if profile is not None: data['profile'] = profile
            with self.subTest(profile=profile):
                with self.assertRaises(ValueError): validate_cold_binding(self.args('lemma-silicon-dev/0.11.0'), data)

    def test_other_profile_cannot_reuse_a_wire_boundary(self):
        for profile in ('lemma-silicon-dev/0.8.0', 'lemma-silicon-dev/0.13.0'):
            with self.assertRaises(ValueError):
                validate_cold_binding(self.args(profile), self.boundary(profile='lemma-silicon-dev/0.11.0'))

    def test_wrong_saved_sequence_receipt_count_or_unstable_state_rejects(self):
        good = self.boundary(profile='lemma-silicon-dev/0.11.0')
        for field, value in (('saved_sequence', 5), ('high_water', 36), ('high_water', 73),
                             ('status', 'FAIL'), ('source_before_after_equal', False)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    validate_cold_binding(self.args('lemma-silicon-dev/0.11.0'), {**good, field: value})


if __name__ == '__main__': unittest.main()
