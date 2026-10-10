"""Host mutations of the explicit IPC checked-status CFG binding."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import validate_failed_call_gate
from core0_common import Core0Error

FAILED="""entry:
  %cmp0 = icmp eq i8 %arg0, 0
  br i1 %cmp0, label %if.then.0, label %if.else.1
if.then.0:
  br label %if.merge.2
if.else.1:
  br label %if.merge.2
if.merge.2:
  %if.result1 = phi i1 [ 0, %if.then.0 ], [ 1, %if.else.1 ]
  ret i1 %if.result1
"""
BODY="""entry:
  %result = call { i64, i64 } @authority(i64 %arg0)
  %status64 = extractvalue { i64, i64 } %result, 0
  %status8 = trunc i64 %status64 to i8
  %bad = call zeroext i1 @failed(i8 zeroext %status8)
  %condition = icmp eq i1 %bad, 1
  br i1 %condition, label %failure, label %success
failure:
  ret { i64, i64 } zeroinitializer
success:
  %published = call { i64, i64 } @publish(i64 %arg0)
  ret { i64, i64 } %published
"""

class IPCStatusGateFailures(unittest.TestCase):
    def test_genuine_aggregate_status_success_edge_required(self):
        value=validate_failed_call_gate(BODY,'authority','publish','failed',FAILED)
        self.assertEqual(value['gate']['success'],'success')
        for body in [BODY.replace('%result, 0','%result, 1'),
                     BODY.replace('@failed(i8 zeroext %status8)','@failed(i8 zeroext 0)'),
                     BODY.replace('to i8','to i32'),
                     BODY.replace('%bad, 1','%bad, 0'),
                     BODY.replace('label %failure, label %success','label %success, label %failure'),
                     BODY.replace('ret { i64, i64 } zeroinitializer','br label %success'),
                     BODY.replace('  %result =','  %extra = call { i64, i64 } @authority(i64 %arg0)\n  %result =')]:
            with self.assertRaises(Core0Error):validate_failed_call_gate(body,'authority','publish','failed',FAILED)

    def test_false_failure_helper_and_protected_call_bypass_rejected(self):
        for helper in [FAILED.replace('[ 1, %if.else.1 ]','[ 0, %if.else.1 ]'),
                       FAILED.replace('icmp eq i8 %arg0, 0','icmp eq i8 %arg0, 1'),
                       FAILED.replace('ret i1 %if.result1','ret i1 0')]:
            with self.assertRaises(Core0Error):validate_failed_call_gate(BODY,'authority','publish','failed',helper)
        bypass=BODY.replace('  %result =', '  %early = call { i64, i64 } @publish(i64 %arg0)\n  %result =')
        with self.assertRaises(Core0Error):validate_failed_call_gate(bypass,'authority','publish','failed',FAILED)


class IPCBranchScopeFailures(unittest.TestCase):
    def test_shared_completion_is_scoped_to_the_actual_copy_branch(self):
        branch=BODY.replace('entry:\n','entry:\n  br i1 %choice, label %copy, label %receive\nreceive:\n  %receiveResult = call { i64, i64 } @publish(i64 %arg0)\n  ret { i64, i64 } %receiveResult\ncopy:\n',1)
        value=validate_failed_call_gate(branch,'authority','publish','failed',FAILED,checked_branch_only=True)
        self.assertEqual(value['gate']['protected_blocks'],['success'])
        with self.assertRaises(Core0Error):validate_failed_call_gate(branch,'authority','publish','failed',FAILED)
        for bad in [branch.replace('ret { i64, i64 } zeroinitializer','br label %success'),
                    branch.replace('label %copy, label %receive','label %success, label %receive')]:
            with self.assertRaises(Core0Error):validate_failed_call_gate(bad,'authority','publish','failed',FAILED,checked_branch_only=True)

class IPCLoadedFieldFailures(unittest.TestCase):
    def test_wakeup_full_generation_binding_and_failure_edge_are_required(self):
        from audit_kernel import validate_ipc_read_guard
        body='''entry:
  %offset = call i64 @epochOffset()
  %address = add i64 %arg0, %offset
  %read = call { i64, i64 } @read64(i64 %address)
  %epoch = extractvalue { i64, i64 } %read, 1
  %matches = icmp eq i64 %epoch, %arg2
  br i1 %matches, label %success, label %failure
success:
  %write = call { i64, i64 } @write64(i64 %arg0, i64 2)
  ret { i64, i64 } %write
failure:
  ret { i64, i64 } zeroinitializer
'''
        constants={'epochOffset':128}
        validate_ipc_read_guard(body,'read64',constants,('add','%arg0',128),'%arg2','write64')
        for bad in [body.replace('%read, 1','%read, 0'),body.replace('%epoch, %arg2','%epoch, %arg3'),
                    body.replace('label %success, label %failure','label %failure, label %success'),
                    body.replace('ret { i64, i64 } zeroinitializer','br label %success'),
                    body.replace('%address = add i64 %arg0','%address = add i64 %arg1')]:
            with self.assertRaises(Core0Error):validate_ipc_read_guard(bad,'read64',constants,('add','%arg0',128),'%arg2','write64')

class IPCPublicationFailures(unittest.TestCase):
    def test_exact_state_write_inventory_and_prior_success_required(self):
        from audit_kernel import validate_ipc_write_inventory
        body='''entry:
  %offset = call i64 @stateOffset()
  %address = add i64 %arg0, %offset
  %first = call { i64, i64 } @write64(i64 %arg0, i64 %arg1)
  %status64 = extractvalue { i64, i64 } %first, 0
  %status8 = trunc i64 %status64 to i8
  %bad = call zeroext i1 @failed(i8 zeroext %status8)
  %condition = icmp eq i1 %bad, 1
  br i1 %condition, label %failure, label %publish
publish:
  %second = call { i64, i64 } @write64(i64 %address, i64 2)
  ret { i64, i64 } %second
failure:
  ret { i64, i64 } zeroinitializer
'''
        constants={'stateOffset':8};expected=[('%arg0','%arg1'),(('add','%arg0',8),2)]
        value=validate_ipc_write_inventory(body,'write64',constants,expected,'failed',FAILED)
        self.assertEqual(len(value['successful_write_gates']),1)
        for bad in [body.replace('i64 %address, i64 2','i64 %address, i64 1'),
                    body.replace('add i64 %arg0','add i64 %arg1'),body.replace('@failed(i8 zeroext %status8)','@failed(i8 zeroext 0)'),
                    body.replace('label %failure, label %publish','label %publish, label %failure'),
                    body.replace('ret { i64, i64 } zeroinitializer','br label %publish')]:
            with self.assertRaises(Core0Error):validate_ipc_write_inventory(bad,'write64',constants,expected,'failed',FAILED)

if __name__=='__main__':unittest.main()
