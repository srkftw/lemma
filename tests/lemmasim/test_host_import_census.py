"""Actual subprocess exit/import accounting, without a guest execution claim."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ImportCensusExit(unittest.TestCase):
    def invoke(self, directory, *, exit_code=0, publish=True):
        scripts = directory / 'scripts'
        scripts.mkdir()
        observer = scripts / 'host_import_census.py'
        shutil.copyfile(ROOT / 'scripts/host_import_census.py', observer)
        (scripts / 'late.py').write_text('VALUE = 73\n')
        cli = scripts / 'entry.py'
        cli.write_text('import atexit, importlib\n'
                       'atexit.register(lambda: importlib.import_module("late"))\n'
                       f'raise SystemExit({exit_code})\n')
        output = directory / ('census.json' if publish else 'missing/census.json')
        result = subprocess.run([sys.executable, '-B', str(observer), str(output), str(cli)],
                                capture_output=True, text=True, timeout=10)
        return result, output, observer, cli, scripts / 'late.py'

    def test_actual_runpy_cleanup_and_exit_import_are_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            result, output, observer, cli, late = self.invoke(directory)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
            actual = json.loads(output.read_text())
            self.assertEqual(actual, {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in (observer, cli, late)})

    def test_cli_failure_retains_its_exit_code_and_final_census(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, output, _, _, _ = self.invoke(Path(tmp), exit_code=7)
            self.assertEqual((result.returncode, result.stderr), (7, ''))
            self.assertIn('scripts/late.py', json.loads(output.read_text()))

    def test_publication_failure_cannot_exit_successfully(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, output, _, _, _ = self.invoke(Path(tmp), publish=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
