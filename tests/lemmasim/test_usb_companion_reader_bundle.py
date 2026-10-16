"""Reject wrong-profile and downgraded software authority before opening media."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from silicon_guest_bundle import (usb_native_deployment, usb_software_deployment,
    bundle_configurations, USB_CLOCKED_PROFILE, SCHEMA_USB_COMPANION_READER,
    SCHEMA_USB_PACKAGE_RECOVERY, USB_COMPANION_READER_CONFIGURATIONS)


class CompanionReaderBundleAuthority(unittest.TestCase):
    def test_versioned_entry_contract_cannot_be_downgraded_or_mixed(self):
        selected = usb_native_deployment(USB_CLOCKED_PROFILE, companion_reader=True)
        self.assertEqual(selected[0], SCHEMA_USB_COMPANION_READER)
        manifest = {'profile': USB_CLOCKED_PROFILE, 'schema': selected[0],
                    'software_deployment': usb_software_deployment(*selected)}
        self.assertEqual(bundle_configurations(manifest), USB_COMPANION_READER_CONFIGURATIONS)
        for mutation in ('schema', 'entry_contract', 'recovery_contract', 'reader_contract', 'configurations'):
            bad = copy.deepcopy(manifest)
            if mutation == 'schema': bad['schema'] = SCHEMA_USB_PACKAGE_RECOVERY
            elif mutation in ('entry_contract','recovery_contract','reader_contract'): del bad['software_deployment'][mutation]
            else: bad['software_deployment']['configurations']['usb-clocked-reader-entry2-bulk-notebook'] = 'lemmasim-silicon-usb-clocked-package-retry-bulk-notebook'
            with self.assertRaises(ValueError): bundle_configurations(bad)
        for old_flag in ('recovery', 'closure_recovery', 'package_recovery', 'package_entry2'):
            with self.assertRaises(ValueError):
                usb_native_deployment(USB_CLOCKED_PROFILE, companion_reader=True, **{old_flag: True})
        with self.assertRaises(ValueError):
            usb_native_deployment('lemma-silicon-dev/0.3.0', companion_reader=True)

    def test_invalid_cli_selection_creates_no_bundle(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'must-remain-absent'
            command = [str(root / 'scripts/lemmasim'), 'native-bundle-build',
                '--profile', USB_CLOCKED_PROFILE, '--usb-companion-reader-deployment',
                '--usb-package-recovery-deployment', '--output-dir', str(output)]
            result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires exclusive Clocked13 schema11', result.stderr + result.stdout)
            self.assertFalse(output.exists())

    def test_new_launch_requires_live_recovery_before_touching_media(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            session = Path(directory) / 'must-remain-absent'
            command = [str(root / 'scripts/lemmasim'), 'session', '--profile', USB_CLOCKED_PROFILE,
                '--workload', 'usb-clocked-reader-entry2-bulk-notebook', '--mode', 'laboratory',
                '--session-dir', str(session), '--paused', '--headless']
            result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('usb-recovery', result.stderr + result.stdout)
            self.assertFalse(session.exists())
