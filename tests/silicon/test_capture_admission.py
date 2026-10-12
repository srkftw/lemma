# SPDX-License-Identifier: Apache-2.0
"""Failure injection at the capture/device boundary; no guest behavior oracle."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import lemmasim_session as runtime


class AdmittingMachine:
    identity = {'backend': 'literal transport failure fixture'}

    def __init__(self):
        self.commands = []
        self.admitted = []
        self.cycle = 10
        self.fail_after_admission = False

    def call(self, command):
        self.commands.append(command)
        if command.startswith('inject ') or command in ('warm-reset', 'cold-cycle'):
            self.admitted.append(command)
            if self.fail_after_admission:
                raise RuntimeError('device admitted event; subsequent inspection failed')
        if command.startswith('snapshot '):
            Path(command[9:]).write_bytes(b'literal complete checkpoint')
        if command.startswith('run '):
            self.cycle += int(command[4:])
        return {'cycle': self.cycle, 'ticks': 1, 'finished': False}

    def close(self):
        pass


class CaptureAdmissionFailures(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'live'
        self.directory.mkdir()
        self.machine = AdmittingMachine()
        self.session = runtime.Session(self.machine, self.directory,
            SimpleNamespace(mode='developer', paused=True, quantum=1000))
        self.addCleanup(self.session.close)
        self.input = {'action': 'inject', 'kind': 'pen', 'cycle': 25,
                      'words': [2**64-1, 3, 4, 4095, 7, 2, 3]}

    def rows(self):
        return [json.loads(line) for line in
                (self.directory / 'external.jsonl').read_text().splitlines()]

    def assert_stopped_timeline(self):
        self.assertTrue(self.session.capture_uncertain)
        self.assertFalse(self.session.automatic)
        before = list(self.machine.commands)
        for request in ({'action': 'run', 'cycles': 1}, {'action': 'resume'},
                        self.input, {'action': 'warm-reset'}, {'action': 'cold-cycle'},
                        {'action': 'snapshot', 'path': str(self.root / 'new')},
                        {'action': 'restore', 'path': str(self.root / 'absent')},
                        {'action': 'replay', 'snapshot': str(self.root / 'absent'),
                         'capture': str(self.root / 'absent')}):
            with self.subTest(request=request), self.assertRaisesRegex(RuntimeError, 'uncertain'):
                self.session.dispatch(request)
        for operation in (lambda: self.session.run(1),
                          lambda: self.session.snapshot(self.root / 'new'),
                          lambda: self.session.restore(self.root / 'absent'),
                          lambda: self.session.replay(self.root / 'absent', self.root / 'absent', 20)):
            with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                operation()
        self.assertEqual(self.machine.commands, before)
        self.assertTrue(self.session.dispatch({'action': 'inspect'})['capture_uncertain'])
        self.session.dispatch({'action': 'export-medium', 'path': str(self.root / 'export.raw')})
        self.session.dispatch({'action': 'destroy'})
        self.assertTrue(self.session.closed)

    def test_success_marks_same_row_applied_preserving_raw_fields_and_ordinals(self):
        for _ in range(2):
            self.session.dispatch(self.input)
        rows = self.rows()
        self.assertEqual([row['admission'] for row in rows], ['applied', 'applied'])
        self.assertEqual([(row['ordinal'], row['cursor']) for row in rows], [(0, 0), (1, 1)])
        self.assertEqual([row['request'] for row in rows], [self.input, self.input])
        self.assertEqual([row['cycle'] for row in rows], [10, 10])
        self.assertEqual((self.session.event_count, self.session.event_cursor), (2, 2))

    def test_admission_followed_by_inspection_failure_retains_pending_and_freezes(self):
        self.machine.fail_after_admission = True
        self.session.automatic = True
        with self.assertRaisesRegex(RuntimeError, 'subsequent inspection failed'):
            self.session.dispatch(self.input)
        self.assertEqual(len(self.machine.admitted), 1)
        self.assertEqual(self.rows()[0]['admission'], 'pending')
        self.assertEqual(self.rows()[0]['request'], self.input)
        self.assertEqual((self.session.event_count, self.session.event_cursor), (0, 0))
        self.assert_stopped_timeline()

    def test_partial_pending_write_failure_prevents_admission_and_freezes(self):
        actual = self.session.capture
        def partial_write(wire):
            actual.write(wire[:19])
            actual.flush()
            raise OSError('partial capture write')
        with mock.patch.object(self.session, 'capture', wraps=actual) as capture:
            capture.write.side_effect = partial_write
            with self.assertRaisesRegex(OSError, 'partial capture write'):
                self.session.dispatch(self.input)
            capture.truncate.assert_not_called()
        self.assertEqual(self.machine.admitted, [])
        self.assertGreater((self.directory / 'external.jsonl').stat().st_size, 0)
        self.assert_stopped_timeline()

    def test_pending_flush_failure_prevents_admission_even_with_complete_record(self):
        actual = self.session.capture
        def flush_failure():
            actual.flush()
            raise OSError('capture flush failed')
        with mock.patch.object(self.session, 'capture', wraps=actual) as capture:
            capture.flush.side_effect = flush_failure
            with self.assertRaisesRegex(OSError, 'capture flush failed'):
                self.session.dispatch(self.input)
        self.assertEqual(self.machine.admitted, [])
        self.assertEqual(self.rows()[0]['admission'], 'pending')
        self.assert_stopped_timeline()

    def test_acknowledgement_write_failure_retains_admitted_pending_record(self):
        actual = self.session.capture
        def mark_failure(wire):
            if wire == 'applied':
                raise OSError('admission marker write failed')
            return actual.write(wire)
        with mock.patch.object(self.session, 'capture', wraps=actual) as capture:
            capture.write.side_effect = mark_failure
            with self.assertRaisesRegex(OSError, 'marker write failed'):
                self.session.dispatch(self.input)
            capture.truncate.assert_not_called()
        self.assertEqual(len(self.machine.admitted), 1)
        self.assertEqual(self.rows()[0]['admission'], 'pending')
        self.assert_stopped_timeline()

    def test_partial_marker_and_ack_flush_failures_freeze_without_truncating(self):
        for partial in (True, False):
            with self.subTest(partial=partial):
                directory = self.root / ('partial' if partial else 'ack-flush')
                directory.mkdir()
                machine = AdmittingMachine()
                session = runtime.Session(machine, directory,
                    SimpleNamespace(mode='developer', paused=True, quantum=1000))
                try:
                    actual = session.capture
                    flushed = 0
                    def write(wire):
                        if partial and wire == 'applied':
                            actual.write(wire[:3]); actual.flush()
                            raise OSError('partial marker write')
                        return actual.write(wire)
                    def flush():
                        nonlocal flushed
                        actual.flush(); flushed += 1
                        if not partial and flushed == 2:
                            raise OSError('acknowledgement flush failed')
                    with mock.patch.object(session, 'capture', wraps=actual) as capture:
                        capture.write.side_effect = write
                        capture.flush.side_effect = flush
                        with self.assertRaises(OSError):
                            session.dispatch(self.input)
                        capture.truncate.assert_not_called()
                    self.assertTrue(session.capture_uncertain)
                    self.assertEqual(len(machine.admitted), 1)
                    self.assertEqual((session.event_count, session.event_cursor), (0, 0))
                    with self.assertRaisesRegex(RuntimeError, 'uncertain'):
                        session.run(1)
                    if partial:
                        row = json.loads((directory / 'external.jsonl').read_text())
                        self.assertNotEqual(row['admission'], 'applied')
                finally:
                    session.close()

    def test_replay_rejects_pending_or_partial_marker_before_any_restore(self):
        checkpoint = self.root / 'snapshot'
        self.session.snapshot(checkpoint)
        capture = self.root / 'closed.jsonl'
        row = {'ordinal': 0, 'cursor': 0, 'cycle': 20, 'request': self.input}
        for marker in ('pending', 'appding', None, True):
            with self.subTest(marker=marker):
                capture.write_text(json.dumps(dict(row, admission=marker)) + '\n')
                before = list(self.machine.commands)
                with self.assertRaisesRegex(ValueError, 'uncertain external admission'):
                    self.session.replay(checkpoint, capture, 30)
                self.assertEqual(self.machine.commands, before)
        # A rejected pending row outside the requested suffix is still an
        # uncertain timeline; it must not be silently skipped.
        capture.write_text(json.dumps(dict(row, admission='applied')) + '\n' +
                           json.dumps(dict(row, ordinal=1, cursor=1, cycle=40,
                                           admission='pending')) + '\n')
        before = list(self.machine.commands)
        with self.assertRaisesRegex(ValueError, 'uncertain external admission'):
            self.session.replay(checkpoint, capture, 30)
        self.assertEqual(self.machine.commands, before)


if __name__ == '__main__':
    unittest.main()
