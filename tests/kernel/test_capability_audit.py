"""Host-only fail-closed compiled lifecycle/checked capability-gate fixtures."""
from pathlib import Path
import sys
import unittest
import json
import tempfile
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import audit, validate_call_precedes, validate_checked_call_gate, validate_boolean_gate, validate_h_legacy_console_denial, validate_h_endpoint_budget
from core0_common import Core0Error

GATE='''entry:
  %r = call { i64, i64 } @checked(i64 %arg0)
  %sw = extractvalue { i64, i64 } %r, 0
  %s = trunc i64 %sw to i8
  %v = extractvalue { i64, i64 } %r, 1
  %ok = icmp eq i8 %s, 0
  br i1 %ok, label %success, label %failure
success:
  %p = call { i64, i64 } @protected(i64 %arg0)
  ret { i64, i64 } %p
failure:
  ret { i64, i64 } %r
'''

class CapabilityCompiledGateFailures(unittest.TestCase):
    def test_missing_inspection_tool_removes_stale_pass_and_retains_failure(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(dir=root/'build/kernel') as directory:
            out=Path(directory);(out/'audit.json').write_text('{"status":"PASS"}')
            with patch('audit_kernel.require_tools',side_effect=Core0Error('missing pinned tool')):
                with self.assertRaisesRegex(Core0Error,'missing pinned tool'):audit(root=root,output_dir=out)
            self.assertFalse((out/'audit.json').exists())
            self.assertEqual(json.loads((out/'audit-failure.json').read_text())['status'],'FAIL')

    def test_exact_checked_status_gate_accepts_only_success_path(self):
        value=validate_checked_call_gate(GATE,'checked','protected')
        self.assertEqual(value['gates'][0]['protected_blocks'],['success'])
        for bad in [GATE.replace('%s, 0','%s, 1'), GATE.replace('label %success, label %failure','label %failure, label %success'),
                    GATE.replace('failure:\n  ret','failure:\n  %bypass = call { i64, i64 } @protected(i64 %arg0)\n  ret'),
                    GATE.replace('%s = trunc i64 %sw to i8','%s = trunc i64 %v to i8')]:
            with self.assertRaises(Core0Error):validate_checked_call_gate(bad,'checked','protected')

    def test_checked_managed_value_gate_is_explicit_and_not_status_substitution(self):
        good=GATE.replace('icmp eq i8 %s, 0','icmp eq i64 %v, 1')
        validate_checked_call_gate(good,'checked','protected',component='value',value=1)
        with self.assertRaises(Core0Error):validate_checked_call_gate(good,'checked','protected')
        with self.assertRaises(Core0Error):validate_checked_call_gate(good,'checked','protected',component='value',value=0)

    def test_boolean_readback_gate_rejects_failure_and_entry_bypass(self):
        body=GATE.replace("icmp eq i8 %s, 0","icmp eq i64 %v, 199")
        validate_boolean_gate(body,"%ok","protected")
        for bad in [body.replace("label %success, label %failure","label %failure, label %success"),
                    body.replace("failure:\n  ret","failure:\n  %b = call { i64, i64 } @protected(i64 %arg0)\n  ret"),
                    body.replace("entry:\n","entry:\n  %b = call { i64, i64 } @protected(i64 %arg0)\n")]:
            with self.assertRaises(Core0Error):validate_boolean_gate(bad,"%ok","protected")

    def test_managed_legacy_console_denial_cannot_fall_through(self):
        body="""entry:
  %console = call i64 @console()
  %match = icmp eq i64 %arg1, %console
  br i1 %match, label %denied, label %ordinary
denied:
  br label %merge
ordinary:
  %r = call { i64, i64 } @legacy(i64 %arg0, i64 %arg1)
  %sw = extractvalue { i64, i64 } %r, 0
  %s = trunc i64 %sw to i8
  br label %merge
merge:
  %status = phi i8 [ 72, %denied ], [ %s, %ordinary ]
  ret i8 %status
"""
        names={"Lemma.User.ABI.console":"console","Lemma.Kernel.Syscall.dispatchLegacy":"legacy"}
        validate_h_legacy_console_denial(body,names)
        for bad in [body.replace("[ 72, %denied ]","[ 0, %denied ]"),
                    body.replace("denied:\n  br label %merge","denied:\n  br label %ordinary"),
                    body.replace("i64 %arg1, %console","i64 %arg2, %console")]:
            with self.assertRaises(Core0Error):validate_h_legacy_console_denial(bad,names)

    def test_endpoint_budget_guards_slot_scan_and_allocation(self):
        body="""entry:
  %budget = icmp ule i32 16, 16
  br i1 %budget, label %preheader, label %exhausted
preheader:
  br label %header
header:
  %index = phi i32 [ 0, %preheader ], [ %next, %latch ]
  %acc = phi i64 [ 0, %preheader ], [ %cbv, %latch ]
  %continue = icmp ult i32 %index, 16
  br i1 %continue, label %count, label %done
count:
  %cb = call { i64, i64 } @count(i32 signext %index, i32 signext 16, i64 %acc, i64 %base, i64 0, i64 0, i64 0)
  %cbw = extractvalue { i64, i64 } %cb, 0
  %cbs = trunc i64 %cbw to i8
  %cbv = extractvalue { i64, i64 } %cb, 1
  %ok = icmp eq i8 %cbs, 0
  br i1 %ok, label %latch, label %stopped
latch:
  %next = add i32 %index, 1
  br label %header
exhausted:
  br label %outcome
stopped:
  br label %outcome
done:
  br label %outcome
outcome:
  %s = phi i8 [ 9, %exhausted ], [ %cbs, %stopped ], [ 0, %done ]
  %v = phi i64 [ 0, %exhausted ], [ %cbv, %stopped ], [ %acc, %done ]
  %failed = call zeroext i1 @failed(i8 zeroext %s)
  %bad = icmp eq i1 %failed, 1
  br i1 %bad, label %error, label %limit
limit:
  %cap = call i64 @capacity()
  %room = icmp ult i64 %v, %cap
  br i1 %room, label %allocate, label %full
allocate:
  %slot = call { i64, i64 } @free(i32 signext 0, i32 signext 16, i64 16, i64 %base, i64 0, i64 0, i64 0)
  %r = call { i64, i64 } @allocate(i64 1, i64 1)
  ret { i64, i64 } %r
error:
  ret { i64, i64 } zeroinitializer
full:
  ret { i64, i64 } zeroinitializer
"""
        names={"Lemma.Kernel.Objects."+key:value for key,value in
               [("endpointCountStep","count"),("endpointCapacity","capacity"),("failed","failed"),("freeObjectStep","free")]}
        names["Lemma.Kernel.Memory.Frames.allocate"]="allocate"
        result=validate_h_endpoint_budget(body,names)
        self.assertEqual(result["capacity"],4)
        for bad in [body.replace("i32 signext 16, i64 %acc","i32 signext 17, i64 %acc"),
                    body.replace("phi i64 [ 0, %preheader ]","phi i64 [ 1, %preheader ]"),
                    body.replace("icmp ult i64 %v, %cap","icmp ule i64 %v, %cap"),
                    body.replace("label %allocate, label %full","label %full, label %allocate"),
                    body.replace("label %error, label %limit","label %limit, label %error"),
                    body.replace("error:\n  ret","error:\n  %bypass = call { i64, i64 } @allocate(i64 1, i64 1)\n  ret")]:
            with self.assertRaises(Core0Error):validate_h_endpoint_budget(bad,names)

    def test_lifecycle_order_rejects_direct_bypass_same_block_and_cycle(self):
        good='''entry:
  %r = call { i64, i64 } @detach(i64 %arg0)
  %p = call { i64, i64 } @teardown(i64 %arg0)
  ret { i64, i64 } %p
'''
        validate_call_precedes(good,'detach','teardown')
        bad=good.replace('  %r = call { i64, i64 } @detach(i64 %arg0)\n','')
        with self.assertRaises(Core0Error):validate_call_precedes(bad,'detach','teardown')
        reversed_body=good.replace('  %r = call { i64, i64 } @detach(i64 %arg0)\n  %p = call { i64, i64 } @teardown(i64 %arg0)',
                                   '  %p = call { i64, i64 } @teardown(i64 %arg0)\n  %r = call { i64, i64 } @detach(i64 %arg0)')
        with self.assertRaises(Core0Error):validate_call_precedes(reversed_body,'detach','teardown')
        bypass='''entry:
  br i1 %condition, label %checked, label %bypass
checked:
  %r = call { i64, i64 } @detach(i64 %arg0)
  br label %bypass
bypass:
  %p = call { i64, i64 } @teardown(i64 %arg0)
  br label %checked
'''
        with self.assertRaises(Core0Error):validate_call_precedes(bypass,'detach','teardown')

if __name__=='__main__':unittest.main()
