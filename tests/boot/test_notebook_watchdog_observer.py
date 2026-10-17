"""The observed unclocked boundary must not admit a later reset."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_authenticated_notebook_update import require_original_power_origin


class WatchdogOriginObserverTests(unittest.TestCase):
    def state(self, cycle=0):
        return {'cycle': cycle, 'pc': 0, 'retired': 0,
                'power': {'reset_cause': 0 if cycle == 0 else 1, 'reset_epoch': 0,
                          'watchdog_armed': 0, 'watchdog_remaining': 0, 'reset_remaining': 0}}

    def test_actual_zero_then_first_reset_edge(self):
        for cycle in (0, 1, 8, 9, 1000000):
            require_original_power_origin(self.state(cycle))

    def test_unclocked_exception_requires_unexecuted_unarmed_state(self):
        original = self.state()
        for owner, name in ((None, 'pc'), (None, 'retired'),
                            ('power', 'watchdog_armed'), ('power', 'watchdog_remaining'),
                            ('power', 'reset_remaining'), ('power', 'reset_epoch')):
            state = copy.deepcopy(original)
            (state[owner] if owner else state)[name] = 1
            with self.subTest(owner=owner, name=name), self.assertRaises(RuntimeError):
                require_original_power_origin(state)

    def test_no_post_clock_zero_or_warm_watchdog_brownout_origin(self):
        for cause in (0, 2, 3, 4, 5):
            state = self.state(1000000)
            state['power']['reset_cause'] = cause
            with self.subTest(cause=cause), self.assertRaises(RuntimeError):
                require_original_power_origin(state)
        state = self.state(1000000)
        state['power']['reset_epoch'] = 1
        with self.assertRaises(RuntimeError):
            require_original_power_origin(state)


if __name__ == '__main__':
    unittest.main()
