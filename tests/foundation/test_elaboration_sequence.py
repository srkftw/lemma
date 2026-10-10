"""Exact host provenance guard regressions; fake oleans do not certify target builds."""
from __future__ import annotations
import ast,copy,inspect,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import audit_core0,build_trap_suite,build_timer_suite,build_monitor
from core0_common import Core0Error,sha256
DEPENDENCY="Lemma/Platform/LemmaVM/ConsoleDevice.lean"
CASES=((audit_core0.TEST_TRAP_SUITE_POLICY,build_trap_suite),
       (audit_core0.TEST_TIMER_SUITE_POLICY,build_timer_suite),
       (audit_core0.TEST_MONITOR_IMAGE_POLICY,build_monitor))

def production_guards():
    # Execute the real provenance guards without invoking ELF tools or claiming
    # the host-only fixture bytes were compiled. This also retains the existing
    # per-row source/olean/command checks around the three exact tuple assertions.
    function=ast.parse(inspect.getsource(audit_core0.audit)).body[0]
    def assigned(node,name):
        return isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)
    first=next(i for i,n in enumerate(function.body) if isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name) and n.target.id=='expected_elaboration_commands')
    last=next(i for i,n in enumerate(function.body[first+1:],first+1) if assigned(n,'linked'))
    command_loop=[n for n in function.body if isinstance(n,ast.For) and isinstance(n.iter,ast.Name) and n.iter.id=='expected_elaboration_commands']
    if len(command_loop)!=1:raise AssertionError('real elaboration command guard shape changed')
    return (compile(ast.Module(function.body[first:last],type_ignores=[]),'<real provenance guard>','exec'),
            compile(ast.Module(command_loop,type_ignores=[]),'<real provenance command guard>','exec'))

class ElaborationSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows_guard,cls.command_guard=production_guards()
    def fixture(self,driver):
        temporary=tempfile.TemporaryDirectory();root=Path(temporary.name)
        sources=['examples/core0/Positive.lean',*(str(p) for p in driver.ELABORATION_SOURCES)]
        rows=[]
        for source in sources:
            src=root/source;src.parent.mkdir(parents=True,exist_ok=True);src.write_text('-- host source fixture '+source+'\n')
            olean=Path('.lake/build/lib/lean')/Path(source).with_suffix('.olean');obj=root/olean;obj.parent.mkdir(parents=True,exist_ok=True);obj.write_bytes(b'host olean fixture '+source.encode())
            rows.append({'source':source,'source_sha256':sha256(src),'olean':str(olean),'olean_sha256':sha256(obj),'generation_command':['lake','env','lean','-o',str(olean),source]})
        return temporary,root,rows
    def checked(self,policy,root,rows,*,observed=None,commands=None):
        observed=set(n for r in rows for n in (r['source'],r['olean'])) if observed is None else observed
        scope=dict(vars(audit_core0));scope.update(provenance_schema=2,provenance_obj={'elaborated_inputs':rows},root=root,observed_sources=observed,policy=policy)
        exec(self.rows_guard,scope)
        scope['command_argv']=[r['generation_command'] for r in rows] if commands is None else commands
        exec(self.command_guard,scope)
        return scope['expected_elaboration_commands']
    def test_exact_dependency_sequence_matches_all_three_builders(self):
        for policy,driver in CASES:
            with self.subTest(policy=policy):
                temporary,root,rows=self.fixture(driver)
                with temporary:
                    self.assertEqual([r['source'] for r in rows][:3],['examples/core0/Positive.lean',DEPENDENCY,'examples/foundation/DeviceConformanceSupport.lean'])
                    self.assertEqual(self.checked(policy,root,rows),[r['generation_command'] for r in rows])
    def test_dependency_is_mandatory_ordered_and_hash_bound(self):
        for policy,driver in CASES:
            temporary,root,rows=self.fixture(driver)
            with temporary:
                for mutant,fragment in [('missing','sequence'),('reordered','sequence'),('duplicate','duplicate'),('source-hash','hash mismatch'),('olean-hash','hash mismatch'),('missing-source-binding','absent from source-input hashes'),('missing-olean-binding','absent from source-input hashes'),('generation-command','generation command')]:
                    with self.subTest(policy=policy,mutant=mutant):
                        changed=copy.deepcopy(rows);observed=set(n for r in rows for n in (r['source'],r['olean']))
                        if mutant=='missing':changed.pop(1)
                        elif mutant=='reordered':changed[1],changed[2]=changed[2],changed[1]
                        elif mutant=='duplicate':changed.insert(2,copy.deepcopy(changed[1]))
                        elif mutant=='source-hash':changed[1]['source_sha256']='0'*64
                        elif mutant=='olean-hash':changed[1]['olean_sha256']='0'*64
                        elif mutant=='missing-source-binding':observed.remove(changed[1]['source'])
                        elif mutant=='missing-olean-binding':observed.remove(changed[1]['olean'])
                        else:changed[1]['generation_command'][-1]='examples/foundation/DeviceConformanceSupport.lean'
                        with self.assertRaisesRegex(Core0Error,fragment):self.checked(policy,root,changed,observed=observed)
    def test_missing_real_dependency_command_rejects(self):
        for policy,driver in CASES:
            with self.subTest(policy=policy):
                temporary,root,rows=self.fixture(driver)
                with temporary:
                    commands=[r['generation_command'] for r in rows if r['source']!=DEPENDENCY]
                    with self.assertRaisesRegex(Core0Error,'omits Lean elaboration command'):self.checked(policy,root,rows,commands=commands)
if __name__=='__main__':unittest.main()
