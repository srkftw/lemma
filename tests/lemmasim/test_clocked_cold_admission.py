"""Clocked cold admission guards; these do not establish cold execution."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import check_usb_cold_boundary as cold
import silicon_guest_bundle


class ClockedColdAdmission(unittest.TestCase):
    def args(self, **changes):
        return SimpleNamespace(**{'profile': cold.CLOCKED_PROFILE,
            'saved_sequence': 11, 'high_water': 72, 'native_bundle': Path('/unused'),
            'rtl_source_root': None, 'guest_source_root': None, **changes})

    def test_clocked_requires_its_exact_saved11_boundary(self):
        boundary = dict(status='PASS', source_before_after_equal=True,
            profile=cold.CLOCKED_PROFILE, saved_sequence=11, high_water=72)
        cold.validate_cold_binding(self.args(), boundary)
        for field, value in (('profile', None), ('profile', 'lemma-silicon-dev/0.11.0'),
                             ('saved_sequence', 5), ('high_water', 36),
                             ('source_before_after_equal', False)):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    cold.validate_cold_binding(self.args(), {**boundary, field: value})

    def test_missing_or_mixed_authority_rejects_before_package_access(self):
        with mock.patch.object(silicon_guest_bundle, 'prepared',
                               side_effect=AssertionError('package access')):
            for changes in ({'native_bundle': None}, {'rtl_source_root': Path('/live')},
                            {'guest_source_root': Path('/live')}):
                with self.subTest(changes=changes):
                    with self.assertRaises(ValueError):
                        cold.validate_clocked_deployment(self.args(**changes))

    def test_bad_package_rejects_before_checker_or_peer_creation(self):
        args = self.args(expected_source_sha=cold.sha(cold.__file__))
        with mock.patch.object(silicon_guest_bundle, 'prepared',
                               side_effect=ValueError('incomplete package')) as admission:
            with mock.patch.object(cold, 'ColdChecker', side_effect=AssertionError('actor creation')):
                with self.assertRaisesRegex(ValueError, 'incomplete package'):
                    cold.execute(args)
            admission.assert_called_once_with(Path('/unused'), 'rtl',
                'usb-clocked-bulk-notebook', cold.CLOCKED_PROFILE)

    def test_historical_profiles_do_not_use_new_clocked_admission(self):
        with mock.patch.object(silicon_guest_bundle, 'prepared',
                               side_effect=AssertionError('new admission')):
            for profile in ('lemma-silicon-dev/0.8.0', 'lemma-silicon-dev/0.11.0'):
                cold.validate_clocked_deployment(self.args(profile=profile))

    def test_nominal_clocks_require_all_eight_facts(self):
        facts = dict(zip(('quantum_hz', 'controller_hz', 'nominal_phy_hz', 'position',
                          'host_ppm', 'chip_ppm', 'host_initial_phase', 'chip_initial_phase'),
                         (2400000000, 100000000, 48000000, 0, 0, 0, 0, 0)))
        cold.validate_clocked_facts({'usb_clocks': facts})
        for key, value in facts.items():
            with self.subTest(key=key):
                for altered in ({**facts, key: value + 1},
                                {**facts, key: float(value)},
                                {k: v for k, v in facts.items() if k != key}):
                    with self.assertRaises(ValueError):
                        cold.validate_clocked_facts({'usb_clocks': altered})
        for wrong in (None, False, []):
            with self.assertRaises(ValueError):
                cold.validate_clocked_facts({'usb_clocks': wrong})


if __name__ == '__main__': unittest.main()
