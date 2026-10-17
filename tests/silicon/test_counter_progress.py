"""Counter oracle/admission failure fixtures; these do not execute a guest."""
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import check_guest_counter_progress as c
from core0_common import Core0Error


class CounterProgressOracle(unittest.TestCase):
    def test_literal_masks_keep_s_write_before_each_alias_group(self):
        rows = c.literal_cases()
        self.assertEqual(len(rows), 112)
        for group in range(16):
            low = group % 8
            mask = low if group < 8 else 0xfffffffffffffff8 | low
            inhibit = 5 if group < 8 else 0
            self.assertEqual(rows[group * 7], (1, 10, mask, low, inhibit))
            self.assertEqual(rows[group * 7 + 1:group * 7 + 7],
                             [(mode, op, mask, low, inhibit)
                              for mode in (1, 0) for op in range(3)])
        self.assertEqual(sum(mode == 0 and not mask & (1 << op)
                             for mode, op, _, mask, _ in rows), 24)

    def test_missing_partial_and_uncompleted_records_reject(self):
        for raw in (b'', bytes(c.SIZE - 8), bytes(c.SIZE)):
            with self.subTest(bytes=len(raw)), self.assertRaises(Core0Error):
                c.validate_records(raw, {'lemma_counter_su_lower': (0x80000100, 16)})

    def test_original_and_fork_share_backend_deadline(self):
        # No process is launched. A fork created at75s must retain the original
        # deadline, rather than obtaining another120s transport budget.
        def process(*args, **kwargs):
            return SimpleNamespace(poll=lambda: None, stdin=io.StringIO(),
                                   stdout=io.StringIO())
        data = {'binary': {'path': '/mock/native'}, 'rom': {'path': '/mock/rom'}}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(c.subprocess, 'Popen', side_effect=process), \
                patch.object(c.time, 'monotonic', return_value=75):
            path = Path(directory)
            original = c.Native(data, path, path / 'original', backend_start=0)
            fork = c.Native(data, path, path / 'fork', backend_start=0)
            try:
                self.assertEqual(original.start, 0)
                self.assertEqual(fork.start, 0)
                with patch.object(c.time, 'monotonic', return_value=121):
                    for owner in (original, fork):
                        with self.assertRaisesRegex(Core0Error, '120s host bound'):
                            owner.call('inspect')
                        self.assertEqual(owner.p.stdin.getvalue(), '')
            finally:
                original.log.close()
                fork.log.close()


if __name__ == '__main__':
    unittest.main()
