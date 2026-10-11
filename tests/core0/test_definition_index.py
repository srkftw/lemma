"""Literal body-extraction invariants for the bounded host-only index."""
import re
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_core0 import _ir_definition_body, _ir_definition_index, validate_loop_stack_call_graph
from core0_common import Core0Error


def reference(ir,symbol):
    expression=(rf'^define\s+[^\n]*@{re.escape(symbol)}\([^\n]*\)[^\n]*\{{\n'
                rf'(?P<body>.*?)^\}}\s*$')
    matches=list(re.finditer(expression,ir,re.MULTILINE|re.DOTALL))
    if len(matches)!=1:raise Core0Error('not exactly one literal definition')
    return matches[0].group('body')


def source(name,body=' ret i64 0\n',header='i64'):
    return f'define {header} @{name}() {{\n'+body+'}\n'


class DefinitionIndex(unittest.TestCase):
    def setUp(self):_ir_definition_index.cache_clear()

    def test_exact_bodies_headers_attributes_and_whitespace(self):
        fixtures=[source('alpha')+source('beta','entry:\n ret i64 9\n'),
                  source('alpha',header='{ i64, i64 }')+source('beta'),
                  'define\n i64 @alpha() local_unnamed_addr #0 {\n\tret i64 4\n}\n\n'+source('beta'),
                  source('alpha',header='i64')+'; define i64 @alpha() {\n'+source('beta'),
                  'define i64 @holder(ptr @alpha()) {\n ret i64 3\n}\n'+source('beta')]
        for ir in fixtures:
            for symbol in ['alpha','beta','missing']:
                try:expected=reference(ir,symbol)
                except Core0Error:
                    with self.assertRaises(Core0Error):_ir_definition_body(ir,symbol)
                else:self.assertEqual(_ir_definition_body(ir,symbol),expected)

    def test_duplicates_absent_and_malformed_nested_boundary(self):
        for ir in [source('alpha')*2,source('other'),'define i64 @alpha() {\n ret i64 0\n']:
            with self.assertRaises(Core0Error):_ir_definition_body(ir,'alpha')
        nested='define i64 @outer() {\n'+source('inner')+'}\n'
        self.assertIsNone(_ir_definition_index(nested))
        for symbol in ['outer','inner']:
            self.assertEqual(_ir_definition_body(nested,symbol),reference(nested,symbol))
        nonlexical=source('"space name"')
        self.assertEqual(_ir_definition_body(nonlexical,'"space name"'),reference(nonlexical,'"space name"'))

    def test_changed_body_cannot_reuse_original_call_graph(self):
        ir=source('leaf')+source('root',' %value = call i64 @leaf()\n ret i64 %value\n')
        frames={'leaf':16,'root':16}
        self.assertEqual(validate_loop_stack_call_graph(ir,frames)['maximum_frame_chain_bytes'],32)
        changed=ir.replace('define i64 @leaf() {\n ret i64 0',
                           'define i64 @leaf() {\n %cycle = call i64 @root()\n ret i64 %cycle')
        with self.assertRaisesRegex(Core0Error,'cycle'):validate_loop_stack_call_graph(changed,frames)
        allocated=ir.replace(' ret i64 0',' %storage = alloca i64\n ret i64 0')
        with self.assertRaisesRegex(Core0Error,'allocation'):validate_loop_stack_call_graph(allocated,frames)
        self.assertEqual(_ir_definition_body(ir,'leaf'),' ret i64 0\n')

    def test_two_actual_texts_bound_cache_and_source_mutation_is_distinct(self):
        for value in range(5):
            ir=source('alpha',f' ret i64 {value}\n')
            self.assertEqual(_ir_definition_body(ir,'alpha'),f' ret i64 {value}\n')
        self.assertEqual(_ir_definition_index.cache_info().maxsize,2)
        self.assertEqual(_ir_definition_index.cache_info().currsize,2)


if __name__=='__main__':unittest.main()
