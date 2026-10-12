"""Mutations must expose missing isolated processing or stale applicability."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from check_arithmetic_trace import validate, validate_isolation


class ArithmeticTrace(unittest.TestCase):
    def isolation(self):
        return json.loads((Path(__file__).parent / 'fixtures/arithmetic-isolation-trace-generated.json').read_text())

    def test_actual_cancelled_stale_revision_and_exact_raw_counts(self):
        fixture = self.isolation()
        observed = validate_isolation(fixture['rows'], 'stall', fixture['expected_raw'], fixture['stored_raw'])
        self.assertEqual(observed['actual_raw_samples'], 12)

    def test_missing_cancel_late_authority_and_duplicated_raw_rejected(self):
        fixture = self.isolation()
        rows, expected, stored = fixture['rows'], fixture['expected_raw'], fixture['stored_raw']
        for changed in ([row for row in rows if row[0] != 0x458],
                        [row for row in rows if row[0] != 0x45a],
                        rows + [[0x424, 99, 1, 1, 1]],
                        rows + [[0x450, 2, 1, 1, 2]]):
            with self.assertRaises(ValueError):
                validate_isolation(changed, 'stall', expected, stored)
        for changed in (stored[:-1], stored + [stored[0]], list(reversed(stored))):
            with self.assertRaises(ValueError):
                validate_isolation(rows, 'stall', expected, changed)
        changed = copy.deepcopy(stored)
        changed[0][4] += 1
        with self.assertRaises(ValueError):
            validate_isolation(rows, 'stall', expected, changed)
        changed = copy.deepcopy(rows)
        requests = [row for row in changed if row[0] == 0x459]
        late = next(row for row in changed if row[0] == 0x45a and row[1] == requests[1][1])
        changed.remove(late)
        changed.insert(0, late)
        with self.assertRaises(ValueError):
            validate_isolation(changed, 'stall', expected, stored)

    def test_actual_trace_fragment(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/arithmetic-ipc-trace-generated.json').read_text())
        self.assertEqual(len(validate(fixture['rows'], fixture['history'])), 5)

    def test_missing_reply_wrong_revision_and_fake_local_outcome_rejected(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/arithmetic-ipc-trace-generated.json').read_text())
        rows, history = fixture['rows'], fixture['history']
        bad = [[], [row for row in rows if row[0] != 0x455],
               [row for row in rows if row[0] != 0x459],
               [row for row in rows if row[0] != 0xf1],
               rows + [next(row for row in rows if row[0] == 0x455)]]
        for offset, value in ((1, 0), (2, 999), (3, 237), (4, 4)):
            changed = copy.deepcopy(rows)
            next(row for row in changed if row[0] == 0x455)[offset] = value
            bad.append(changed)
        changed = copy.deepcopy(rows)
        next(row for row in changed if row[0] == 0xf1 and row[2] == 2)[2] = 3
        bad.append(changed)
        for changed in bad:
            with self.assertRaises(ValueError):
                validate(changed, history)


if __name__ == '__main__':
    unittest.main()
