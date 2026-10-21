"""Host presentation only: exact review callbacks and readable activity logs."""
import copy
import json
from pathlib import Path
import queue
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from lemmasim_school_panel import Panel, activity_result_summary


class Text:
    def __init__(self):
        self.value = ''

    def insert(self, _where, value):
        self.value += value

    def see(self, _where):
        pass


class Status:
    def set(self, value):
        self.value = value


class Window:
    def after(self, delay, callback):
        self.next = delay, callback


class ActivitySummary(unittest.TestCase):
    def result(self):
        return {'attempt': {'key': 'immutable-attempt', 'data': {'checker': 'Verified'}},
                'rubric': {'criteria': ['domain', 'justification']},
                'inkPreview': {'digest': 'a' * 64, 'documentRevision': 8,
                               'width': 1650, 'height': 2200, 'stride': 825,
                               'scope': 'hosted Lean preview, not recognition or assessment',
                               'gray4Hex': 'ff' * (825 * 2200)}}

    def test_exact_named_payload_is_summarized_without_mutating_evidence(self):
        result = self.result()
        before = copy.deepcopy(result)
        summary = activity_result_summary(result)
        self.assertEqual(result, before)
        self.assertNotIn('gray4Hex', summary['inkPreview'])
        self.assertEqual(summary['inkPreview']['gray4HexSummary'],
                         {'omittedFromActivityLog': True, 'encodedCharacters': 3630000})
        for key in ('digest', 'documentRevision', 'width', 'height', 'stride', 'scope'):
            self.assertEqual(summary['inkPreview'][key], result['inkPreview'][key])
        self.assertIs(summary['attempt'], result['attempt'])
        self.assertIs(summary['rubric'], result['rubric'])
        self.assertLess(len(json.dumps(summary)), 1000)

    def test_actual_poll_delivers_full_result_before_only_log_projection(self):
        panel = Panel.__new__(Panel)
        panel.messages = queue.Queue()
        panel.output, panel.status, panel.window = Text(), Status(), Window()
        panel.busy = True
        result = self.result()
        received = []

        def render(value):
            self.assertEqual(panel.output.value, '')
            self.assertEqual(len(value['inkPreview']['gray4Hex']), 3630000)
            received.append(value)

        panel.messages.put(('Open original learner work', True, result, render))
        panel.poll()
        self.assertIs(received[0], result)
        self.assertIn('Open original learner work · completed', panel.output.value)
        self.assertIn('gray4HexSummary', panel.output.value)
        self.assertIn('immutable-attempt', panel.output.value)
        self.assertLess(len(panel.output.value), 1500)
        self.assertFalse(panel.busy)
        self.assertEqual(panel.status.value, 'Ready')
        self.assertEqual(panel.window.next[0], 100)

    def test_unrelated_legacy_and_malformed_results_keep_their_diagnostics(self):
        for result in (None, 'error', [1, 2], {'hex': 'abcd'},
                       {'inkPreview': None}, {'inkPreview': {'gray4Hex': 17}},
                       {'inkPreview': {'error': 'geometry differs'}}):
            self.assertIs(activity_result_summary(result), result)
        result = {'other': {'gray4Hex': 'keep this diagnostic'},
                  'inkPreview': {'gray4Hex': '', 'error': 'empty image'}}
        summary = activity_result_summary(result)
        self.assertEqual(summary['other']['gray4Hex'], 'keep this diagnostic')
        self.assertEqual(summary['inkPreview']['error'], 'empty image')
        self.assertEqual(summary['inkPreview']['gray4HexSummary']['encodedCharacters'], 0)


if __name__ == '__main__':
    unittest.main()
