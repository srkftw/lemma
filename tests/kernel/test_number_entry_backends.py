"""Host observation/bound tests; real RTL execution has separate evidence."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_course_math_workflow import CourseMathWorkflow, Session
from check_live_notebook import PublicSession
from check_rtl_number_entry import RTLNumberEntry, AGGREGATE_CLOCKS


class NumberEntryBackends(unittest.TestCase):
    def test_fast_session_and_idle_shape_remain_unchanged(self):
        actor = object.__new__(CourseMathWorkflow)
        self.assertIs(actor.session_type, Session)
        state = {'devices': {'pen': {'count': 0}, 'paper': {'status': 0}},
                 'storage': {'phase': 0}}
        self.assertTrue(actor.idle(state))
        for path in ('pen', 'paper', 'storage'):
            other = copy.deepcopy(state)
            if path == 'pen': other['devices']['pen']['count'] = 1
            elif path == 'paper': other['devices']['paper']['status'] = 1
            else: other['storage']['phase'] = 1
            self.assertFalse(actor.idle(other))

    def rtl_state(self):
        return dict(event_queue=0, pen_queue=0, uart_queue=0, paper_busy=0,
                    panel_pending_pixels=0, block_state=0, dma_outstanding=0,
                    backing_io=dict(phase=2, next_id=8, completed=7,
                        durable_barrier=7, observed_write=6, retry_ready=False,
                        fork_suspended=False, orphan=False, poisoned=False))

    def test_rtl_predicate_uses_actual_pending_and_fork_state(self):
        actor = object.__new__(RTLNumberEntry)
        self.assertIs(actor.session_type, PublicSession)
        self.assertTrue(actor.idle(self.rtl_state()))
        for key, value in [('event_queue', 1), ('dma_outstanding', 1),
                           ('paper_busy', 1), ('pen_queue', 1)]:
            state = self.rtl_state(); state[key] = value
            self.assertFalse(actor.idle(state))
        for key, value in [('phase', 1), ('fork_suspended', True),
                           ('orphan', True), ('poisoned', True), ('next_id', 9)]:
            state = self.rtl_state(); state['backing_io'][key] = value
            self.assertFalse(actor.idle(state))

    def actor(self):
        actor = object.__new__(RTLNumberEntry)
        actor.cycles, actor.deadline = 0, 100_000
        actor.check_sources = lambda: None
        actor.rows = lambda session: []
        actor.progress = lambda: None
        actor.report = {'phases': []}
        return actor

    def test_completion_does_not_hide_exceeded_phase_clock_cap(self):
        actor = self.actor()
        class Native:
            def __init__(self): self.calls = 0
            def inspect(self):
                self.calls += 1
                return {'machine': {'cycle': 0 if self.calls == 1 else 11,
                                    'finished': False}}
        with patch('check_rtl_number_entry.time.monotonic', return_value=0):
            with self.assertRaisesRegex(ValueError, 'phase/aggregate bound'):
                actor.phase(Native(), 'bounded-control', 10, lambda state: True)
        self.assertEqual(actor.report['phases'], [])

    def test_completion_does_not_hide_host_or_aggregate_limit(self):
        class Native:
            def inspect(self): return {'machine': {'cycle': 0, 'finished': False}}
        for clock, times in [(0, [0, 1801]), (AGGREGATE_CLOCKS + 1, [0, 0])]:
            actor = self.actor(); actor.cycles = clock
            with patch('check_rtl_number_entry.time.monotonic', side_effect=times):
                with self.assertRaisesRegex(ValueError, 'phase/aggregate bound'):
                    actor.phase(Native(), 'bounded-control', 10, lambda state: True)
            self.assertEqual(actor.report['phases'], [])


if __name__ == '__main__': unittest.main()
