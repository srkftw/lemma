"""Host-only gates from actual clean78 H pre-IR; no target compilation/guest claim."""
from pathlib import Path
import json,re,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from audit_kernel import validate_h_console_router
from core0_common import Core0Error
class CapabilityConsoleRouterFailures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=json.loads((Path(__file__).parent/'fixtures/capability-console-router.json').read_text())
        cls.ir=value['pre_ir'];cls.names=value['by_source']
    def test_actual_checked_intermediary_retains_capability_and_both_mode_gates(self):
        result=validate_h_console_router(self.ir,self.names)
        self.assertEqual(result['raw_mode'],0);self.assertEqual(result['buffered_modes'],[1,2])
        self.assertEqual(len(result['successful_mode_gates']),2)
        self.assertEqual(result['capability_status_gate']['equals'],0)
    def test_genuine_router_mutations_reject_failure_fallback_or_changed_range(self):
        source='Lemma.Kernel.Syscall.';input_source='Lemma.Kernel.KernelInput.'
        mode=self.names[input_source+'mode'];selected=self.names[source+'selectedConsoleRead']
        raw=self.names[source+'consoleRead'];buffered=self.names[input_source+'read']
        start=self.ir.index('@'+selected+'(');end=self.ir.index('\n}',start)
        original=self.ir[start:end]
        mutants=[original.replace('%action.call.value3, 0','%action.call.value3, 3'),
                 original.replace('%action.call.value3, 1','%action.call.value3, 3'),
                 original.replace('%action.call.value3, 2','%action.call.value3, 3'),
                 original.replace('[ 0, %if.else.10 ]','[ 1, %if.else.10 ]'),
                 original.replace('label %action.if.then.0, label %action.if.else.1','label %action.if.else.1, label %action.if.then.0'),
                 original.replace('label %action.if.then.12, label %action.if.else.13','label %action.if.else.13, label %action.if.then.12'),
                 original.replace('@'+raw+'(i64 %arg0, i64 %arg1, i64 %arg2)','@'+raw+'(i64 %arg0, i64 %arg1, i64 1)'),
                 original.replace('@'+buffered+'(i64 %arg0, i64 %arg1, i64 %arg2)','@'+buffered+'(i64 %arg1, i64 %arg1, i64 %arg2)')]
        for mutant in mutants:
            with self.subTest(mutant=mutant):
                self.assertNotEqual(mutant,original)
                with self.assertRaises(Core0Error):validate_h_console_router(self.ir[:start]+mutant+self.ir[end:],self.names)
    def test_capability_failure_and_direct_dispatcher_bypasses_reject(self):
        y='Lemma.Kernel.Syscall.';selected=self.names[y+'selectedConsoleRead']
        start=self.ir.index('@'+self.names[y+'capConsole']+'(');end=self.ir.index('\n}',start)
        body=self.ir[start:end]
        bad=body.replace('%action.call.status19, 0','%action.call.status19, 1')
        self.assertNotEqual(bad,body)
        with self.assertRaises(Core0Error):validate_h_console_router(self.ir[:start]+bad+self.ir[end:],self.names)
        for arguments in ['i64 %arg1, i64 %arg3, i64 %arg4', 'i64 %arg0, i64 %arg4, i64 %arg4', 'i64 %arg0, i64 %arg3, i64 1']:
            bad=body.replace('@'+selected+'(i64 %arg0, i64 %arg3, i64 %arg4)','@'+selected+'('+arguments+')')
            self.assertNotEqual(bad,body)
            with self.assertRaisesRegex(Core0Error,'changed actual caller/pointer/length'):
                validate_h_console_router(self.ir[:start]+bad+self.ir[end:],self.names)
        for callee in [selected,self.names[y+'consoleRead'],self.names[y+'consoleWrite'],self.names['Lemma.Kernel.KernelInput.read']]:
            start=self.ir.index('@'+self.names[y+'dispatchManaged']+'(');entry=self.ir.index('entry:\n',start)+len('entry:\n')
            bad=self.ir[:entry]+'  %unchecked_console = call { i64, i64 } @'+callee+'(i64 %arg0, i64 0, i64 0)\n'+self.ir[entry:]
            with self.assertRaisesRegex(Core0Error,'bypasses capability-checked'):validate_h_console_router(bad,self.names)
if __name__=='__main__':unittest.main()
