"""Laboratory-only external boot backing condition; no guest result injection."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import lemmasim_auth as auth


class BootWriteLimit(unittest.TestCase):
    def test_missing_condition_keeps_legacy_launch_admission(self):
        self.assertIsNone(auth.boot_write_limit(None, 'student', 64, True))

    def test_only_explicit_single_thread_cold_laboratory_condition(self):
        self.assertEqual(auth.boot_write_limit('000:01024:00768', 'laboratory', 1), '0:1024:768')
        for mode, threads, restoring in [('student', 1, False), ('developer', 1, False),
                                          ('laboratory', 2, False), ('laboratory', 1, True)]:
            with self.subTest(mode=mode, threads=threads, restoring=restoring), self.assertRaises(ValueError):
                auth.boot_write_limit('0:1024:768', mode, threads, restoring)

    def test_invalid_extent_never_reaches_a_machine(self):
        for value in ['0:0:0', '1024:512:768', '-1:1024:768', '0:0x400:768',
                      '0:1024:768:0', f'0:{auth.product.BOOT_BYTES + 1}:0',
                      f'0:1024:{auth.product.BOOT_BYTES + 1}']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                auth.boot_write_limit(value, 'laboratory', 1)

    def test_student_cli_rejects_before_owner_or_preparation(self):
        with patch.object(auth.sessions, 'serve') as serve, patch.object(auth, 'prepared') as prepared:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                auth.main(['--public-development-key', 'launch', '--prepared', '/missing',
                           '--session-dir', '/missing', '--mode', 'student',
                           '--boot-write-limit', '0:1024:768'])
            self.assertEqual(stopped.exception.code, 2)
            serve.assert_not_called()
            prepared.assert_not_called()
