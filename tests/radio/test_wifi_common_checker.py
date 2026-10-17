"""Host admission failures only; no mocked CPU/device result counts as a pass."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('common_guest_checker', ROOT / 'scripts/check_wifi_common_guest.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class CommonCheckerAdmission(unittest.TestCase):
    def test_rejection_survives_python_optimization(self):
        code = "import sys;sys.path.insert(0,'scripts');from check_wifi_common_guest import require;require(False,'expected rejection')"
        result = subprocess.run([sys.executable, '-O', '-c', code], cwd=ROOT, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'expected rejection', result.stderr)

    def test_resume_cannot_skip_whole_target_admission(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
            parent = Path(directory)
            observation = parent / 'observed.json'
            observation.write_text(json.dumps({'status': 'PASS_OBSERVED_GENUINE_CPU_CUT', 'cycle': 12}))
            out = parent / 'unused'
            argv = ['check', '--native-build', str(parent), '--target-capture', str(parent),
                    '--rom-bundle', str(parent), '--resume-observation', str(observation), '--work-dir', str(out)]
            with (patch.object(sys, 'argv', argv),
                  patch.object(checker, 'validate_inputs', side_effect=RuntimeError('unqualified target')),
                  patch.object(checker, 'initial_guest') as initial,
                  patch.object(checker, 'exact_suffix') as suffix):
                with self.assertRaisesRegex(RuntimeError, 'unqualified target'):
                    checker.main()
            initial.assert_not_called()
            suffix.assert_not_called()
            self.assertEqual(json.loads((out / 'result.json').read_text())['status'], 'FAIL')

    def test_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
            parent = Path(directory)
            marker = parent / 'original-failure.json'
            marker.write_text('retained')
            argv = ['check', '--native-build', str(parent), '--target-capture', str(parent),
                    '--rom-bundle', str(parent), '--work-dir', str(parent)]
            with patch.object(sys, 'argv', argv), patch.object(checker, 'validate_inputs') as inputs:
                with self.assertRaises(SystemExit):
                    checker.main()
            inputs.assert_not_called()
            self.assertEqual(marker.read_text(), 'retained')


if __name__ == '__main__':
    unittest.main()
