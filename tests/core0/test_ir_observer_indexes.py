"""Exact old extraction relations, including malformed LLVM boundaries."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import audit_core0 as audit
import course_await_deployment as course
from core0_common import Core0Error

PLAIN = 'define i64 @x(i64 %arg) {\n ret i64 %arg\n}\n'
FIXTURES = [PLAIN, PLAIN.replace('define ', 'define\t'),
            PLAIN.replace('}\n', '} trailing\n'),
            PLAIN.replace('define ', 'define\n'),
            PLAIN.replace('define ', 'define \n '),
            PLAIN.replace('define ', 'define \t\n\t'),
            PLAIN.replace('define ', 'define\r\n'),
            PLAIN.replace('define ', 'define\v'),
            PLAIN.replace('}\n', '}\t\n'),
            PLAIN.replace('}\n', ' }\n'),
            PLAIN.replace('@x', '@1odd'), PLAIN + PLAIN,
            'define i64 @x() {\n define i64 @y() {\n ret i64 0\n}\n}\n',
            'definebad\n' + PLAIN,
            'define \n' + PLAIN,
            PLAIN.replace('define ', 'declare '),
            PLAIN.replace('(i64 %arg)', '(ptr @y())'),
            PLAIN.replace('}\n', '} ; unparsed\n'),
            '; comment @x()\n' + PLAIN,
            PLAIN.replace('i64 @x', '{ i64, i8 } @x')]
SYMBOLS = ('x', 'y', '1odd', 'absent', 'x\ny')


def original_arguments(ir, symbol):
    return re.findall(r'(?m)^define\s+[^\n]*@' + re.escape(symbol) + r'\(([^\n]*)\)', ir)


def original_body(ir, symbol):
    rows = re.findall(r'(?ms)^define [^\n]*@' + re.escape(symbol) + r'\([^\n]*\)[^\n]*\{\n(.*?)^\}', ir)
    if len(rows) != 1:
        raise Core0Error('mount-result LLVM owner missing/duplicated: ' + symbol)
    return rows[0]


def outcome(function, ir, symbol):
    try:
        return ('value', function(ir, symbol))
    except Core0Error as error:
        return ('error', str(error))


class ExactObserverIndexes(unittest.TestCase):
    def setUp(self):
        audit._ir_header_projection.cache_clear()
        course._compatible_body_index.cache_clear()

    def test_original_outcomes_for_one_hundred_symbol_boundaries(self):
        for ir in FIXTURES:
            for symbol in SYMBOLS:
                with self.subTest(ir=ir, symbol=symbol):
                    self.assertEqual(audit._ir_signature_arguments(ir, symbol), original_arguments(ir, symbol))
                    self.assertEqual(outcome(course._body, ir, symbol), outcome(original_body, ir, symbol))

    def test_mutation_never_reuses_prior_complete_text(self):
        self.assertEqual(audit._ir_signature_arguments(PLAIN, 'x'), ['i64 %arg'])
        changed = PLAIN.replace('%arg)', '%other)')
        self.assertEqual(audit._ir_signature_arguments(changed, 'x'), ['i64 %other'])
        self.assertNotEqual(course._body(PLAIN, 'x'), course._body(PLAIN.replace('ret i64 %arg', 'ret i64 9'), 'x'))
        self.assertEqual(audit._ir_signature_arguments(PLAIN, 'x'), ['i64 %arg'])

    def test_signature_results_are_fresh_and_internal_projections_immutable(self):
        arguments = audit._ir_signature_arguments(PLAIN, 'x')
        arguments.append('fabricated')
        self.assertEqual(audit._ir_signature_arguments(PLAIN, 'x'), ['i64 %arg'])
        self.assertIsInstance(audit._ir_header_projection(PLAIN), str)

    def test_both_new_indexes_retain_at_most_two_complete_texts(self):
        for index in range(6):
            text = '; identity ' + str(index) + '\n' + PLAIN
            audit._ir_signature_arguments(text, 'x')
            course._body(text, 'x')
        self.assertEqual(audit._ir_header_projection.cache_info().currsize, 2)
        self.assertEqual(course._compatible_body_index.cache_info().currsize, 2)
        misses = audit._ir_header_projection.cache_info().misses
        audit._ir_signature_arguments('; identity 0\n' + PLAIN, 'x')
        self.assertEqual(audit._ir_header_projection.cache_info().misses, misses + 1)

    def test_bare_definition_with_space_before_newline_keeps_original_rejection(self):
        text = PLAIN.replace('define ', 'define \n ')
        self.assertIsNone(audit._ir_header_projection(text))
        self.assertIsNone(course._compatible_body_index(text))
        with self.assertRaisesRegex(Core0Error, 'missing/duplicated'):
            course._body(text, 'x')


if __name__ == '__main__':
    unittest.main(verbosity=2)
