"""Small independent failures for the narrow local-borrow audit machinery.

The genuine emitted corpus is separately required by check_kernel_local_borrow;
these host tests never claim to elaborate or execute a guest.
"""
import ast
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import audit_kernel
from audit_kernel import (_local_checked_result, _local_closed_calls,
                          _local_arithmetic)
from core0_common import Core0Error


class LocalBorrowHostFailures(unittest.TestCase):
    def test_exact_fresh_argument_and_value_component(self):
        body='''entry:
  %r = call { i64, i64 } @checked(i64 %arg0, i64 32)
  %s = extractvalue { i64, i64 } %r, 0
  %value = extractvalue { i64, i64 } %r, 1
'''
        self.assertEqual(_local_checked_result(body,'checked','i64 %arg0, i64 32'),('%r','%value'))
        for bad in [body.replace('i64 %arg0','i64 %arg1'),body.replace('%r, 1','%r, 0'),body+body]:
            with self.assertRaises(Core0Error):_local_checked_result(bad,'checked','i64 %arg0, i64 32')

    def test_new_effect_or_opaque_call_is_rejected(self):
        _local_closed_calls('%r = call { i64, i64 } @read(i64 %arg0)',{'read'})
        for body in ['%r = call { i64, i64 } @write(i64 %arg0)',
                     '%r = call { i64, i64 } @schedule()', 'store i64 0, ptr %arg0',
                     'fence seq_cst', '%r = atomicrmw add ptr %arg0, i64 1 monotonic']:
            with self.assertRaises(Core0Error):_local_closed_calls(body,{'read'})

    def test_original_word_index_and_checked_page_arithmetic(self):
        body='''entry:
  %i = zext i32 %arg0 to i64
  %off = mul i64 %i, 8
  %address = add i64 %arg3, %off
'''
        self.assertEqual(_local_arithmetic(body,{})['%address'],('add','%arg3',('mul',('zext32','%arg0'),8)))

    def test_canonical_audit_invokes_both_guards_from_public_reachability(self):
        tree=ast.parse(Path(audit_kernel.__file__).read_text())
        main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='audit')
        assignments={node.targets[0].id:ast.unparse(node.value) for node in ast.walk(main)
                     if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)}
        self.assertIn('validate_task_capture_borrow',assignments['task_capture_borrow'])
        self.assertIn('Lemma.Kernel.Task.capture',assignments['task_capture_borrow'])
        self.assertIn('validate_surface_read_page_borrow',assignments['surface_read_page_borrow'])
        self.assertIn('Lemma.Platform.LemmaSim.DeviceService.surface',assignments['surface_read_page_borrow'])
        self.assertNotIn('Task.contextAt',assignments['task_capture_borrow'])
        self.assertNotIn('DeviceService.uploadBorrowed',assignments['surface_read_page_borrow'])


if __name__=='__main__':unittest.main()
